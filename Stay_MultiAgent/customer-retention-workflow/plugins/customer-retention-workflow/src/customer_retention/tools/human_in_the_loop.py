"""Human-in-the-Loop (HITL) approval gateways.

The workflow must pause and request human authority when an offer exceeds the
policy cost threshold. Gateways are pluggable so the same workflow can run
non-interactively in CI (auto policy) and interactively in the CLI (console).
"""

from __future__ import annotations

import logging
from typing import Mapping, Protocol

from customer_retention.domain.contracts import OfferProposal, ValueReport
from customer_retention.domain.enums import ApprovalStatus

_LOGGER = logging.getLogger(__name__)


class ApprovalGateway(Protocol):
    """Port for requesting human authorisation of an expensive offer."""

    def request_approval(self, offer: OfferProposal, value: ValueReport) -> ApprovalStatus:
        """Return the approval decision for ``offer``."""


class AutoApprovalGateway:
    """Non-interactive gateway used for tests and automated demos.

    It approves an expensive offer only when it is economically justified
    (positive ROI and the customer is not worthless), otherwise rejects it.
    This keeps automated runs deterministic while still exercising the
    approve/reject branches.
    """

    def request_approval(self, offer: OfferProposal, value: ValueReport) -> ApprovalStatus:
        """Auto-decide based on ROI and customer value.

        Args:
            offer: The proposed offer requiring approval.
            value: The value report for the same customer.

        Returns:
            ``APPROVED`` when justified, otherwise ``REJECTED``.
        """
        justified = offer.roi >= 1.0 and value.cost_of_loss >= offer.cost
        decision = ApprovalStatus.APPROVED if justified else ApprovalStatus.REJECTED
        _LOGGER.info(
            "auto approval decision=%s offer_cost=%.2f roi=%.2f",
            decision.value,
            offer.cost,
            offer.roi,
        )
        return decision


class AuditApprovalGateway:
    """Non-blocking gateway: every case is processed, expensive offers are
    *flagged for audit* instead of stopping the pipeline.

    This implements the "human as auditor" model: 100% of customers are
    scored and actioned automatically; offers whose cost exceeds the policy
    threshold are recorded in :attr:`alerts` so a human can review them
    afterwards through the downloadable alert report.
    """

    def __init__(self) -> None:
        """Initialise the empty alert registry."""
        self.alerts: list[tuple[OfferProposal, ValueReport]] = []

    def request_approval(self, offer: OfferProposal, value: ValueReport) -> ApprovalStatus:
        """Record the offer as an audit alert and let processing continue.

        Args:
            offer: The expensive offer that crossed the policy threshold.
            value: The value report for the same customer.

        Returns:
            Always :attr:`ApprovalStatus.FLAGGED_FOR_AUDIT` — the workflow
            proceeds; the human audits the report afterwards.
        """
        self.alerts.append((offer, value))
        _LOGGER.info(
            "audit alert customer=%s cost=%.2f roi=%.2f",
            offer.customer_id,
            offer.cost,
            offer.roi,
        )
        return ApprovalStatus.FLAGGED_FOR_AUDIT


class MappingApprovalGateway:
    """Approval gateway driven by a pre-computed mapping of decisions.

    This is the bridge used by stateless / rerun-based front-ends (such as
    Streamlit): the UI collects human decisions across reruns into a mapping
    keyed by ``customer_id`` and injects them here. Every approval request is
    also *recorded* so the UI can render the exact offers awaiting a decision,
    even when the consolidated decision hides a withdrawn offer.
    """

    def __init__(
        self,
        decisions: Mapping[str, ApprovalStatus] | None = None,
        default: ApprovalStatus = ApprovalStatus.REJECTED,
    ) -> None:
        """Initialise the gateway.

        Args:
            decisions: Map of ``customer_id`` to a human approval decision.
            default: Status returned when a customer has no explicit decision
                yet. Defaults to ``REJECTED`` (safe: never spend without an
                explicit approval).
        """
        self._decisions = dict(decisions or {})
        self._default = default
        self.requests: list[tuple[OfferProposal, ValueReport]] = []

    def request_approval(self, offer: OfferProposal, value: ValueReport) -> ApprovalStatus:
        """Record the request and return the mapped (or default) decision.

        Args:
            offer: The proposed offer requiring approval.
            value: The value report for the same customer.

        Returns:
            The human decision if present, otherwise the configured default.
        """
        self.requests.append((offer, value))
        status = self._decisions.get(offer.customer_id, self._default)
        _LOGGER.info("mapping approval customer=%s decision=%s", offer.customer_id, status.value)
        return status


class ConsoleApprovalGateway:  # pragma: no cover - interactive I/O
    """Interactive gateway that prompts a human operator on the console."""

    def request_approval(self, offer: OfferProposal, value: ValueReport) -> ApprovalStatus:
        """Prompt the operator to approve or reject the offer."""
        print("\n=== HUMAN-IN-THE-LOOP APPROVAL REQUIRED ===")
        print(f"Customer     : {offer.customer_id}")
        print(f"Offer        : {offer.offer_name}")
        print(f"Cost         : {offer.cost:.2f}")
        print(f"Discount     : {offer.discount_pct:.1f}%")
        print(f"Expected ROI : {offer.roi:.2f}")
        print(f"Cost of loss : {value.cost_of_loss:.2f}")
        answer = input("Approve this offer? [y/N]: ").strip().lower()
        return ApprovalStatus.APPROVED if answer in {"y", "yes", "si"} else ApprovalStatus.REJECTED

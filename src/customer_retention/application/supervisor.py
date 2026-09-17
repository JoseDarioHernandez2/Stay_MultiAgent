"""Retention Supervisor: coordinates agents and consolidates the decision.

The Supervisor performs **no analysis**. Its sole responsibilities are:
    1. Decide parallelism — run Behavior and Value analysts concurrently.
    2. Delegate — invoke the Offer Specialist once analyses are ready.
    3. Request review — submit all artifacts to the mandatory quality gate.
    4. Enforce Human-in-the-Loop — request approval for expensive offers.
    5. Consolidate — assemble the final :class:`WorkflowDecision`.

A bounded revision loop (one retry) guards against infinite iteration when the
Reviewer returns ``NEEDS_REVISION``.
"""

from __future__ import annotations

import asyncio
import logging

from customer_retention.agents.behavior_analyst import BehaviorAnalystAgent
from customer_retention.agents.offer_specialist import OfferInput, OfferSpecialistAgent
from customer_retention.agents.reviewer import ReviewerAgent, ReviewInput
from customer_retention.agents.value_analyst import ValueAnalystAgent
from customer_retention.application.policy import RetentionPolicy
from customer_retention.domain.contracts import (
    BehaviorReport,
    CustomerRecord,
    OfferProposal,
    ReviewResult,
    ValueReport,
    WorkflowDecision,
)
from customer_retention.domain.enums import (
    ApprovalStatus,
    DecisionAction,
    ImportanceLevel,
    ReviewStatus,
    RiskLevel,
)
from customer_retention.domain.exceptions import AgentExecutionError
from customer_retention.tools.clv import compute_clv
from customer_retention.tools.human_in_the_loop import ApprovalGateway

_LOGGER = logging.getLogger(__name__)
_MAX_REVISIONS = 1


class RetentionSupervisor:
    """Orchestrate the four specialist agents for a single customer."""

    def __init__(
        self,
        behavior: BehaviorAnalystAgent,
        value: ValueAnalystAgent,
        offer: OfferSpecialistAgent,
        reviewer: ReviewerAgent,
        policy: RetentionPolicy,
        approval_gateway: ApprovalGateway,
    ) -> None:
        """Wire the agents and collaborators (dependency injection)."""
        self._behavior = behavior
        self._value = value
        self._offer = offer
        self._reviewer = reviewer
        self._policy = policy
        self._approval = approval_gateway

    async def handle(self, record: CustomerRecord) -> WorkflowDecision:
        """Coordinate the full pipeline for one customer.

        Args:
            record: The customer to process.

        Returns:
            The consolidated :class:`WorkflowDecision`.
        """
        behavior, value = await self._run_analyses_in_parallel(record)

        offer: OfferProposal | None = None
        review: ReviewResult | None = None
        for attempt in range(_MAX_REVISIONS + 1):
            offer = await self._offer.run(
                OfferInput(behavior=behavior, value=value, policy=self._policy)
            )
            review = await self._reviewer.run(
                ReviewInput(behavior=behavior, value=value, offer=offer, policy=self._policy)
            )
            if review.status is not ReviewStatus.NEEDS_REVISION:
                break
            _LOGGER.info("revision requested (attempt %d) for %s", attempt + 1, record.customer_id)

        if offer is None or review is None:  # pragma: no cover - defensive
            raise AgentExecutionError("supervisor", "offer/review not produced")
        approval_status = await self._resolve_approval(offer, value, review)
        action = self._consolidate_action(behavior, value, review, approval_status)

        return WorkflowDecision(
            customer_id=record.customer_id,
            action=action,
            approval_status=approval_status,
            behavior=behavior,
            value=value,
            # The proposed offer is always retained for auditability; ``action``
            # indicates whether it is actually executed.
            offer=offer,
            review=review,
            summary=self._summary(behavior, value, offer, action, approval_status),
        )

    async def _run_analyses_in_parallel(
        self, record: CustomerRecord
    ) -> tuple[BehaviorReport, ValueReport]:
        """Execute Behavior and Value analyses with maximum concurrency.

        ``compute_clv(record)`` depends only on the customer record, not on the
        churn probability. The Supervisor therefore launches the Behavior agent
        (which runs the churn model) **and** the CLV computation concurrently
        via :func:`asyncio.gather`. Once both complete, the Value agent
        finalises the probability-dependent metrics (``expected_value``,
        ``cost_of_loss``) using the churn probability from the Behavior report
        and the pre-computed CLV — avoiding the sequential bottleneck.
        """
        # Phase 1 — truly parallel: model prediction ∥ CLV computation
        behavior, precomputed_clv = await asyncio.gather(
            self._behavior.run(record),
            asyncio.to_thread(compute_clv, record),
        )
        _LOGGER.debug(
            "parallel phase complete for %s: p_churn=%.3f, clv=%.2f",
            record.customer_id,
            behavior.churn_probability,
            precomputed_clv,
        )
        # Phase 2 — Value agent uses the pre-computed CLV + churn probability
        value = await self._value.run(
            (record, behavior.churn_probability),
            precomputed_clv=precomputed_clv,
        )
        return behavior, value

    async def _resolve_approval(
        self, offer: OfferProposal, value: ValueReport, review: ReviewResult
    ) -> ApprovalStatus:
        """Apply the Human-in-the-Loop gate when required by policy."""
        if review.status is ReviewStatus.REJECT:
            return ApprovalStatus.NOT_REQUIRED
        if not offer.requires_approval:
            return ApprovalStatus.NOT_REQUIRED
        _LOGGER.info("requesting HITL approval for %s", offer.customer_id)
        return await asyncio.to_thread(self._approval.request_approval, offer, value)

    @staticmethod
    def _consolidate_action(
        behavior: BehaviorReport,
        value: ValueReport,
        review: ReviewResult,
        approval: ApprovalStatus,
    ) -> DecisionAction:
        """Combine risk, value, review and approval into a final action."""
        if review.status is ReviewStatus.REJECT:
            return DecisionAction.ESCALATE
        if approval is ApprovalStatus.REJECTED:
            return DecisionAction.MONITOR
        low_risk = behavior.risk_level is RiskLevel.LOW
        low_value = value.importance_level is ImportanceLevel.BRONZE
        if low_risk and low_value:
            return DecisionAction.NO_ACTION
        if low_risk:
            return DecisionAction.MONITOR
        return DecisionAction.RETAIN_WITH_OFFER

    @staticmethod
    def _summary(
        behavior: BehaviorReport,
        value: ValueReport,
        offer: OfferProposal,
        action: DecisionAction,
        approval: ApprovalStatus,
    ) -> str:
        """Compose a one-line human-readable decision summary."""
        return (
            f"risk={behavior.risk_level.value} "
            f"(p={behavior.churn_probability:.2f}), "
            f"value={value.importance_level.value} "
            f"(clv={value.customer_lifetime_value:.0f}), "
            f"offer={offer.offer_id}@{offer.cost:.0f}, "
            f"action={action.value}, approval={approval.value}"
        )

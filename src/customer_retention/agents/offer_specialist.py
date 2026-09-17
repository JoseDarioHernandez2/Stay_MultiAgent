"""Offer Specialist agent: designs a policy-compliant OfferProposal."""

from __future__ import annotations

from dataclasses import dataclass

from customer_retention.agents.base import BaseAgent
from customer_retention.application.policy import RetentionPolicy
from customer_retention.domain.contracts import BehaviorReport, OfferProposal, ValueReport
from customer_retention.domain.enums import RiskLevel
from customer_retention.infrastructure.tracing import TraceRecorder, TraceSpan
from customer_retention.prompts.offer import SYSTEM_PROMPT


@dataclass(frozen=True)
class OfferInput:
    """Bundle of artifacts the Offer Specialist consumes."""

    behavior: BehaviorReport
    value: ValueReport
    policy: RetentionPolicy


# Offer catalogue: (id, name, base discount %, base cost).
_CATALOGUE: tuple[tuple[str, str, float, float], ...] = (
    ("OFF-LOYALTY", "Loyalty thank-you credit", 5.0, 20.0),
    ("OFF-STANDARD", "Standard retention discount", 15.0, 80.0),
    ("OFF-PREMIUM", "Premium win-back package", 30.0, 250.0),
)


class OfferSpecialistAgent(BaseAgent[OfferInput, OfferProposal]):
    """Select the best retention offer subject to the enterprise policy."""

    name = "offer-specialist"

    def __init__(self, recorder: TraceRecorder) -> None:
        """Initialise the agent with its trace recorder."""
        super().__init__(recorder)
        self._prompt = SYSTEM_PROMPT

    async def _execute(self, payload: OfferInput, span: TraceSpan) -> OfferProposal:
        """Pick a compliant offer and compute its economics."""
        offer_id, name, discount, cost = self._select_offer(payload.behavior)
        policy = payload.policy

        discount = min(discount, policy.max_discount_pct)
        if cost > policy.max_offer_cost:
            span.warn("selected offer exceeded cost cap; downgraded to cap")
            cost = policy.max_offer_cost

        expected_benefit = self._expected_benefit(payload)
        # ROI expressed as a benefit/cost ratio: >= 1.0 means at least break-even,
        # which aligns with ``policy.min_roi``.
        roi = round(expected_benefit / cost, 4) if cost > 0 else 0.0
        requires_approval = cost > policy.approval_cost_threshold

        return OfferProposal(
            customer_id=payload.value.customer_id,
            offer_id=offer_id,
            offer_name=name,
            cost=round(cost, 2),
            discount_pct=round(discount, 2),
            expected_benefit=round(expected_benefit, 2),
            roi=roi,
            requires_approval=requires_approval,
            rationale=self._rationale(payload, roi, requires_approval),
        )

    @staticmethod
    def _select_offer(behavior: BehaviorReport) -> tuple[str, str, float, float]:
        """Choose a catalogue tier from the churn risk band."""
        if behavior.risk_level in (RiskLevel.CRITICAL, RiskLevel.HIGH):
            return _CATALOGUE[2]
        if behavior.risk_level is RiskLevel.MEDIUM:
            return _CATALOGUE[1]
        return _CATALOGUE[0]

    @staticmethod
    def _expected_benefit(payload: OfferInput) -> float:
        """Expected benefit of the offer.

        ``cost_of_loss`` already equals ``clv * churn_probability`` (the value
        at risk). An offer recovers a fraction of that at-risk value, so the
        benefit is ``cost_of_loss * recovery_rate`` — the churn probability is
        intentionally *not* multiplied again to avoid double counting.
        """
        recovery_rate = 0.6
        return payload.value.cost_of_loss * recovery_rate

    @staticmethod
    def _rationale(payload: OfferInput, roi: float, approval: bool) -> str:
        """Compose an auditable rationale string."""
        base = (
            f"risk={payload.behavior.risk_level.value}, "
            f"tier={payload.value.importance_level.value}, roi={roi:.2f}"
        )
        return base + (" | requires HITL approval" if approval else " | auto-eligible")

    def _summarise_output(self, result: OfferProposal) -> str:
        """Summarise the offer for the trace."""
        return f"offer={result.offer_id} cost={result.cost:.2f} approval={result.requires_approval}"

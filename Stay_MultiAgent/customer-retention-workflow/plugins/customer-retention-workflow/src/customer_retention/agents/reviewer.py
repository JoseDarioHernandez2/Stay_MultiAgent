"""Reviewer agent: the mandatory quality gate."""

from __future__ import annotations

from dataclasses import dataclass

from customer_retention.agents.base import BaseAgent
from customer_retention.application.policy import RetentionPolicy
from customer_retention.domain.contracts import (
    BehaviorReport,
    OfferProposal,
    ReviewCheck,
    ReviewResult,
    ValueReport,
    risk_from_probability,
)
from customer_retention.domain.enums import ReviewStatus
from customer_retention.infrastructure.tracing import TraceRecorder, TraceSpan
from customer_retention.prompts.reviewer import SYSTEM_PROMPT


@dataclass(frozen=True)
class ReviewInput:
    """Bundle of artifacts the Reviewer validates."""

    behavior: BehaviorReport
    value: ValueReport
    offer: OfferProposal
    policy: RetentionPolicy


class ReviewerAgent(BaseAgent[ReviewInput, ReviewResult]):
    """Validate upstream artifacts against consistency and policy rules.

    The Reviewer performs no analysis: it only checks. It returns APPROVE,
    NEEDS_REVISION or REJECT based on the collected checks.
    """

    name = "reviewer"

    def __init__(self, recorder: TraceRecorder) -> None:
        """Initialise the agent with its trace recorder."""
        super().__init__(recorder)
        self._prompt = SYSTEM_PROMPT

    async def _execute(self, payload: ReviewInput, span: TraceSpan) -> ReviewResult:
        """Run all checks and derive the review status."""
        checks = self._run_checks(payload)
        issues = [f"{c.name}: {c.detail}" for c in checks if not c.passed]
        status = self._status(checks)
        if status is not ReviewStatus.APPROVE:
            span.warn(f"review status={status.value}")
        return ReviewResult(
            customer_id=payload.behavior.customer_id,
            status=status,
            checks=checks,
            issues=issues,
        )

    def _run_checks(self, payload: ReviewInput) -> list[ReviewCheck]:
        """Execute every validation and return the check list."""
        return [
            self._check_ids_match(payload),
            self._check_risk_band(payload),
            self._check_discount_policy(payload),
            self._check_cost_cap(payload),
            self._check_approval_flag(payload),
            self._check_values_finite(payload),
        ]

    @staticmethod
    def _check_ids_match(p: ReviewInput) -> ReviewCheck:
        """All artifacts must reference the same customer."""
        ids = {p.behavior.customer_id, p.value.customer_id, p.offer.customer_id}
        ok = len(ids) == 1
        return ReviewCheck(
            name="ids_consistent", passed=ok, detail="" if ok else f"mismatched ids: {ids}"
        )

    @staticmethod
    def _check_risk_band(p: ReviewInput) -> ReviewCheck:
        """Risk band must match the probability thresholds."""
        expected = risk_from_probability(p.behavior.churn_probability)
        ok = expected is p.behavior.risk_level
        return ReviewCheck(
            name="risk_band_coherent",
            passed=ok,
            detail="" if ok else f"expected {expected.value}",
        )

    @staticmethod
    def _check_discount_policy(p: ReviewInput) -> ReviewCheck:
        """Discount must not exceed the policy maximum."""
        ok = p.offer.discount_pct <= p.policy.max_discount_pct
        return ReviewCheck(
            name="discount_within_policy",
            passed=ok,
            detail="" if ok else f"{p.offer.discount_pct} > {p.policy.max_discount_pct}",
        )

    @staticmethod
    def _check_cost_cap(p: ReviewInput) -> ReviewCheck:
        """Offer cost must not exceed the hard cap."""
        ok = p.offer.cost <= p.policy.max_offer_cost
        return ReviewCheck(
            name="cost_within_cap",
            passed=ok,
            detail="" if ok else f"{p.offer.cost} > {p.policy.max_offer_cost}",
        )

    @staticmethod
    def _check_approval_flag(p: ReviewInput) -> ReviewCheck:
        """requires_approval must match the policy threshold."""
        expected = p.offer.cost > p.policy.approval_cost_threshold
        ok = expected == p.offer.requires_approval
        return ReviewCheck(
            name="approval_flag_correct",
            passed=ok,
            detail="" if ok else "approval flag inconsistent with cost threshold",
        )

    @staticmethod
    def _check_values_finite(p: ReviewInput) -> ReviewCheck:
        """No negative monetary values are allowed."""
        ok = min(p.value.customer_lifetime_value, p.value.cost_of_loss, p.offer.cost) >= 0
        return ReviewCheck(
            name="values_non_negative", passed=ok, detail="" if ok else "negative value found"
        )

    @staticmethod
    def _status(checks: list[ReviewCheck]) -> ReviewStatus:
        """Derive the terminal review status from the checks."""
        failed = [c for c in checks if not c.passed]
        if not failed:
            return ReviewStatus.APPROVE
        hard = {"discount_within_policy", "cost_within_cap", "values_non_negative"}
        if any(c.name in hard for c in failed):
            return ReviewStatus.REJECT
        return ReviewStatus.NEEDS_REVISION

    def _summarise_output(self, result: ReviewResult) -> str:
        """Summarise the review outcome for the trace."""
        return f"status={result.status.value} issues={len(result.issues)}"

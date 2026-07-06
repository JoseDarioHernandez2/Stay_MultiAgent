"""Unit tests for the reviewer's reject / needs-revision branches."""

from __future__ import annotations

import asyncio

from customer_retention.agents.reviewer import ReviewerAgent, ReviewInput
from customer_retention.application.policy import RetentionPolicy
from customer_retention.domain.contracts import BehaviorReport, OfferProposal, ValueReport
from customer_retention.domain.enums import ImportanceLevel, ReviewStatus, RiskLevel


def _behavior() -> BehaviorReport:
    return BehaviorReport(
        customer_id="c1", churn_probability=0.6, risk_level=RiskLevel.HIGH, model_name="m"
    )


def _value() -> ValueReport:
    return ValueReport(
        customer_id="c1",
        customer_lifetime_value=800.0,
        expected_value=320.0,
        cost_of_loss=480.0,
        importance_level=ImportanceLevel.GOLD,
        segment="gold-new",
    )


def test_reviewer_rejects_discount_over_policy(recorder) -> None:
    """A discount above the policy maximum yields REJECT (hard failure)."""
    strict = RetentionPolicy(max_discount_pct=5.0)
    offer = OfferProposal(
        customer_id="c1",
        offer_id="OFF-X",
        offer_name="oversized",
        cost=100.0,
        discount_pct=15.0,  # above the 5% policy cap
        expected_benefit=200.0,
        roi=2.0,
        requires_approval=False,
        rationale="test",
    )
    review = asyncio.run(
        ReviewerAgent(recorder).run(
            ReviewInput(behavior=_behavior(), value=_value(), offer=offer, policy=strict)
        )
    )
    assert review.status is ReviewStatus.REJECT
    assert any(not c.passed for c in review.checks)


def test_reviewer_needs_revision_on_soft_failure(recorder) -> None:
    """An inconsistent approval flag is a soft failure -> NEEDS_REVISION."""
    policy = RetentionPolicy.default()
    offer = OfferProposal(
        customer_id="c1",
        offer_id="OFF-Y",
        offer_name="mislabelled",
        cost=250.0,  # > 200 threshold, so approval SHOULD be required
        discount_pct=10.0,
        expected_benefit=400.0,
        roi=1.6,
        requires_approval=False,  # inconsistent -> soft failure
        rationale="test",
    )
    review = asyncio.run(
        ReviewerAgent(recorder).run(
            ReviewInput(behavior=_behavior(), value=_value(), offer=offer, policy=policy)
        )
    )
    assert review.status is ReviewStatus.NEEDS_REVISION

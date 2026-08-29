"""Unit tests for the individual agents."""

from __future__ import annotations

import asyncio

from customer_retention.agents.behavior_analyst import BehaviorAnalystAgent
from customer_retention.agents.offer_specialist import OfferInput, OfferSpecialistAgent
from customer_retention.agents.reviewer import ReviewerAgent, ReviewInput
from customer_retention.agents.value_analyst import ValueAnalystAgent
from customer_retention.domain.enums import ReviewStatus, RiskLevel


def test_behavior_agent_emits_report_with_signals(recorder, model, high_risk_customer) -> None:
    """The behavior agent produces a coherent BehaviorReport with signals."""
    agent = BehaviorAnalystAgent(recorder, model)
    report = asyncio.run(agent.run(high_risk_customer))
    assert report.customer_id == "HR-1"
    assert report.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    assert report.signals
    assert recorder.traces[0].agent_name == "behavior-analyst"


def test_value_agent_tiers_customer(recorder, high_risk_customer) -> None:
    """The value agent returns a non-negative CLV and a tier."""
    agent = ValueAnalystAgent(recorder, high_value_clv=1000.0)
    report = asyncio.run(agent.run((high_risk_customer, 0.9)))
    assert report.customer_lifetime_value >= 0
    assert report.cost_of_loss >= 0


def test_offer_agent_flags_expensive_offer(recorder, policy, model, high_risk_customer) -> None:
    """A premium offer above the threshold requires approval."""
    behavior = asyncio.run(BehaviorAnalystAgent(recorder, model).run(high_risk_customer))
    value = asyncio.run(
        ValueAnalystAgent(recorder, 1000.0).run((high_risk_customer, behavior.churn_probability))
    )
    offer = asyncio.run(
        OfferSpecialistAgent(recorder).run(
            OfferInput(behavior=behavior, value=value, policy=policy)
        )
    )
    assert offer.discount_pct <= policy.max_discount_pct
    assert offer.cost <= policy.max_offer_cost
    assert offer.requires_approval is (offer.cost > policy.approval_cost_threshold)


def test_reviewer_approves_consistent_artifacts(
    recorder, policy, model, high_risk_customer
) -> None:
    """The reviewer approves a fully consistent artifact set."""
    behavior = asyncio.run(BehaviorAnalystAgent(recorder, model).run(high_risk_customer))
    value = asyncio.run(
        ValueAnalystAgent(recorder, 1000.0).run((high_risk_customer, behavior.churn_probability))
    )
    offer = asyncio.run(
        OfferSpecialistAgent(recorder).run(
            OfferInput(behavior=behavior, value=value, policy=policy)
        )
    )
    review = asyncio.run(
        ReviewerAgent(recorder).run(
            ReviewInput(behavior=behavior, value=value, offer=offer, policy=policy)
        )
    )
    assert review.status is ReviewStatus.APPROVE
    assert all(check.passed for check in review.checks)

"""Contract tests: every agent must return its declared typed artifact."""

from __future__ import annotations

import asyncio

from customer_retention.agents.behavior_analyst import BehaviorAnalystAgent
from customer_retention.agents.offer_specialist import OfferInput, OfferSpecialistAgent
from customer_retention.agents.reviewer import ReviewerAgent, ReviewInput
from customer_retention.agents.value_analyst import ValueAnalystAgent
from customer_retention.domain.contracts import (
    BehaviorReport,
    OfferProposal,
    ReviewResult,
    ValueReport,
)


def test_agents_return_declared_types(recorder, policy, model, loyal_customer) -> None:
    """Each agent returns exactly its contract type (no free text)."""
    behavior = asyncio.run(BehaviorAnalystAgent(recorder, model).run(loyal_customer))
    assert isinstance(behavior, BehaviorReport)

    value = asyncio.run(
        ValueAnalystAgent(recorder, 1000.0).run((loyal_customer, behavior.churn_probability))
    )
    assert isinstance(value, ValueReport)

    offer = asyncio.run(
        OfferSpecialistAgent(recorder).run(
            OfferInput(behavior=behavior, value=value, policy=policy)
        )
    )
    assert isinstance(offer, OfferProposal)

    review = asyncio.run(
        ReviewerAgent(recorder).run(
            ReviewInput(behavior=behavior, value=value, offer=offer, policy=policy)
        )
    )
    assert isinstance(review, ReviewResult)


def test_artifacts_are_immutable(recorder, model, loyal_customer) -> None:
    """Emitted artifacts are frozen: agents cannot share mutable memory."""
    behavior = asyncio.run(BehaviorAnalystAgent(recorder, model).run(loyal_customer))
    try:
        behavior.churn_probability = 0.0  # type: ignore[misc]
    except (TypeError, ValueError, AttributeError):
        return
    raise AssertionError("artifact should be immutable")

"""Shared pytest fixtures for the retention workflow test suite."""

from __future__ import annotations

import pytest

from customer_retention.application.policy import RetentionPolicy
from customer_retention.domain.contracts import CustomerRecord
from customer_retention.infrastructure.model_adapter import HeuristicChurnModel
from customer_retention.infrastructure.tracing import TraceRecorder


@pytest.fixture()
def policy() -> RetentionPolicy:
    """Return the default enterprise policy."""
    return RetentionPolicy.default()


@pytest.fixture()
def recorder() -> TraceRecorder:
    """Return a fresh trace recorder."""
    return TraceRecorder()


@pytest.fixture()
def model() -> HeuristicChurnModel:
    """Return the deterministic heuristic churn model."""
    return HeuristicChurnModel()


@pytest.fixture()
def high_risk_customer() -> CustomerRecord:
    """A customer with strong churn signals."""
    return CustomerRecord(
        customer_id="HR-1",
        tenure_months=1,
        monthly_charges=99.9,
        total_charges=99.9,
        contract_type="month-to-month",
        support_calls=6,
        complaints=3,
        is_active=False,
    )


@pytest.fixture()
def loyal_customer() -> CustomerRecord:
    """A long-tenured, low-risk customer."""
    return CustomerRecord(
        customer_id="LO-1",
        tenure_months=48,
        monthly_charges=42.0,
        total_charges=2016.0,
        contract_type="two-year",
        support_calls=0,
        complaints=0,
        is_active=True,
    )

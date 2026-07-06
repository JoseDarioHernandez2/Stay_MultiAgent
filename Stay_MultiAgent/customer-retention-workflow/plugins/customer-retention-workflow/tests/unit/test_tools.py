"""Unit tests for the deterministic CLV tools."""

from __future__ import annotations

from customer_retention.domain.contracts import CustomerRecord
from customer_retention.tools.clv import (
    compute_clv,
    compute_cost_of_loss,
    compute_expected_value,
)


def test_clv_is_non_negative_and_monotonic() -> None:
    """Higher monthly charges yield higher CLV."""
    low = CustomerRecord(customer_id="a", monthly_charges=10.0, tenure_months=12)
    high = CustomerRecord(customer_id="b", monthly_charges=100.0, tenure_months=12)
    assert compute_clv(low) >= 0
    assert compute_clv(high) > compute_clv(low)


def test_expected_value_and_cost_of_loss_split_clv() -> None:
    """Expected value + cost of loss reconstitute the CLV."""
    clv = 1000.0
    churn = 0.3
    assert compute_expected_value(clv, churn) == 700.0
    assert compute_cost_of_loss(clv, churn) == 300.0

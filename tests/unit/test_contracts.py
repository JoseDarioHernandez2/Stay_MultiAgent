"""Unit tests for domain contracts and validators."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from customer_retention.domain.contracts import (
    BehaviorReport,
    ReviewCheck,
    ReviewResult,
    risk_from_probability,
)
from customer_retention.domain.enums import ReviewStatus, RiskLevel


@pytest.mark.parametrize(
    ("probability", "expected"),
    [
        (0.05, RiskLevel.LOW),
        (0.40, RiskLevel.MEDIUM),
        (0.60, RiskLevel.HIGH),
        (0.95, RiskLevel.CRITICAL),
    ],
)
def test_risk_from_probability_bands(probability: float, expected: RiskLevel) -> None:
    """Probability bands map to the expected risk level."""
    assert risk_from_probability(probability) is expected


def test_risk_from_probability_rejects_out_of_range() -> None:
    """Out-of-range probabilities raise ValueError."""
    with pytest.raises(ValueError):
        risk_from_probability(1.5)


def test_behavior_report_rejects_inconsistent_band() -> None:
    """A risk band that contradicts the probability is rejected."""
    with pytest.raises(ValidationError):
        BehaviorReport(
            customer_id="c1",
            churn_probability=0.9,
            risk_level=RiskLevel.LOW,  # inconsistent
            model_name="m",
        )


def test_review_result_cannot_approve_with_failing_check() -> None:
    """APPROVE with a failing check is forbidden by the validator."""
    with pytest.raises(ValidationError):
        ReviewResult(
            customer_id="c1",
            status=ReviewStatus.APPROVE,
            checks=[ReviewCheck(name="x", passed=False, detail="bad")],
        )


def test_contract_forbids_extra_fields() -> None:
    """Unknown (hallucinated) fields are rejected."""
    with pytest.raises(ValidationError):
        BehaviorReport(
            customer_id="c1",
            churn_probability=0.1,
            risk_level=RiskLevel.LOW,
            model_name="m",
            hallucinated=123,  # type: ignore[call-arg]
        )

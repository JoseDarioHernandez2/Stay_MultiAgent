"""Unit tests for the churn model adapter."""

from __future__ import annotations

from customer_retention.domain.contracts import CustomerRecord
from customer_retention.infrastructure.model_adapter import HeuristicChurnModel, build_churn_model


def test_heuristic_is_deterministic_and_bounded() -> None:
    """The heuristic model returns a stable value in [0, 1]."""
    model = HeuristicChurnModel()
    record = CustomerRecord(customer_id="c", support_calls=4, complaints=2, is_active=False)
    first = model.predict_proba(record)
    second = model.predict_proba(record)
    assert first == second
    assert 0.0 <= first <= 1.0


def test_build_model_falls_back_when_path_missing() -> None:
    """A missing model path yields the heuristic fallback."""
    model = build_churn_model("/does/not/exist.py")
    assert isinstance(model, HeuristicChurnModel)


def test_higher_pressure_increases_probability() -> None:
    """More support pressure raises the churn probability."""
    model = HeuristicChurnModel()
    calm = CustomerRecord(customer_id="a", support_calls=0, complaints=0, tenure_months=40)
    stressed = CustomerRecord(customer_id="b", support_calls=6, complaints=3, tenure_months=1)
    assert model.predict_proba(stressed) > model.predict_proba(calm)

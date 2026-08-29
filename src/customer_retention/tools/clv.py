"""Customer Lifetime Value (CLV) computation utilities.

These are pure, deterministic functions so the Value Analyst's numbers are
reproducible and unit-testable without any model or network dependency.
"""

from __future__ import annotations

from customer_retention.domain.contracts import CustomerRecord

# Assumed gross margin applied to recurring revenue when deriving value.
_GROSS_MARGIN = 0.30
# Discount rate used to damp the value of a projected retention horizon.
_DISCOUNT_RATE = 0.10
# Retention horizon (months) used when a customer has little history.
_DEFAULT_HORIZON_MONTHS = 24


def compute_clv(record: CustomerRecord) -> float:
    """Estimate the Customer Lifetime Value.

    A simple discounted-margin model: recurring margin projected over an
    expected horizon (bounded by observed tenure) and discounted.

    Args:
        record: The customer to evaluate.

    Returns:
        A non-negative CLV estimate.
    """
    horizon = max(record.tenure_months, _DEFAULT_HORIZON_MONTHS)
    monthly_margin = record.monthly_charges * _GROSS_MARGIN
    discount = 1.0 / (1.0 + _DISCOUNT_RATE)
    clv = monthly_margin * horizon * discount
    return round(max(clv, 0.0), 2)


def compute_expected_value(clv: float, churn_probability: float) -> float:
    """Return the retention-weighted expected value of a customer.

    Args:
        clv: The customer lifetime value.
        churn_probability: Probability the customer will churn.

    Returns:
        ``clv * (1 - churn_probability)``, never negative.
    """
    return round(max(clv * (1.0 - churn_probability), 0.0), 2)


def compute_cost_of_loss(clv: float, churn_probability: float) -> float:
    """Return the expected monetary cost of losing the customer.

    Args:
        clv: The customer lifetime value.
        churn_probability: Probability the customer will churn.

    Returns:
        ``clv * churn_probability``, never negative.
    """
    return round(max(clv * churn_probability, 0.0), 2)

"""Pure reporting helpers that turn workflow results into UI-friendly data.

Kept free of any Streamlit dependency so the aggregations are unit-testable and
reusable by the CLI, notebooks or any other front-end.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from customer_retention.domain.contracts import WorkflowResult
from customer_retention.domain.enums import ApprovalStatus, DecisionAction


def result_to_row(result: WorkflowResult) -> dict[str, Any]:
    """Flatten a :class:`WorkflowResult` into a single tabular row.

    Args:
        result: One workflow result.

    Returns:
        A flat, JSON-friendly mapping suitable for a dataframe row.
    """
    decision = result.decision
    offer = decision.offer
    return {
        "customer_id": decision.customer_id,
        "churn_probability": round(decision.behavior.churn_probability, 4),
        "risk_level": decision.behavior.risk_level.value,
        "clv": decision.value.customer_lifetime_value,
        "cost_of_loss": decision.value.cost_of_loss,
        "importance": decision.value.importance_level.value,
        "segment": decision.value.segment,
        "offer_id": offer.offer_id if offer else "-",
        "offer_cost": offer.cost if offer else 0.0,
        "discount_pct": offer.discount_pct if offer else 0.0,
        "roi": offer.roi if offer else 0.0,
        "action": decision.action.value,
        "approval": decision.approval_status.value,
        "review": decision.review.status.value,
        "duration_ms": round(result.total_duration_ms, 2),
    }


def build_table(results: list[WorkflowResult]) -> list[dict[str, Any]]:
    """Return one flat row per result."""
    return [result_to_row(r) for r in results]


def summarize(results: list[WorkflowResult]) -> dict[str, Any]:
    """Compute headline metrics and distributions over the batch.

    Args:
        results: The batch of workflow results.

    Returns:
        A mapping with counts by action/risk/importance and monetary totals.
    """
    actions = Counter(r.decision.action.value for r in results)
    risks = Counter(r.decision.behavior.risk_level.value for r in results)
    tiers = Counter(r.decision.value.importance_level.value for r in results)
    retained = [r for r in results if r.decision.action is DecisionAction.RETAIN_WITH_OFFER]
    pending = sum(1 for r in results if r.decision.approval_status is ApprovalStatus.PENDING)
    return {
        "total_customers": len(results),
        "retained": len(retained),
        "by_action": dict(actions),
        "by_risk": dict(risks),
        "by_importance": dict(tiers),
        "offer_spend": round(sum(r.decision.offer.cost for r in retained if r.decision.offer), 2),
        "value_protected": round(sum(r.decision.value.cost_of_loss for r in retained), 2),
        "pending_approvals": pending,
    }


def pending_approvals(results: list[WorkflowResult]) -> list[dict[str, Any]]:
    """List customers whose offer required (and still awaits) approval.

    A customer is surfaced when the offer flagged ``requires_approval`` but the
    consolidated approval status is not ``APPROVED``.

    Args:
        results: The batch of workflow results.

    Returns:
        Rows describing each offer awaiting a human decision.
    """
    rows: list[dict[str, Any]] = []
    for result in results:
        decision = result.decision
        offer = decision.offer
        if (
            offer is not None
            and offer.requires_approval
            and decision.approval_status is not ApprovalStatus.APPROVED
        ):
            rows.append(
                {
                    "customer_id": decision.customer_id,
                    "offer_name": offer.offer_name,
                    "cost": offer.cost,
                    "roi": offer.roi,
                    "cost_of_loss": decision.value.cost_of_loss,
                }
            )
    return rows


def alerted_rows(results: list[WorkflowResult]) -> list[dict[str, Any]]:
    """Rows for customers whose offer was flagged for human audit.

    Args:
        results: The batch of workflow results.

    Returns:
        One row per alerted customer, ready for the audit report.
    """
    rows: list[dict[str, Any]] = []
    for result in results:
        decision = result.decision
        offer = decision.offer
        if offer is not None and decision.approval_status is ApprovalStatus.FLAGGED_FOR_AUDIT:
            rows.append(
                {
                    "customer_id": decision.customer_id,
                    "churn_probability": round(decision.behavior.churn_probability, 4),
                    "risk_level": decision.behavior.risk_level.value,
                    "clv": decision.value.customer_lifetime_value,
                    "cost_of_loss": decision.value.cost_of_loss,
                    "offer_id": offer.offer_id,
                    "offer_name": offer.offer_name,
                    "offer_cost": offer.cost,
                    "discount_pct": offer.discount_pct,
                    "roi": offer.roi,
                    "action": decision.action.value,
                    "signals": "; ".join(decision.behavior.signals),
                }
            )
    return rows


def efficiency_metrics(results: list[WorkflowResult]) -> dict[str, float]:
    """Aggregate processing-efficiency metrics for the dashboard gauge.

    Efficiency is the share of customers whose artifacts passed the quality
    gate on the first pass with zero agent errors — i.e. the pipeline ran
    end-to-end cleanly and automatically.

    Args:
        results: The batch of workflow results.

    Returns:
        A mapping with ``efficiency_pct``, ``avg_latency_ms``,
        ``processed``, ``approved_first_pass`` and ``agent_error_count``.
    """
    total = len(results)
    if total == 0:
        return {
            "efficiency_pct": 0.0,
            "avg_latency_ms": 0.0,
            "processed": 0,
            "approved_first_pass": 0,  # nosec B105 - metric key, not a secret
            "agent_error_count": 0,
        }
    approved = sum(1 for r in results if r.decision.review.status.value == "approve")
    errors = sum(len(t.errors) for r in results for t in r.traces)
    avg_ms = sum(r.total_duration_ms for r in results) / total
    return {
        "efficiency_pct": round(100.0 * approved / total, 1),
        "avg_latency_ms": round(avg_ms, 2),
        "processed": total,
        "approved_first_pass": approved,  # nosec B105 - metric key
        "agent_error_count": errors,
    }


def watchlist(results: list[WorkflowResult], top_n: int = 12) -> list[dict[str, Any]]:
    """Highest-churn-risk customers for the retention priority panel.

    Args:
        results: The batch of workflow results.
        top_n: Maximum number of customers to return.

    Returns:
        Rows sorted by churn probability (descending).
    """
    ranked = sorted(
        results,
        key=lambda r: r.decision.behavior.churn_probability,
        reverse=True,
    )
    return [
        {
            "customer_id": r.decision.customer_id,
            "churn_probability": r.decision.behavior.churn_probability,
            "risk_level": r.decision.behavior.risk_level.value,
            "action": r.decision.action.value,
            "clv": r.decision.value.customer_lifetime_value,
        }
        for r in ranked[:top_n]
    ]

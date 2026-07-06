"""Unit tests for reporting helpers and the mapping approval gateway."""

from __future__ import annotations

import asyncio
from pathlib import Path

from customer_retention.application.reporting import (
    build_table,
    pending_approvals,
    result_to_row,
    summarize,
)
from customer_retention.application.workflow import RetentionWorkflow
from customer_retention.domain.contracts import OfferProposal, ValueReport
from customer_retention.domain.enums import ApprovalStatus, ImportanceLevel
from customer_retention.infrastructure.data_loader import load_customers
from customer_retention.tools.human_in_the_loop import MappingApprovalGateway

_RES = Path(__file__).resolve().parents[2] / "src" / "customer_retention" / "resources"


def _offer(customer_id: str, cost: float) -> OfferProposal:
    return OfferProposal(
        customer_id=customer_id,
        offer_id="OFF-P",
        offer_name="premium",
        cost=cost,
        discount_pct=30.0,
        expected_benefit=cost * 2,
        roi=2.0,
        requires_approval=True,
        rationale="test",
    )


def _value(customer_id: str) -> ValueReport:
    return ValueReport(
        customer_id=customer_id,
        customer_lifetime_value=900.0,
        expected_value=400.0,
        cost_of_loss=500.0,
        importance_level=ImportanceLevel.GOLD,
        segment="gold-new",
    )


def test_mapping_gateway_returns_default_when_undecided() -> None:
    """Unknown customers get the safe default (rejected) and are recorded."""
    gateway = MappingApprovalGateway(decisions={}, default=ApprovalStatus.REJECTED)
    status = gateway.request_approval(_offer("X", 250.0), _value("X"))
    assert status is ApprovalStatus.REJECTED
    assert len(gateway.requests) == 1


def test_mapping_gateway_honours_explicit_decision() -> None:
    """An explicit human decision overrides the default."""
    gateway = MappingApprovalGateway(
        decisions={"Y": ApprovalStatus.APPROVED}, default=ApprovalStatus.REJECTED
    )
    assert gateway.request_approval(_offer("Y", 250.0), _value("Y")) is ApprovalStatus.APPROVED


def test_reporting_row_and_summary_are_consistent() -> None:
    """build_table and summarize agree on the customer count."""
    records = load_customers(_RES / "sample_customers.csv")
    workflow = RetentionWorkflow.from_paths(policy_path=_RES / "politica_retencion.md")
    results = asyncio.run(workflow.run_batch(records))

    table = build_table(results)
    summary = summarize(results)
    assert len(table) == summary["total_customers"] == len(records)
    assert set(result_to_row(results[0])) >= {"customer_id", "action", "roi"}
    # Pending approvals helper never raises and returns a list.
    assert isinstance(pending_approvals(results), list)

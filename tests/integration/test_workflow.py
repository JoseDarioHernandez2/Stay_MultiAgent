"""Integration tests for the end-to-end multi-agent workflow."""

from __future__ import annotations

import asyncio
from pathlib import Path

from customer_retention.application.workflow import RetentionWorkflow
from customer_retention.domain.contracts import CustomerRecord, WorkflowResult
from customer_retention.domain.enums import ApprovalStatus, DecisionAction, ReviewStatus
from customer_retention.infrastructure.data_loader import load_customers
from customer_retention.tools.human_in_the_loop import ApprovalGateway

_RES = Path(__file__).resolve().parents[2] / "src" / "customer_retention" / "resources"


class _RejectAllGateway:
    """Gateway that always rejects, to exercise the rejection branch."""

    def request_approval(self, offer, value) -> ApprovalStatus:  # noqa: ANN001, D102
        return ApprovalStatus.REJECTED


def test_workflow_runs_all_agents_and_gates(policy_free=None) -> None:
    """Every customer gets four agent traces and a reviewed decision."""
    records = load_customers(_RES / "sample_customers.csv")
    workflow = RetentionWorkflow.from_paths(policy_path=_RES / "politica_retencion.md")
    results = asyncio.run(workflow.run_batch(records))

    assert len(results) == len(records)
    for result in results:
        assert isinstance(result, WorkflowResult)
        traced = {t.agent_name for t in result.traces}
        assert {"behavior-analyst", "value-analyst", "offer-specialist", "reviewer"} <= traced
        # Quality gate always ran.
        assert result.decision.review.status in set(ReviewStatus)


def test_expensive_offer_triggers_human_in_the_loop() -> None:
    """A premium offer above threshold requests HITL and can be rejected."""
    record = CustomerRecord(
        customer_id="RISK",
        tenure_months=1,
        monthly_charges=120.0,
        total_charges=120.0,
        contract_type="month-to-month",
        support_calls=6,
        complaints=3,
        is_active=False,
    )
    gateway: ApprovalGateway = _RejectAllGateway()
    workflow = RetentionWorkflow.from_paths(
        policy_path=_RES / "politica_retencion.md", approval_gateway=gateway
    )
    result = asyncio.run(workflow.run_one(record))
    decision = result.decision
    assert decision.approval_status is ApprovalStatus.REJECTED
    # A rejected approval must not end in retain_with_offer.
    assert decision.action is DecisionAction.MONITOR
    # The proposed offer is kept for auditability but is not executed.
    assert decision.offer is not None
    assert decision.offer.requires_approval is True


def test_workflow_output_is_json_serialisable() -> None:
    """The full result serialises to JSON without errors."""
    records = load_customers(_RES / "sample_customers.csv")
    workflow = RetentionWorkflow.from_paths(policy_path=_RES / "politica_retencion.md")
    results = asyncio.run(workflow.run_batch(records))
    payload = [r.as_dict() for r in results]
    assert payload and "decision" in payload[0] and "traces" in payload[0]

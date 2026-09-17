"""Unit tests: audit gateway, alert reports and recommendations engine."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from customer_retention.application.recommendations import (
    RuleBasedRecommendationEngine,
    build_recommendation_engine,
)
from customer_retention.application.reporting import alerted_rows, efficiency_metrics, watchlist
from customer_retention.application.workflow import RetentionWorkflow
from customer_retention.domain.contracts import CustomerRecord
from customer_retention.domain.enums import ApprovalStatus, DecisionAction
from customer_retention.infrastructure.report_builder import build_alert_report
from customer_retention.tools.human_in_the_loop import AuditApprovalGateway

_RES = Path(__file__).resolve().parents[2] / "src" / "customer_retention" / "resources"


def _high_risk_record(customer_id: str = "AUD-1") -> CustomerRecord:
    """A customer that triggers a premium (expensive) offer."""
    return CustomerRecord(
        customer_id=customer_id,
        tenure_months=1,
        monthly_charges=120.0,
        total_charges=120.0,
        contract_type="month-to-month",
        support_calls=6,
        complaints=3,
        is_active=False,
    )


def _run_audit_batch(records: list[CustomerRecord]):
    """Run the workflow in audit mode over the given records."""
    gateway = AuditApprovalGateway()
    workflow = RetentionWorkflow.from_paths(
        policy_path=_RES / "politica_retencion.md",
        approval_gateway=gateway,
    )
    results = asyncio.run(workflow.run_batch(records))
    return results, gateway


def test_audit_gateway_never_blocks_processing() -> None:
    """Expensive offers are flagged, not blocked: action stays retain."""
    results, gateway = _run_audit_batch([_high_risk_record()])
    decision = results[0].decision
    assert decision.approval_status is ApprovalStatus.FLAGGED_FOR_AUDIT
    assert decision.action is DecisionAction.RETAIN_WITH_OFFER
    assert len(gateway.alerts) == 1


def test_alerted_rows_match_gateway_alerts() -> None:
    """Reporting surfaces exactly the flagged customers."""
    records = [_high_risk_record(f"AUD-{i}") for i in range(3)]
    results, gateway = _run_audit_batch(records)
    rows = alerted_rows(results)
    assert len(rows) == len(gateway.alerts) == 3
    assert {r["customer_id"] for r in rows} == {"AUD-0", "AUD-1", "AUD-2"}
    assert all("offer_cost" in r and "roi" in r for r in rows)


def test_alert_report_builds_in_all_three_formats() -> None:
    """JSON, XLSX and PDF reports all produce non-empty valid bytes."""
    results, _ = _run_audit_batch([_high_risk_record()])
    rows = alerted_rows(results)

    json_bytes = build_alert_report(rows, "json")
    parsed = json.loads(json_bytes.decode("utf-8"))
    assert parsed["alert_count"] == 1

    xlsx_bytes = build_alert_report(rows, "xlsx")
    assert xlsx_bytes[:2] == b"PK"  # zip container signature

    pdf_bytes = build_alert_report(rows, "pdf")
    assert pdf_bytes[:5] == b"%PDF-"


def test_alert_report_rejects_unknown_format() -> None:
    """An unsupported format raises ValueError."""
    try:
        build_alert_report([], "docx")
    except ValueError:
        return
    raise AssertionError("expected ValueError for unsupported format")


def test_efficiency_metrics_and_watchlist() -> None:
    """Efficiency and watchlist aggregate correctly over the batch."""
    records = [_high_risk_record(f"AUD-{i}") for i in range(4)]
    results, _ = _run_audit_batch(records)

    eff = efficiency_metrics(results)
    assert eff["processed"] == 4
    assert 0.0 <= eff["efficiency_pct"] <= 100.0
    assert eff["agent_error_count"] == 0

    top = watchlist(results, top_n=2)
    assert len(top) == 2
    assert top[0]["churn_probability"] >= top[1]["churn_probability"]


def test_rule_engine_returns_max_five_grounded_bullets() -> None:
    """The rule engine emits at most 5 non-empty recommendations."""
    records = [_high_risk_record(f"AUD-{i}") for i in range(5)]
    results, _ = _run_audit_batch(records)
    bullets = RuleBasedRecommendationEngine().recommend(results)
    assert 1 <= len(bullets) <= 5
    assert all(isinstance(b, str) and b for b in bullets)


def test_rule_engine_handles_empty_batch() -> None:
    """An empty batch yields a graceful single message."""
    bullets = RuleBasedRecommendationEngine().recommend([])
    assert len(bullets) == 1


def test_factory_defaults_to_rule_engine() -> None:
    """The factory returns the rule engine when Ollama is disabled."""
    engine = build_recommendation_engine(use_ollama=False)
    assert engine.name == "rule-based-insights-v1"

"""Unit tests for the retention policy loader."""

from __future__ import annotations

from pathlib import Path

from customer_retention.application.policy import RetentionPolicy, load_policy


def test_default_policy_values() -> None:
    """The default policy exposes the documented thresholds."""
    policy = RetentionPolicy.default()
    assert policy.approval_cost_threshold == 200.0
    assert policy.max_offer_cost == 500.0
    assert policy.max_discount_pct == 40.0


def test_missing_policy_falls_back_to_default() -> None:
    """A missing policy file yields defaults, not an error."""
    assert load_policy(None) == RetentionPolicy.default()


def test_policy_parses_thresholds_from_markdown(tmp_path: Path) -> None:
    """Numeric thresholds are parsed from markdown when present."""
    md = tmp_path / "policy.md"
    md.write_text(
        "El costo maximo de una oferta es 750.\n"
        "Las ofertas que superen el umbral de aprobacion de 300 requieren aprobacion.\n",
        encoding="utf-8",
    )
    policy = load_policy(md)
    assert policy.max_offer_cost == 750.0
    assert policy.approval_cost_threshold == 300.0

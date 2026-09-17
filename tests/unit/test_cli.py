"""Tests for the CLI entry point (customer_retention.cli)."""

from __future__ import annotations

import json
from pathlib import Path

from customer_retention.cli import main


def test_cli_main_returns_zero(tmp_path: Path) -> None:
    """main() runs the workflow over the sample dataset and exits 0."""
    out_file = tmp_path / "report.json"
    exit_code = main(["--quiet", "--out", str(out_file)])
    assert exit_code == 0
    assert out_file.exists()


def test_cli_produces_valid_json(tmp_path: Path) -> None:
    """The JSON report contains the expected top-level keys."""
    out_file = tmp_path / "report.json"
    main(["--quiet", "--out", str(out_file)])
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert "customers" in data
    assert "results" in data
    assert data["customers"] == len(data["results"])


def test_cli_report_has_traces_and_decisions(tmp_path: Path) -> None:
    """Every result entry has decision, traces and total_duration_ms."""
    out_file = tmp_path / "report.json"
    main(["--quiet", "--out", str(out_file)])
    data = json.loads(out_file.read_text(encoding="utf-8"))
    for result in data["results"]:
        assert "decision" in result
        assert "traces" in result
        # Each customer went through all 4 agents
        agent_names = {t["agent_name"] for t in result["traces"]}
        assert {"behavior-analyst", "value-analyst", "offer-specialist", "reviewer"} <= agent_names


def test_cli_stdout_when_no_out(capsys) -> None:
    """When --out is omitted, the report goes to stdout."""
    exit_code = main(["--quiet"])
    assert exit_code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["customers"] > 0

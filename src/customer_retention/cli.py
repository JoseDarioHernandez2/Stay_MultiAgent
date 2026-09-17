"""Command-line entry point for ``retention-workflow``.

This thin module exists so that ``pyproject.toml`` can declare a proper
console-script entry point (``retention-workflow = "customer_retention.cli:main"``).
It delegates all logic to :mod:`customer_retention.application.workflow` and
the helper functions in ``scripts/run_workflow.py``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from customer_retention.application.workflow import RetentionWorkflow
from customer_retention.infrastructure.data_loader import load_customers
from customer_retention.infrastructure.logging_config import configure_logging
from customer_retention.tools.human_in_the_loop import (
    AutoApprovalGateway,
    ConsoleApprovalGateway,
)

_LOGGER = logging.getLogger("retention-workflow")
_RES = Path(__file__).resolve().parent / "resources"
_DEFAULT_CSV = _RES / "sample_customers.csv"
_DEFAULT_POLICY = _RES / "politica_retencion.md"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Customer retention multi-agent workflow.",
    )
    parser.add_argument("--csv", default=str(_DEFAULT_CSV), help="Path to customers CSV.")
    parser.add_argument("--policy", default=str(_DEFAULT_POLICY), help="Path to policy markdown.")
    parser.add_argument("--model", default=None, help="Path to churn model (.py or .pkl).")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Use console-based Human-in-the-Loop approval.",
    )
    parser.add_argument("--out", default=None, help="Write JSON report to this file.")
    parser.add_argument("--quiet", action="store_true", help="Suppress structured logs.")
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    records = load_customers(args.csv)
    gateway = ConsoleApprovalGateway() if args.interactive else AutoApprovalGateway()
    workflow = RetentionWorkflow.from_paths(
        policy_path=args.policy, model_path=args.model, approval_gateway=gateway
    )
    results = await workflow.run_batch(records)
    return {
        "customers": len(results),
        "results": [r.as_dict() for r in results],
    }


def main(argv: list[str] | None = None) -> int:
    """Program entry point callable by the console-script wrapper.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv``).

    Returns:
        Process exit code (``0`` on success).
    """
    args = _parse_args(argv)
    if not args.quiet:
        configure_logging()
    report = asyncio.run(_run(args))
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
        _LOGGER.info("Report written to %s", args.out)
    else:
        print(payload)  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

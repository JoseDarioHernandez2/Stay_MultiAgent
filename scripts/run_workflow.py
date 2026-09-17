#!/usr/bin/env python3
"""Command-line entry point for the customer-retention workflow.

Runs the multi-agent pipeline over a CSV of customers and prints a JSON report
(decisions + traces). Designed to be invoked by the plugin runner, by Docker,
or directly from the shell.

Example:
    python scripts/run_workflow.py \
        --csv challenges/session7/churn/customers.csv \
        --policy challenges/session7/churn/politica_retencion.md \
        --model challenges/session7/model_base.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

# Make ``src`` importable when run as a plain script.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# pylint: disable=wrong-import-position

from customer_retention.application.workflow import RetentionWorkflow  # noqa: E402
from customer_retention.infrastructure.data_loader import load_customers  # noqa: E402
from customer_retention.infrastructure.logging_config import configure_logging  # noqa: E402
from customer_retention.tools.human_in_the_loop import (  # noqa: E402
    AutoApprovalGateway,
    ConsoleApprovalGateway,
)

_LOGGER = logging.getLogger("run_workflow")
_DEFAULT_CSV = _SRC / "customer_retention" / "resources" / "sample_customers.csv"
_DEFAULT_POLICY = _SRC / "customer_retention" / "resources" / "politica_retencion.md"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Customer retention multi-agent workflow.")
    parser.add_argument("--csv", default=str(_DEFAULT_CSV), help="Path to customers.csv.")
    parser.add_argument("--policy", default=str(_DEFAULT_POLICY), help="Path to policy .md.")
    parser.add_argument("--model", default=None, help="Path to base model .py (optional).")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Use the console Human-in-the-Loop approval gateway.",
    )
    parser.add_argument("--out", default=None, help="Write the JSON report to this path.")
    parser.add_argument("--quiet", action="store_true", help="Suppress structured logs.")
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    """Execute the workflow and return a serialisable report."""
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
    """Program entry point.

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
        _LOGGER.info("report written to %s", args.out)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

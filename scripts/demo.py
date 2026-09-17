#!/usr/bin/env python3
"""Interactive demo of the customer-retention multi-agent workflow.

Runs the pipeline over the bundled sample dataset and prints a rich,
colour-coded summary designed for live presentations and seminars.

Usage:
    python scripts/demo.py                  # auto-approval (non-interactive)
    python scripts/demo.py --interactive    # console Human-in-the-Loop
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

# Make ``src`` importable when run as a plain script.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# pylint: disable=wrong-import-position
from customer_retention.application.workflow import RetentionWorkflow  # noqa: E402
from customer_retention.infrastructure.data_loader import load_customers  # noqa: E402
from customer_retention.tools.human_in_the_loop import (  # noqa: E402
    AutoApprovalGateway,
    ConsoleApprovalGateway,
)

# ── ANSI helpers ─────────────────────────────────────────────────────────────
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
BLUE = "\033[94m"
WHITE = "\033[97m"

AGENT_COLOURS = {
    "behavior-analyst": CYAN,
    "value-analyst": MAGENTA,
    "offer-specialist": YELLOW,
    "reviewer": GREEN,
}

_RES = _SRC / "customer_retention" / "resources"
_DEFAULT_CSV = _RES / "sample_customers.csv"
_DEFAULT_POLICY = _RES / "politica_retencion.md"

LINE = f"{DIM}{'─' * 72}{RESET}"


def _banner() -> None:
    print(
        f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════════╗
║       CUSTOMER RETENTION — MULTI-AGENT WORKFLOW DEMO             ║
║       Equipo 2 · Seminario Modelos Multiagentes                  ║
╚══════════════════════════════════════════════════════════════════╝{RESET}
"""
    )


def _section(title: str) -> None:
    print(f"\n{BOLD}{BLUE}▸ {title}{RESET}")
    print(LINE)


def _print_traces(traces: list[dict]) -> None:
    """Print agent traces with colour and timing."""
    for t in traces:
        name = t.get("agent_name", "unknown")
        colour = AGENT_COLOURS.get(name, WHITE)
        ms = t.get("duration_ms", 0)
        status = t.get("status", "?")
        icon = "✓" if status == "success" else "✗"
        status_colour = GREEN if status == "success" else RED

        print(
            f"  {colour}{BOLD}{name:<20}{RESET} "
            f"{status_colour}{icon}{RESET}  "
            f"{DIM}{ms:>6.0f} ms{RESET}"
        )

        # Show output_summary if present
        summary = t.get("output_summary", "")
        if summary:
            # Truncate long summaries for readability
            short = summary[:90] + "…" if len(summary) > 90 else summary
            print(f"    {DIM}{short}{RESET}")


def _action_colour(action: str) -> str:
    a = action.lower()
    if "retain" in a or "accept" in a:
        return GREEN
    if "reject" in a or "escalat" in a:
        return RED
    return YELLOW


def _print_decision(decision: dict) -> None:
    """Print the WorkflowDecision with key details."""
    action = decision.get("action", "unknown")
    a_colour = _action_colour(action)
    approval = decision.get("approval_status", "?")

    # Behavior
    behavior = decision.get("behavior", {})
    risk = behavior.get("risk_level", "?")
    churn_prob = behavior.get("churn_probability")

    # Value
    value = decision.get("value", {})
    clv = value.get("customer_lifetime_value")
    importance = value.get("importance_level", "?")
    segment = value.get("segment", "?")

    # Offer
    offer = decision.get("offer")
    offer_name = offer.get("offer_name", "none") if offer else "none"
    offer_cost = offer.get("cost") if offer else None
    offer_roi = offer.get("roi") if offer else None
    requires_approval = offer.get("requires_approval", False) if offer else False

    # Review
    review = decision.get("review", {})
    review_status = review.get("status", "?")
    checks = review.get("checks", [])
    passed_checks = sum(1 for c in checks if c.get("passed"))

    print(f"    {DIM}Action        :{RESET} {a_colour}{BOLD}{action}{RESET}")
    print(f"    {DIM}Approval      :{RESET} {approval}")
    if churn_prob is not None:
        print(f"    {DIM}Churn prob    :{RESET} {churn_prob:.1%}  ({risk})")
    if clv is not None:
        print(f"    {DIM}CLV           :{RESET} ${clv:,.0f}  [{importance} · {segment}]")
    if offer:
        cost_str = f"${offer_cost:,.0f}" if offer_cost is not None else "?"
        roi_str = f"{offer_roi:.1f}x" if offer_roi is not None else "?"
        approval_flag = f"  {RED}⚠ requires approval{RESET}" if requires_approval else ""
        print(
            f"    {DIM}Offer         :{RESET} {offer_name}  "
            f"(cost: {cost_str}, ROI: {roi_str}){approval_flag}"
        )
    print(
        f"    {DIM}Quality gate  :{RESET} {review_status}  "
        f"({passed_checks}/{len(checks)} checks passed)"
    )

    # Summary
    summary = decision.get("summary", "")
    if summary:
        short = summary[:100] + "…" if len(summary) > 100 else summary
        print(f"    {DIM}Summary       :{RESET} {short}")


async def _run_demo(interactive: bool = False) -> None:
    _banner()

    # ── 1. Load data ─────────────────────────────────────────────────────
    _section("1 · Loading sample customers")
    records = load_customers(str(_DEFAULT_CSV))
    print(f"  Loaded {BOLD}{len(records)}{RESET} customer records from sample dataset")

    # ── 2. Build workflow ────────────────────────────────────────────────
    _section("2 · Building workflow")
    gateway = ConsoleApprovalGateway() if interactive else AutoApprovalGateway()
    mode_label = "Console HITL (interactive)" if interactive else "Auto-approval"
    workflow = RetentionWorkflow.from_paths(
        policy_path=str(_DEFAULT_POLICY), approval_gateway=gateway
    )
    print(f"  Approval gateway : {BOLD}{mode_label}{RESET}")
    print("  Policy           : politica_retencion.md")
    print("  Agents           : behavior-analyst, value-analyst, " "offer-specialist, reviewer")
    print(f"  Parallelism      : {GREEN}behavior + CLV via " f"asyncio.gather{RESET}")

    # ── 3. Execute ───────────────────────────────────────────────────────
    _section("3 · Running multi-agent pipeline")
    print(f"  {DIM}Processing {len(records)} customers …{RESET}")
    t0 = time.perf_counter()
    results = await workflow.run_batch(records)
    elapsed = (time.perf_counter() - t0) * 1000
    print(f"  {GREEN}✓ Pipeline complete in {elapsed:,.0f} ms{RESET}")

    # ── 4. Per-customer results ──────────────────────────────────────────
    _section("4 · Results per customer")
    all_dicts = []
    for r in results:
        rd = r.as_dict()
        all_dicts.append(rd)
        decision = rd.get("decision", {})
        cid = decision.get("customer_id", "?")
        action = decision.get("action", "?")
        a_colour = _action_colour(action)
        total_ms = rd.get("total_duration_ms", 0)

        print(
            f"\n  {BOLD}{WHITE}Customer {cid}{RESET}  →  "
            f"{a_colour}{BOLD}{action}{RESET}  "
            f"{DIM}({total_ms:.0f} ms){RESET}"
        )

        # Agent traces
        traces = rd.get("traces", [])
        _print_traces(traces)

        # Decision details
        _print_decision(decision)

    # ── 5. Summary ───────────────────────────────────────────────────────
    _section("5 · Summary")
    actions = [d.get("decision", {}).get("action", "").lower() for d in all_dicts]
    retained = sum(1 for a in actions if "retain" in a or "accept" in a)
    rejected = sum(1 for a in actions if "reject" in a or "escalat" in a)
    other = len(actions) - retained - rejected

    print(f"  Total customers  : {BOLD}{len(results)}{RESET}")
    print(f"  {GREEN}Retained{RESET}         : {BOLD}{retained}{RESET}")
    if rejected:
        print(f"  {RED}Rejected/Escalated{RESET}: {BOLD}{rejected}{RESET}")
    if other:
        print(f"  {YELLOW}Other{RESET}            : {BOLD}{other}{RESET}")
    print(f"  Total time       : {BOLD}{elapsed:,.0f} ms{RESET}")
    print("  Avg per customer : " f"{BOLD}{elapsed / max(len(results), 1):,.0f} ms{RESET}")

    print(f"\n{BOLD}{GREEN}✓ Demo complete.{RESET}\n")


def main() -> int:
    interactive = "--interactive" in sys.argv
    asyncio.run(_run_demo(interactive))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

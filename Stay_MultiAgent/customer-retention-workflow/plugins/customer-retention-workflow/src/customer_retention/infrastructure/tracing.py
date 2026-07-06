"""Execution tracing utilities.

The :class:`TraceRecorder` is a lightweight, per-run collector. It is passed
explicitly to agents (dependency injection) rather than being a global, which
keeps concurrent workflow runs isolated.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from customer_retention.domain.contracts import AgentTrace
from customer_retention.domain.enums import AgentStatus


class TraceSpan:
    """Mutable scratch space filled in while an agent runs."""

    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self.model_used: str = "n/a"
        self.tokens: int = 0
        self.input_summary: str = ""
        self.output_summary: str = ""
        self.status: AgentStatus = AgentStatus.SUCCESS

    def warn(self, message: str) -> None:
        """Record a non-fatal warning."""
        self.warnings.append(message)

    def error(self, message: str) -> None:
        """Record a fatal error and mark the context as failed."""
        self.errors.append(message)
        self.status = AgentStatus.FAILED


class TraceRecorder:
    """Collects :class:`AgentTrace` records for a single workflow run."""

    def __init__(self) -> None:
        self._traces: list[AgentTrace] = []

    @property
    def traces(self) -> list[AgentTrace]:
        """Return an immutable copy of the collected traces."""
        return list(self._traces)

    @contextmanager
    def track(self, agent_name: str) -> Iterator[TraceSpan]:
        """Time an agent execution and persist an :class:`AgentTrace`.

        Args:
            agent_name: Identifier of the executing agent.

        Yields:
            A mutable context the agent can annotate with warnings, tokens,
            model name and summaries.
        """
        ctx = TraceSpan()
        started = datetime.now(timezone.utc)
        start_perf = time.perf_counter()
        try:
            yield ctx
        except Exception as exc:  # noqa: BLE001 - trace then re-raise
            ctx.error(f"{type(exc).__name__}: {exc}")
            raise
        finally:
            duration_ms = (time.perf_counter() - start_perf) * 1000.0
            self._traces.append(
                AgentTrace(
                    agent_name=agent_name,
                    status=ctx.status,
                    started_at=started,
                    finished_at=datetime.now(timezone.utc),
                    duration_ms=round(duration_ms, 3),
                    model_used=ctx.model_used,
                    tokens=ctx.tokens,
                    warnings=ctx.warnings,
                    errors=ctx.errors,
                    input_summary=ctx.input_summary,
                    output_summary=ctx.output_summary,
                )
            )

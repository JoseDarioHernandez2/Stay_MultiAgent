"""Abstract base class shared by every agent."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from customer_retention.infrastructure.tracing import TraceRecorder, TraceSpan

TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


class BaseAgent(ABC, Generic[TInput, TOutput]):
    """Common contract for all retention agents.

    Sub-classes implement :meth:`_execute` with their pure logic. The public
    :meth:`run` wraps that logic in a trace span so every execution is timed
    and recorded uniformly.
    """

    #: Stable, human-readable agent identifier used in traces and logs.
    name: str = "base-agent"
    #: Prompt/model identifier recorded for traceability.
    model_name: str = "deterministic"

    def __init__(self, recorder: TraceRecorder) -> None:
        """Store the per-run trace recorder (dependency injection).

        Args:
            recorder: Collector for this workflow run's traces.
        """
        self._recorder = recorder

    async def run(self, payload: TInput) -> TOutput:
        """Execute the agent within a traced span.

        Args:
            payload: The typed input artifact(s) for this agent.

        Returns:
            The typed output artifact produced by the agent.
        """
        with self._recorder.track(self.name) as ctx:
            ctx.model_used = self.model_name
            ctx.input_summary = self._summarise_input(payload)
            result = await self._execute(payload, ctx)
            ctx.output_summary = self._summarise_output(result)
            return result

    @abstractmethod
    async def _execute(self, payload: TInput, span: TraceSpan) -> TOutput:
        """Run the agent's core logic. Implemented by sub-classes."""

    def _summarise_input(self, payload: TInput) -> str:
        """Return a short, log-safe summary of the input."""
        return type(payload).__name__

    def _summarise_output(self, result: TOutput) -> str:
        """Return a short, log-safe summary of the output."""
        return type(result).__name__

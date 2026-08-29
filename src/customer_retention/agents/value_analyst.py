"""Value Analyst agent: computes economic worth into a ValueReport."""

from __future__ import annotations

import asyncio

from customer_retention.agents.base import BaseAgent
from customer_retention.domain.contracts import CustomerRecord, ValueReport
from customer_retention.domain.enums import ImportanceLevel
from customer_retention.infrastructure.tracing import TraceRecorder, TraceSpan
from customer_retention.prompts.value import SYSTEM_PROMPT
from customer_retention.tools.clv import (
    compute_clv,
    compute_cost_of_loss,
    compute_expected_value,
)


class ValueAnalystAgent(BaseAgent[tuple[CustomerRecord, float], ValueReport]):
    """Quantify Customer Lifetime Value and importance for one customer."""

    name = "value-analyst"

    def __init__(self, recorder: TraceRecorder, high_value_clv: float) -> None:
        """Initialise the agent.

        Args:
            recorder: Per-run trace recorder.
            high_value_clv: CLV threshold above which a customer is high value.
        """
        super().__init__(recorder)
        self._high_value_clv = high_value_clv
        self._prompt = SYSTEM_PROMPT

    async def _execute(self, payload: tuple[CustomerRecord, float], span: TraceSpan) -> ValueReport:
        """Compute CLV-derived metrics and tier the customer."""
        record, churn_probability = payload
        clv = await asyncio.to_thread(compute_clv, record)
        expected = compute_expected_value(clv, churn_probability)
        cost_of_loss = compute_cost_of_loss(clv, churn_probability)
        importance = self._tier(clv)
        return ValueReport(
            customer_id=record.customer_id,
            customer_lifetime_value=clv,
            expected_value=expected,
            cost_of_loss=cost_of_loss,
            importance_level=importance,
            segment=self._segment(importance, record),
        )

    def _tier(self, clv: float) -> ImportanceLevel:
        """Map a CLV to an importance tier."""
        if clv >= self._high_value_clv:
            return ImportanceLevel.PLATINUM
        if clv >= self._high_value_clv * 0.6:
            return ImportanceLevel.GOLD
        if clv >= self._high_value_clv * 0.3:
            return ImportanceLevel.SILVER
        return ImportanceLevel.BRONZE

    @staticmethod
    def _segment(importance: ImportanceLevel, record: CustomerRecord) -> str:
        """Derive a readable segment label."""
        loyalty = "loyal" if record.tenure_months >= 24 else "new"
        return f"{importance.value}-{loyalty}"

    def _summarise_input(self, payload: tuple[CustomerRecord, float]) -> str:
        """Summarise the customer id for the trace."""
        return f"customer={payload[0].customer_id}"

    def _summarise_output(self, result: ValueReport) -> str:
        """Summarise CLV and tier for the trace."""
        return f"clv={result.customer_lifetime_value:.2f} tier={result.importance_level.value}"

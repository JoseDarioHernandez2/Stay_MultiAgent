"""Behavior Analyst agent: turns model output into a BehaviorReport."""

from __future__ import annotations

import asyncio

from customer_retention.agents.base import BaseAgent
from customer_retention.domain.contracts import (
    BehaviorReport,
    CustomerRecord,
    risk_from_probability,
)
from customer_retention.infrastructure.model_adapter import ChurnModelPort
from customer_retention.infrastructure.tracing import TraceRecorder, TraceSpan
from customer_retention.prompts.behavior import SYSTEM_PROMPT


class BehaviorAnalystAgent(BaseAgent[CustomerRecord, BehaviorReport]):
    """Analyse historical behaviour and predict churn for one customer."""

    name = "behavior-analyst"

    def __init__(self, recorder: TraceRecorder, model: ChurnModelPort) -> None:
        """Initialise the agent.

        Args:
            recorder: Per-run trace recorder.
            model: Churn model satisfying :class:`ChurnModelPort`.
        """
        super().__init__(recorder)
        self._model = model
        self.model_name = model.name
        self._prompt = SYSTEM_PROMPT

    async def _execute(self, payload: CustomerRecord, span: TraceSpan) -> BehaviorReport:
        """Score the customer and assemble the BehaviorReport."""
        probability = await asyncio.to_thread(self._model.predict_proba, payload)
        signals = self._detect_signals(payload)
        if not signals:
            span.warn("no explicit behavioural signals detected")
        return BehaviorReport(
            customer_id=payload.customer_id,
            churn_probability=probability,
            risk_level=risk_from_probability(probability),
            signals=signals,
            feature_contributions=self._contributions(payload),
            model_name=self._model.name,
        )

    @staticmethod
    def _detect_signals(record: CustomerRecord) -> list[str]:
        """Extract interpretable churn signals from the record."""
        signals: list[str] = []
        if record.support_calls >= 3:
            signals.append(f"{record.support_calls} recent support calls")
        if record.complaints >= 1:
            signals.append(f"{record.complaints} complaint(s) filed")
        if not record.is_active:
            signals.append("account currently inactive")
        if "month" in record.contract_type.lower():
            signals.append("month-to-month contract")
        if record.tenure_months <= 3:
            signals.append("very short tenure")
        return signals

    @staticmethod
    def _contributions(record: CustomerRecord) -> dict[str, float]:
        """Return a coarse feature-contribution map for explainability."""
        return {
            "support_calls": float(record.support_calls),
            "complaints": float(record.complaints),
            "tenure_months": float(record.tenure_months),
            "inactive": 0.0 if record.is_active else 1.0,
        }

    def _summarise_input(self, payload: CustomerRecord) -> str:
        """Summarise the customer id for the trace."""
        return f"customer={payload.customer_id}"

    def _summarise_output(self, result: BehaviorReport) -> str:
        """Summarise probability and risk for the trace."""
        return f"p={result.churn_probability:.3f} risk={result.risk_level.value}"

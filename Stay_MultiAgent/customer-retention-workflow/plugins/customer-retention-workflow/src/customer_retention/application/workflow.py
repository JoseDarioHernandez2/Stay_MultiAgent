"""High-level workflow facade wiring every component together.

:class:`RetentionWorkflow` is the single public entry point. It builds the
churn model, loads the policy, instantiates the agents with a fresh trace
recorder per customer (so concurrent runs never share memory), delegates to
the :class:`RetentionSupervisor` and returns fully-typed results.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from customer_retention.agents.behavior_analyst import BehaviorAnalystAgent
from customer_retention.agents.offer_specialist import OfferSpecialistAgent
from customer_retention.agents.reviewer import ReviewerAgent
from customer_retention.agents.value_analyst import ValueAnalystAgent
from customer_retention.application.policy import RetentionPolicy, load_policy
from customer_retention.application.supervisor import RetentionSupervisor
from customer_retention.domain.contracts import CustomerRecord, WorkflowResult
from customer_retention.infrastructure.model_adapter import ChurnModelPort, build_churn_model
from customer_retention.infrastructure.tracing import TraceRecorder
from customer_retention.tools.human_in_the_loop import ApprovalGateway, AutoApprovalGateway

_LOGGER = logging.getLogger(__name__)


class RetentionWorkflow:
    """Executable customer-retention multi-agent workflow."""

    def __init__(
        self,
        policy: RetentionPolicy,
        model: ChurnModelPort,
        approval_gateway: ApprovalGateway | None = None,
    ) -> None:
        """Initialise the workflow with its collaborators.

        Args:
            policy: The enterprise retention policy.
            model: The churn model to use.
            approval_gateway: Human-in-the-Loop gateway; defaults to the
                deterministic auto gateway for non-interactive runs.
        """
        self._policy = policy
        self._model = model
        self._approval = approval_gateway or AutoApprovalGateway()

    @classmethod
    def from_paths(
        cls,
        policy_path: str | Path | None = None,
        model_path: str | Path | None = None,
        approval_gateway: ApprovalGateway | None = None,
    ) -> "RetentionWorkflow":
        """Build a workflow from on-disk policy and model artefacts.

        Args:
            policy_path: Path to ``politica_retencion.md`` (optional).
            model_path: Path to ``model_base.py`` (optional).
            approval_gateway: Optional HITL gateway.

        Returns:
            A ready-to-run :class:`RetentionWorkflow`.
        """
        return cls(
            policy=load_policy(policy_path),
            model=build_churn_model(model_path),
            approval_gateway=approval_gateway,
        )

    async def run_one(self, record: CustomerRecord) -> WorkflowResult:
        """Process a single customer end-to-end.

        Args:
            record: The customer to evaluate.

        Returns:
            A :class:`WorkflowResult` with the decision and this run's traces.
        """
        recorder = TraceRecorder()
        supervisor = self._build_supervisor(recorder)
        start = time.perf_counter()
        decision = await supervisor.handle(record)
        elapsed = (time.perf_counter() - start) * 1000.0
        _LOGGER.info(
            "decision ready",
            extra={"customer_id": record.customer_id, "status": decision.action.value},
        )
        return WorkflowResult(
            decision=decision, traces=recorder.traces, total_duration_ms=round(elapsed, 3)
        )

    async def run_batch(self, records: list[CustomerRecord]) -> list[WorkflowResult]:
        """Process many customers concurrently.

        Args:
            records: The customers to evaluate.

        Returns:
            One :class:`WorkflowResult` per input customer, in order.
        """
        return await asyncio.gather(*(self.run_one(r) for r in records))

    def _build_supervisor(self, recorder: TraceRecorder) -> RetentionSupervisor:
        """Instantiate agents bound to a per-run recorder."""
        return RetentionSupervisor(
            behavior=BehaviorAnalystAgent(recorder, self._model),
            value=ValueAnalystAgent(recorder, self._policy.high_value_clv),
            offer=OfferSpecialistAgent(recorder),
            reviewer=ReviewerAgent(recorder),
            policy=self._policy,
            approval_gateway=self._approval,
        )

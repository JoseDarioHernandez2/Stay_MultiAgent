"""Typed artifacts (contracts) exchanged between agents.

Every agent in the workflow receives and returns one of these Pydantic models.
This guarantees that inter-agent communication is *structured* and *validated*
at every hop, which is the backbone of a real multi-agent architecture.

Design notes:
    * Models are immutable-by-convention: agents build a new artifact rather
      than mutating one they received (no shared memory).
    * ``model_config`` enforces strict validation and forbids unexpected keys
      so a hallucinated field is rejected instead of silently ignored.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from customer_retention.domain.enums import (
    AgentStatus,
    ApprovalStatus,
    DecisionAction,
    ImportanceLevel,
    ReviewStatus,
    RiskLevel,
)

_STRICT = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


def _utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class CustomerRecord(BaseModel):
    """Normalised representation of a single customer row from the CSV.

    Unknown numeric columns are preserved in ``features`` so the model
    adapter can consume whatever schema the challenge dataset ships with.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    customer_id: str = Field(..., min_length=1, description="Unique customer id.")
    tenure_months: int = Field(0, ge=0, description="Months as an active customer.")
    monthly_charges: float = Field(0.0, ge=0, description="Recurring monthly revenue.")
    total_charges: float = Field(0.0, ge=0, description="Lifetime charges to date.")
    contract_type: str = Field("unknown", description="Contract modality.")
    support_calls: int = Field(0, ge=0, description="Recent support contacts.")
    complaints: int = Field(0, ge=0, description="Formal complaints filed.")
    is_active: bool = Field(True, description="Whether the customer is still active.")
    features: dict[str, float] = Field(
        default_factory=dict, description="Extra numeric features from the dataset."
    )


class BehaviorReport(BaseModel):
    """Artifact emitted by the Behavior Analyst agent."""

    model_config = _STRICT

    customer_id: str = Field(..., min_length=1)
    churn_probability: float = Field(..., ge=0.0, le=1.0)
    risk_level: RiskLevel
    signals: list[str] = Field(default_factory=list, description="Observed churn signals.")
    feature_contributions: dict[str, float] = Field(default_factory=dict)
    model_name: str = Field(..., min_length=1, description="Predictive model used.")

    @model_validator(mode="after")
    def _risk_matches_probability(self) -> "BehaviorReport":
        """Ensure the reported band is coherent with the probability."""
        expected = risk_from_probability(self.churn_probability)
        if expected is not self.risk_level:
            raise ValueError(
                f"risk_level {self.risk_level} inconsistent with "
                f"probability {self.churn_probability:.3f} (expected {expected})"
            )
        return self


class ValueReport(BaseModel):
    """Artifact emitted by the Value Analyst agent."""

    model_config = _STRICT

    customer_id: str = Field(..., min_length=1)
    customer_lifetime_value: float = Field(..., ge=0.0)
    expected_value: float = Field(..., ge=0.0)
    cost_of_loss: float = Field(..., ge=0.0)
    importance_level: ImportanceLevel
    segment: str = Field(..., min_length=1)


class OfferProposal(BaseModel):
    """Artifact emitted by the Offer Specialist agent."""

    model_config = _STRICT

    customer_id: str = Field(..., min_length=1)
    offer_id: str = Field(..., min_length=1)
    offer_name: str = Field(..., min_length=1)
    cost: float = Field(..., ge=0.0)
    discount_pct: float = Field(..., ge=0.0, le=100.0)
    expected_benefit: float = Field(..., ge=0.0)
    roi: float = Field(..., ge=0.0, description="Benefit/cost ratio; >= 1.0 is break-even.")
    requires_approval: bool = Field(...)
    rationale: str = Field(..., min_length=1)


class ReviewCheck(BaseModel):
    """A single named check produced by the Reviewer."""

    model_config = _STRICT

    name: str = Field(..., min_length=1)
    passed: bool
    detail: str = Field("", description="Explanation when the check fails.")


class ReviewResult(BaseModel):
    """Quality-gate artifact emitted by the Reviewer agent."""

    model_config = _STRICT

    customer_id: str = Field(..., min_length=1)
    status: ReviewStatus
    checks: list[ReviewCheck] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _status_matches_checks(self) -> "ReviewResult":
        """A report cannot be APPROVE while carrying failed checks."""
        failed = [c for c in self.checks if not c.passed]
        if self.status is ReviewStatus.APPROVE and failed:
            raise ValueError("cannot APPROVE with failing checks present")
        return self


class WorkflowDecision(BaseModel):
    """Final consolidated decision produced by the Supervisor."""

    model_config = _STRICT

    customer_id: str = Field(..., min_length=1)
    action: DecisionAction
    approval_status: ApprovalStatus
    behavior: BehaviorReport
    value: ValueReport
    offer: OfferProposal | None = None
    review: ReviewResult
    summary: str = Field(..., min_length=1)
    decided_at: datetime = Field(default_factory=_utcnow)


class AgentTrace(BaseModel):
    """Structured trace record captured for every agent execution."""

    model_config = ConfigDict(extra="forbid")

    agent_name: str
    status: AgentStatus
    started_at: datetime
    finished_at: datetime
    duration_ms: float = Field(..., ge=0.0)
    model_used: str = "n/a"
    tokens: int = Field(0, ge=0)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    input_summary: str = ""
    output_summary: str = ""


class WorkflowResult(BaseModel):
    """Top-level artifact returned by the workflow engine."""

    model_config = ConfigDict(extra="forbid")

    decision: WorkflowDecision
    traces: list[AgentTrace] = Field(default_factory=list)
    total_duration_ms: float = Field(..., ge=0.0)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation of the result."""
        return self.model_dump(mode="json")


# --- shared pure helpers -------------------------------------------------- #


def risk_from_probability(probability: float) -> RiskLevel:
    """Map a churn probability to a :class:`RiskLevel` band.

    Args:
        probability: Churn probability in the closed range ``[0, 1]``.

    Returns:
        The corresponding risk band.

    Raises:
        ValueError: If ``probability`` is outside ``[0, 1]``.
    """
    if not 0.0 <= probability <= 1.0:
        raise ValueError(f"probability out of range: {probability}")
    if probability >= 0.80:
        return RiskLevel.CRITICAL
    if probability >= 0.55:
        return RiskLevel.HIGH
    if probability >= 0.30:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW

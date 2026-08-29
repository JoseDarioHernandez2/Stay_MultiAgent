"""Enumerations shared across the retention domain.

All decision-bearing categorical values live here so that every agent and
validator references a single source of truth (DRY).
"""

from __future__ import annotations

from enum import Enum


class RiskLevel(str, Enum):
    """Churn-risk band derived from the predicted churn probability."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ImportanceLevel(str, Enum):
    """Strategic importance of a customer derived from value analysis."""

    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"


class ReviewStatus(str, Enum):
    """Terminal states the Reviewer (quality gate) can emit."""

    APPROVE = "approve"
    REJECT = "reject"
    NEEDS_REVISION = "needs_revision"


class ApprovalStatus(str, Enum):
    """Result of a Human-in-the-Loop approval or audit request."""

    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    FLAGGED_FOR_AUDIT = "flagged_for_audit"


class DecisionAction(str, Enum):
    """Final retention action consolidated by the Supervisor."""

    RETAIN_WITH_OFFER = "retain_with_offer"
    MONITOR = "monitor"
    NO_ACTION = "no_action"
    ESCALATE = "escalate"


class AgentStatus(str, Enum):
    """Lifecycle status recorded in each agent trace."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"

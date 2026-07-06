"""Domain-specific exception hierarchy.

A narrow, explicit hierarchy lets the workflow distinguish *recoverable*
validation problems (which the Reviewer can turn into ``NEEDS_REVISION``)
from *fatal* configuration problems that must abort the run.
"""

from __future__ import annotations


class RetentionError(Exception):
    """Base class for every error raised inside the retention domain."""


class ContractValidationError(RetentionError):
    """Raised when an artifact fails schema/type validation."""


class BusinessRuleError(RetentionError):
    """Raised when a business invariant is violated (e.g. negative CLV)."""


class PolicyError(RetentionError):
    """Raised when the retention policy cannot be loaded or is inconsistent."""


class DataError(RetentionError):
    """Raised when the source dataset is missing required columns or rows."""


class AgentExecutionError(RetentionError):
    """Raised when an agent fails irrecoverably during execution."""

    def __init__(self, agent_name: str, message: str) -> None:
        """Initialise the error.

        Args:
            agent_name: Human-readable identifier of the failing agent.
            message: Detailed cause of the failure.
        """
        self.agent_name = agent_name
        super().__init__(f"[{agent_name}] {message}")


class ApprovalRejectedError(RetentionError):
    """Raised when a required Human-in-the-Loop approval is denied."""

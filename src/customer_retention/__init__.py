"""customer-retention-workflow: enterprise multi-agent churn retention plugin.

Public API re-exports the workflow facade and the primary artifacts so callers
can ``from customer_retention import RetentionWorkflow``.
"""

from customer_retention.application.workflow import RetentionWorkflow
from customer_retention.domain.contracts import (
    CustomerRecord,
    WorkflowDecision,
    WorkflowResult,
)

__all__ = [
    "RetentionWorkflow",
    "CustomerRecord",
    "WorkflowDecision",
    "WorkflowResult",
]

__version__ = "1.0.0"

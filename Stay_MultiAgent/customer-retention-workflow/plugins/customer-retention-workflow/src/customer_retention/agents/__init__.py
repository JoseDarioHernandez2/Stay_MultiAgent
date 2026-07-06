"""Independent, single-responsibility agents.

Each agent is a standalone entity with its own prompt, inputs, outputs,
validations and trace. Agents never share memory: they communicate strictly
through typed artifacts passed by the Supervisor.
"""

from customer_retention.agents.behavior_analyst import BehaviorAnalystAgent
from customer_retention.agents.offer_specialist import OfferSpecialistAgent
from customer_retention.agents.reviewer import ReviewerAgent
from customer_retention.agents.value_analyst import ValueAnalystAgent

__all__ = [
    "BehaviorAnalystAgent",
    "ValueAnalystAgent",
    "OfferSpecialistAgent",
    "ReviewerAgent",
]

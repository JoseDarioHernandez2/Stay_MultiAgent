"""Domain layer: pure business models, enums and errors.

This package has **no** dependency on infrastructure (pandas, files, LLMs).
It defines the typed artifacts every agent must emit and consume so that
inter-agent communication is always structured, never free text.
"""

from customer_retention.domain import contracts, enums, exceptions

__all__ = ["contracts", "enums", "exceptions"]

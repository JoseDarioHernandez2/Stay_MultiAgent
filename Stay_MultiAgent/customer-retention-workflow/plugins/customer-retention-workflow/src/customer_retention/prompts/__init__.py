"""Per-agent prompt specifications.

Each module holds the independent prompt for one agent: role, context,
constraints, strict output contract, evaluation criteria, worked examples and
guardrails. Prompts are kept separate from agent logic (single responsibility)
so they can be versioned and audited on their own.
"""

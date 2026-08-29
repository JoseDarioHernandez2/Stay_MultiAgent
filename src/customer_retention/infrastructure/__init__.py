"""Infrastructure layer: adapters to files, datasets, models and logging.

Everything that touches the outside world (disk, pandas, an LLM, the base
churn model) lives here so the domain and agents stay pure and testable.
"""

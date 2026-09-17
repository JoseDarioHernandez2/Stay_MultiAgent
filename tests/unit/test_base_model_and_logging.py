"""Tests for base-model loading and structured logging."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from customer_retention.domain.contracts import CustomerRecord
from customer_retention.infrastructure.logging_config import JsonFormatter, configure_logging
from customer_retention.infrastructure.model_adapter import BaseModelAdapter, build_churn_model

_MODEL_SRC = '''\
def predict_proba(features):
    """Toy model: churn rises with support calls."""
    return min(1.0, 0.1 + 0.2 * float(features.get("support_calls", 0)))
'''


def test_build_model_uses_base_model_file(tmp_path: Path) -> None:
    """A valid model_base.py is wrapped by BaseModelAdapter."""
    model_file = tmp_path / "model_base.py"
    model_file.write_text(_MODEL_SRC, encoding="utf-8")
    model = build_churn_model(model_file)
    assert isinstance(model, BaseModelAdapter)
    record = CustomerRecord(customer_id="c", support_calls=3)
    prob = model.predict_proba(record)
    assert 0.0 <= prob <= 1.0
    assert "model_base" in model.name


def test_json_formatter_emits_valid_json() -> None:
    """The JSON formatter renders a parseable single-line document."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    payload = json.loads(formatter.format(record))
    assert payload["message"] == "hello"
    assert payload["level"] == "INFO"


def test_configure_logging_is_idempotent() -> None:
    """configure_logging installs exactly one handler when called twice."""
    configure_logging()
    configure_logging()
    assert len(logging.getLogger().handlers) == 1

"""Adapter that exposes the base churn model behind a stable port.

The challenge ships ``challenges/session7/model_base.py``. Its exact API is
not fixed, so this adapter probes for the most common conventions
(``predict_proba`` / ``predict`` on a class or module) and wires them behind
the :class:`ChurnModelPort` protocol. When the base model cannot be located
or invoked, a fully deterministic :class:`HeuristicChurnModel` is used so the
workflow always runs — a graceful-degradation strategy suitable for demos and
CI while still preferring the real model in production.
"""

from __future__ import annotations

import importlib.util
import logging
import math
from pathlib import Path
from types import ModuleType
from typing import Callable, Protocol, cast, runtime_checkable

from customer_retention.domain.contracts import CustomerRecord

_LOGGER = logging.getLogger(__name__)


@runtime_checkable
class ChurnModelPort(Protocol):
    """Port every churn model implementation must satisfy."""

    name: str

    def predict_proba(self, record: CustomerRecord) -> float:
        """Return the churn probability in ``[0, 1]`` for one customer."""


class HeuristicChurnModel:
    """Deterministic logistic-style fallback churn scorer.

    The score combines interpretable risk drivers (support pressure, tenure,
    complaints, inactivity) through a logistic squashing function. It is not a
    trained model — it exists so the pipeline is always executable and its
    output is reproducible in tests.
    """

    name = "heuristic-churn-v1"

    def predict_proba(self, record: CustomerRecord) -> float:
        """Score a customer's churn probability.

        Args:
            record: The customer to score.

        Returns:
            A churn probability in the closed interval ``[0, 1]``.
        """
        tenure_penalty = -0.04 * min(record.tenure_months, 60)
        support_pressure = 0.35 * record.support_calls
        complaint_pressure = 0.55 * record.complaints
        inactivity = 1.6 if not record.is_active else 0.0
        month_to_month = 0.6 if "month" in record.contract_type.lower() else 0.0
        logit = (
            -1.2
            + tenure_penalty
            + support_pressure
            + complaint_pressure
            + inactivity
            + month_to_month
        )
        return round(1.0 / (1.0 + math.exp(-logit)), 6)


class BaseModelAdapter:
    """Wrap the challenge's ``model_base.py`` behind :class:`ChurnModelPort`."""

    def __init__(self, callable_: Callable[[dict[str, float]], float], name: str) -> None:
        """Store the resolved prediction callable.

        Args:
            callable_: A function taking a feature mapping and returning a
                churn probability (or a value coercible to one).
            name: Human-readable model identifier for traceability.
        """
        self._callable = callable_
        self.name = name

    def predict_proba(self, record: CustomerRecord) -> float:
        """Delegate scoring to the wrapped base model."""
        features = {
            "tenure_months": record.tenure_months,
            "monthly_charges": record.monthly_charges,
            "total_charges": record.total_charges,
            "support_calls": record.support_calls,
            "complaints": record.complaints,
            "is_active": int(record.is_active),
            **record.features,
        }
        raw = self._callable(features)
        value = float(raw)
        return max(0.0, min(1.0, value))


def _load_module(model_path: Path) -> ModuleType | None:
    """Import ``model_base.py`` as an isolated module, or return ``None``."""
    if not model_path.exists():
        return None
    spec = importlib.util.spec_from_file_location("challenge_model_base", model_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        _LOGGER.warning("could not import base model: %s", exc)
        return None
    return module


def _resolve_callable(module: ModuleType) -> tuple[Callable[..., object], str] | None:
    """Find a usable prediction callable inside the imported module."""
    for attr in ("predict_proba", "predict", "score"):
        func = getattr(module, attr, None)
        if callable(func):
            return func, f"model_base.{attr}"
    for cls_name in ("ChurnModel", "Model", "BaseModel", "Classifier"):
        cls = getattr(module, cls_name, None)
        if isinstance(cls, type):
            instance = cls()
            for attr in ("predict_proba", "predict", "score"):
                method = getattr(instance, attr, None)
                if callable(method):
                    return method, f"model_base.{cls_name}.{attr}"
    return None


def build_churn_model(model_path: str | Path | None = None) -> ChurnModelPort:
    """Return the best available churn model.

    Args:
        model_path: Optional path to the challenge ``model_base.py``. When
            omitted or unusable, the heuristic fallback is returned.

    Returns:
        An object satisfying :class:`ChurnModelPort`.
    """
    if model_path is not None:
        module = _load_module(Path(model_path))
        if module is not None:
            resolved = _resolve_callable(module)
            if resolved is not None:
                func, name = resolved
                _LOGGER.info("using base churn model: %s", name)
                typed_func = cast(Callable[[dict[str, float]], float], func)
                return BaseModelAdapter(typed_func, name)
        _LOGGER.warning("falling back to heuristic model (base model unusable)")
    return HeuristicChurnModel()


def build_churn_model_from_any(
    source: str | None,
) -> "ChurnModelPort":
    """Build a churn model from a pkl file, a .py script, or the heuristic.

    Args:
        source: Path to a ``.pkl`` file, a ``model_base.py`` script, or
            ``None`` / empty string to use the built-in heuristic.

    Returns:
        An object satisfying :class:`ChurnModelPort`.
    """
    if not source:
        return HeuristicChurnModel()
    src_path = Path(source)
    if src_path.suffix.lower() == ".pkl":
        # lazy import to keep model_adapter free of sklearn at import time
        # pylint: disable=import-outside-toplevel
        from customer_retention.infrastructure.model_trainer import PickleModelAdapter

        return PickleModelAdapter(src_path)
    return build_churn_model(src_path)

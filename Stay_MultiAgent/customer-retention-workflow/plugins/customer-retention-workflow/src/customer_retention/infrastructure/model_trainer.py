"""Train, evaluate and persist a scikit-learn churn classifier.

This module is the bridge between a labelled dataset and the
:class:`~customer_retention.infrastructure.model_adapter.ChurnModelPort`
consumed by the multi-agent workflow.

Typical lifecycle
-----------------
1. A user uploads a labelled CSV (with a ``churn`` column) via the UI.
2. :func:`train_model` fits a classifier and returns a
   :class:`TrainedModelResult` with metrics and the saved ``.pkl`` path.
3. :class:`PickleModelAdapter` wraps the ``.pkl`` behind the port so the
   workflow agents are completely unaware of the underlying algorithm.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from customer_retention.domain.contracts import CustomerRecord
from customer_retention.domain.exceptions import DataError

_LOGGER = logging.getLogger(__name__)


# ── sklearn protocol ──────────────────────────────────────────────────────────


class _SklearnClassifier(Protocol):
    """Minimal sklearn classifier protocol (fit / predict / predict_proba)."""

    def fit(self, x: np.ndarray, y: np.ndarray) -> "_SklearnClassifier":
        """Fit the classifier to training data."""
        ...  # pylint: disable=unnecessary-ellipsis

    def predict(self, x: np.ndarray) -> np.ndarray:
        """Return hard predictions."""
        ...  # pylint: disable=unnecessary-ellipsis

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        """Return class probabilities."""
        ...  # pylint: disable=unnecessary-ellipsis


# ── feature contract ──────────────────────────────────────────────────────────

_FEATURE_COLS: list[str] = [
    "tenure",
    "monthly_charges",
    "total_charges",
    "support_calls",
    "complaints",
    "auto_pay",
    "num_products",
    "age",
    "is_active",
    "is_month_to_month",
    "is_one_year",
]
_TARGET_COL = "churn"

# ── algorithm catalogue ───────────────────────────────────────────────────────

_ALGORITHMS: dict[str, _SklearnClassifier] = {
    "Random Forest": RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        min_samples_leaf=10,
        random_state=42,
        n_jobs=-1,
    ),
    "Gradient Boosting": GradientBoostingClassifier(
        n_estimators=150,
        max_depth=4,
        learning_rate=0.05,
        random_state=42,
    ),
    "Logistic Regression": Pipeline(
        [
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=1000, random_state=42)),
        ]
    ),
}


# ── result artefact ───────────────────────────────────────────────────────────


@dataclass
class TrainedModelResult:
    """Container for training outcomes and artefact location."""

    algorithm: str
    model_path: Path
    auc_roc: float
    cv_auc_mean: float
    cv_auc_std: float
    accuracy: float
    n_train: int
    n_test: int
    feature_importance: dict[str, float] = field(default_factory=dict)
    classification_report_text: str = ""

    def summary(self) -> str:
        """Return a single-line human-readable training summary."""
        return (
            f"{self.algorithm} | AUC-ROC={self.auc_roc:.4f} "
            f"| CV-AUC={self.cv_auc_mean:.4f}±{self.cv_auc_std:.4f} "
            f"| Accuracy={self.accuracy:.4f} "
            f"| Train={self.n_train} Test={self.n_test}"
        )


# ── feature engineering ───────────────────────────────────────────────────────


def _prepare_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Engineer a numeric feature matrix from a raw customer dataframe.

    Args:
        frame: Raw dataset (without the target column).

    Returns:
        A dataframe with exactly the columns listed in :data:`_FEATURE_COLS`.
    """
    df = frame.copy()
    df.columns = [c.lower().strip() for c in df.columns]

    contract_col = next((c for c in df.columns if "contract" in c or "contrato" in c), None)
    if contract_col:
        df["is_month_to_month"] = (
            df[contract_col].str.lower().str.contains("month", na=False).astype(int)
        )
        df["is_one_year"] = df[contract_col].str.lower().str.contains("one", na=False).astype(int)
    else:
        df["is_month_to_month"] = 0
        df["is_one_year"] = 0

    if "tenure" not in df.columns and "tenure_months" in df.columns:
        df["tenure"] = df["tenure_months"]

    for col in ("is_active", "auto_pay"):
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.lower()
                .map(lambda v: 1 if v in {"1", "true", "yes", "y", "si", "activo"} else 0)
            )

    missing = set(_FEATURE_COLS) - set(df.columns)
    if missing:
        _LOGGER.warning("missing feature columns (will use 0): %s", missing)
        for col in missing:
            df[col] = 0

    return df[_FEATURE_COLS].fillna(0)


# ── training entry point ──────────────────────────────────────────────────────


def _get_base_clf(model: _SklearnClassifier) -> Any:
    """Extract the base classifier from a pipeline, or return the model itself.

    Args:
        model: A fitted sklearn estimator or pipeline.

    Returns:
        The leaf classifier with ``feature_importances_`` if available.
    """
    named: Any = getattr(model, "named_steps", None)
    if isinstance(named, dict) and "clf" in named:
        return named["clf"]
    return model


def train_model(  # pylint: disable=too-many-locals
    csv_path: str | Path,
    algorithm_name: str = "Random Forest",
    test_size: float = 0.20,
    model_dir: str | Path = "models",
) -> TrainedModelResult:
    """Train a churn classifier and save it as a ``.pkl`` file.

    Args:
        csv_path: Path to the labelled dataset.  Must contain a ``churn``
            column with values 0 / 1.
        algorithm_name: Key from the internal algorithm catalogue.
        test_size: Fraction of data reserved for evaluation.
        model_dir: Directory where the ``.pkl`` artefact is written.

    Returns:
        A :class:`TrainedModelResult` with metrics and the saved model path.

    Raises:
        DataError: If the dataset is missing, empty or lacks the target column.
        ValueError: If ``algorithm_name`` is not recognised.
    """
    path = Path(csv_path)
    if not path.exists():
        raise DataError(f"training dataset not found: {path}")
    if algorithm_name not in _ALGORITHMS:
        raise ValueError(f"unknown algorithm '{algorithm_name}'. Choose from: {list(_ALGORITHMS)}")

    frame = pd.read_excel(path) if path.suffix.lower() in {".xlsx", ".xls"} else pd.read_csv(path)
    frame.columns = [c.lower().strip() for c in frame.columns]

    target_col = next(
        (c for c in frame.columns if c in {"churn", "abandono", "target", "label"}),
        None,
    )
    if target_col is None:
        raise DataError(
            "dataset must contain a target column named 'churn', 'abandono', "
            "'target' or 'label'."
        )

    y: np.ndarray = frame[target_col].astype(int).to_numpy()
    x_feat = _prepare_features(frame.drop(columns=[target_col]))
    x: np.ndarray = x_feat.to_numpy()

    _LOGGER.info("training %s on %d samples (%d features)", algorithm_name, len(x), x.shape[1])

    x_tr, x_te, y_tr, y_te = train_test_split(
        x, y, test_size=test_size, random_state=42, stratify=y
    )
    model = _ALGORITHMS[algorithm_name]
    model.fit(x_tr, y_tr)

    y_prob: np.ndarray = model.predict_proba(x_te)[:, 1]
    y_pred: np.ndarray = model.predict(x_te)
    auc = float(roc_auc_score(y_te, y_prob))
    acc = float(np.mean(y_pred == y_te))
    report: str = classification_report(y_te, y_pred, target_names=["retained", "churned"])

    cv_scores: np.ndarray = cross_val_score(model, x_tr, y_tr, cv=5, scoring="roc_auc", n_jobs=-1)

    importance: dict[str, float] = {}
    clf: Any = _get_base_clf(model)
    if hasattr(clf, "feature_importances_"):
        importance = dict(zip(_FEATURE_COLS, clf.feature_importances_.round(4).tolist()))

    model_dir_path = Path(model_dir)
    model_dir_path.mkdir(parents=True, exist_ok=True)
    slug = algorithm_name.lower().replace(" ", "_")
    model_path = model_dir_path / f"churn_{slug}.pkl"

    joblib.dump(
        {
            "model": model,
            "feature_cols": _FEATURE_COLS,
            "algorithm": algorithm_name,
            "auc_roc": auc,
        },
        model_path,
    )
    _LOGGER.info("model saved → %s (AUC-ROC=%.4f)", model_path, auc)

    return TrainedModelResult(
        algorithm=algorithm_name,
        model_path=model_path,
        auc_roc=auc,
        cv_auc_mean=float(cv_scores.mean()),
        cv_auc_std=float(cv_scores.std()),
        accuracy=acc,
        n_train=len(x_tr),
        n_test=len(x_te),
        feature_importance=importance,
        classification_report_text=report,
    )


# ── pkl adapter ───────────────────────────────────────────────────────────────


class PickleModelAdapter:
    """Load a persisted ``.pkl`` churn model and expose it behind the port.

    The ``.pkl`` file must contain the dict produced by :func:`train_model`.
    """

    def __init__(self, pkl_path: str | Path) -> None:
        """Load the model from disk.

        Args:
            pkl_path: Path to the ``.pkl`` file produced by :func:`train_model`.

        Raises:
            DataError: If the file does not exist or is malformed.
        """
        path = Path(pkl_path)
        if not path.exists():
            raise DataError(f"model file not found: {path}")
        try:
            payload: dict[str, Any] = joblib.load(path)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            raise DataError(f"could not load model from {path}: {exc}") from exc

        self._model: _SklearnClassifier = payload["model"]
        self._feature_cols: list[str] = payload.get("feature_cols", _FEATURE_COLS)
        algorithm: str = payload.get("algorithm", "unknown")
        auc: float = payload.get("auc_roc", 0.0)
        self.name = f"pkl:{path.stem} ({algorithm}, AUC={auc:.4f})"

    def predict_proba(self, record: CustomerRecord) -> float:
        """Score one customer using the trained model.

        Args:
            record: The customer to evaluate.

        Returns:
            Churn probability in the closed interval ``[0, 1]``.
        """
        alias: dict[str, float] = {
            "tenure": float(record.tenure_months),
            "monthly_charges": record.monthly_charges,
            "total_charges": record.total_charges,
            "support_calls": float(record.support_calls),
            "complaints": float(record.complaints),
            "is_active": float(record.is_active),
            "auto_pay": record.features.get("auto_pay", 0.0),
            "num_products": record.features.get("num_products", 1.0),
            "age": record.features.get("age", 45.0),
            "is_month_to_month": float("month" in record.contract_type.lower()),
            "is_one_year": float("one" in record.contract_type.lower()),
        }
        row = [alias.get(col, record.features.get(col, 0.0)) for col in self._feature_cols]
        prob: float = float(self._model.predict_proba(np.array([row]))[0][1])
        return max(0.0, min(1.0, prob))

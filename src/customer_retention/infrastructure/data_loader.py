"""Dataset loading and normalisation for the churn challenge.

The loader reads both CSV and Excel (``.xlsx``/``.xls``) and is deliberately
*schema-tolerant*: the source may use any of
several common column spellings. We map known aliases onto the canonical
:class:`CustomerRecord` fields and preserve every remaining numeric column as
an extra feature, so the predictive model can exploit the full signal.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Mapping

import pandas as pd

from customer_retention.domain.contracts import CustomerRecord
from customer_retention.domain.exceptions import DataError

_LOGGER = logging.getLogger(__name__)

# Canonical field -> accepted source-column aliases (lower-cased).
_ALIASES: Mapping[str, tuple[str, ...]] = {
    "customer_id": ("customer_id", "customerid", "id", "cliente_id", "id_cliente"),
    "tenure_months": ("tenure", "tenure_months", "antiguedad", "meses"),
    "monthly_charges": ("monthlycharges", "monthly_charges", "cargo_mensual"),
    "total_charges": ("totalcharges", "total_charges", "cargo_total"),
    "contract_type": ("contract", "contract_type", "tipo_contrato"),
    "support_calls": ("support_calls", "llamadas_soporte", "num_support"),
    "complaints": ("complaints", "quejas", "reclamos"),
    "is_active": ("is_active", "active", "activo"),
}

_RESERVED = {"churn", "target", "abandono", "label"}


def _resolve_columns(columns: list[str]) -> dict[str, str]:
    """Map canonical field names to the actual dataframe column names."""
    lowered = {c.lower(): c for c in columns}
    resolved: dict[str, str] = {}
    for field, aliases in _ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                resolved[field] = lowered[alias]
                break
    return resolved


def _to_bool(value: object) -> bool:
    """Coerce heterogeneous truthy encodings to ``bool``."""
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "si", "activo"}
    return bool(value)


def _read_frame(path: Path) -> pd.DataFrame:
    """Read a CSV or Excel file into a dataframe based on its extension.

    Args:
        path: Path to a ``.csv``, ``.tsv``, ``.xlsx`` or ``.xls`` file.

    Returns:
        The loaded dataframe.

    Raises:
        DataError: If the file cannot be parsed.
    """
    suffix = path.suffix.lower()
    try:
        if suffix in {".xlsx", ".xls"}:
            return pd.read_excel(path)
        separator = "\\t" if suffix == ".tsv" else ","
        return pd.read_csv(path, sep=separator)
    except (ValueError, OSError) as exc:
        raise DataError(f"could not read dataset {path}: {exc}") from exc


def load_customers(csv_path: str | Path) -> list[CustomerRecord]:
    """Load and normalise the customer dataset.

    Args:
        csv_path: Path to ``customers.csv``.

    Returns:
        A list of validated :class:`CustomerRecord` instances.

    Raises:
        DataError: If the file is missing, empty, or lacks an id column.
    """
    path = Path(csv_path)
    if not path.exists():
        raise DataError(f"dataset not found: {path}")
    frame = _read_frame(path)
    if frame.empty:
        raise DataError(f"dataset is empty: {path}")

    resolved = _resolve_columns(list(frame.columns))
    if "customer_id" not in resolved:
        raise DataError("no recognisable customer id column in dataset")

    mapped_sources = set(resolved.values())
    records: list[CustomerRecord] = []
    for _, row in frame.iterrows():
        extra: dict[str, float] = {}
        for column in frame.columns:
            if column in mapped_sources or column.lower() in _RESERVED:
                continue
            raw = row[column]
            if pd.api.types.is_number(raw) and pd.notna(raw):
                extra[column] = float(raw)
        record = CustomerRecord(
            customer_id=str(row[resolved["customer_id"]]),
            tenure_months=int(row[resolved["tenure_months"]]) if "tenure_months" in resolved else 0,
            monthly_charges=(
                float(row[resolved["monthly_charges"]]) if "monthly_charges" in resolved else 0.0
            ),
            total_charges=(
                float(row[resolved["total_charges"]]) if "total_charges" in resolved else 0.0
            ),
            contract_type=(
                str(row[resolved["contract_type"]]) if "contract_type" in resolved else "unknown"
            ),
            support_calls=int(row[resolved["support_calls"]]) if "support_calls" in resolved else 0,
            complaints=int(row[resolved["complaints"]]) if "complaints" in resolved else 0,
            is_active=_to_bool(row[resolved["is_active"]]) if "is_active" in resolved else True,
            features=extra,
        )
        records.append(record)

    _LOGGER.info("loaded %d customers from %s", len(records), path)
    return records

"""Unit tests for the synthetic dataset generator and xlsx loading."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

from customer_retention.infrastructure.data_loader import load_customers

_GEN_PATH = Path(__file__).resolve().parents[2] / "scripts" / "generate_synthetic_dataset.py"


def _load_generator():
    """Import the generator script as a module."""
    spec = importlib.util.spec_from_file_location("gen", _GEN_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generator_is_deterministic() -> None:
    """The same seed reproduces the exact same dataset."""
    gen = _load_generator()
    first = gen.build_dataframe(rows=200, seed=7)
    second = gen.build_dataframe(rows=200, seed=7)
    pd.testing.assert_frame_equal(first, second)


def test_generator_schema_and_churn_rate() -> None:
    """The dataset has the expected columns and a realistic churn rate."""
    gen = _load_generator()
    frame = gen.build_dataframe(rows=1000, seed=42)
    expected = {
        "customer_id",
        "tenure",
        "contract",
        "monthly_charges",
        "total_charges",
        "num_products",
        "support_calls",
        "complaints",
        "auto_pay",
        "age",
        "is_active",
        "churn",
    }
    assert expected <= set(frame.columns)
    # Churn should be present but not degenerate (realistic, overlapping).
    rate = frame["churn"].mean()
    assert 0.10 < rate < 0.45


def test_generated_csv_flows_through_loader(tmp_path: Path) -> None:
    """A generated CSV loads into valid CustomerRecords with extra features."""
    gen = _load_generator()
    frame = gen.build_dataframe(rows=50, seed=1)
    csv_path = tmp_path / "customers.csv"
    frame.to_csv(csv_path, index=False)
    records = load_customers(csv_path)
    assert len(records) == 50
    # Extra numeric features are preserved; the churn label is not leaked in.
    assert "age" in records[0].features
    assert "churn" not in records[0].features


def test_loader_reads_xlsx(tmp_path: Path) -> None:
    """The loader reads .xlsx datasets identically to .csv."""
    gen = _load_generator()
    frame = gen.build_dataframe(rows=30, seed=3)
    xlsx_path = tmp_path / "customers.xlsx"
    frame.to_excel(xlsx_path, index=False)
    records = load_customers(xlsx_path)
    assert len(records) == 30
    assert records[0].customer_id == "CUST-00001"

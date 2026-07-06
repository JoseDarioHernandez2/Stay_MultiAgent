#!/usr/bin/env python3
"""Generate a realistic synthetic customer-churn dataset for testing.

The generator produces overlapping, noisy features (not a perfectly separable,
"over-acted" dataset): a latent churn propensity is built from interpretable
drivers — contract type, tenure, support pressure, complaints, auto-pay,
number of products and activity — plus Gaussian noise, and the ``churn`` label
is *sampled* from that propensity rather than computed deterministically.

The output schema matches what :mod:`customer_retention.infrastructure.data_loader`
understands (``customer_id``, ``tenure``, ``monthly_charges``, ``total_charges``,
``contract``, ``support_calls``, ``complaints``, ``is_active``) plus extra
numeric features (``age``, ``num_products``, ``auto_pay``) and the ``churn``
target column.

Example:
    python scripts/generate_synthetic_dataset.py --rows 1000 --seed 42 \
        --out-dir data --formats csv xlsx
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

_CONTRACTS = ("month-to-month", "one-year", "two-year")
_CONTRACT_WEIGHTS = (0.55, 0.25, 0.20)


def _sigmoid(values: np.ndarray) -> np.ndarray:
    """Numerically stable logistic function."""
    return cast(np.ndarray, 1.0 / (1.0 + np.exp(-values)))


def _churn_logit(frame: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    """Build the latent churn logit from interpretable, noisy drivers.

    Args:
        frame: The partially built feature dataframe.
        rng: The seeded random generator (for the noise term).

    Returns:
        A per-customer logit array.
    """
    month_to_month = (frame["contract"] == "month-to-month").to_numpy(dtype=float)
    logit = (
        -1.60
        + 0.95 * month_to_month
        - 0.020 * frame["tenure"].to_numpy()
        + 0.26 * frame["support_calls"].to_numpy()
        + 0.60 * frame["complaints"].to_numpy()
        - 0.65 * frame["auto_pay"].to_numpy()
        + 0.010 * (frame["monthly_charges"].to_numpy() - 70.0)
        - 0.18 * (frame["num_products"].to_numpy() - 1.0)
        + 1.30 * (1.0 - frame["is_active"].to_numpy())
        - 0.008 * (frame["age"].to_numpy() - 45.0)
    )
    noise = rng.normal(0.0, 0.70, size=len(frame))
    return cast(np.ndarray, logit + noise)


def build_dataframe(rows: int, seed: int) -> pd.DataFrame:
    """Build a synthetic churn dataframe.

    Args:
        rows: Number of customers to generate.
        seed: Random seed for full reproducibility.

    Returns:
        A dataframe with features and a sampled ``churn`` label.
    """
    rng = np.random.default_rng(seed)

    tenure = np.clip(rng.gamma(shape=2.0, scale=9.0, size=rows), 0, 72).astype(int)
    contract = rng.choice(_CONTRACTS, size=rows, p=_CONTRACT_WEIGHTS)
    # Longer contracts skew towards longer tenure.
    tenure = np.where(contract == "two-year", np.clip(tenure + 12, 0, 72), tenure)
    tenure = np.where(contract == "one-year", np.clip(tenure + 5, 0, 72), tenure)

    num_products = rng.choice((1, 2, 3, 4), size=rows, p=(0.45, 0.30, 0.18, 0.07))
    monthly_charges = np.clip(
        rng.normal(55.0, 18.0, size=rows) + 12.0 * (num_products - 1),
        15.0,
        160.0,
    ).round(2)
    total_charges = (tenure * monthly_charges * rng.uniform(0.92, 1.03, size=rows)).round(2)

    support_calls = rng.poisson(np.where(contract == "month-to-month", 1.6, 0.7)).astype(int)
    complaints = rng.poisson(0.35 + 0.25 * support_calls).astype(int)
    complaints = np.clip(complaints, 0, 6)
    auto_pay = rng.binomial(1, np.where(contract == "two-year", 0.8, 0.5)).astype(int)
    age = np.clip(rng.normal(45.0, 15.0, size=rows), 18, 88).astype(int)
    is_active = rng.binomial(1, 0.92, size=rows).astype(int)

    frame = pd.DataFrame(
        {
            "customer_id": [f"CUST-{i:05d}" for i in range(1, rows + 1)],
            "tenure": tenure,
            "contract": contract,
            "monthly_charges": monthly_charges,
            "total_charges": total_charges,
            "num_products": num_products,
            "support_calls": support_calls,
            "complaints": complaints,
            "auto_pay": auto_pay,
            "age": age,
            "is_active": is_active,
        }
    )

    probability = _sigmoid(_churn_logit(frame, rng))
    frame["churn"] = rng.binomial(1, probability).astype(int)
    return frame


def _write_xlsx(frame: pd.DataFrame, path: Path) -> None:
    """Write the dataset to a formatted Excel workbook with a data dictionary.

    Args:
        frame: The dataset to persist.
        path: Destination ``.xlsx`` path.
    """
    dictionary = pd.DataFrame(
        {
            "column": [
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
            ],
            "description": [
                "Unique customer identifier",
                "Months as a customer (0-72)",
                "Contract type: month-to-month / one-year / two-year",
                "Recurring monthly charge",
                "Lifetime charges to date",
                "Number of contracted products (1-4)",
                "Support calls in the recent period",
                "Formal complaints filed (0-6)",
                "1 if enrolled in automatic payment",
                "Customer age in years",
                "1 if the account is currently active",
                "TARGET: 1 if the customer churned (sampled, noisy)",
            ],
        }
    )

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="customers", index=False)
        dictionary.to_excel(writer, sheet_name="diccionario", index=False)
        for sheet_name in ("customers", "diccionario"):
            sheet = writer.sheets[sheet_name]
            sheet.freeze_panes = "A2"
            for col_idx, column in enumerate(sheet.iter_cols(min_row=1, max_row=1), 1):
                header = column[0]
                header.font = Font(name="Arial", bold=True, color="FFFFFF")
                header.fill = PatternFill("solid", start_color="2F5496")
                header.alignment = Alignment(horizontal="center")
                sheet.column_dimensions[get_column_letter(col_idx)].width = 18


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Generate a synthetic churn dataset.")
    parser.add_argument("--rows", type=int, default=1000, help="Number of customers.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument("--out-dir", default="data", help="Output directory.")
    parser.add_argument(
        "--formats",
        nargs="+",
        default=["csv", "xlsx"],
        choices=["csv", "xlsx"],
        help="Output formats to write.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Generate the dataset and write it to disk.

    Args:
        argv: Optional argument vector.

    Returns:
        Process exit code (``0`` on success).
    """
    args = _parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    frame = build_dataframe(args.rows, args.seed)
    churn_rate = frame["churn"].mean()

    if "csv" in args.formats:
        frame.to_csv(out_dir / "customers.csv", index=False)
    if "xlsx" in args.formats:
        _write_xlsx(frame, out_dir / "customers.xlsx")

    print(
        f"Generated {len(frame)} customers "
        f"(churn rate={churn_rate:.1%}) -> {out_dir}/ [{', '.join(args.formats)}]"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

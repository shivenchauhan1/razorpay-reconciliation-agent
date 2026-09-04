"""
loaders.py — Typed DataFrame loaders for ledger and settlements CSVs.

Exported functions:
    load_ledger(path)      -> pd.DataFrame
    load_settlements(path) -> pd.DataFrame
"""

from pathlib import Path

import pandas as pd


def load_ledger(path: str | Path) -> pd.DataFrame:
    """
    Load ledger.csv with correct column dtypes.

    Columns: txn_id (str), order_id (str), amount (float), method (str),
             fee (float), gst_on_fee (float), net_amount (float),
             txn_date (datetime), status (str)
    """
    df = pd.read_csv(
        path,
        dtype={
            "txn_id": str,
            "order_id": str,
            "amount": float,
            "method": str,
            "fee": float,
            "gst_on_fee": float,
            "net_amount": float,
            "status": str,
        },
        parse_dates=["txn_date"],
    )
    return df


def load_settlements(path: str | Path) -> pd.DataFrame:
    """
    Load settlements.csv with correct column dtypes.

    Columns: utr_number (str), order_id (str), settled_amount (float),
             settlement_date (datetime), batch_id (str)
    """
    df = pd.read_csv(
        path,
        dtype={
            "utr_number": str,
            "order_id": str,
            "settled_amount": float,
            "batch_id": str,
        },
        parse_dates=["settlement_date"],
    )
    return df

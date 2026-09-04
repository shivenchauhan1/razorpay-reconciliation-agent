"""
match_fuzzy.py — Second-pass reconciliation on leftovers from exact matching.

Targets rows where order_id is garbled/missing by matching on amount ± tolerance
within a settlement date window. Single unambiguous candidate → fuzzy match.
Multiple candidates → held as ambiguous (sent to exception classifier).

Exported function:
    match_fuzzy(unmatched_ledger_df, unmatched_settlements_df,
                amount_tolerance=5.0, date_window_days=3)
        -> (fuzzy_matched_df, still_unmatched_ledger_df, still_unmatched_settlements_df)
"""

import pandas as pd


def match_fuzzy(
    unmatched_ledger_df: pd.DataFrame,
    unmatched_settlements_df: pd.DataFrame,
    amount_tolerance: float = 5.0,
    date_window_days: int = 3,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Fuzzy second-pass reconciliation.

    For each unmatched ledger row, search the unmatched settlements pool for rows where:
      - abs(settled_amount - net_amount) <= amount_tolerance
      - 0 <= (settlement_date - txn_date).days <= date_window_days

    Outcomes:
      0 candidates  → stays unmatched
      1 candidate   → fuzzy match (match_type="fuzzy", confidence="low")
      2+ candidates → ambiguous; row stays unmatched with ambiguity_flag=True

    Returns
    -------
    fuzzy_matched_df
    still_unmatched_ledger_df   (includes ambiguous rows)
    still_unmatched_settlements_df
    """
    if unmatched_ledger_df.empty or unmatched_settlements_df.empty:
        return (
            pd.DataFrame(),
            unmatched_ledger_df.copy(),
            unmatched_settlements_df.copy(),
        )

    ledger = unmatched_ledger_df.copy().reset_index(drop=True)
    settlements = unmatched_settlements_df.copy().reset_index(drop=True)

    fuzzy_matched_rows = []
    consumed_utrs: set[str] = set()
    ambiguous_txn_ids: set[str] = set()

    for _, lrow in ledger.iterrows():
        net = lrow["net_amount"]
        txn_date = pd.to_datetime(lrow["txn_date"])

        # Filter available (not yet consumed) settlements
        available = settlements[~settlements["utr_number"].isin(consumed_utrs)]

        # Apply amount tolerance
        amount_mask = (available["settled_amount"] - net).abs() <= amount_tolerance
        # Apply date window (settlement must be within [txn_date, txn_date + window])
        sett_dates = pd.to_datetime(available["settlement_date"])
        day_diff = (sett_dates - txn_date).dt.days
        date_mask = (day_diff >= 0) & (day_diff <= date_window_days)

        candidates = available[amount_mask & date_mask]

        if len(candidates) == 0:
            # No candidate — stays unmatched
            continue

        elif len(candidates) == 1:
            srow = candidates.iloc[0]
            fuzzy_matched_rows.append({
                "txn_id": lrow["txn_id"],
                "order_id": lrow["order_id"],
                "utr_number": srow["utr_number"],
                "net_amount": net,
                "settled_amount": srow["settled_amount"],
                "txn_date": lrow["txn_date"],
                "settlement_date": srow["settlement_date"],
                "match_type": "fuzzy",
                "confidence": "low",
            })
            consumed_utrs.add(srow["utr_number"])

        else:
            # 2+ candidates — ambiguous, do NOT pick one
            ambiguous_txn_ids.add(lrow["txn_id"])

    # -----------------------------------------------------------------------
    # Build output DataFrames
    # -----------------------------------------------------------------------
    fuzzy_matched_df = pd.DataFrame(fuzzy_matched_rows) if fuzzy_matched_rows else pd.DataFrame()

    matched_txn_ids = set(fuzzy_matched_df["txn_id"]) if not fuzzy_matched_df.empty else set()

    still_unmatched_ledger = ledger[
        ~ledger["txn_id"].isin(matched_txn_ids)
    ].copy()
    # Tag ambiguous rows so the classifier can use this information
    still_unmatched_ledger["ambiguity_flag"] = still_unmatched_ledger["txn_id"].isin(
        ambiguous_txn_ids
    )

    still_unmatched_settlements = settlements[
        ~settlements["utr_number"].isin(consumed_utrs)
    ].copy()

    return fuzzy_matched_df, still_unmatched_ledger, still_unmatched_settlements

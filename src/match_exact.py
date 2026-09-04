"""
match_exact.py — First-pass reconciliation: exact join on order_id + amount tolerance.

Exported function:
    match_exact(ledger_df, settlements_df, duplicate_order_ids=None)
        -> (matched_df, unmatched_ledger_df, unmatched_settlements_df)
"""

import pandas as pd

AMOUNT_TOLERANCE = 1.00   # Rs.1.00 rounding tolerance
SETTLEMENT_DAY_MAX = 3    # reject if settlement is more than 3 days after txn


def match_exact(
    ledger_df: pd.DataFrame,
    settlements_df: pd.DataFrame,
    duplicate_order_ids: set | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Attempt an exact reconciliation pass.

    Parameters
    ----------
    ledger_df : DataFrame
        Full transaction ledger (must have: txn_id, order_id, net_amount, txn_date).
    settlements_df : DataFrame
        Full settlements file (must have: utr_number, order_id, settled_amount, settlement_date).
    duplicate_order_ids : set, optional
        Pre-computed set of order_ids with 2+ rows in the original settlements file.
        These are excluded from matching upfront so both legs stay in the unmatched pool.

    Returns
    -------
    matched_df : DataFrame
        Confirmed exact matches. Columns include match_type="exact".
    unmatched_ledger_df : DataFrame
        Ledger rows with no confirmed match.
    unmatched_settlements_df : DataFrame
        Settlement rows not consumed by a match (including ambiguous duplicates).
    """
    if duplicate_order_ids is None:
        duplicate_order_ids = set()

    # -----------------------------------------------------------------------
    # 1. Exclude known-duplicate order_ids from both pools before joining
    #    so the classifier can handle them cleanly
    # -----------------------------------------------------------------------
    dup_ledger_mask = ledger_df["order_id"].isin(duplicate_order_ids)
    dup_sett_mask = settlements_df["order_id"].isin(duplicate_order_ids)

    eligible_ledger = ledger_df[~dup_ledger_mask].copy()
    eligible_sett = settlements_df[~dup_sett_mask].copy()

    held_back_ledger = ledger_df[dup_ledger_mask].copy()
    held_back_sett = settlements_df[dup_sett_mask].copy()

    # -----------------------------------------------------------------------
    # 2. Inner join on order_id
    # -----------------------------------------------------------------------
    merged = eligible_ledger.merge(
        eligible_sett,
        on="order_id",
        how="inner",
        suffixes=("_ledger", "_sett"),
    )

    # -----------------------------------------------------------------------
    # 3. Amount tolerance + date window filter
    # -----------------------------------------------------------------------
    merged["_amount_delta"] = (merged["net_amount"] - merged["settled_amount"]).abs()
    amount_ok = merged["_amount_delta"] <= AMOUNT_TOLERANCE

    # Also enforce settlement date window: reject if > SETTLEMENT_DAY_MAX days late
    # This ensures timing_mismatch rows fall through to the classifier.
    day_diff = (
        pd.to_datetime(merged["settlement_date"]) - pd.to_datetime(merged["txn_date"])
    ).dt.days
    date_ok = (day_diff >= 0) & (day_diff <= SETTLEMENT_DAY_MAX)

    confirmed = merged[amount_ok & date_ok].copy()
    rejected_by_amount = merged[~(amount_ok & date_ok)].copy()

    # -----------------------------------------------------------------------
    # 4. Guard: if somehow a single order_id matched >1 settlement row
    #    (shouldn't happen after duplicate pre-filter, but be defensive)
    # -----------------------------------------------------------------------
    dup_in_confirmed = confirmed["order_id"].duplicated(keep=False)
    if dup_in_confirmed.any():
        ambiguous_oids = set(confirmed.loc[dup_in_confirmed, "order_id"])
        confirmed = confirmed[~confirmed["order_id"].isin(ambiguous_oids)]

    # -----------------------------------------------------------------------
    # 5. Build matched_df
    # -----------------------------------------------------------------------
    matched_df = pd.DataFrame()
    if not confirmed.empty:
        matched_df = confirmed[[
            "txn_id", "order_id", "utr_number",
            "net_amount", "settled_amount",
            "txn_date", "settlement_date",
            "_amount_delta",
        ]].copy()
        matched_df["match_type"] = "exact"
        matched_df["confidence"] = "high"
        matched_df = matched_df.drop(columns=["_amount_delta"])

    matched_order_ids = set(matched_df["order_id"]) if not matched_df.empty else set()

    # -----------------------------------------------------------------------
    # 6. Build unmatched pools
    # -----------------------------------------------------------------------
    # Ledger rows that didn't get matched: dup-held-back + not in confirmed
    unmatched_ledger_df = pd.concat([
        held_back_ledger,
        eligible_ledger[~eligible_ledger["order_id"].isin(matched_order_ids)],
    ], ignore_index=True)

    # Settlement rows not consumed: dup-held-back + not matched + rejected-by-amount
    consumed_utrs = set(matched_df["utr_number"]) if not matched_df.empty else set()
    unmatched_settlements_df = pd.concat([
        held_back_sett,
        eligible_sett[~eligible_sett["utr_number"].isin(consumed_utrs)],
    ], ignore_index=True)

    return matched_df, unmatched_ledger_df, unmatched_settlements_df

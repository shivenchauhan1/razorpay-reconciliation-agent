"""
classify_exceptions.py — Deterministic rule-based exception tagger.

Every ledger row that survives both matching passes is assigned exactly one
exception type, a human-readable reason string, and a supporting_data dict
(JSON-serialised) that feeds the LLM narration step.

Priority order (first rule that fires wins):
  1. duplicate_settlement  — order_id had 2+ rows in the original settlements file
  2. amount_mismatch       — candidate found by order_id but amount differs > ₹1
                             and settled >= 90 % of net (not a partial)
  3. partial_settlement    — candidate found but settled < 90 % of net
  4. timing_mismatch       — candidate matches on order_id + amount but date > T+3
  5. missing_settlement    — no settlement row for this order_id at all
  6. ambiguous_match       — no order_id match but 2+ fuzzy candidates existed

Exported function:
    classify_exceptions(unmatched_ledger_df, unmatched_settlements_df,
                        all_settlements_df, duplicate_order_ids)
        -> exceptions_df
"""

import json

import pandas as pd

AMOUNT_TOLERANCE = 1.00      # same as exact matcher
PARTIAL_THRESHOLD = 0.90     # below 90 % of net → partial settlement
TIMING_MAX_DAYS = 3          # beyond T+3 → timing mismatch


def _fmt(amount: float) -> str:
    return f"₹{amount:,.2f}"


def classify_exceptions(
    unmatched_ledger_df: pd.DataFrame,
    unmatched_settlements_df: pd.DataFrame,
    all_settlements_df: pd.DataFrame,
    duplicate_order_ids: set | None = None,
) -> pd.DataFrame:
    """
    Classify every unmatched ledger row into one of six exception types.

    Parameters
    ----------
    unmatched_ledger_df : DataFrame
        Rows from the ledger that neither exact nor fuzzy matching resolved.
        May contain an 'ambiguity_flag' column from match_fuzzy.
    unmatched_settlements_df : DataFrame
        Settlement rows not consumed by either matching pass.
    all_settlements_df : DataFrame
        The original complete settlements file — needed for duplicate counting.
    duplicate_order_ids : set, optional
        Pre-computed set of order_ids with 2+ rows in all_settlements_df.

    Returns
    -------
    exceptions_df : DataFrame
        Columns: txn_id, order_id, exception_type, reason, supporting_data
    """
    if duplicate_order_ids is None:
        duplicate_order_ids = set()

    # Build a fast lookup: order_id → list of unmatched settlement rows
    sett_by_order: dict[str, list[dict]] = {}
    for _, srow in unmatched_settlements_df.iterrows():
        oid = srow["order_id"]
        sett_by_order.setdefault(oid, []).append(srow.to_dict())

    # Also build a lookup over ALL settlements (for duplicate check completeness)
    all_sett_by_order: dict[str, list] = {}
    for _, srow in all_settlements_df.iterrows():
        oid = srow["order_id"]
        all_sett_by_order.setdefault(oid, []).append(srow.to_dict())

    records = []

    for _, lrow in unmatched_ledger_df.iterrows():
        txn_id = str(lrow["txn_id"])
        order_id = str(lrow["order_id"])
        net = float(lrow["net_amount"])
        txn_date = pd.to_datetime(lrow["txn_date"])
        ambiguous = bool(lrow.get("ambiguity_flag", False))

        exception_type = None
        reason = ""
        supporting: dict = {
            "txn_id": txn_id,
            "order_id": order_id,
            "net_amount": net,
            "txn_date": str(txn_date.date()),
        }

        # -------------------------------------------------------------------
        # Priority 1 — Duplicate settlement
        # -------------------------------------------------------------------
        if order_id in duplicate_order_ids:
            all_legs = all_sett_by_order.get(order_id, [])
            utrs = [s["utr_number"] for s in all_legs]
            exception_type = "duplicate_settlement"
            reason = (
                f"{len(all_legs)} settlement rows found for {order_id} "
                f"(UTRs: {', '.join(utrs)}); cannot safely select one"
            )
            supporting["utr_numbers"] = utrs
            supporting["duplicate_count"] = len(all_legs)
            records.append(_build_row(txn_id, order_id, exception_type, reason, supporting))
            continue

        # -------------------------------------------------------------------
        # Find closest candidate in unmatched settlements by order_id
        # -------------------------------------------------------------------
        candidates = sett_by_order.get(order_id, [])

        if candidates:
            # Pick the candidate with the smallest amount delta
            best = min(candidates, key=lambda s: abs(s["settled_amount"] - net))
            best_settled = float(best["settled_amount"])
            best_utr = str(best["utr_number"])
            best_date = pd.to_datetime(best["settlement_date"])
            day_diff = (best_date - txn_date).days
            delta = round(best_settled - net, 2)

            supporting.update({
                "utr_number": best_utr,
                "settled_amount": best_settled,
                "settlement_date": str(best_date.date()),
                "day_diff": day_diff,
                "amount_delta": delta,
            })

            # Add secondary timing note if also late (used even for amount/partial)
            if day_diff > TIMING_MAX_DAYS:
                supporting["timing_note"] = (
                    f"Settlement also {day_diff} days after txn_date "
                    f"(expected ≤ T+{TIMING_MAX_DAYS})"
                )

            amount_diff = abs(best_settled - net)

            # ---------------------------------------------------------------
            # Priority 2 — Amount mismatch (> ₹1 but not a partial)
            # ---------------------------------------------------------------
            if amount_diff > AMOUNT_TOLERANCE and best_settled >= net * PARTIAL_THRESHOLD:
                exception_type = "amount_mismatch"
                reason = (
                    f"Settled amount {_fmt(best_settled)} differs from expected "
                    f"{_fmt(net)} (delta: {_fmt(delta)})"
                )

            # ---------------------------------------------------------------
            # Priority 3 — Partial settlement (< 90 % of net)
            # ---------------------------------------------------------------
            elif amount_diff > AMOUNT_TOLERANCE and best_settled < net * PARTIAL_THRESHOLD:
                exception_type = "partial_settlement"
                pct = round(best_settled / net * 100, 1)
                reason = (
                    f"Only {_fmt(best_settled)} settled out of {_fmt(net)} "
                    f"expected ({pct} % of net)"
                )

            # ---------------------------------------------------------------
            # Priority 4 — Timing mismatch (amount OK but date > T+3)
            # ---------------------------------------------------------------
            elif amount_diff <= AMOUNT_TOLERANCE and day_diff > TIMING_MAX_DAYS:
                exception_type = "timing_mismatch"
                reason = (
                    f"Settlement date {best_date.date()} is {day_diff} days "
                    f"after txn_date {txn_date.date()} (expected ≤ T+{TIMING_MAX_DAYS})"
                )

            else:
                # Candidate matches on amount AND date but something else is off
                # (shouldn't normally reach here; treat as amount mismatch safety)
                exception_type = "amount_mismatch"
                reason = (
                    f"Settlement candidate found but could not be confirmed "
                    f"(settled: {_fmt(best_settled)}, expected: {_fmt(net)}, "
                    f"days: {day_diff})"
                )

        else:
            # No candidate found by order_id at all
            # ---------------------------------------------------------------
            # Priority 5 — Missing settlement
            # ---------------------------------------------------------------
            if not ambiguous:
                exception_type = "missing_settlement"
                reason = (
                    f"No settlement row found for order_id {order_id} "
                    f"in either matched or unmatched pools"
                )

            # ---------------------------------------------------------------
            # Priority 6 — Ambiguous match (2+ fuzzy candidates, none selected)
            # ---------------------------------------------------------------
            else:
                exception_type = "ambiguous_match"
                reason = (
                    f"Multiple fuzzy candidates exist for {txn_id} "
                    f"(net: {_fmt(net)}); cannot safely pick one — sent to review"
                )

        records.append(_build_row(txn_id, order_id, exception_type, reason, supporting))

    return pd.DataFrame(records) if records else pd.DataFrame(
        columns=["txn_id", "order_id", "exception_type", "reason", "supporting_data"]
    )


def _build_row(
    txn_id: str,
    order_id: str,
    exception_type: str,
    reason: str,
    supporting: dict,
) -> dict:
    return {
        "txn_id": txn_id,
        "order_id": order_id,
        "exception_type": exception_type,
        "reason": reason,
        "supporting_data": json.dumps(supporting, default=str),
    }


# ---------------------------------------------------------------------------
# Pre-matching helper — call this BEFORE exact/fuzzy matching
# ---------------------------------------------------------------------------

def compute_duplicate_order_ids(all_settlements_df: pd.DataFrame) -> set:
    """
    Return the set of order_ids that appear more than once in all_settlements_df.
    Must be called before any matching so duplicate legs are never consumed.
    """
    counts = all_settlements_df["order_id"].value_counts()
    return set(counts[counts > 1].index)

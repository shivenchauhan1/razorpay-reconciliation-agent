"""
metrics.py — Ground-truth-verified metrics computation.

Computes the four metrics required by the brief:
  1. match_rate        — (exact + fuzzy) / total ledger rows
  2. precision         — of agent-matched rows, % correct per ground truth
  3. exception_recall  — of ground-truth exceptions, % correctly left unresolved
  4. exception_breakdown — counts per exception type

Exported function:
    compute_metrics(matched_df, exceptions_df, ground_truth_path, total_ledger_rows)
        -> dict
"""

import json
from pathlib import Path

import pandas as pd


def compute_metrics(
    matched_df: pd.DataFrame,
    exceptions_df: pd.DataFrame,
    ground_truth_path: str | Path,
    total_ledger_rows: int,
) -> dict:
    """
    Compute all four reconciliation metrics against ground truth.

    Parameters
    ----------
    matched_df : DataFrame
        All confirmed matches (exact + fuzzy). Must have 'txn_id'.
    exceptions_df : DataFrame
        All classified exceptions. Must have 'txn_id', 'exception_type'.
    ground_truth_path : str | Path
        Path to ground_truth.json.
    total_ledger_rows : int
        Full ledger row count (denominator for match_rate).
        Passed explicitly so it never depends on matched + unmatched counts.

    Returns
    -------
    dict with keys: match_rate, precision, exception_recall,
                    exception_breakdown, raw_counts
    """
    with open(ground_truth_path, "r") as f:
        ground_truth: dict = json.load(f)

    # -----------------------------------------------------------------------
    # 1. Match rate
    # -----------------------------------------------------------------------
    n_matched = len(matched_df)
    match_rate = n_matched / total_ledger_rows if total_ledger_rows else 0.0

    # -----------------------------------------------------------------------
    # 2. Precision
    #    Of everything the agent matched, how many does ground truth also call "matched"?
    # -----------------------------------------------------------------------
    precision_correct = 0
    precision_total = n_matched
    for txn_id in (matched_df["txn_id"] if not matched_df.empty else []):
        gt = ground_truth.get(str(txn_id), {})
        if gt.get("expected_outcome") == "matched":
            precision_correct += 1

    precision = precision_correct / precision_total if precision_total else 0.0

    # -----------------------------------------------------------------------
    # 3. Exception recall
    #    Of all rows ground truth calls exceptions, how many did the agent flag?
    # -----------------------------------------------------------------------
    gt_exception_ids = {
        txn_id
        for txn_id, v in ground_truth.items()
        if v.get("expected_outcome") == "exception"
    }
    agent_exception_ids = set(
        exceptions_df["txn_id"].astype(str) if not exceptions_df.empty else []
    )
    recall_correct = len(gt_exception_ids & agent_exception_ids)
    recall_total = len(gt_exception_ids)
    exception_recall = recall_correct / recall_total if recall_total else 0.0

    # -----------------------------------------------------------------------
    # 4. Exception breakdown
    # -----------------------------------------------------------------------
    exception_breakdown: dict[str, int] = {}
    if not exceptions_df.empty:
        exception_breakdown = (
            exceptions_df["exception_type"]
            .value_counts()
            .to_dict()
        )

    # -----------------------------------------------------------------------
    # 5. Raw counts (useful for the report)
    # -----------------------------------------------------------------------
    n_exact = int((matched_df["match_type"] == "exact").sum()) if not matched_df.empty else 0
    n_fuzzy = int((matched_df["match_type"] == "fuzzy").sum()) if not matched_df.empty else 0
    n_exceptions = len(exceptions_df)
    n_gt_exceptions = len(gt_exception_ids)
    n_unaccounted = total_ledger_rows - n_matched - n_exceptions

    raw_counts = {
        "total_ledger_rows": total_ledger_rows,
        "exact_matches": n_exact,
        "fuzzy_matches": n_fuzzy,
        "total_matched": n_matched,
        "total_exceptions": n_exceptions,
        "gt_exception_count": n_gt_exceptions,
        "correctly_flagged_exceptions": recall_correct,
        "precision_correct": precision_correct,
        "unaccounted_rows": n_unaccounted,
    }

    metrics = {
        "match_rate": round(match_rate, 4),
        "precision": round(precision, 4),
        "exception_recall": round(exception_recall, 4),
        "exception_breakdown": exception_breakdown,
        "raw_counts": raw_counts,
    }

    # -----------------------------------------------------------------------
    # Pretty-print to stdout
    # -----------------------------------------------------------------------
    _print_metrics(metrics)
    return metrics


def _print_metrics(m: dict) -> None:
    rc = m["raw_counts"]
    sep = "-" * 52
    print(f"\n{sep}")
    print("  RECONCILIATION METRICS")
    print(sep)
    print(f"  Total ledger rows      : {rc['total_ledger_rows']}")
    print(f"  Exact matches          : {rc['exact_matches']}")
    print(f"  Fuzzy matches          : {rc['fuzzy_matches']}")
    print(f"  Total matched          : {rc['total_matched']}")
    print(f"  Exceptions flagged     : {rc['total_exceptions']}")
    print(sep)
    print(f"  Match rate             : {m['match_rate']:.1%}")
    print(f"  Precision (vs GT)      : {m['precision']:.1%}")
    print(f"  Exception recall       : {m['exception_recall']:.1%}")
    print(sep)
    print("  Exception breakdown:")
    for exc_type, count in sorted(m["exception_breakdown"].items()):
        print(f"    {exc_type:<28} {count}")
    print(sep)
    if rc.get("unaccounted_rows", 0) > 0:
        print(f"  WARNING: {rc['unaccounted_rows']} ledger row(s) unaccounted for!")
        print(sep)
    print()

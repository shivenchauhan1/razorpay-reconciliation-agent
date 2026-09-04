"""
run_agent.py — Orchestrator for the Razorpay Payment Reconciliation Agent.

Usage:
    python run_agent.py                # full pipeline (generates data + reconciles)
    python run_agent.py --skip-generate  # skip data generation (use existing data/)

Pipeline steps:
    [1/7] Generate synthetic data (skippable)
    [2/7] Load ledger & settlements
    [3/7] Exact matching
    [4/7] Fuzzy matching
    [5/7] Classify exceptions
    [6/7] LLM narration (falls back gracefully if API key absent)
    [7/7] Compute metrics & generate report
"""

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — ensure src/ is importable regardless of cwd
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.resolve()
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output"
sys.path.insert(0, str(REPO_ROOT))

from src.classify_exceptions import classify_exceptions, compute_duplicate_order_ids
from src.explain import explain_exceptions
from src.loaders import load_ledger, load_settlements
from src.match_exact import match_exact
from src.match_fuzzy import match_fuzzy
from src.metrics import compute_metrics
from src.report import generate_report


# ---------------------------------------------------------------------------
# Banner helpers
# ---------------------------------------------------------------------------

def _step(n: int, total: int, msg: str) -> None:
    print(f"\n[{n}/{total}] {msg}")


def _banner() -> None:
    print("=" * 60)
    print("  Razorpay Payment Reconciliation Agent")
    print("=" * 60)


def _check_data_files() -> bool:
    """Return True if all three data files exist."""
    required = [DATA_DIR / "ledger.csv", DATA_DIR / "settlements.csv", DATA_DIR / "ground_truth.json"]
    return all(p.exists() for p in required)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run(skip_generate: bool = False) -> int:
    """
    Execute the full reconciliation pipeline.

    Returns exit code: 0 = success, 1 = error.
    """
    _banner()
    TOTAL_STEPS = 7

    # -----------------------------------------------------------------------
    # Step 1 — Data generation
    # -----------------------------------------------------------------------
    _step(1, TOTAL_STEPS, "Generating synthetic data" if not skip_generate else "Skipping data generation (--skip-generate)")

    if skip_generate:
        if not _check_data_files():
            print(
                "ERROR: --skip-generate was set but data files are missing.\n"
                f"       Expected: {DATA_DIR / 'ledger.csv'}, settlements.csv, ground_truth.json\n"
                "       Run without --skip-generate to generate them first."
            )
            return 1
        print(f"       Using existing files in {DATA_DIR}/")
    else:
        from src.generate_data import generate
        generate(output_dir=str(DATA_DIR))

    # -----------------------------------------------------------------------
    # Step 2 — Load data
    # -----------------------------------------------------------------------
    _step(2, TOTAL_STEPS, "Loading ledger & settlements")
    try:
        ledger_df = load_ledger(DATA_DIR / "ledger.csv")
        settlements_df = load_settlements(DATA_DIR / "settlements.csv")
    except FileNotFoundError as exc:
        print(f"ERROR: Could not load data files: {exc}")
        return 1

    total_ledger_rows = len(ledger_df)
    print(f"       Ledger: {total_ledger_rows} rows | Settlements: {len(settlements_df)} rows")

    # -----------------------------------------------------------------------
    # Pre-matching: identify duplicate order_ids before any row is consumed
    # -----------------------------------------------------------------------
    duplicate_order_ids = compute_duplicate_order_ids(settlements_df)
    if duplicate_order_ids:
        print(f"       Duplicate order_ids detected (pre-filter): {sorted(duplicate_order_ids)}")

    # -----------------------------------------------------------------------
    # Step 3 — Exact matching
    # -----------------------------------------------------------------------
    _step(3, TOTAL_STEPS, "Exact matching (order_id join + Rs.1.00 tolerance)")
    matched_exact, unmatched_ledger, unmatched_sett = match_exact(
        ledger_df, settlements_df, duplicate_order_ids=duplicate_order_ids
    )
    print(f"       Exact matches: {len(matched_exact)} | Unmatched ledger: {len(unmatched_ledger)}")

    # -----------------------------------------------------------------------
    # Step 4 — Fuzzy matching
    # -----------------------------------------------------------------------
    _step(4, TOTAL_STEPS, "Fuzzy matching (amount +/- Rs.5.00, date window 3 days)")
    matched_fuzzy, still_unmatched_ledger, still_unmatched_sett = match_fuzzy(
        unmatched_ledger, unmatched_sett
    )
    print(f"       Fuzzy matches: {len(matched_fuzzy)} | Still unmatched: {len(still_unmatched_ledger)}")

    # Combine all matches
    import pandas as pd
    matched_df = pd.concat([matched_exact, matched_fuzzy], ignore_index=True)

    # -----------------------------------------------------------------------
    # Step 5 — Classify exceptions
    # -----------------------------------------------------------------------
    _step(5, TOTAL_STEPS, "Classifying exceptions (6-rule deterministic pipeline)")
    exceptions_df = classify_exceptions(
        unmatched_ledger_df=still_unmatched_ledger,
        unmatched_settlements_df=still_unmatched_sett,
        all_settlements_df=settlements_df,
        duplicate_order_ids=duplicate_order_ids,
    )
    print(f"       Exceptions classified: {len(exceptions_df)}")
    if not exceptions_df.empty:
        for exc_type, cnt in exceptions_df["exception_type"].value_counts().items():
            print(f"         {exc_type:<30} {cnt}")

    # -----------------------------------------------------------------------
    # Step 6 — LLM narration
    # -----------------------------------------------------------------------
    _step(6, TOTAL_STEPS, "LLM narration (Claude — fallback-safe)")
    exceptions_df = explain_exceptions(exceptions_df)

    # -----------------------------------------------------------------------
    # Step 7 — Metrics + report
    # -----------------------------------------------------------------------
    _step(7, TOTAL_STEPS, "Computing metrics & generating report")
    metrics = compute_metrics(
        matched_df=matched_df,
        exceptions_df=exceptions_df,
        ground_truth_path=DATA_DIR / "ground_truth.json",
        total_ledger_rows=total_ledger_rows,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generate_report(
        matched_df=matched_df,
        exceptions_df=exceptions_df,
        metrics_dict=metrics,
        output_dir=OUTPUT_DIR,
    )

    print("\n" + "=" * 60)
    print("  DONE — outputs written to output/")
    print(f"    CSV  : {OUTPUT_DIR / 'reconciliation_report.csv'}")
    print(f"    HTML : {OUTPUT_DIR / 'reconciliation_report.html'}")
    print("=" * 60)
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Razorpay Payment Reconciliation Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python run_agent.py                 # full run (generates new data)\n"
            "  python run_agent.py --skip-generate # reuse existing data/\n"
        ),
    )
    parser.add_argument(
        "--skip-generate",
        action="store_true",
        help="Skip synthetic data generation; use existing files in data/",
    )
    args = parser.parse_args()
    sys.exit(run(skip_generate=args.skip_generate))

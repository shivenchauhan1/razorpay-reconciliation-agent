"""
generate_data.py — Synthetic data generator for the Razorpay Reconciliation Agent.

Produces:
  data/ledger.csv          — 80 transaction records
  data/settlements.csv     — corresponding bank settlement rows (with injected exceptions)
  data/ground_truth.json   — oracle mapping txn_id → expected outcome

Run standalone:
  python src/generate_data.py
"""

import json
import os
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SEED = 42
TOTAL_RECORDS = 80
FEE_RATE = 0.02        # 2 % of gross amount
GST_RATE = 0.18        # 18 % of fee
AMOUNT_TOLERANCE = 1.00  # ₹1 rounding tolerance used by the matcher

# Exception injection: 2–3 rows per type (15–18 total across 6 types)
EXCEPTION_COUNTS = {
    "missing_settlement": 3,
    "amount_mismatch": 3,
    "timing_mismatch": 3,
    "duplicate_settlement": 3,
    "garbled_order_id": 3,
    "partial_settlement": 3,
}

PAYMENT_METHODS = ["UPI", "CARD", "NETBANKING", "WALLET"]
BASE_DATE = date(2026, 8, 1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_net(amount: float) -> tuple[float, float, float]:
    """Return (fee, gst_on_fee, net_amount) for a given gross amount."""
    fee = round(amount * FEE_RATE, 2)
    gst = round(fee * GST_RATE, 2)
    net = round(amount - fee - gst, 2)
    return fee, gst, net


def _garble_order_id(order_id: str) -> str:
    """Return a visually similar but wrong order_id."""
    # e.g. "O1042" → "O1O42" or "O1042X"
    choices = [
        order_id[:-1] + "X",          # replace last char
        order_id[:2] + "??" + order_id[4:],  # replace middle chars
        order_id + "0",               # append extra digit
    ]
    return random.choice(choices)


def _new_utr(idx: int) -> str:
    return f"UTR{9000 + idx:04d}"


def _new_batch(txn_date: date) -> str:
    # Batch changes weekly
    week = (txn_date - BASE_DATE).days // 7
    return f"BATCH{55 + week}"


# ---------------------------------------------------------------------------
# Core generator
# ---------------------------------------------------------------------------

def generate(output_dir: str = "data") -> None:
    random.seed(SEED)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------------
    # Step 1 — Generate 80 base ledger rows
    # -----------------------------------------------------------------------
    ledger_rows = []
    for i in range(TOTAL_RECORDS):
        txn_id = f"TXN{1001 + i}"
        order_id = f"O{1001 + i}"
        amount = round(random.uniform(200.0, 5000.0), 2)
        fee, gst, net = _compute_net(amount)
        txn_date = BASE_DATE + timedelta(days=random.randint(0, 20))
        method = random.choice(PAYMENT_METHODS)
        status = "captured"  # refunded status added for specific exceptions below

        ledger_rows.append({
            "txn_id": txn_id,
            "order_id": order_id,
            "amount": amount,
            "method": method,
            "fee": fee,
            "gst_on_fee": gst,
            "net_amount": net,
            "txn_date": txn_date,
            "status": status,
        })

    # -----------------------------------------------------------------------
    # Step 2 — Generate 1:1 clean settlement rows for every ledger row
    # -----------------------------------------------------------------------
    utr_counter = 0
    settlement_rows = []
    for row in ledger_rows:
        utr_counter += 1
        settlement_rows.append({
            "utr_number": _new_utr(utr_counter),
            "order_id": row["order_id"],
            "settled_amount": row["net_amount"],
            "settlement_date": row["txn_date"] + timedelta(days=1),
            "batch_id": _new_batch(row["txn_date"]),
        })

    # -----------------------------------------------------------------------
    # Step 3 — Select exception candidates (no overlaps)
    # -----------------------------------------------------------------------
    total_exceptions = sum(EXCEPTION_COUNTS.values())
    exception_indices = random.sample(range(TOTAL_RECORDS), total_exceptions)
    random.shuffle(exception_indices)

    assigned: dict[int, str] = {}
    idx_iter = iter(exception_indices)
    for exc_type, count in EXCEPTION_COUNTS.items():
        for _ in range(count):
            assigned[next(idx_iter)] = exc_type

    # -----------------------------------------------------------------------
    # Step 4 — Apply injections and build ground truth
    # -----------------------------------------------------------------------
    ground_truth: dict[str, dict] = {}
    settlements_to_remove: set[int] = set()
    extra_settlements: list[dict] = []

    for i, ledger_row in enumerate(ledger_rows):
        txn_id = ledger_row["txn_id"]
        order_id = ledger_row["order_id"]
        net = ledger_row["net_amount"]
        txn_date = ledger_row["txn_date"]

        if i not in assigned:
            # Clean record
            ground_truth[txn_id] = {
                "expected_outcome": "matched",
                "exception_type": None,
                "reason": "Clean 1:1 match",
            }
            continue

        exc_type = assigned[i]
        srow = settlement_rows[i]

        if exc_type == "missing_settlement":
            # Remove the settlement row entirely
            settlements_to_remove.add(i)
            ledger_rows[i]["status"] = "captured"
            ground_truth[txn_id] = {
                "expected_outcome": "exception",
                "exception_type": "missing_settlement",
                "reason": f"No settlement row exists for {order_id}",
            }

        elif exc_type == "amount_mismatch":
            # Delta large enough to exceed ₹1 tolerance but < 90 % threshold
            delta = round(random.uniform(5.0, 50.0) * random.choice([-1, 1]), 2)
            new_amount = round(net + delta, 2)
            # Ensure it stays positive and not a partial (>= 90% of net)
            if new_amount < net * 0.90:
                new_amount = round(net + abs(delta), 2)
            settlement_rows[i]["settled_amount"] = new_amount
            ground_truth[txn_id] = {
                "expected_outcome": "exception",
                "exception_type": "amount_mismatch",
                "reason": (
                    f"Settled amount ₹{new_amount} differs from expected "
                    f"₹{net} (delta: ₹{round(new_amount - net, 2)})"
                ),
            }

        elif exc_type == "timing_mismatch":
            # Settlement date is 5–7 days after txn_date (> 3-day window)
            delay = random.randint(5, 7)
            settlement_rows[i]["settlement_date"] = txn_date + timedelta(days=delay)
            ground_truth[txn_id] = {
                "expected_outcome": "exception",
                "exception_type": "timing_mismatch",
                "reason": (
                    f"Settlement {delay} days after txn_date "
                    f"(expected T+1, max T+3)"
                ),
            }

        elif exc_type == "duplicate_settlement":
            # Keep original settlement row; add a second one with a new UTR
            utr_counter += 1
            extra_settlements.append({
                "utr_number": _new_utr(utr_counter),
                "order_id": order_id,
                "settled_amount": net,
                "settlement_date": txn_date + timedelta(days=1),
                "batch_id": _new_batch(txn_date),
            })
            ground_truth[txn_id] = {
                "expected_outcome": "exception",
                "exception_type": "duplicate_settlement",
                "reason": (
                    f"Two settlement rows found for {order_id}; "
                    f"cannot safely pick one"
                ),
            }

        elif exc_type == "garbled_order_id":
            # Corrupt the order_id in the settlement row.
            # The fuzzy pass is designed to recover these (single unambiguous candidate).
            # Ground truth = "matched" because the agent SHOULD resolve these via fuzzy pass.
            # (If it can't, it will show up as a real exception with ambiguous_match type.)
            garbled = _garble_order_id(order_id)
            settlement_rows[i]["order_id"] = garbled
            ground_truth[txn_id] = {
                "expected_outcome": "matched",
                "exception_type": None,
                "reason": (
                    f"Garbled order_id '{garbled}' — expect fuzzy recovery"
                ),
            }

        elif exc_type == "partial_settlement":
            # Settled amount is 50–75 % of net_amount
            fraction = round(random.uniform(0.50, 0.75), 4)
            partial = round(net * fraction, 2)
            settlement_rows[i]["settled_amount"] = partial
            ledger_rows[i]["status"] = "refunded"
            ground_truth[txn_id] = {
                "expected_outcome": "exception",
                "exception_type": "partial_settlement",
                "reason": (
                    f"Only ₹{partial} settled out of ₹{net} expected "
                    f"({round(fraction * 100, 1)} %)"
                ),
            }

    # -----------------------------------------------------------------------
    # Step 5 — Build final DataFrames
    # -----------------------------------------------------------------------
    ledger_df = pd.DataFrame(ledger_rows)
    ledger_df["txn_date"] = pd.to_datetime(ledger_df["txn_date"])

    # Filter out removed settlement rows, then add extras (duplicates)
    final_settlements = [
        row for i, row in enumerate(settlement_rows)
        if i not in settlements_to_remove
    ]
    final_settlements.extend(extra_settlements)

    settlements_df = pd.DataFrame(final_settlements)
    settlements_df["settlement_date"] = pd.to_datetime(settlements_df["settlement_date"])

    # Shuffle so exceptions aren't clustered
    ledger_df = ledger_df.sample(frac=1, random_state=SEED).reset_index(drop=True)
    settlements_df = settlements_df.sample(frac=1, random_state=SEED).reset_index(drop=True)

    # -----------------------------------------------------------------------
    # Step 6 — Save files
    # -----------------------------------------------------------------------
    ledger_df.to_csv(out / "ledger.csv", index=False)
    settlements_df.to_csv(out / "settlements.csv", index=False)

    with open(out / "ground_truth.json", "w") as f:
        json.dump(ground_truth, f, indent=2)

    # Summary
    exception_summary = {}
    for v in ground_truth.values():
        if v["exception_type"]:
            exception_summary[v["exception_type"]] = (
                exception_summary.get(v["exception_type"], 0) + 1
            )
    clean_count = sum(1 for v in ground_truth.values() if v["expected_outcome"] == "matched")

    # Count ground-truth exceptions (garbled_order_id rows are "matched" by fuzzy pass,
    # so they do not appear in the final unreconciled exception count)
    gt_exception_count = sum(
        1 for v in ground_truth.values() if v["expected_outcome"] == "exception"
    )

    print(f"[generate_data] Written {len(ledger_df)} ledger rows -> {out / 'ledger.csv'}")
    print(f"[generate_data] Written {len(settlements_df)} settlement rows -> {out / 'settlements.csv'}")
    print(f"[generate_data] Clean (expect matched): {clean_count}")
    print(f"[generate_data] Injected exception conditions: {total_exceptions}  (includes garbled_order_id recovered by fuzzy pass)")
    print(f"[generate_data] Final unreconciled exceptions (ground truth): {gt_exception_count}")
    for k, v in sorted(exception_summary.items()):
        print(f"              {k}: {v}")
    print(f"[generate_data] Ground truth -> {out / 'ground_truth.json'}")


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    generate(output_dir=os.path.join(os.path.dirname(__file__), "..", "data"))

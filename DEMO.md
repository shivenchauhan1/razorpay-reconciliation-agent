# 2-Minute Demo Script

> Use this script for a live demo or screen recording walkthrough.

---

## Setup (before you start)

```bash
cd razorpay-recon-agent
pip install -r requirements.txt
# Optionally add ANTHROPIC_API_KEY to .env for live narration
```

---

## Step 1 — Run the agent (30 seconds)

```bash
python run_agent.py
```

**Say:** "This is a single command that runs the entire reconciliation pipeline —
data generation, two-pass matching, exception classification, metrics, and report output."

Point out the step counter `[1/7]` through `[7/7]` in the console output.

---

## Step 2 — Walk through the metrics (45 seconds)

Point to the printed metrics block:

```
  Match rate             : 81.2%
  Precision (vs GT)      : 100.0%
  Exception recall       : 100.0%
```

**Say:** "81.2 % of the 80 records were matched — but the important numbers are the
next two. Precision of 100 % means every match the agent made was *correct* per our
ground truth oracle. Exception recall of 100 % means the agent correctly refused to
resolve all 15 injected problem records rather than force-matching them.

A lazy implementation that matches everything could claim 100 % match rate. This agent
reports an honest 81 % and shows you exactly what it couldn't resolve — and why."

---

## Step 3 — Call out 3 specific exceptions (30 seconds)

Open `output/reconciliation_report.csv` or the HTML dashboard.

Point to these rows:

**TXN1008 — duplicate_settlement**
> "Two settlement rows exist for order O1008 with different UTR numbers. The bank sent
> the same payment twice. The agent detected this before matching started, so neither
> leg was silently consumed. A human needs to confirm which UTR is the real settlement."

**TXN1041 — amount_mismatch**
> "The bank settled Rs.X but the ledger says net payable was Rs.Y — a Rs.Z delta.
> This is above the Rs.1 rounding tolerance. The agent flagged it rather than accepting
> the wrong amount. This is exactly the kind of discrepancy that would get missed in
> manual reconciliation at scale."

**TXN1021 — missing_settlement**
> "No settlement row exists for this transaction anywhere in the bank file. It wasn't
> late — it simply isn't there. The agent surfaced this explicitly so the finance team
> can chase the bank for the missing batch entry."

---

## Step 4 — Open the HTML dashboard (15 seconds)

```bash
start output/reconciliation_report.html
```
(or `open` on macOS / `xdg-open` on Linux)

**Say:** "The dashboard shows the same information visually — a match vs exceptions
pie chart, exception breakdown bar chart, and a scrollable exceptions table with the
Claude narration column when the API key is configured."

---

## Closing line

> "This agent closes the reconciliation loop for a 80-record batch in under a second.
> Scale it to 5,000 records and the only thing that changes is the input files — the
> pipeline, the precision guarantee, and the honest exception list stay exactly the same."

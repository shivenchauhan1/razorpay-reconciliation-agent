# Razorpay Payment Reconciliation Agent


> **Track 04 — AI Finance Controller**
> Closes the payment gateway ↔ bank settlement reconciliation loop across an 80-record batch. Reports match rate, precision against ground truth, and an honest exception list with plain-English explanations.

## AI Design Principle

**The deterministic reconciliation engine is the source of truth. Gemini is an explanation layer only.**

Gemini receives exceptions that have already been classified by deterministic rules. It does not decide transaction matches, exception types, metrics, or financial outcomes. If the API is unavailable, deterministic fallback explanations keep the pipeline running.

---

## Problem


Every payment collected through Razorpay is recorded internally as a transaction (with fees, GST, and net payable amount). Separately, banks settle these funds in lump-sum batches via UTR numbers — often a day or more later, minus deductions. Finance teams must manually verify that every transaction is accounted for in a settlement batch and investigate the ones that aren't.

This is slow, manual, and error-prone at scale. At 50–500 transactions per batch, even a 2 % discrepancy rate means dozens of open questions a week that someone has to chase.

**This agent automates that loop end-to-end.**

---

## What It Does


1. **Matches** transactions to settlements via a two-pass pipeline (exact + fuzzy)
2. **Classifies** every unresolved row into one of six exception types using deterministic rules
3. **Narrates** each exception in plain English using Gemini (optional — falls back gracefully)
4. **Reports** match rate + precision + exception recall against a ground truth oracle
5. **Outputs** a CSV ledger and an interactive HTML dashboard

The matching logic is intentionally rule-based — not ML. Finance reconciliation must be auditable. A rules engine is a *feature*, not a limitation.

---

## Architecture


```
run_agent.py (orchestrator)
  |
  +-- [1/7] src/generate_data.py     Generate 80 ledger + settlement rows
  |                                  Inject 15 exceptions across 5 types
  |                                  Write ground_truth.json oracle
  |
  +-- [2/7] src/loaders.py           Load ledger.csv + settlements.csv
  |                                  Typed DataFrames (dates parsed, amounts float64)
  |
  +-- PRE  classify_exceptions.py    compute_duplicate_order_ids()
  |        (pre-scan before any row is consumed by matching)
  |
  +-- [3/7] src/match_exact.py       Join on order_id
  |                                  Amount tolerance: Rs.1.00
  |                                  Date window: T+0 to T+3
  |                                  Duplicates held back (not consumed)
  |
  +-- [4/7] src/match_fuzzy.py       Amount tolerance: Rs.5.00, date window 3 days
  |                                  0 candidates -> stays unmatched
  |                                  1 candidate  -> fuzzy match (low confidence)
  |                                  2+ candidates -> ambiguous, sent to exceptions
  |
  +-- [5/7] src/classify_exceptions.py  6-rule priority chain:
  |                                     1. duplicate_settlement
  |                                     2. amount_mismatch
  |                                     3. partial_settlement
  |                                     4. timing_mismatch
  |                                     5. missing_settlement
  |                                     6. ambiguous_match
  |
  +-- [6/7] src/explain.py           Gemini API (one batch call for all exceptions)
  |                                  Fallback: deterministic per-type explanation
  |                                  Model read from GEMINI_MODEL env var
  |
  +-- [7/7] src/metrics.py           match_rate, precision, exception_recall
            src/report.py            reconciliation_report.csv
                                     reconciliation_report.html (Chart.js dashboard)

```

**svg**

---

## Setup


```
# 1. Clone / navigate to repo root
cd razorpay-recon-agent

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure API key (optional — only needed for LLM narration)
cp .env.example .env
# Edit .env and set GEMINI_API_KEY=your_gemini_api_key
# Optionally set GEMINI_MODEL=gemini-2.5-flash (default)
```

**svg**

---

## Usage


```
# Full pipeline: generate data + reconcile + report
python run_agent.py

# Skip data generation (reuse existing data/)
python run_agent.py --skip-generate
```

**svg**

Outputs are written to `output/`:

- `reconciliation_report.csv` — one row per ledger record
- `reconciliation_report.html` — interactive dashboard (open in any browser)

---

## Sample Output


```
============================================================
  Razorpay Payment Reconciliation Agent
============================================================

[1/7] Generating synthetic data
[generate_data] Written 80 ledger rows -> data/ledger.csv
[generate_data] Clean (expect matched): 65
[generate_data] Injected exception conditions: 18 (includes garbled_order_id recovered by fuzzy pass)
[generate_data] Final unreconciled exceptions (ground truth): 15
              amount_mismatch: 3
              duplicate_settlement: 3
              missing_settlement: 3
              partial_settlement: 3
              timing_mismatch: 3

[3/7] Exact matching (order_id join + Rs.1.00 tolerance)
       Exact matches: 62 | Unmatched ledger: 18

[4/7] Fuzzy matching (amount +/- Rs.5.00, date window 3 days)
       Fuzzy matches: 3 | Still unmatched: 15

[5/7] Classifying exceptions
       Exceptions classified: 15
         duplicate_settlement    3
         amount_mismatch         3
         partial_settlement      3
         timing_mismatch         3
         missing_settlement      3

----------------------------------------------------
  RECONCILIATION METRICS
----------------------------------------------------
  Total ledger rows      : 80
  Exact matches          : 62
  Fuzzy matches          : 3
  Total matched          : 65
  Exceptions flagged     : 15
----------------------------------------------------
  Match rate             : 81.2%
  Precision (vs GT)      : 100.0%
  Exception recall       : 100.0%
----------------------------------------------------

```

**svg**

---

## Dashboard Preview

The generated HTML dashboard provides a finance-ops view of the reconciliation results, including key metrics, exception distribution, the deterministic-vs-AI architecture, and detailed exception explanations.

### Key Metrics & Exception Overview

![Dashboard metrics and exception overview](assets/Screenshot%202026-09-05%20010951.png)

### Reconciliation Architecture

The dashboard makes the separation between the deterministic financial engine and Gemini explanation layer explicit.

![Deterministic engine and Gemini explanation layer](assets/Screenshot%202026-09-05%20011247.png)

### Exception Detail

Each unresolved transaction includes the deterministic finding alongside either a Gemini-generated explanation or a deterministic fallback.

![Exception detail table](assets/Screenshot%202026-09-05%20011351.png)

## Metrics


| **MetricValueWhat it means** |         |                                                            |
| ---------------------------- | ------- | ---------------------------------------------------------- |
| **Match rate**               | 81.2 %  | 65 of 80 records reconciled                                |
| **Precision**                | 100.0 % | Every match the agent made was correct per ground truth    |
| **Exception recall**         | 100.0 % | Every ground-truth exception was correctly left unresolved |

### Why match rate alone is insufficient


A lazy agent could "match" everything and report 100 % match rate — even if most matches are wrong. **Precision** is the metric that proves the matches are correct. And **exception recall** proves the agent didn't cheat by force-matching bad pairs.

Reporting all three — with ground-truth verification — is what makes the accuracy claim defensible.

---

## Exception Types


| **TypeHow it's createdHow it's detected** |                                                     |                                                                |
| ----------------------------------------- | --------------------------------------------------- | -------------------------------------------------------------- |
| `duplicate_settlement`                    | Two settlement rows for same order\_id              | Pre-scan before matching; order\_id count > 1                  |
| `amount_mismatch`                         | settled\_amount differs from net\_amount by Rs.5–50 | Closest candidate found but delta > Rs.1.00 and >= 90 % of net |
| `partial_settlement`                      | settled\_amount is 50–75 % of net\_amount           | Closest candidate but settled < 90 % of net                    |
| `timing_mismatch`                         | Settlement date is T+5 to T+7 (beyond T+3 window)   | Exact matcher rejects; classifier detects via date delta       |
| `missing_settlement`                      | Settlement row removed entirely                     | No candidate found in any pool                                 |
| `ambiguous_match`                         | (fuzzy pass: 2+ candidates)                         | Fuzzy pass refuses to pick; flagged explicitly                 |

---

## Data Schema


**ledger.csv**

| **FieldTypeDescription** |        |                                  |
| ------------------------ | ------ | -------------------------------- |
| txn\_id                  | string | TXN1001–TXN1080                  |
| order\_id                | string | O1001–O1080                      |
| amount                   | float  | Gross charged amount             |
| method                   | string | UPI / CARD / NETBANKING / WALLET |
| fee                      | float  | 2 % of amount                    |
| gst\_on\_fee             | float  | 18 % of fee                      |
| net\_amount              | float  | amount - fee - gst\_on\_fee      |
| txn\_date                | date   | 2026-08-01 to 2026-08-20         |
| status                   | string | captured / refunded              |

**settlements.csv**

| **FieldTypeDescription** |        |                                                |
| ------------------------ | ------ | ---------------------------------------------- |
| utr\_number              | string | Unique bank transaction reference              |
| order\_id                | string | Join key (may be blank/garbled for exceptions) |
| settled\_amount          | float  | Amount bank actually paid                      |
| settlement\_date         | date   | Usually T+1                                    |
| batch\_id                | string | Groups multiple settlements                    |

---

## Project Structure


```
razorpay-recon-agent/
├── data/
│   ├── ledger.csv              (generated)
│   ├── settlements.csv         (generated)
│   └── ground_truth.json       (generated — oracle for metrics)
├── src/
│   ├── generate_data.py        Data generation + exception injection
│   ├── loaders.py              Typed CSV loaders
│   ├── match_exact.py          First-pass reconciliation
│   ├── match_fuzzy.py          Second-pass reconciliation
│   ├── classify_exceptions.py  6-rule exception tagger
│   ├── explain.py              Gemini narration layer
│   ├── metrics.py              Ground-truth-verified metrics
│   └── report.py               CSV + HTML report generator
├── output/
│   ├── reconciliation_report.csv
│   └── reconciliation_report.html
├── run_agent.py                Single orchestrator entry point
├── requirements.txt
├── .env.example
├── .gitignore
├── DEMO.md
└── README.md

```

**svg**

---

## Known Limitations


1. **Synthetic data only** — real Razorpay batches would need connector code to pull from the actual settlement API and internal ledger.
2. **Garbled order\_id fuzzy matching** — the fuzzy pass recovers single-candidate garbled IDs but doesn't use edit-distance string matching (Levenshtein). Adding that would improve recall for more heavily corrupted IDs.
3. **LLM cost at scale** — one API call per exception row works for 15–20 exceptions per batch, but would need batching or caching for thousands.
4. **No deduplication across batches** — the agent reconciles one batch at a time; cross-batch duplicate detection is out of scope.
5. **Fixed fee/GST rates** — the 2 %/18 % rates are constants. Real Razorpay fees vary by payment method and merchant agreement.
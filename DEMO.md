# Demo

This document provides a quick walkthrough of the Razorpay Payment Reconciliation Agent and explains what to expect when running the project.

## 1. Setup

From the project directory:

```bash
pip install -r requirements.txt
```

For Gemini-powered exception explanations, create a `.env` file using `.env.example`:

```env
GEMINI_API_KEY=your_api_key_here
```

The `.env` file must not be committed to GitHub.

---

## 2. Run the Agent

Run the complete reconciliation pipeline with:

```bash
python run_agent.py
```

The pipeline performs the following stages:

1. Generate synthetic payment and settlement data
2. Load the ledger and settlement files
3. Perform deterministic exact matching
4. Perform fuzzy matching on unmatched records
5. Classify unresolved exceptions
6. Generate Gemini-powered explanations
7. Calculate metrics and generate the reports

The entire process is executed with a single command.

---

## 3. Expected Results

The current synthetic dataset contains **80 payment transactions**.

A successful run produces:

```text
Total ledger rows: 80
Exact matches: 62
Fuzzy matches: 3
Total matched: 65
Exceptions flagged: 15

Match rate: 81.2%
Precision: 100.0%
Exception recall: 100.0%
```

### What the metrics mean

**Match Rate — 81.2%**

65 of the 80 ledger transactions were successfully reconciled.

**Precision — 100%**

Every transaction that the reconciliation engine marked as matched agrees with the ground-truth dataset.

**Exception Recall — 100%**

All 15 intentionally injected unreconciled cases were correctly identified as exceptions.

The system does not force-match unresolved records simply to increase the match rate.

---

## 4. Exception Types

The current dataset contains five types of unresolved exceptions:

| Exception              | Count | Description                                                                       |
| ---------------------- | ----: | --------------------------------------------------------------------------------- |
| `amount_mismatch`      |     3 | Settlement amount differs from the expected ledger amount beyond the ₹1 tolerance |
| `duplicate_settlement` |     3 | Multiple settlement records exist for the same order                              |
| `missing_settlement`   |     3 | No corresponding settlement record exists                                         |
| `partial_settlement`   |     3 | The settlement amount is lower than the expected amount                           |
| `timing_mismatch`      |     3 | A valid settlement exists but falls outside the expected settlement window        |

The reconciliation engine also performs fuzzy recovery for certain corrupted or garbled order IDs. These records can still be safely matched when exactly one valid candidate satisfies the matching rules.

---

## 5. Reconciliation Logic

The matching process is deliberately deterministic.

### Exact Matching

The first pass matches records using strong identifiers and amount/date constraints.

Amount differences within **₹1** are treated as acceptable rounding differences.

### Fuzzy Matching

Records that cannot be matched exactly are passed to a second matching stage.

The fuzzy matcher uses:

* Order ID similarity
* Amount tolerance
* Settlement date window

A fuzzy match is accepted only when there is **exactly one valid candidate**.

If multiple candidates are possible, the system does not guess and instead reports an `ambiguous_match`.

### Exception Classification

Records that remain unmatched are classified using deterministic business rules.

The exception priority is:

```text
duplicate
→ amount_mismatch
→ partial_settlement
→ timing_mismatch
→ missing_settlement
→ ambiguous_match
```

---

## 6. AI Explanation Layer

Gemini is used only as an **explanation layer**.

The AI does **not**:

* Decide whether transactions match
* Determine exception types
* Calculate financial metrics
* Override deterministic rules
* Resolve ambiguous transactions

The deterministic reconciliation engine remains the source of truth.

Gemini converts the already-classified exceptions into concise explanations that are easier for finance-ops teams to understand.

If the Gemini API is unavailable, the pipeline automatically uses deterministic fallback explanations and continues successfully.

---

## 7. Generated Reports

After a successful run, the project generates:

```text
output/
├── reconciliation_report.csv
└── reconciliation_report.html
```

### CSV Report

The CSV contains the reconciliation results for each transaction, including:

* Transaction ID
* Order ID
* Match status
* Match method
* Exception type
* Amount information
* Timing information
* Explanation

### HTML Dashboard

The HTML report provides a visual overview of the reconciliation:

* Match rate
* Precision
* Exception recall
* Matched vs. exception breakdown
* Exception type distribution
* Detailed exception table
* Rule-based classification
* Gemini-generated explanations
* Fallback explanations when AI narration is unavailable

To open the dashboard on Windows:

```bash
start output/reconciliation_report.html
```

---

## 8. Example Exceptions

The generated dataset contains representative finance-ops scenarios.

### TXN1008 — Duplicate Settlement

The settlement file contains multiple settlement records for the same order. The duplicate is detected before normal matching so that a settlement row is not silently consumed.

### TXN1041 — Amount Mismatch

The bank settlement amount differs from the expected ledger amount by more than the configured ₹1 tolerance. The transaction is flagged instead of being incorrectly reconciled.

### TXN1021 — Missing Settlement

No corresponding settlement record exists in the bank settlement file. The transaction is reported as a missing settlement and requires finance-ops investigation.

---

## 9. Key Design Principle

The project separates **financial decision-making** from **AI-generated communication**.

```text
                RECONCILIATION PIPELINE

Ledger + Bank Settlement Files
              │
              ▼
     Deterministic Engine
              │
       ┌──────┴──────┐
       ▼             ▼
   Matched       Exceptions
       │             │
       │             ▼
       │       Gemini Explanation
       │             │
       └──────┬──────┘
              ▼
       Metrics + Reports
```

The deterministic engine provides the financial source of truth.

Gemini improves the readability of the resulting exceptions without controlling the underlying reconciliation decisions.

---

## 10. Demo Flow

For a quick demonstration:

```bash
python run_agent.py
```

Then open:

```bash
start output/reconciliation_report.html
```

The complete workflow can be demonstrated from data generation through reconciliation, exception analysis, metrics, and dashboard generation using these two commands.

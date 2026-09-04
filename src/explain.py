"""
explain.py â€” Provider-agnostic LLM narration layer.

Enriches each exception row with a plain-English explanation.
The matching and classification are already complete before this runs â€”
this is purely a communication layer for human finance reviewers.

Provider selection via LLM_PROVIDER env var:
    gemini     (default) â€” Google Gemini via google-genai SDK (ONE batch request)
    anthropic             â€” Anthropic Claude via anthropic SDK (one call per row)
    none                  â€” Skip LLM calls entirely

Required env vars per provider:
    gemini:    GEMINI_API_KEY, GEMINI_MODEL (default: gemini-2.0-flash)
    anthropic: ANTHROPIC_API_KEY, ANTHROPIC_MODEL (default: claude-haiku-3-5)

If the API key is absent or the batch call fails, deterministic fallback
explanations are used per exception type â€” the pipeline never crashes.

Exported function:
    explain_exceptions(exceptions_df) -> exceptions_df  (adds 'llm_explanation' column)
"""

import json
import os
import re

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

FALLBACK = "[LLM narration unavailable]"

# ---------------------------------------------------------------------------
# Deterministic fallback explanations keyed by exception_type.
# Used when Gemini is unavailable OR when a specific row is missing from
# the batch response.
# ---------------------------------------------------------------------------
FALLBACK_BY_TYPE: dict[str, str] = {
    "duplicate_settlement": (
        "Two settlement rows were found for this order ID. "
        "The bank may have sent the payment twice. "
        "Verify which UTR is the authoritative settlement and void the duplicate."
    ),
    "amount_mismatch": (
        "The settled amount does not match the expected net payable amount. "
        "The delta exceeds the Rs.1.00 rounding tolerance. "
        "Contact the bank to confirm whether a fee adjustment or correction credit is pending."
    ),
    "partial_settlement": (
        "The bank settled only a fraction of the expected net amount. "
        "This may indicate a partial refund netting or a bank processing error. "
        "Check the original transaction status and raise a query with the acquiring bank."
    ),
    "timing_mismatch": (
        "The settlement arrived more than 3 days after the transaction date. "
        "This exceeds the expected T+3 settlement window. "
        "Confirm with the bank whether a batch processing delay caused the late credit."
    ),
    "missing_settlement": (
        "No settlement row was found for this transaction in the bank file. "
        "The payment may have been excluded from the current batch. "
        "Check whether a subsequent batch covers this transaction or raise a chargeback query."
    ),
    "ambiguous_match": (
        "Multiple possible settlement candidates were found but none could be safely selected. "
        "Manual review is required to identify the correct settlement row."
    ),
}

SYSTEM_PROMPT = """\
You are a finance operations assistant for Razorpay, a payment gateway.
Your job is to explain payment reconciliation exceptions to human finance reviewers.

Rules:
- Only use the data provided. Do not invent figures, dates, or IDs.
- Be concise: 2-3 sentences per exception.
- Name the specific transaction ID, amounts, and dates from the data.
- End each explanation with one clear suggested next action for the reviewer.
- Do not include any preamble, greeting, or meta-commentary.
"""


# ---------------------------------------------------------------------------
# Prompt builder â€” single row summary (used inside the batch prompt)
# ---------------------------------------------------------------------------

def _row_summary(row: dict) -> str:
    supporting = {}
    try:
        supporting = json.loads(row.get("supporting_data", "{}"))
    except (json.JSONDecodeError, TypeError):
        pass

    parts = [
        f"Transaction ID: {row['txn_id']}",
        f"Order ID: {row['order_id']}",
        f"Exception type: {row['exception_type']}",
        f"Reason: {row['reason']}",
    ]
    for key in (
        "net_amount", "settled_amount", "amount_delta",
        "txn_date", "settlement_date", "day_diff",
        "utr_number", "utr_numbers", "duplicate_count", "timing_note",
    ):
        if key in supporting:
            label = key.replace("_", " ").capitalize()
            parts.append(f"{label}: {supporting[key]}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Batch prompt builder
# ---------------------------------------------------------------------------

def _build_batch_prompt(rows: list[dict]) -> str:
    sections = [SYSTEM_PROMPT, ""]
    sections.append(
        "Below are payment reconciliation exceptions. "
        "For EACH exception, write exactly one concise explanation (2-3 sentences) "
        "that names the transaction ID, key amounts/dates, and ends with a suggested action.\n"
        "Format your response EXACTLY as shown â€” one block per exception, "
        "separated by a blank line, starting with the transaction ID on its own line:\n"
        "TXN_ID\n<explanation text>\n"
    )
    for i, row in enumerate(rows, 1):
        sections.append(f"--- Exception {i} ---")
        sections.append(_row_summary(row))
        sections.append("")
    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def _parse_batch_response(response_text: str, rows: list[dict]) -> list[str]:
    """
    Parse Gemini's batch response into one explanation per row.

    Expected format per block:
        TXN1041
        <explanation text>

    Falls back to the deterministic explanation for any missing or
    unmatched transaction ID.
    """
    # Build a lookup: txn_id (upper) -> row index
    txn_order = {row["txn_id"].upper(): i for i, row in enumerate(rows)}
    results: list[str | None] = [None] * len(rows)

    # Split on blank lines to isolate blocks; each block should start with a txn_id
    blocks = re.split(r"\n{2,}", response_text.strip())
    for block in blocks:
        lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]
        if not lines:
            continue
        # First non-empty line that matches a known txn_id is the key
        matched_idx = None
        explanation_lines = []
        for j, line in enumerate(lines):
            candidate = line.upper().strip(":-. ")
            if candidate in txn_order:
                matched_idx = txn_order[candidate]
                explanation_lines = lines[j + 1:]
                break
        if matched_idx is not None and explanation_lines:
            results[matched_idx] = " ".join(explanation_lines)

    # Fill any gaps with the deterministic fallback for that exception type
    for i, (result, row) in enumerate(zip(results, rows)):
        if not result:
            exc_type = row.get("exception_type", "")
            results[i] = FALLBACK_BY_TYPE.get(exc_type, FALLBACK)

    return results  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Provider: Gemini  â€” ONE batch request for all rows
# ---------------------------------------------------------------------------

def _explain_gemini(rows: list[dict], model: str, api_key: str) -> list[str]:
    try:
        from google import genai  # noqa: PLC0415
        from google.genai import types  # noqa: PLC0415
    except ImportError:
        print("[explain][gemini] google-genai package not installed â€” using deterministic fallbacks")
        return _deterministic_fallbacks(rows)

    client = genai.Client(api_key=api_key)
    total = len(rows)

    print(f"[explain][gemini] Sending {total} exceptions in one batch request")
    try:
        batch_prompt = _build_batch_prompt(rows)
        response = client.models.generate_content(
            model=model,
            contents=batch_prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=150 * total,  # ~150 tokens per explanation
                temperature=0.2,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True,
                ),
            ),
        )
        print("[explain][gemini] Batch narration completed")
        return _parse_batch_response(response.text, rows)

    except Exception as exc:  # noqa: BLE001
        print(f"[explain][gemini] Warning: batch call failed: {exc}")
        print("[explain][gemini] Using deterministic fallback explanations")
        return _deterministic_fallbacks(rows)


def _deterministic_fallbacks(rows: list[dict]) -> list[str]:
    return [
        FALLBACK_BY_TYPE.get(row.get("exception_type", ""), FALLBACK)
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Provider: Anthropic  â€” one call per row (unchanged behaviour)
# ---------------------------------------------------------------------------

def _explain_anthropic(rows: list[dict], model: str, api_key: str) -> list[str]:
    try:
        import anthropic  # noqa: PLC0415
    except ImportError:
        print("[explain] anthropic package not installed â€” skipping LLM narration")
        return [FALLBACK] * len(rows)

    client = anthropic.Anthropic(api_key=api_key)
    results = []
    total = len(rows)

    for i, row in enumerate(rows, 1):
        print(f"[explain][anthropic] {i}/{total}: {row['txn_id']} ({row['exception_type']})")
        try:
            user_text = _row_summary(row)
            response = client.messages.create(
                model=model,
                max_tokens=200,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_text}],
            )
            results.append(response.content[0].text.strip())
        except Exception as exc:  # noqa: BLE001
            print(f"[explain][anthropic] Warning: call failed for {row['txn_id']}: {exc}")
            exc_type = row.get("exception_type", "")
            results.append(FALLBACK_BY_TYPE.get(exc_type, FALLBACK))

    return results


# ---------------------------------------------------------------------------
# Public entry point  â€” interface unchanged
# ---------------------------------------------------------------------------

def explain_exceptions(exceptions_df: pd.DataFrame) -> pd.DataFrame:
    """
    Enrich exceptions_df with a 'llm_explanation' column.

    Provider is selected via LLM_PROVIDER env var (default: gemini).
    Gemini uses ONE batch API call for all rows.
    Falls back to deterministic per-type explanations on any error.
    """
    df = exceptions_df.copy()

    if df.empty:
        df["llm_explanation"] = pd.Series(dtype="object")
        return df

    provider = os.getenv("LLM_PROVIDER", "gemini").lower().strip()

    if provider == "none":
        print("[explain] LLM_PROVIDER=none â€” skipping narration")
        df["llm_explanation"] = FALLBACK
        return df

    rows = df.to_dict("records")

    if provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY", "")
        model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        if not api_key:
            print("[explain] GEMINI_API_KEY not set â€” using deterministic fallback explanations")
            df["llm_explanation"] = _deterministic_fallbacks(rows)
            return df
        explanations = _explain_gemini(rows, model, api_key)

    elif provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        model = os.getenv("ANTHROPIC_MODEL", "claude-haiku-3-5")
        if not api_key or api_key.startswith("sk-ant-..."):
            print("[explain] ANTHROPIC_API_KEY not set â€” skipping LLM narration")
            df["llm_explanation"] = FALLBACK
            return df
        explanations = _explain_anthropic(rows, model, api_key)

    else:
        print(f"[explain] Unknown LLM_PROVIDER '{provider}' â€” skipping narration")
        df["llm_explanation"] = FALLBACK
        return df

    df["llm_explanation"] = explanations
    return df

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# -----------------------------------------------------------------------------
# Repository paths / imports
# -----------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output"
SRC_DIR = REPO_ROOT / "src"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.classify_exceptions import classify_exceptions, compute_duplicate_order_ids
from src.explain import explain_exceptions
from src.generate_data import generate
from src.loaders import load_ledger, load_settlements
from src.match_exact import match_exact
from src.match_fuzzy import match_fuzzy
from src.metrics import compute_metrics
from src.report import _classify_explanation, generate_report


# -----------------------------------------------------------------------------
# Page / styling
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Razorpay Reconciliation Agent",
    page_icon="₹",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    .hero {
        padding: 1.4rem 1.6rem;
        border: 1px solid rgba(128,128,128,.25);
        border-radius: 16px;
        margin-bottom: 1.2rem;
    }
    .hero h1 { margin: 0 0 .35rem 0; }
    .hero p { margin: 0; opacity: .78; }
    .source-pill {
        display: inline-block;
        padding: .2rem .55rem;
        border-radius: 999px;
        font-size: .78rem;
        font-weight: 600;
        border: 1px solid rgba(128,128,128,.3);
        margin-right: .35rem;
    }
    .deterministic { background: rgba(100,100,100,.08); }
    .ai { background: rgba(45,130,80,.10); }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
        <h1>Razorpay Payment Reconciliation Agent</h1>
        <p>Deterministic financial reconciliation with optional Gemini explanations.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# Secrets / provider configuration
# -----------------------------------------------------------------------------
def _secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, default)
    except Exception:
        value = default
    return str(value or "")


secret_gemini_key = _secret("GEMINI_API_KEY")
secret_gemini_model = _secret("GEMINI_MODEL", "gemini-2.0-flash")

with st.sidebar:
    st.header("Run configuration")

    provider_options = ["none", "gemini"]
    default_provider = "gemini" if secret_gemini_key else "none"
    provider = st.selectbox(
        "Explanation provider",
        provider_options,
        index=provider_options.index(default_provider),
        help="Gemini only explains already-classified exceptions. It does not perform matching.",
    )

    if provider == "gemini":
        model = st.text_input("Gemini model", value=secret_gemini_model)
        if not secret_gemini_key:
            st.warning("GEMINI_API_KEY is not configured. The app will use deterministic fallback explanations.")
    else:
        model = ""
        st.info("LLM narration is disabled. Deterministic explanations will be used.")

    run_clicked = st.button("Run reconciliation", type="primary", use_container_width=True)
    clear_clicked = st.button("Clear results", use_container_width=True)

    st.divider()
    st.caption("Synthetic dataset: 80 ledger records with injected reconciliation exceptions.")


if clear_clicked:
    st.session_state.pop("result", None)
    st.rerun()

if run_clicked:
    # Configure the explanation layer before executing it.
    os.environ["LLM_PROVIDER"] = provider
    if provider == "gemini":
        os.environ["GEMINI_API_KEY"] = secret_gemini_key
        os.environ["GEMINI_MODEL"] = model or secret_gemini_model

    try:
        with st.status("Running reconciliation pipeline...", expanded=True) as status:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

            status.write("1/7 — Generating synthetic ledger and settlement data")
            generate(output_dir=str(DATA_DIR))

            status.write("2/7 — Loading ledger and settlement files")
            ledger_df = load_ledger(DATA_DIR / "ledger.csv")
            settlements_df = load_settlements(DATA_DIR / "settlements.csv")

            status.write("3/7 — Exact matching")
            duplicate_order_ids = compute_duplicate_order_ids(settlements_df)
            matched_exact, unmatched_ledger, unmatched_sett = match_exact(
                ledger_df,
                settlements_df,
                duplicate_order_ids=duplicate_order_ids,
            )

            status.write("4/7 — Fuzzy matching")
            matched_fuzzy, still_unmatched_ledger, still_unmatched_sett = match_fuzzy(
                unmatched_ledger,
                unmatched_sett,
            )
            matched_df = pd.concat([matched_exact, matched_fuzzy], ignore_index=True)

            status.write("5/7 — Deterministic exception classification")
            exceptions_df = classify_exceptions(
                unmatched_ledger_df=still_unmatched_ledger,
                unmatched_settlements_df=still_unmatched_sett,
                all_settlements_df=settlements_df,
                duplicate_order_ids=duplicate_order_ids,
            )

            status.write("6/7 — Exception narration")
            exceptions_df = explain_exceptions(exceptions_df)

            status.write("7/7 — Metrics and report generation")
            metrics = compute_metrics(
                matched_df=matched_df,
                exceptions_df=exceptions_df,
                ground_truth_path=DATA_DIR / "ground_truth.json",
                total_ledger_rows=len(ledger_df),
            )
            generate_report(
                matched_df=matched_df,
                exceptions_df=exceptions_df,
                metrics_dict=metrics,
                output_dir=str(OUTPUT_DIR),
            )

            status.update(label="Reconciliation completed", state="complete", expanded=False)

        st.session_state["result"] = {
            "ledger": ledger_df,
            "settlements": settlements_df,
            "matched": matched_df,
            "exceptions": exceptions_df,
            "metrics": metrics,
            "provider": provider,
            "model": model,
        }
        st.success("Reconciliation completed successfully.")
    except Exception as exc:
        st.error(f"Pipeline failed: {type(exc).__name__}: {exc}")
        with st.expander("Technical error details"):
            st.exception(exc)


result = st.session_state.get("result")

if result is None:
    st.info("Click **Run reconciliation** in the sidebar to execute the full agent.")
    st.markdown("### Deployment checklist")
    st.code(
        """Repository: shivenchauhan1/razorpay-reconciliation-agent
Branch: main
Main file: app.py
Python: 3.11+
Secrets: GEMINI_API_KEY (optional)\n"""
    )
    st.stop()


ledger_df: pd.DataFrame = result["ledger"]
settlements_df: pd.DataFrame = result["settlements"]
matched_df: pd.DataFrame = result["matched"]
exceptions_df: pd.DataFrame = result["exceptions"]
metrics: dict = result["metrics"]
provider = result["provider"]
model = result["model"]
raw = metrics["raw_counts"]


# -----------------------------------------------------------------------------
# Dashboard header / KPIs
# -----------------------------------------------------------------------------
st.caption(
    f"Last run: deterministic engine + {provider} narration"
    + (f" ({model})" if provider == "gemini" and model else "")
)

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total records", raw["total_ledger_rows"])
k2.metric("Match rate", f"{metrics['match_rate'] * 100:.1f}%")
k3.metric("Precision", f"{metrics['precision'] * 100:.1f}%")
k4.metric("Exception recall", f"{metrics['exception_recall'] * 100:.1f}%")
k5.metric("Exceptions", raw["total_exceptions"])


tab_overview, tab_matches, tab_exceptions, tab_data, tab_arch = st.tabs(
    ["Overview", "Matched Transactions", "Exceptions", "Raw Data", "Architecture"]
)

with tab_overview:
    left, right = st.columns(2)

    with left:
        st.subheader("Reconciliation outcome")
        outcome_df = pd.DataFrame(
            {
                "Outcome": ["Exact matched", "Fuzzy matched", "Exceptions"],
                "Count": [raw["exact_matches"], raw["fuzzy_matches"], raw["total_exceptions"]],
            }
        )
        st.bar_chart(outcome_df.set_index("Outcome"))

    with right:
        st.subheader("Exception breakdown")
        breakdown = metrics.get("exception_breakdown", {})
        if breakdown:
            breakdown_df = (
                pd.Series(breakdown, name="Count")
                .sort_values(ascending=False)
                .to_frame()
            )
            breakdown_df.index = breakdown_df.index.str.replace("_", " ").str.title()
            st.bar_chart(breakdown_df)
        else:
            st.success("No exceptions detected.")

    st.subheader("AI vs deterministic responsibility")
    st.markdown(
        """
        **Deterministic engine:** exact matching, fuzzy matching, exception classification, and metrics.

        **Gemini:** plain-English narration only. When Gemini is unavailable or disabled, the app uses deterministic fallback explanations.
        """
    )

    summary_df = pd.DataFrame(
        [
            ["Deterministic", "Exact + fuzzy matching", "Financial source of truth"],
            ["Deterministic", "Exception classification", "Financial source of truth"],
            ["Deterministic", "Metrics / ground-truth checks", "Financial source of truth"],
            ["AI (optional)", "Exception narration", "Communication layer only"],
        ],
        columns=["Layer", "Responsibility", "Role"],
    )
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

with tab_matches:
    st.subheader(f"Matched transactions ({len(matched_df)})")
    if matched_df.empty:
        st.warning("No matched rows.")
    else:
        display_cols = [
            c for c in [
                "txn_id", "order_id", "utr_number", "net_amount", "settled_amount",
                "txn_date", "settlement_date", "match_type", "confidence"
            ] if c in matched_df.columns
        ]
        st.dataframe(
            matched_df[display_cols],
            use_container_width=True,
            hide_index=True,
        )

        csv_bytes = matched_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download matched transactions CSV",
            data=csv_bytes,
            file_name="matched_transactions.csv",
            mime="text/csv",
        )

with tab_exceptions:
    st.subheader(f"Exceptions requiring review ({len(exceptions_df)})")

    if exceptions_df.empty:
        st.success("No exceptions found.")
    else:
        # Add a user-facing source label without changing the original backend data.
        exception_view = exceptions_df.copy()
        source = exception_view["llm_explanation"].fillna("").astype(str).apply(_classify_explanation)
        exception_view["explanation_source"] = source.apply(
            lambda x: "AI" if x[0] else ("Deterministic fallback" if x[1] else "Unavailable")
        )

        st.dataframe(
            exception_view[
                [
                    c for c in [
                        "txn_id", "order_id", "exception_type", "reason",
                        "explanation_source", "llm_explanation"
                    ]
                    if c in exception_view.columns
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("#### Exception details")
        for _, row in exception_view.iterrows():
            label = f"{row['txn_id']} · {str(row['exception_type']).replace('_', ' ').title()}"
            with st.expander(label):
                st.write(f"**Order ID:** {row.get('order_id', '')}")
                st.write(f"**Deterministic reason:** {row.get('reason', '')}")
                st.write(f"**Explanation source:** {row.get('explanation_source', '')}")
                st.write(f"**Explanation:** {row.get('llm_explanation', '')}")

        report_df = pd.concat(
            [
                matched_df.assign(exception_type="", match_type=matched_df.get("match_type", "matched")),
                exceptions_df.assign(match_type="exception"),
            ],
            ignore_index=True,
            sort=False,
        )
        st.download_button(
            "Download complete reconciliation CSV",
            data=report_df.to_csv(index=False).encode("utf-8"),
            file_name="reconciliation_report.csv",
            mime="text/csv",
        )

with tab_data:
    st.subheader("Ledger")
    st.dataframe(ledger_df, use_container_width=True, hide_index=True)

    st.subheader("Settlements")
    st.dataframe(settlements_df, use_container_width=True, hide_index=True)

    c1, c2 = st.columns(2)
    c1.download_button(
        "Download ledger.csv",
        data=ledger_df.to_csv(index=False).encode("utf-8"),
        file_name="ledger.csv",
        mime="text/csv",
    )
    c2.download_button(
        "Download settlements.csv",
        data=settlements_df.to_csv(index=False).encode("utf-8"),
        file_name="settlements.csv",
        mime="text/csv",
    )

with tab_arch:
    st.subheader("Pipeline")
    st.code(
        """Ledger + bank settlements
          ↓
    Pre-scan duplicate order IDs
          ↓
    Exact matching
    • order_id join
    • ±₹1 amount tolerance
    • T+0 to T+3 date window
          ↓
    Fuzzy matching
    • ±₹5 amount tolerance
    • T+0 to T+3 date window
    • single candidate only
          ↓
    Deterministic exception classification
    • duplicate settlement
    • amount mismatch
    • partial settlement
    • timing mismatch
    • missing settlement
    • ambiguous match
          ↓
    Optional Gemini narration
          ↓
    Ground-truth metrics + report
"""
    )

    st.subheader("Current run counts")
    counts_df = pd.DataFrame({"Metric": list(raw.keys()), "Value": list(raw.values())})
    st.dataframe(counts_df, use_container_width=True, hide_index=True)

    st.subheader("Generated files")
    generated = []
    for path in [
        DATA_DIR / "ledger.csv",
        DATA_DIR / "settlements.csv",
        DATA_DIR / "ground_truth.json",
        OUTPUT_DIR / "reconciliation_report.csv",
        OUTPUT_DIR / "reconciliation_report.html",
    ]:
        generated.append([path.relative_to(REPO_ROOT).as_posix(), path.exists()])
    st.dataframe(
        pd.DataFrame(generated, columns=["File", "Exists"]),
        use_container_width=True,
        hide_index=True,
    )

# -----------------------------------------------------------------------------
# Optional HTML report download
# -----------------------------------------------------------------------------
html_path = OUTPUT_DIR / "reconciliation_report.html"
if html_path.exists():
    st.download_button(
        "Download generated HTML dashboard",
        data=html_path.read_bytes(),
        file_name="reconciliation_report.html",
        mime="text/html",
    )

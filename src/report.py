"""
report.py -- Final report generation: CSV + self-contained HTML dashboard.

Exported function:
    generate_report(matched_df, exceptions_df, metrics_dict, output_dir)

Outputs:
    output/reconciliation_report.csv
    output/reconciliation_report.html  (Chart.js dashboard)
"""

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
from jinja2 import Template

# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------
_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Razorpay Payment Reconciliation Agent</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
/* -- Reset & base -------------------------------------------------------- */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
  font-family: -apple-system, "Segoe UI", system-ui, Arial, sans-serif;
  background: #f0f2f5;
  color: #1a1d23;
  font-size: 14px;
  line-height: 1.6;
}
a { color: inherit; }
code {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 11.5px;
  background: #eef0f5;
  padding: 1px 5px;
  border-radius: 3px;
  color: #2d3748;
}

/* -- Layout -------------------------------------------------------------- */
.container { max-width: 1160px; margin: 0 auto; padding: 28px 32px; }

/* -- Page header --------------------------------------------------------- */
.page-header {
  background: linear-gradient(135deg, #0f1628 0%, #12172b 60%, #161d35 100%);
  color: #fff;
  padding: 0;
  border-bottom: 1px solid #1e2645;
}
.header-inner {
  max-width: 1160px;
  margin: 0 auto;
  padding: 32px 32px 24px;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
}
.header-brand { display: flex; flex-direction: column; gap: 4px; }
.header-wordmark {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .22em;
  text-transform: uppercase;
  color: #4f6ef7;
}
.header-title {
  font-size: 24px;
  font-weight: 700;
  color: #fff;
  letter-spacing: -.01em;
  line-height: 1.2;
}
.header-subtitle {
  font-size: 13px;
  color: #8b95b8;
  margin-top: 5px;
}
.header-meta {
  text-align: right;
  font-size: 12px;
  color: #8b95b8;
  white-space: nowrap;
  line-height: 1.8;
}
.header-meta strong { color: #c5cce8; }

/* -- Architecture pipeline banner --------------------------------------- */
.arch-banner {
  background: #1a2040;
  border-top: 1px solid #2a3260;
}
.arch-inner {
  max-width: 1160px;
  margin: 0 auto;
  padding: 14px 32px;
  display: flex;
  align-items: center;
  gap: 0;
  flex-wrap: wrap;
}
.arch-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 9px 16px;
  border-radius: 6px;
  min-width: 120px;
}
.arch-block.det {
  background: rgba(74, 144, 226, 0.1);
  border: 1px solid rgba(74, 144, 226, 0.28);
}
.arch-block.ai {
  background: rgba(130, 80, 220, 0.1);
  border: 1px solid rgba(130, 80, 220, 0.28);
}
.arch-block-tag {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: .14em;
  text-transform: uppercase;
  opacity: .85;
}
.arch-block.det .arch-block-tag { color: #7ab3f0; }
.arch-block.ai  .arch-block-tag { color: #b48fe8; }
.arch-block-label {
  font-size: 11.5px;
  font-weight: 600;
  color: #c5cce8;
  text-align: center;
}
.arch-block-sub {
  font-size: 10px;
  color: #5e6a8a;
  text-align: center;
}
.arch-arrow {
  color: #2e3860;
  font-size: 18px;
  padding: 0 5px;
  user-select: none;
  flex-shrink: 0;
}
.arch-note {
  margin-left: auto;
  font-size: 11px;
  color: #5e6a8a;
  font-style: italic;
  padding-left: 20px;
  border-left: 1px solid #2a3260;
  line-height: 1.5;
}

/* -- Section labels ------------------------------------------------------ */
.section-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .14em;
  text-transform: uppercase;
  color: #6b7a9b;
  margin-bottom: 12px;
  padding-bottom: 6px;
  border-bottom: 1px solid #e3e6ed;
}

/* -- KPI cards ----------------------------------------------------------- */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-bottom: 28px;
}
.kpi {
  background: #fff;
  border: 1px solid #e3e6ed;
  border-radius: 8px;
  padding: 22px 22px 18px;
  position: relative;
  overflow: hidden;
  transition: box-shadow .15s ease;
}
.kpi:hover { box-shadow: 0 2px 10px rgba(0,0,0,.07); }
.kpi::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
}
.kpi-green::before  { background: #1a7f4b; }
.kpi-blue::before   { background: #3b82d4; }
.kpi-purple::before { background: #7c5cd8; }
.kpi-amber::before  { background: #b45309; }
.kpi-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .12em;
  text-transform: uppercase;
  color: #6b7a9b;
  margin-bottom: 2px;
}
.kpi-value {
  font-size: 34px;
  font-weight: 700;
  line-height: 1.1;
  margin: 6px 0 5px;
  letter-spacing: -.025em;
}
.kpi-green  .kpi-value { color: #1a7f4b; }
.kpi-blue   .kpi-value { color: #3b82d4; }
.kpi-purple .kpi-value { color: #7c5cd8; }
.kpi-amber  .kpi-value { color: #b45309; }
.kpi-sub { font-size: 11.5px; color: #8896b0; line-height: 1.4; }

/* -- Generic cards ------------------------------------------------------- */
.card {
  background: #fff;
  border: 1px solid #e3e6ed;
  border-radius: 8px;
  padding: 22px 24px;
}
.card-title {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .12em;
  text-transform: uppercase;
  color: #6b7a9b;
  margin-bottom: 16px;
}

/* -- Charts row ---------------------------------------------------------- */
.charts-row {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 14px;
  margin-bottom: 28px;
  align-items: start;
}
.pie-outer { max-width: 190px; margin: 0 auto; }
.bar-outer { height: 220px; position: relative; }

/* -- Pipeline visual (deterministic left, AI right) --------------------- */
.pipeline-section {
  margin-bottom: 28px;
}
.pipeline-layout {
  display: grid;
  grid-template-columns: 1fr 48px 1fr;
  gap: 0;
  align-items: stretch;
}
.pipeline-col {
  border-radius: 8px;
  padding: 20px 22px;
}
.pipeline-det {
  background: #f4f8ff;
  border: 1px solid #c3d6f5;
}
.pipeline-ai {
  background: #f8f4ff;
  border: 1px solid #d5c3f5;
}
.pipeline-col-title {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .12em;
  text-transform: uppercase;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 7px;
}
.pipeline-col-title-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.pipeline-det .pipeline-col-title { color: #2c5ea8; }
.pipeline-det .pipeline-col-title-dot { background: #3b82d4; }
.pipeline-ai  .pipeline-col-title { color: #6b3ea8; }
.pipeline-ai  .pipeline-col-title-dot { background: #9c5cd4; }
.pipeline-flow {
  display: flex;
  flex-direction: column;
  gap: 0;
}
.pipeline-step-row {
  display: flex;
  align-items: flex-start;
  gap: 0;
}
.pipeline-step-connector {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 22px;
  flex-shrink: 0;
}
.pipeline-node-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 5px;
}
.pipeline-det .pipeline-node-dot { background: #3b82d4; }
.pipeline-ai  .pipeline-node-dot { background: #9c5cd4; }
.pipeline-node-line {
  width: 1px;
  flex: 1;
  min-height: 14px;
}
.pipeline-det .pipeline-node-line { background: #c3d6f5; }
.pipeline-ai  .pipeline-node-line { background: #d5c3f5; }
.pipeline-step-text {
  font-size: 12.5px;
  color: #344060;
  padding: 2px 0 14px 8px;
  line-height: 1.4;
}
.pipeline-step-text strong { font-weight: 600; }
.pipeline-step-sub {
  display: block;
  font-size: 11px;
  color: #6b7a9b;
  margin-top: 2px;
}
.pipeline-middle {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #b0b8d0;
  font-size: 24px;
}
.pipeline-ai-note {
  margin-top: 14px;
  padding: 10px 12px;
  background: rgba(108, 62, 168, 0.06);
  border-radius: 5px;
  border-left: 3px solid #9c5cd4;
  font-size: 11.5px;
  color: #5c3a98;
  line-height: 1.5;
}

/* -- Two-col info row ---------------------------------------------------- */
.info-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin-bottom: 28px;
}
.audit-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 4px;
}
.audit-list li {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  font-size: 12.5px;
  color: #344060;
  line-height: 1.4;
}
.audit-check {
  color: #1a7f4b;
  font-weight: 700;
  flex-shrink: 0;
  margin-top: 1px;
  font-size: 13px;
}
.ai-does { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 4px; }
.ai-col-title {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .1em;
  text-transform: uppercase;
  margin-bottom: 8px;
}
.ai-does-col { font-size: 12.5px; }
.ai-col-yes .ai-col-title { color: #1a7f4b; }
.ai-col-no  .ai-col-title { color: #b91c1c; }
.ai-item {
  display: flex;
  gap: 7px;
  margin-bottom: 6px;
  color: #344060;
  align-items: flex-start;
  line-height: 1.4;
}
.ai-item-icon { flex-shrink: 0; font-size: 12px; margin-top: 1px; }
.ai-col-yes .ai-item-icon { color: #1a7f4b; }
.ai-col-no  .ai-item-icon { color: #b91c1c; }

/* -- Exception table ----------------------------------------------------- */
.table-card {
  background: #fff;
  border: 1px solid #e3e6ed;
  border-radius: 8px;
  padding: 22px 24px;
  margin-bottom: 28px;
}
.table-header-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 10px;
}
.table-legend {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
  align-items: center;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: #6b7a9b;
}
.legend-pip {
  display: inline-block;
  font-size: 12px;
  flex-shrink: 0;
}
.legend-pip-rule { color: #3b82d4; }
.legend-pip-ai   { color: #9c5cd4; }
.legend-pip-fb   { color: #9ea8bc; }
.table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  min-width: 800px;
}
thead tr { border-bottom: 2px solid #e3e6ed; }
th {
  background: #f7f8fb;
  padding: 11px 14px;
  text-align: left;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .1em;
  text-transform: uppercase;
  color: #6b7a9b;
  white-space: nowrap;
  border-bottom: 2px solid #e3e6ed;
}
.th-sub {
  display: block;
  font-size: 9px;
  font-weight: 400;
  letter-spacing: 0;
  text-transform: none;
  color: #9ea8bc;
  margin-top: 2px;
}
td {
  padding: 13px 14px;
  border-bottom: 1px solid #f0f1f5;
  vertical-align: top;
  line-height: 1.5;
}
tr:last-child td { border-bottom: none; }
tr:nth-child(even) td { background: #fafbfd; }
tr:hover td { background: #f3f5fc; }
.col-txn    { width: 88px; }
.col-order  { width: 76px; }
.col-badge  { width: 170px; }
.col-reason { width: 260px; }
.col-ai     { min-width: 320px; }
code.mono { white-space: nowrap; }

/* -- Exception type badges ---------------------------------------------- */
.badge {
  display: inline-block;
  padding: 3px 9px 3px 8px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .04em;
  text-transform: uppercase;
  white-space: nowrap;
  line-height: 1.6;
}
.badge-missing_settlement   { background: #fff1f1; color: #9b1c1c; border: 1px solid #fecaca; }
.badge-amount_mismatch      { background: #fffbeb; color: #92400e; border: 1px solid #fde68a; }
.badge-timing_mismatch      { background: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe; }
.badge-duplicate_settlement { background: #f5f3ff; color: #5b21b6; border: 1px solid #ddd6fe; }
.badge-garbled_order_id     { background: #f0fdf4; color: #14532d; border: 1px solid #bbf7d0; }
.badge-partial_settlement   { background: #fefce8; color: #713f12; border: 1px solid #fef08a; }
.badge-ambiguous_match      { background: #f8fafc; color: #475569; border: 1px solid #cbd5e1; }

/* -- Table cell source labels ------------------------------------------- */
.cell-tag {
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: .1em;
  text-transform: uppercase;
  margin-bottom: 5px;
  display: flex;
  align-items: center;
  gap: 4px;
}
.cell-tag-rule { color: #2563eb; }
.cell-tag-ai   { color: #7c3aed; }
.cell-tag-fb   { color: #8896b0; }
.cell-reason  { font-size: 12.5px; color: #374151; line-height: 1.5; }
.cell-ai-text { font-size: 12.5px; color: #4b5563; line-height: 1.55; }
.cell-ai-text.is-fallback { color: #8896b0; font-style: italic; }

/* -- Footer -------------------------------------------------------------- */
footer {
  border-top: 1px solid #e3e6ed;
  margin-top: 4px;
  padding: 22px 0 26px;
}
.footer-inner {
  max-width: 1160px;
  margin: 0 auto;
  padding: 0 32px;
  text-align: center;
}
.footer-title { font-size: 13px; font-weight: 600; color: #3a4a6b; margin-bottom: 4px; }
.footer-sub   { font-size: 11.5px; color: #8896b0; line-height: 1.6; }

/* -- Responsive ---------------------------------------------------------- */
@media (max-width: 960px) {
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
  .charts-row { grid-template-columns: 1fr; }
  .pipeline-layout { grid-template-columns: 1fr; }
  .pipeline-middle { transform: rotate(90deg); padding: 8px 0; }
  .info-row { grid-template-columns: 1fr; }
  .header-inner { flex-direction: column; align-items: flex-start; }
  .header-meta { text-align: left; }
  .arch-inner { gap: 4px; }
  .arch-note { margin-left: 0; width: 100%; padding-left: 0; border-left: none;
               padding-top: 8px; border-top: 1px solid #2a3260; }
}
@media (max-width: 600px) {
  .kpi-grid { grid-template-columns: 1fr; }
  .container { padding: 16px; }
  .header-inner { padding: 20px 16px 16px; }
  .arch-inner { padding: 12px 16px; flex-wrap: wrap; gap: 6px; }
  .ai-does { grid-template-columns: 1fr; }
  .table-header-row { flex-direction: column; align-items: flex-start; }
}
</style>
</head>
<body>

<!-- ================================================================ -->
<!-- PAGE HEADER                                                        -->
<!-- ================================================================ -->
<div class="page-header">
  <div class="header-inner">
    <div class="header-brand">
      <span class="header-wordmark">Razorpay</span>
      <div class="header-title">Payment Reconciliation Agent</div>
      <div class="header-subtitle">Automated payment gateway &harr; bank settlement reconciliation</div>
    </div>
    <div class="header-meta">
      <strong>{{ raw.total_ledger_rows }}</strong> transactions processed<br>
      <strong>{{ raw.total_matched }}</strong> matched &nbsp;&middot;&nbsp; <strong>{{ raw.total_exceptions }}</strong> exceptions<br>
      Generated {{ generated_at }}
    </div>
  </div>

  <!-- Architecture pipeline banner -->
  <div class="arch-banner">
    <div class="arch-inner">
      <div class="arch-block det">
        <span class="arch-block-tag">Deterministic</span>
        <span class="arch-block-label">Exact Match</span>
        <span class="arch-block-sub">order_id + &#8377;1 tolerance</span>
      </div>
      <span class="arch-arrow">&#8594;</span>
      <div class="arch-block det">
        <span class="arch-block-tag">Deterministic</span>
        <span class="arch-block-label">Fuzzy Match</span>
        <span class="arch-block-sub">amount &#177; tolerance</span>
      </div>
      <span class="arch-arrow">&#8594;</span>
      <div class="arch-block det">
        <span class="arch-block-tag">Deterministic</span>
        <span class="arch-block-label">Exception Classify</span>
        <span class="arch-block-sub">6-rule priority chain</span>
      </div>
      <span class="arch-arrow">&#8594;</span>
      <div class="arch-block det">
        <span class="arch-block-tag">Deterministic</span>
        <span class="arch-block-label">Metrics</span>
        <span class="arch-block-sub">vs ground truth</span>
      </div>
      <span class="arch-arrow">&#8594;</span>
      <div class="arch-block ai">
        <span class="arch-block-tag">AI Layer</span>
        <span class="arch-block-label">Gemini Narration</span>
        <span class="arch-block-sub">explains exceptions only</span>
      </div>
      <span class="arch-note">AI does not determine matches,<br>exception types, or metrics.</span>
    </div>
  </div>
</div>

<!-- ================================================================ -->
<!-- MAIN CONTENT                                                       -->
<!-- ================================================================ -->
<div class="container">

  <!-- KPI CARDS -->
  <div class="section-label">Key Metrics</div>
  <div class="kpi-grid">
    <div class="kpi kpi-green">
      <div class="kpi-label">Match Rate</div>
      <div class="kpi-value">{{ "%.1f"|format(match_rate * 100) }}%</div>
      <div class="kpi-sub">{{ raw.total_matched }} / {{ raw.total_ledger_rows }} records matched</div>
    </div>
    <div class="kpi kpi-blue">
      <div class="kpi-label">Precision</div>
      <div class="kpi-value">{{ "%.1f"|format(precision * 100) }}%</div>
      <div class="kpi-sub">vs ground truth oracle</div>
    </div>
    <div class="kpi kpi-purple">
      <div class="kpi-label">Exception Recall</div>
      <div class="kpi-value">{{ "%.1f"|format(exception_recall * 100) }}%</div>
      <div class="kpi-sub">{{ raw.correctly_flagged_exceptions }} / {{ raw.gt_exception_count }} GT exceptions found</div>
    </div>
    <div class="kpi kpi-amber">
      <div class="kpi-label">Unresolved Exceptions</div>
      <div class="kpi-value">{{ raw.total_exceptions }}</div>
      <div class="kpi-sub">Requires finance-ops review</div>
    </div>
  </div>

  <!-- CHARTS -->
  <div class="section-label">Overview</div>
  <div class="charts-row">
    <div class="card">
      <div class="card-title">Match vs Exceptions</div>
      <div class="pie-outer">
        <canvas id="pieChart"></canvas>
      </div>
    </div>
    <div class="card">
      <div class="card-title">Exception Breakdown</div>
      <div class="bar-outer">
        <canvas id="barChart"></canvas>
      </div>
    </div>
  </div>

  <!-- PIPELINE VISUAL -->
  <div class="section-label">Reconciliation Pipeline</div>
  <div class="pipeline-section">
    <div class="pipeline-layout">

      <!-- LEFT: Deterministic Engine -->
      <div class="pipeline-col pipeline-det">
        <div class="pipeline-col-title">
          <span class="pipeline-col-title-dot"></span>
          Deterministic Engine &mdash; Source of Truth
        </div>
        <div class="pipeline-flow">
          <div class="pipeline-step-row">
            <div class="pipeline-step-connector">
              <span class="pipeline-node-dot"></span>
              <span class="pipeline-node-line"></span>
            </div>
            <div class="pipeline-step-text">
              <strong>Load Ledger &amp; Settlements</strong>
              <span class="pipeline-step-sub">Parse CSV inputs; pre-scan for duplicate order IDs</span>
            </div>
          </div>
          <div class="pipeline-step-row">
            <div class="pipeline-step-connector">
              <span class="pipeline-node-dot"></span>
              <span class="pipeline-node-line"></span>
            </div>
            <div class="pipeline-step-text">
              <strong>Exact Match</strong>
              <span class="pipeline-step-sub">order_id join + &#8377;1.00 rounding tolerance + T+3 window</span>
            </div>
          </div>
          <div class="pipeline-step-row">
            <div class="pipeline-step-connector">
              <span class="pipeline-node-dot"></span>
              <span class="pipeline-node-line"></span>
            </div>
            <div class="pipeline-step-text">
              <strong>Fuzzy Match</strong>
              <span class="pipeline-step-sub">&#8377;5.00 tolerance; single unambiguous candidate only</span>
            </div>
          </div>
          <div class="pipeline-step-row">
            <div class="pipeline-step-connector">
              <span class="pipeline-node-dot"></span>
              <span class="pipeline-node-line"></span>
            </div>
            <div class="pipeline-step-text">
              <strong>Exception Classification</strong>
              <span class="pipeline-step-sub">6-rule deterministic priority chain</span>
            </div>
          </div>
          <div class="pipeline-step-row">
            <div class="pipeline-step-connector">
              <span class="pipeline-node-dot"></span>
            </div>
            <div class="pipeline-step-text">
              <strong>Compute Metrics</strong>
              <span class="pipeline-step-sub">Match rate, precision &amp; recall vs ground truth oracle</span>
            </div>
          </div>
        </div>
      </div>

      <!-- MIDDLE ARROW -->
      <div class="pipeline-middle">&#8594;</div>

      <!-- RIGHT: AI Explanation Layer -->
      <div class="pipeline-col pipeline-ai">
        <div class="pipeline-col-title">
          <span class="pipeline-col-title-dot"></span>
          Gemini AI &mdash; Explanation Layer Only
        </div>
        <div class="pipeline-flow">
          <div class="pipeline-step-row">
            <div class="pipeline-step-connector">
              <span class="pipeline-node-dot"></span>
              <span class="pipeline-node-line"></span>
            </div>
            <div class="pipeline-step-text">
              <strong>Receives Already-Classified Exceptions</strong>
              <span class="pipeline-step-sub">Exception type and reason are fixed before AI is called</span>
            </div>
          </div>
          <div class="pipeline-step-row">
            <div class="pipeline-step-connector">
              <span class="pipeline-node-dot"></span>
              <span class="pipeline-node-line"></span>
            </div>
            <div class="pipeline-step-text">
              <strong>Single Batch Request</strong>
              <span class="pipeline-step-sub">All exceptions sent in one call for efficiency</span>
            </div>
          </div>
          <div class="pipeline-step-row">
            <div class="pipeline-step-connector">
              <span class="pipeline-node-dot"></span>
              <span class="pipeline-node-line"></span>
            </div>
            <div class="pipeline-step-text">
              <strong>Plain-English Narration</strong>
              <span class="pipeline-step-sub">Explains amounts, dates, UTRs, and suggested follow-up</span>
            </div>
          </div>
          <div class="pipeline-step-row">
            <div class="pipeline-step-connector">
              <span class="pipeline-node-dot"></span>
            </div>
            <div class="pipeline-step-text">
              <strong>Deterministic Fallback</strong>
              <span class="pipeline-step-sub">Per-type fallback used if API is unavailable</span>
            </div>
          </div>
        </div>
        <div class="pipeline-ai-note">
          Gemini does <strong>not</strong> influence matching decisions, exception
          classification, precision, recall, or any metric. All reconciliation
          decisions are made before AI is called.
        </div>
      </div>

    </div>
  </div>

  <!-- AUDITABILITY + AI SCOPE -->
  <div class="section-label">Design Guarantees</div>
  <div class="info-row">
    <div class="card">
      <div class="card-title">Auditability</div>
      <ul class="audit-list">
        <li><span class="audit-check">&#10003;</span>Deterministic matching &mdash; reproducible on every run</li>
        <li><span class="audit-check">&#10003;</span>Explicit &#8377;1.00 amount tolerance for rounding</li>
        <li><span class="audit-check">&#10003;</span>3-day settlement window enforced at match time</li>
        <li><span class="audit-check">&#10003;</span>Fuzzy recovery limited to single unambiguous candidates</li>
        <li><span class="audit-check">&#10003;</span>Duplicate settlements detected before matching begins</li>
        <li><span class="audit-check">&#10003;</span>Ambiguous matches are never force-matched</li>
        <li><span class="audit-check">&#10003;</span>Precision and recall verified against ground truth oracle</li>
        <li><span class="audit-check">&#10003;</span>AI does not influence any reconciliation decision</li>
      </ul>
    </div>
    <div class="card">
      <div class="card-title">What the AI Explanation Layer Does</div>
      <div class="ai-does">
        <div class="ai-does-col ai-col-yes">
          <div class="ai-col-title">It Explains</div>
          <div class="ai-item"><span class="ai-item-icon">&#10003;</span>What happened to the transaction</div>
          <div class="ai-item"><span class="ai-item-icon">&#10003;</span>Why reconciliation failed</div>
          <div class="ai-item"><span class="ai-item-icon">&#10003;</span>Relevant amounts, dates &amp; UTRs</div>
          <div class="ai-item"><span class="ai-item-icon">&#10003;</span>Suggested finance-ops follow-up</div>
        </div>
        <div class="ai-does-col ai-col-no">
          <div class="ai-col-title">It Does NOT</div>
          <div class="ai-item"><span class="ai-item-icon">&#10007;</span>Decide which transactions match</div>
          <div class="ai-item"><span class="ai-item-icon">&#10007;</span>Classify exception types</div>
          <div class="ai-item"><span class="ai-item-icon">&#10007;</span>Modify transaction records</div>
          <div class="ai-item"><span class="ai-item-icon">&#10007;</span>Calculate or affect metrics</div>
        </div>
      </div>
    </div>
  </div>

  <!-- EXCEPTION TABLE -->
  <div class="table-card">
    <div class="table-header-row">
      <div class="card-title" style="margin-bottom:0">
        Exception Detail &mdash; {{ exceptions|length }} rows requiring finance-ops review
      </div>
      <div class="table-legend">
        <div class="legend-item">
          <span class="legend-pip legend-pip-rule">&#9679;</span>
          <span><strong>Rule-Based</strong> &mdash; deterministic engine</span>
        </div>
        <div class="legend-item">
          <span class="legend-pip legend-pip-ai">&#9670;</span>
          <span><strong>AI-Generated</strong> &mdash; Gemini narration</span>
        </div>
        <div class="legend-item">
          <span class="legend-pip legend-pip-fb">&#9632;</span>
          <span><strong>Fallback</strong> &mdash; AI unavailable</span>
        </div>
      </div>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th class="col-txn">Transaction</th>
            <th class="col-order">Order</th>
            <th class="col-badge">Exception Type</th>
            <th class="col-reason">
              <span style="color:#2563eb;margin-right:3px">&#9679;</span>Deterministic Finding
              <span class="th-sub">Rule-based reason from the reconciliation engine</span>
            </th>
            <th class="col-ai">
              <span style="color:#7c3aed;margin-right:3px">&#9670;</span>AI Explanation
              <span class="th-sub">Gemini narration (or deterministic fallback)</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {% for row in exceptions %}
          <tr>
            <td class="col-txn"><code class="mono">{{ row.txn_id }}</code></td>
            <td class="col-order"><code class="mono">{{ row.order_id }}</code></td>
            <td class="col-badge">
              <span class="badge badge-{{ row.exception_type }}">{{ row.exception_type | replace("_", " ") }}</span>
            </td>
            <td class="col-reason">
              <div class="cell-tag cell-tag-rule"><span>&#9679;</span> Rule-Based</div>
              <div class="cell-reason">{{ row.reason }}</div>
            </td>
            <td class="col-ai">
              {% if row.is_ai %}
                <div class="cell-tag cell-tag-ai"><span>&#9670;</span> AI-Generated</div>
                <div class="cell-ai-text">{{ row.llm_explanation }}</div>
              {% elif row.is_fallback %}
                <div class="cell-tag cell-tag-fb"><span>&#9632;</span> Fallback</div>
                <div class="cell-ai-text is-fallback">{{ row.llm_explanation }}</div>
              {% else %}
                <div class="cell-tag cell-tag-fb"><span>&#9632;</span> Unavailable</div>
                <div class="cell-ai-text is-fallback">{{ row.llm_explanation }}</div>
              {% endif %}
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

</div><!-- /.container -->

<!-- ================================================================ -->
<!-- FOOTER                                                             -->
<!-- ================================================================ -->
<footer>
  <div class="footer-inner">
    <div class="footer-title">Razorpay Payment Reconciliation Agent</div>
    <div class="footer-sub">
      Deterministic reconciliation + AI-assisted exception narration &nbsp;&middot;&nbsp;
      All matching, classification, and metrics are computed deterministically.
      Gemini AI explains already-detected exceptions only.
    </div>
  </div>
</footer>

<script>
// -- Pie chart ------------------------------------------------------------
new Chart(document.getElementById("pieChart"), {
  type: "doughnut",
  data: {
    labels: ["Matched ({{ raw.total_matched }})", "Exceptions ({{ raw.total_exceptions }})"],
    datasets: [{
      data: [{{ raw.total_matched }}, {{ raw.total_exceptions }}],
      backgroundColor: ["#1a7f4b", "#b91c1c"],
      borderWidth: 3,
      borderColor: "#fff",
      hoverOffset: 6
    }]
  },
  options: {
    cutout: "62%",
    plugins: {
      legend: {
        position: "bottom",
        labels: { font: { size: 12 }, padding: 16, boxWidth: 12, color: "#374151" }
      },
      tooltip: {
        callbacks: {
          label: function(ctx) {
            var total = ctx.dataset.data.reduce(function(a, b) { return a + b; }, 0);
            var pct = (ctx.parsed / total * 100).toFixed(1);
            return "  " + ctx.parsed + " records (" + pct + "%)";
          }
        }
      }
    }
  }
});

// -- Bar chart ------------------------------------------------------------
var badgeColors = {
  "amount mismatch":      "#92400e",
  "duplicate settlement": "#5b21b6",
  "missing settlement":   "#9b1c1c",
  "partial settlement":   "#713f12",
  "timing mismatch":      "#1e40af",
  "garbled order id":     "#14532d",
  "ambiguous match":      "#475569"
};
var labels = {{ bar_labels | tojson }};
var colors = labels.map(function(l) { return badgeColors[l] || "#8896b0"; });

new Chart(document.getElementById("barChart"), {
  type: "bar",
  data: {
    labels: labels,
    datasets: [{
      label: "Count",
      data: {{ bar_values | tojson }},
      backgroundColor: colors,
      borderWidth: 0,
      borderRadius: 4
    }]
  },
  options: {
    indexAxis: "y",
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: function(ctx) { return "  " + ctx.parsed.x + " exceptions"; }
        }
      }
    },
    scales: {
      x: {
        beginAtZero: true,
        ticks: { stepSize: 1, font: { size: 11 }, color: "#6b7a9b" },
        grid: { color: "#f0f1f5" }
      },
      y: {
        ticks: { font: { size: 12 }, color: "#374151" },
        grid: { display: false }
      }
    }
  }
});
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Fallback detection helper
# ---------------------------------------------------------------------------

# Text patterns that identify a deterministic fallback explanation
# (written by _deterministic_fallbacks() in explain.py or "[LLM narration unavailable]")
_FALLBACK_PHRASES = (
    "[LLM narration unavailable]",
    "Two settlement rows were found for this order ID.",
    "The settled amount does not match the expected net payable amount.",
    "The bank settled only a fraction of the expected net amount.",
    "The settlement arrived more than 3 days after the transaction date.",
    "No settlement row was found for this transaction in the bank file.",
    "Multiple possible settlement candidates were found but none could be safely selected.",
)


def _classify_explanation(text: str) -> tuple[bool, bool]:
    """Return (is_ai, is_fallback) for a given explanation string."""
    if not text or text.strip() == "[LLM narration unavailable]":
        return False, False  # unavailable
    for phrase in _FALLBACK_PHRASES:
        if text.strip().startswith(phrase):
            return False, True   # deterministic fallback
    return True, False           # ai-generated


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def generate_report(
    matched_df: pd.DataFrame,
    exceptions_df: pd.DataFrame,
    metrics_dict: dict,
    output_dir: str | Path = "output",
) -> None:
    """
    Generate reconciliation_report.csv and reconciliation_report.html.
    Only this function and the template above were changed.
    No reconciliation logic was modified.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------------
    # 1. Build unified CSV (unchanged)
    # -----------------------------------------------------------------------
    csv_rows = []

    if not matched_df.empty:
        for _, row in matched_df.iterrows():
            csv_rows.append({
                "txn_id": row["txn_id"],
                "order_id": row["order_id"],
                "utr_number": row.get("utr_number", ""),
                "net_amount": row.get("net_amount", ""),
                "settled_amount": row.get("settled_amount", ""),
                "txn_date": row.get("txn_date", ""),
                "settlement_date": row.get("settlement_date", ""),
                "match_type": row.get("match_type", ""),
                "confidence": row.get("confidence", "high"),
                "exception_type": "",
                "reason": "",
                "llm_explanation": "",
            })

    if not exceptions_df.empty:
        for _, row in exceptions_df.iterrows():
            csv_rows.append({
                "txn_id": row["txn_id"],
                "order_id": row["order_id"],
                "utr_number": "",
                "net_amount": "",
                "settled_amount": "",
                "txn_date": "",
                "settlement_date": "",
                "match_type": "exception",
                "confidence": "",
                "exception_type": row.get("exception_type", ""),
                "reason": row.get("reason", ""),
                "llm_explanation": row.get("llm_explanation", ""),
            })

    report_df = pd.DataFrame(csv_rows)
    csv_path = out / "reconciliation_report.csv"
    report_df.to_csv(csv_path, index=False)
    print(f"[report] CSV saved -> {csv_path}")

    # -----------------------------------------------------------------------
    # 2. Build HTML
    # -----------------------------------------------------------------------
    breakdown = metrics_dict.get("exception_breakdown", {})
    # Title-case the labels for the bar chart
    bar_labels = [k.replace("_", " ") for k in sorted(breakdown.keys())]
    bar_values = [breakdown[k] for k in sorted(breakdown.keys())]

    # Build exception rows with AI/fallback classification
    exc_records = []
    if not exceptions_df.empty:
        for _, row in exceptions_df.iterrows():
            explanation = str(row.get("llm_explanation", "") or "")
            is_ai, is_fallback = _classify_explanation(explanation)
            exc_records.append({
                "txn_id": row["txn_id"],
                "order_id": row["order_id"],
                "exception_type": row.get("exception_type", ""),
                "reason": row.get("reason", ""),
                "llm_explanation": explanation,
                "is_ai": is_ai,
                "is_fallback": is_fallback,
            })

    template = Template(_HTML_TEMPLATE)
    html = template.render(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        match_rate=metrics_dict["match_rate"],
        precision=metrics_dict["precision"],
        exception_recall=metrics_dict["exception_recall"],
        raw=metrics_dict["raw_counts"],
        exceptions=exc_records,
        bar_labels=bar_labels,
        bar_values=bar_values,
    )

    html_path = out / "reconciliation_report.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"[report] HTML dashboard saved -> {html_path}")

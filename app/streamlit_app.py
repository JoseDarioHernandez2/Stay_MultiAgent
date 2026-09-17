"""Streamlit UI for the customer-retention multi-agent workflow.

A thin presentation layer over the core engine, restyled as a dark, vivid
"AI Core Dashboard": a living neural-network background, an animated core with
live telemetry, glowing glass panels and churn-first analytics. Functionally it
lets a business user:

* load a customer dataset (bundled sample or an uploaded CSV),
* run the multi-agent churn-retention workflow,
* identify which customers are at risk of churn (abandonment) via the model,
* explore per-customer decisions, risk/value distributions and agent traces,
* **approve or reject expensive offers interactively** (Human-in-the-Loop),
* download the full JSON report.

Only the *presentation layer* was reworked. The engine wiring, imports,
session-state keys and control flow are unchanged, so this file is a drop-in
replacement for ``app/streamlit_app.py``.

For the full dark look on native widgets (dataframe, inputs), ship the bundled
``.streamlit/config.toml`` as well.

Run with::

    streamlit run app/streamlit_app.py
"""

# pylint: disable=too-many-lines
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

# Make ``src`` importable when launched via ``streamlit run``.
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# pylint: disable=wrong-import-position
from customer_retention.application.policy import load_policy  # noqa: E402
from customer_retention.application.recommendations import build_recommendation_engine  # noqa: E402
from customer_retention.application.reporting import (  # noqa: E402
    alerted_rows,
    build_table,
    efficiency_metrics,
    summarize,
)
from customer_retention.application.workflow import RetentionWorkflow  # noqa: E402
from customer_retention.domain.contracts import CustomerRecord, WorkflowResult  # noqa: E402
from customer_retention.infrastructure.data_loader import load_customers  # noqa: E402
from customer_retention.infrastructure.model_adapter import build_churn_model_from_any  # noqa: E402
from customer_retention.infrastructure.report_builder import build_alert_report  # noqa: E402
from customer_retention.tools.human_in_the_loop import AuditApprovalGateway  # noqa: E402

_MIME = {
    "json": "application/json",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}

_RESOURCES = _SRC / "customer_retention" / "resources"
_SAMPLE_CSV = _RESOURCES / "sample_customers.csv"
_SAMPLE_POLICY = _RESOURCES / "politica_retencion.md"

# Real specialist agents orchestrated by the supervisor (shown, not simulated).
_AGENTS: tuple[str, ...] = (
    "Supervisor",
    "Comportamiento",
    "Valor",
    "Ofertas",
    "Reviewer",
)

# Vivid, on-brand colours per churn-risk severity (dark theme).
_RISK_COLORS: dict[int, str] = {
    1: "#2dd4bf",  # low      -> teal
    2: "#38bdf8",  # medium   -> sky
    3: "#fbbf24",  # high     -> amber
    4: "#fb7185",  # critical -> rose
}


# --------------------------------------------------------------------------- #
# Premium dark theme + living neural background + animated core telemetry      #
# --------------------------------------------------------------------------- #

_THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@600;700;800&display=swap');
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500&display=swap');

:root {
  --ink: #eaf2ff;
  --ink-2: #9db4d6;
  --ink-3: #6b83a6;
  --cyan: #22d3ee;
  --cyan-2: #5cf0ff;
  --teal: #2dd4bf;
  --violet: #8b7cf6;
  --pink: #f472b6;
  --amber: #fbbf24;
  --rose: #fb7185;
  --line: rgba(120, 185, 240, 0.14);
  --glass: rgba(14, 28, 52, 0.55);
  --glass-2: rgba(20, 38, 66, 0.72);
  --brd: rgba(120, 190, 250, 0.20);
  --glow: 0 0 26px rgba(34, 211, 238, 0.28);
  --radius: 18px;
}

/* Deep, living navy background (not pure black). */
body {
  background:
    radial-gradient(1100px 720px at 8% -6%, #12305a 0%, rgba(18,48,90,0) 55%),
    radial-gradient(1000px 640px at 100% 4%, #0e2f4d 0%, rgba(14,47,77,0) 50%),
    linear-gradient(160deg, #060c18 0%, #0a1628 48%, #081020 100%);
  background-attachment: fixed;
  background-size: 200% 200%;
  animation: bgdrift 22s ease-in-out infinite alternate;
}
@keyframes bgdrift {
  0% { background-position: 0% 0%; }
  50% { background-position: 60% 40%; }
  100% { background-position: 100% 100%; }
}

.stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
  background: transparent !important;
  color: var(--ink);
}
.stApp { font-family: 'Inter', system-ui, sans-serif; }

/* Sweeping "data aurora" band that glides across the screen. */
.stApp {
  position: relative;
}
[data-testid="stAppViewContainer"]::before {
  content: "";
  position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background:
    linear-gradient(115deg, transparent 30%, rgba(34,211,238,0.06) 45%,
      rgba(139,124,246,0.07) 55%, transparent 70%);
  background-size: 300% 300%;
  animation: aurora 16s linear infinite;
}
@keyframes aurora {
  0% { background-position: 0% 50%; }
  100% { background-position: 300% 50%; }
}

/* Drifting colour blobs behind the neural canvas (brighter, livelier). */
.stApp::before, .stApp::after {
  content: "";
  position: fixed;
  width: 48vw;
  height: 48vw;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.48;
  z-index: 0;
  pointer-events: none;
}
.stApp::before {
  left: -12vw; top: -8vw;
  background: radial-gradient(circle, #1e7fd6 0%, rgba(30,127,214,0) 70%);
  animation: blob1 18s ease-in-out infinite alternate;
}
.stApp::after {
  right: -14vw; bottom: -10vw;
  background: radial-gradient(circle, #7c5cf6 0%, rgba(124,92,246,0) 70%);
  animation: blob2 21s ease-in-out infinite alternate;
}
@keyframes blob1 {
  0% { transform: translate(0,0) scale(1); opacity: 0.4; }
  100% { transform: translate(10vw,7vw) scale(1.25); opacity: 0.6; }
}
@keyframes blob2 {
  0% { transform: translate(0,0) scale(1); opacity: 0.42; }
  100% { transform: translate(-9vw,-6vw) scale(1.3); opacity: 0.62; }
}

/* ---- Kill the white top bar: hide header, toolbar and rainbow decoration ---- */
[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
header[data-testid="stHeader"] {
  display: none !important;
  height: 0 !important;
  visibility: hidden !important;
}
#MainMenu, footer { visibility: hidden; height: 0; }

/* The component iframe that hosts the neural canvas must never take layout space. */
.stApp iframe[title="streamlit.components.v1.html"],
iframe[title="st.iframe"] {
  position: fixed !important;
  top: 0; left: 0;
  width: 0 !important; height: 0 !important;
  border: 0 !important; opacity: 0 !important;
  pointer-events: none;
}

.stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
  background: transparent !important;
  color: var(--ink);
}
.stApp { font-family: 'Inter', system-ui, sans-serif; }

/* Drifting colour blobs behind the neural canvas. */
.stApp::before, .stApp::after {
  content: "";
  position: fixed;
  width: 46vw;
  height: 46vw;
  border-radius: 50%;
  filter: blur(90px);
  opacity: 0.35;
  z-index: 0;
  pointer-events: none;
}
.stApp::before {
  left: -12vw; top: -8vw;
  background: radial-gradient(circle, #1e7fd6 0%, rgba(30,127,214,0) 70%);
  animation: blob1 26s ease-in-out infinite alternate;
}
.stApp::after {
  right: -14vw; bottom: -10vw;
  background: radial-gradient(circle, #7c5cf6 0%, rgba(124,92,246,0) 70%);
  animation: blob2 30s ease-in-out infinite alternate;
}
@keyframes blob1 {
  0% { transform: translate(0,0) scale(1); }
  100% { transform: translate(8vw,6vw) scale(1.15); }
}
@keyframes blob2 {
  0% { transform: translate(0,0) scale(1); }
  100% { transform: translate(-7vw,-5vw) scale(1.2); }
}

[data-testid="stMainBlockContainer"], .block-container {
  position: relative;
  z-index: 1;
  padding-top: 1.2rem;
  max-width: 1200px;
}

h1, h2, h3, h4 {
  font-family: 'Manrope', 'Inter', sans-serif !important;
  color: var(--ink) !important;
  letter-spacing: -0.01em;
}
.stApp p, .stApp label, .stApp span, .stMarkdown { color: var(--ink); }

/* Command-rail sidebar. */
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, rgba(10,22,42,0.92), rgba(8,16,32,0.92));
  backdrop-filter: blur(16px) saturate(150%);
  border-right: 1px solid var(--brd);
}
[data-testid="stSidebar"] * { color: var(--ink) !important; }
[data-testid="stSidebar"] .stCaption, [data-testid="stSidebar"] small {
  color: var(--ink-3) !important;
}

/* Inputs: dark glass, larger, glowing focus. */
.stTextInput input, [data-baseweb="input"] {
  border-radius: 13px !important;
  border: 1px solid var(--brd) !important;
  background: rgba(8, 18, 34, 0.7) !important;
  color: var(--ink) !important;
  font-size: 1.03rem !important;
}
.stTextInput input { padding: 0.8rem 1rem !important; }
.stTextInput input:focus { box-shadow: var(--glow) !important; }
[data-testid="stFileUploaderDropzone"] {
  border-radius: 15px !important;
  border: 1px dashed rgba(34, 211, 238, 0.5) !important;
  background: rgba(10, 22, 42, 0.6) !important;
}

/* Premium buttons with animated glow. */
.stButton > button, .stDownloadButton > button {
  border-radius: 13px !important;
  border: 1px solid var(--brd) !important;
  background: rgba(16, 32, 58, 0.8) !important;
  color: var(--ink) !important;
  font-weight: 600 !important;
  padding: 0.6rem 1.15rem !important;
  transition: transform 0.16s ease, box-shadow 0.16s ease, background 0.16s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover {
  transform: translateY(-1px);
  box-shadow: var(--glow);
  background: rgba(22, 44, 78, 0.9) !important;
}
.stButton > button[kind="primary"] {
  background: linear-gradient(135deg, #22d3ee 0%, #6d5cf6 100%) !important;
  color: #04121f !important;
  border: none !important;
  font-weight: 700 !important;
  box-shadow: 0 6px 26px rgba(34, 211, 238, 0.4);
  animation: btnpulse 3.2s ease-in-out infinite;
}
@keyframes btnpulse {
  0%, 100% { box-shadow: 0 6px 26px rgba(34, 211, 238, 0.35); }
  50% { box-shadow: 0 6px 34px rgba(124, 92, 246, 0.55); }
}

/* Alerts / expanders as dark glass. */
[data-testid="stAlert"] {
  border-radius: 14px;
  border: 1px solid var(--brd);
  background: var(--glass) !important;
  color: var(--ink) !important;
  backdrop-filter: blur(10px);
}
[data-testid="stExpander"] {
  border-radius: 15px !important;
  border: 1px solid var(--brd) !important;
  background: var(--glass) !important;
  backdrop-filter: blur(10px);
  overflow: hidden;
}
[data-testid="stExpander"] summary { color: var(--ink) !important; }
[data-testid="stDataFrame"] {
  border-radius: 15px;
  border: 1px solid var(--brd);
  overflow: hidden;
  box-shadow: var(--glow);
}
hr { border-color: var(--line) !important; }

/* ---- Hero (AI core) ---- */
.hero {
  position: relative;
  border-radius: 22px;
  padding: 1.6rem 1.8rem;
  margin-bottom: 0.5rem;
  background: linear-gradient(135deg, var(--glass-2), var(--glass));
  border: 1px solid var(--brd);
  backdrop-filter: blur(18px) saturate(160%);
  box-shadow: var(--glow), inset 0 1px 0 rgba(255,255,255,0.05);
  overflow: hidden;
}
.hero::before {
  content: "";
  position: absolute;
  right: -60px; top: -60px;
  width: 240px; height: 240px;
  background: radial-gradient(circle, rgba(34,211,238,0.22), transparent 65%);
  filter: blur(6px);
  animation: floaty 9s ease-in-out infinite alternate;
}
@keyframes floaty {
  0% { transform: translateY(0); }
  100% { transform: translateY(18px); }
}
.hero-grid {
  display: grid;
  grid-template-columns: 1.45fr 1fr;
  gap: 1.4rem;
  position: relative;
  z-index: 1;
}
@media (max-width: 880px) { .hero-grid { grid-template-columns: 1fr; } }
.eyebrow {
  font-size: 0.72rem; font-weight: 600; letter-spacing: 0.18em;
  text-transform: uppercase; color: var(--cyan); margin-bottom: 0.4rem;
}
.hero h1 {
  font-family: 'Manrope', sans-serif; font-size: 2.05rem; font-weight: 800;
  margin: 0 0 0.4rem 0;
  background: linear-gradient(92deg, #eaf2ff 0%, #7ee7ff 55%, #b6a2ff 100%);
  -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent;
}
.hero p { color: var(--ink-2); margin: 0; max-width: 52ch; line-height: 1.55; }

.agents { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 1rem; }
.agent {
  display: inline-flex; align-items: center; gap: 0.45rem;
  font-size: 0.8rem; color: var(--ink-2);
  background: rgba(20, 40, 70, 0.6); border: 1px solid var(--brd);
  border-radius: 999px; padding: 0.28rem 0.7rem;
}
.agent .dot {
  width: 8px; height: 8px; border-radius: 50%; background: var(--teal);
  animation: pulse 2.2s ease-out infinite;
}
.agent:nth-child(2) .dot { animation-delay: .4s; background: var(--cyan); }
.agent:nth-child(3) .dot { animation-delay: .8s; background: var(--violet); }
.agent:nth-child(4) .dot { animation-delay: 1.2s; background: var(--pink); }
.agent:nth-child(5) .dot { animation-delay: 1.6s; background: var(--amber); }
@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(45,212,191,0.55); }
  70% { box-shadow: 0 0 0 8px rgba(45,212,191,0); }
  100% { box-shadow: 0 0 0 0 rgba(45,212,191,0); }
}

/* ---- Telemetry panel (ambient, live-looking) ---- */
.tele {
  border-radius: 16px; padding: 0.9rem 1rem;
  background: rgba(6, 16, 32, 0.55); border: 1px solid var(--brd);
}
.tele-h {
  font-size: 0.72rem; letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--ink-3); margin-bottom: 0.6rem;
}
.tele-h b { color: var(--teal); }
.eq { display: flex; align-items: flex-end; gap: 3px; height: 46px; }
.eq i {
  flex: 1; border-radius: 3px 3px 0 0;
  background: linear-gradient(180deg, var(--cyan-2), var(--violet));
  animation: eq 1.3s ease-in-out infinite; transform-origin: bottom;
}
@keyframes eq {
  0%, 100% { transform: scaleY(0.25); opacity: .7; }
  50% { transform: scaleY(1); opacity: 1; }
}
.tele-row {
  display: flex; align-items: center; gap: 1rem; margin-top: 0.85rem;
}
.gauge {
  position: relative; width: 82px; height: 82px; border-radius: 50%;
  background:
    conic-gradient(var(--cyan) 0% 72%, rgba(120,160,210,0.14) 72% 100%);
  display: flex; align-items: center; justify-content: center; flex: none;
}
.gauge::before {
  content: ""; position: absolute; inset: 9px; border-radius: 50%;
  background: #08152a;
}
.gauge::after {
  content: ""; position: absolute; inset: -3px; border-radius: 50%;
  background: conic-gradient(from 0deg, transparent, rgba(34,211,238,0.5),
    transparent 40%);
  animation: spin 4.5s linear infinite; z-index: -1; filter: blur(3px);
}
@keyframes spin { to { transform: rotate(360deg); } }
.gauge span {
  position: relative; font-family: 'Manrope', sans-serif; font-weight: 800;
  font-size: 1.05rem; color: var(--cyan-2);
}
.abs { flex: 1; display: flex; flex-direction: column; gap: 0.4rem; }
.ab { display: grid; grid-template-columns: 78px 1fr; align-items: center;
  gap: 0.5rem; }
.ab span { font-size: 0.72rem; color: var(--ink-2); }
.ab-track { height: 6px; border-radius: 999px;
  background: rgba(120,160,210,0.12); overflow: hidden; }
.ab-fill { height: 100%; border-radius: 999px;
  background: linear-gradient(90deg, var(--teal), var(--cyan));
  animation: flow 3.4s ease-in-out infinite; }
@keyframes flow {
  0%, 100% { width: 32%; } 50% { width: 92%; }
}

/* ---- Section headers ---- */
.sec {
  font-family: 'Manrope', sans-serif; font-size: 1.16rem; font-weight: 700;
  color: var(--ink); margin: 0.3rem 0 0.7rem 0;
}
.sec .kicker {
  display: block; font-family: 'Inter', sans-serif; font-size: 0.7rem;
  font-weight: 600; letter-spacing: 0.13em; text-transform: uppercase;
  color: var(--cyan); margin-bottom: 0.15rem;
}
.sec::after {
  content: ""; display: block; width: 54px; height: 2px; margin-top: 0.4rem;
  background: linear-gradient(90deg, var(--cyan), transparent);
  animation: grow2 2.6s ease-in-out infinite alternate;
}
@keyframes grow2 { 0% { width: 34px; } 100% { width: 88px; } }

/* ---- KPI cards ---- */
.kpi-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.85rem; margin: 0.3rem 0;
}
.kpi {
  position: relative; border-radius: var(--radius);
  padding: 1.1rem 1.15rem; background: var(--glass);
  border: 1px solid var(--brd); backdrop-filter: blur(14px);
  box-shadow: 0 6px 24px rgba(0,0,0,0.25); overflow: hidden;
  transition: transform 0.18s ease, box-shadow 0.18s ease;
}
.kpi:hover { transform: translateY(-3px); box-shadow: var(--glow); }
.kpi .k-label {
  font-size: 0.7rem; font-weight: 600; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--ink-2);
}
.kpi .k-value {
  font-family: 'Manrope', sans-serif; font-size: 2rem; font-weight: 800;
  color: var(--ink); margin-top: 0.35rem; line-height: 1;
}
.kpi .k-accent {
  position: absolute; left: 0; top: 0; bottom: 0; width: 4px;
  background: linear-gradient(180deg, var(--cyan), var(--violet));
  box-shadow: 0 0 14px var(--cyan);
}
.kpi.churn { border-color: rgba(251, 113, 133, 0.45); }
.kpi.churn .k-accent {
  background: linear-gradient(180deg, var(--amber), var(--rose));
  box-shadow: 0 0 16px var(--rose);
}
.kpi.churn .k-value { color: var(--rose); }

/* ---- Watchlist ---- */
.watch-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(215px, 1fr));
  gap: 0.75rem;
}
.watch {
  border-radius: 15px; padding: 0.85rem 0.95rem;
  background: var(--glass); border: 1px solid var(--brd);
  backdrop-filter: blur(12px);
  transition: transform 0.16s ease, box-shadow 0.16s ease;
}
.watch:hover { transform: translateY(-2px); box-shadow: var(--glow); }
.watch-top {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 0.55rem;
}
.watch-id {
  font-family: 'JetBrains Mono', monospace; font-size: 0.9rem;
  color: var(--ink);
}
.chip {
  font-size: 0.66rem; font-weight: 700; letter-spacing: 0.04em;
  text-transform: uppercase; padding: 0.16rem 0.5rem; border-radius: 999px;
  color: #04121f;
}
.watch-meter {
  height: 7px; border-radius: 999px; background: rgba(120,160,210,0.12);
  overflow: hidden; margin: 0.5rem 0;
}
.watch-meter i { display: block; height: 100%; border-radius: 999px; }
.watch-foot {
  display: flex; justify-content: space-between; font-size: 0.74rem;
  color: var(--ink-2);
}

/* ---- Distribution bars ---- */
.dist-wrap {
  display: grid; grid-template-columns: 1fr 1fr; gap: 0.85rem;
  margin-top: 0.2rem;
}
@media (max-width: 720px) { .dist-wrap { grid-template-columns: 1fr; } }
.dist-panel {
  border-radius: var(--radius); padding: 1.05rem 1.15rem;
  background: var(--glass); border: 1px solid var(--brd);
  backdrop-filter: blur(12px);
}
.dist-title {
  font-size: 0.72rem; font-weight: 600; letter-spacing: 0.09em;
  text-transform: uppercase; color: var(--ink-2); margin-bottom: 0.8rem;
}
.bar-row {
  display: grid; grid-template-columns: 118px 1fr 40px; align-items: center;
  gap: 0.55rem; margin-bottom: 0.55rem;
}
.bar-name {
  font-size: 0.84rem; color: var(--ink); white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis;
}
.bar-track {
  height: 9px; border-radius: 999px; background: rgba(120,160,210,0.12);
  overflow: hidden;
}
.bar-fill { height: 100%; border-radius: 999px; animation: grow 0.9s ease; }
@keyframes grow { from { width: 0 !important; } }
.bar-val {
  font-size: 0.8rem; font-weight: 600; color: var(--ink-2); text-align: right;
}

/* ---- Getting-started panel ---- */
.start {
  border-radius: 18px; padding: 1.4rem 1.6rem; margin-top: 0.6rem;
  background: var(--glass); border: 1px solid var(--brd);
  backdrop-filter: blur(12px);
}
.start h3 {
  margin: 0 0 0.3rem 0; font-size: 1.15rem;
}
.start p { color: var(--ink-2); margin: 0; }

/* ---- Recommendations panel (churn-mitigation bullets) ---- */
.reco-wrap { display: grid; gap: 0.55rem; }
.reco {
  background: var(--glass); border: 1px solid var(--brd);
  border-left: 3px solid var(--teal); border-radius: 0 14px 14px 0;
  padding: 0.7rem 0.95rem; color: var(--ink-1); font-size: 0.9rem;
  line-height: 1.45; backdrop-filter: blur(10px);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.reco:hover { transform: translateX(3px); box-shadow: 0 6px 22px rgba(45,212,191,.14); }
.reco b { color: var(--teal); }

/* ---- Audit / alert report banner ---- */
.audit {
  border-radius: 16px; padding: 1rem 1.2rem; margin-top: 0.4rem;
  background: linear-gradient(135deg, rgba(248,113,113,.10), rgba(139,124,246,.08));
  border: 1px solid rgba(248,113,113,.35); backdrop-filter: blur(10px);
}
.audit b { color: #f87171; }

/* ---- Efficiency gauge caption ---- */
.gauge-cap { text-align: center; color: var(--ink-2); font-size: 0.78rem; margin-top: -0.3rem; }

/* ============ EXTRA MOTION: livelier, more eye-catching UI ============ */

@keyframes fadeUp {
  from { opacity: 0; transform: translateY(14px); }
  to   { opacity: 1; transform: translateY(0); }
}
.kpi-grid, .hero, .dist-wrap, .watch-grid, .reco-wrap, .audit {
  animation: fadeUp 0.6s cubic-bezier(.2,.7,.3,1) both;
}
.kpi-grid { animation-delay: 0.05s; }
.watch-grid { animation-delay: 0.12s; }
.reco-wrap { animation-delay: 0.18s; }

.kpi { position: relative; overflow: hidden;
  transition: transform 0.25s cubic-bezier(.2,.7,.3,1), box-shadow 0.25s ease; }
.kpi::after {
  content: ""; position: absolute; top: 0; left: -120%;
  width: 60%; height: 100%;
  background: linear-gradient(115deg, transparent, rgba(120,220,255,0.14), transparent);
  transform: skewX(-18deg); animation: sheen 6s ease-in-out infinite;
}
@keyframes sheen { 0%, 72% { left: -120%; } 86%, 100% { left: 140%; } }
.kpi:hover { transform: translateY(-4px) scale(1.015);
  box-shadow: 0 14px 40px rgba(34,211,238,0.22); }
.kpi .k-accent {
  background: linear-gradient(90deg, var(--cyan), var(--teal), var(--violet));
  background-size: 200% 100%; animation: accentflow 5s linear infinite;
}
@keyframes accentflow { 0% { background-position: 0% 0; } 100% { background-position: 200% 0; } }
.kpi.churn .k-value { animation: churnpulse 2.2s ease-in-out infinite; }
@keyframes churnpulse {
  0%, 100% { text-shadow: 0 0 0 rgba(251,113,133,0); }
  50% { text-shadow: 0 0 22px rgba(251,113,133,0.55); }
}

.watch { transition: transform 0.25s ease, box-shadow 0.25s ease; }
.watch:hover { transform: translateY(-3px); box-shadow: 0 12px 30px rgba(124,92,246,0.22); }

.stButton > button, .stDownloadButton > button {
  background: linear-gradient(90deg, #22d3ee, #7c5cf6, #2dd4bf) !important;
  background-size: 220% 100% !important; border: 0 !important;
  color: #061024 !important; font-weight: 700 !important;
  transition: transform 0.12s ease, box-shadow 0.2s ease;
  animation: btnflow 6s linear infinite;
}
@keyframes btnflow { 0% { background-position: 0% 0; } 100% { background-position: 220% 0; } }
.stButton > button:hover, .stDownloadButton > button:hover {
  transform: translateY(-2px) scale(1.02);
  box-shadow: 0 10px 30px rgba(34,211,238,0.45) !important;
}
.stButton > button:active, .stDownloadButton > button:active { transform: translateY(0) scale(0.99); }

.sec { animation: slideIn 0.5s cubic-bezier(.2,.7,.3,1) both; }
@keyframes slideIn {
  from { opacity: 0; transform: translateX(-12px); }
  to   { opacity: 1; transform: translateX(0); }
}

.stTabs [data-baseweb="tab-list"] { gap: 6px; }
.stTabs [data-baseweb="tab"] { border-radius: 12px 12px 0 0; transition: background 0.2s ease; }
.stTabs [aria-selected="true"] {
  background: linear-gradient(180deg, rgba(34,211,238,0.16), transparent) !important;
  box-shadow: inset 0 -2px 0 var(--cyan);
}
</style>
"""

_NEURAL_JS = """
(function () {
  try {
    var win = window.parent, doc = win.document;
    win.__neuralGen = (win.__neuralGen || 0) + 1;
    var gen = win.__neuralGen;
    var old = doc.getElementById('neural-bg');
    if (old) { old.remove(); }
    var cv = doc.createElement('canvas');
    cv.id = 'neural-bg';
    cv.style.cssText =
      'position:fixed;inset:0;width:100%;height:100%;z-index:0;' +
      'opacity:0.9;pointer-events:none;';
    doc.body.appendChild(cv);
    var ctx = cv.getContext('2d');
    var dpr = win.devicePixelRatio || 1;
    var pal = ['#38e1ff', '#22d3ee', '#2dd4bf', '#8b7cf6', '#f472b6', '#fbbf24'];
    function resize() {
      cv.width = win.innerWidth * dpr;
      cv.height = win.innerHeight * dpr;
      cv.style.width = win.innerWidth + 'px';
      cv.style.height = win.innerHeight + 'px';
    }
    resize();
    win.addEventListener('resize', resize);
    var count = Math.min(
      160, Math.floor((win.innerWidth * win.innerHeight) / 11000));
    var nodes = win.__neuralNodes;
    if (!nodes || nodes.length !== count) {
      nodes = [];
      for (var i = 0; i < count; i++) {
        nodes.push({
          x: Math.random() * cv.width,
          y: Math.random() * cv.height,
          vx: (Math.random() - 0.5) * 0.34 * dpr,
          vy: (Math.random() - 0.5) * 0.34 * dpr,
          r: 1.2 + Math.random() * 1.8,
          ph: Math.random() * Math.PI * 2,
          c: pal[Math.floor(Math.random() * pal.length)]
        });
      }
      win.__neuralNodes = nodes;
    }
    var pulses = win.__neuralPulses;
    if (!pulses || !pulses.length) {
      pulses = [];
      for (var k = 0; k < 48; k++) {
        pulses.push({
          i: Math.floor(Math.random() * count),
          j: Math.floor(Math.random() * count),
          t: Math.random(),
          s: 0.006 + Math.random() * 0.014
        });
      }
      win.__neuralPulses = pulses;
    }
    var link = 185 * dpr;
    function step() {
      if (win.__neuralGen !== gen) { return; }
      ctx.clearRect(0, 0, cv.width, cv.height);
      var i, j, n;
      for (i = 0; i < nodes.length; i++) {
        n = nodes[i];
        n.x += n.vx; n.y += n.vy; n.ph += 0.035;
        if (n.x < 0 || n.x > cv.width) { n.vx *= -1; }
        if (n.y < 0 || n.y > cv.height) { n.vy *= -1; }
      }
      ctx.shadowBlur = 0;
      for (i = 0; i < nodes.length; i++) {
        for (j = i + 1; j < nodes.length; j++) {
          var a = nodes[i], b = nodes[j];
          var dx = a.x - b.x, dy = a.y - b.y;
          var d = Math.sqrt(dx * dx + dy * dy);
          if (d < link) {
            ctx.strokeStyle =
              'rgba(110,205,250,' + (1 - d / link) * 0.40 + ')';
            ctx.lineWidth = dpr;
            ctx.beginPath();
            ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
          }
        }
      }
      for (var p = 0; p < pulses.length; p++) {
        var pu = pulses[p];
        pu.t += pu.s;
        if (pu.t > 1) {
          pu.t = 0; pu.i = pu.j;
          pu.j = Math.floor(Math.random() * nodes.length);
        }
        var na = nodes[pu.i], nb = nodes[pu.j];
        var px = na.x + (nb.x - na.x) * pu.t;
        var py = na.y + (nb.y - na.y) * pu.t;
        ctx.beginPath();
        ctx.fillStyle = 'rgba(180,245,255,0.9)';
        ctx.shadowBlur = 10 * dpr; ctx.shadowColor = '#7ef0ff';
        ctx.arc(px, py, 1.7 * dpr, 0, Math.PI * 2); ctx.fill();
      }
      for (i = 0; i < nodes.length; i++) {
        n = nodes[i];
        var g = (Math.sin(n.ph) + 1) / 2;
        ctx.beginPath();
        ctx.fillStyle = n.c;
        ctx.shadowBlur = (6 + g * 8) * dpr; ctx.shadowColor = n.c;
        ctx.arc(n.x, n.y, (n.r + g * 0.8) * dpr, 0, Math.PI * 2); ctx.fill();
      }
      ctx.shadowBlur = 0;
      win.requestAnimationFrame(step);
    }
    win.requestAnimationFrame(step);
  } catch (err) { /* background is decorative; never break the app */ }
})();
"""


def _inject_theme() -> None:
    """Inject the premium dark CSS theme (safe on every rerun)."""
    st.markdown(_THEME_CSS, unsafe_allow_html=True)


def _inject_neural_background() -> None:
    """Inject the living neural-network canvas behind the app.

    The script runs inside a zero-height component iframe and draws onto a
    fixed canvas appended to the parent document. It is fully decorative and
    wrapped in ``try/catch`` so it can never disrupt the workflow.
    """
    components.html(f"<script>{_NEURAL_JS}</script>", height=0)


def _risk_rank(label: Any) -> int:
    """Map a free-form risk label to a severity rank (1=low .. 4=critical)."""
    token = str(label).strip().lower()
    if any(key in token for key in ("crit", "crít")):
        return 4
    if any(key in token for key in ("high", "alto", "elev", "sever")):
        return 3
    if any(key in token for key in ("low", "bajo", "min")):
        return 1
    return 2


def _churn_prob(row: dict[str, Any]) -> float | None:
    """Best-effort extraction of a 0-100 churn probability from a table row."""
    for key, value in row.items():
        token = str(key).lower()
        if any(t in token for t in ("prob", "churn", "score", "propens")):
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if 0.0 <= number <= 1.0:
                number *= 100.0
            if 0.0 <= number <= 100.0:
                return number
    return None


def _section(title: str, kicker: str) -> None:
    """Render a styled, animated section header."""
    st.markdown(
        f'<div class="sec"><span class="kicker">{kicker}</span>{title}</div>',
        unsafe_allow_html=True,
    )


def _render_hero() -> None:
    """Render the AI-core hero with agents and ambient live telemetry."""
    equalizer = "".join(f'<i style="animation-delay:{i * 0.06:.2f}s"></i>' for i in range(24))
    chips = "".join(
        f'<span class="agent"><span class="dot"></span>{name}</span>' for name in _AGENTS
    )
    bars = "".join(
        f'<div class="ab"><span>{name}</span><div class="ab-track">'
        f'<div class="ab-fill" style="animation-delay:{i * 0.4:.2f}s"></div>'
        "</div></div>"
        for i, name in enumerate(_AGENTS)
    )
    st.markdown(
        f"""
        <div class="hero"><div class="hero-grid">
          <div class="hero-main">
            <div class="eyebrow">Plataforma multiagente · Detección de churn</div>
            <h1>Núcleo de Retención Inteligente</h1>
            <p>Un conjunto de agentes especializados analiza cada cliente en
            paralelo, estima su probabilidad de abandono con el modelo y decide
            la acción de retención óptima bajo control humano.</p>
            <div class="agents">{chips}</div>
          </div>
          <div class="tele">
            <div class="tele-h">Actividad del núcleo · <b>en vivo</b></div>
            <div class="eq">{equalizer}</div>
            <div class="tele-row">
              <div class="gauge"><span>72%</span></div>
              <div class="abs">{bars}</div>
            </div>
          </div>
        </div></div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# State, data loading and workflow execution (engine wiring — unchanged)       #
# --------------------------------------------------------------------------- #


def _init_state() -> None:
    """Initialise Streamlit session state keys."""
    st.session_state.setdefault("records", None)
    st.session_state.setdefault("results", None)
    st.session_state.setdefault("trained_model_path", None)


def _load_records(uploaded: Any) -> list[CustomerRecord]:
    """Load customer records from an upload or the bundled sample."""
    if uploaded is not None:
        suffix = Path(uploaded.name).suffix
        tmp = Path(tempfile.gettempdir()) / f"crw_upload{suffix}"
        tmp.write_bytes(uploaded.getvalue())
        return load_customers(tmp)
    return load_customers(_SAMPLE_CSV)


def _run_workflow(
    records: list[CustomerRecord], policy_path: Path, model_source: str | None
) -> tuple[list[WorkflowResult], AuditApprovalGateway]:
    """Execute the workflow in *audit mode*: 100% processed, never blocked.

    Offers exceeding the policy threshold are flagged for human audit instead
    of halting the pipeline, so every customer receives an automated decision.
    """
    gateway = AuditApprovalGateway()
    workflow = RetentionWorkflow(
        policy=load_policy(policy_path),
        model=build_churn_model_from_any(model_source),
        approval_gateway=gateway,
    )
    results = asyncio.run(workflow.run_batch(records))
    return results, gateway


# --------------------------------------------------------------------------- #
# Rendering (restyled presentation only)                                       #
# --------------------------------------------------------------------------- #


def _render_sidebar() -> tuple[Any, Path, str | None, bool]:
    """Render the configuration sidebar and return the chosen inputs."""
    st.sidebar.markdown('<div class="eyebrow">Núcleo · en línea</div>', unsafe_allow_html=True)
    st.sidebar.header("⚙️ Configuración")
    uploaded = st.sidebar.file_uploader("Dataset de clientes (CSV/XLSX)", type=["csv", "xlsx"])
    st.sidebar.caption("Si no subes un archivo, se usa el dataset de ejemplo incluido.")

    use_custom_policy = st.sidebar.checkbox("Subir política propia (.md)", value=False)
    policy_path = _SAMPLE_POLICY
    if use_custom_policy:
        pol = st.sidebar.file_uploader("Política de retención (.md)", type=["md"])
        if pol is not None:
            tmp = Path(tempfile.gettempdir()) / "crw_uploaded_policy.md"
            tmp.write_bytes(pol.getvalue())
            policy_path = tmp

    model_source = st.sidebar.text_input(
        "Ruta al modelo (.pkl o .py, opcional)",
        value=str(st.session_state.get("trained_model_path") or ""),
        placeholder="models/churn_random_forest.pkl",
        help=(
            "Vacío → heurístico incluido · .pkl → modelo entrenado en la "
            "pestaña Entrenar Modelo · .py → model_base.py del challenge."
        ),
    )

    use_ollama = st.sidebar.toggle(
        "Recomendaciones con Ollama (local)",
        value=False,
        help=(
            "Si tienes Ollama corriendo (p. ej. qwen2.5) se usa para las "
            "recomendaciones; si no responde, se usa el motor de reglas."
        ),
    )
    return uploaded, policy_path, (model_source or None), use_ollama


def _render_kpis(results: list[WorkflowResult], alert_count: int) -> None:
    """Render churn-first KPI cards as glowing glass tiles."""
    summary = summarize(results)

    cards = [
        ("Clientes analizados", f"{int(summary['total_customers']):,}", ""),
        ("Alertados para auditoría", f"{alert_count:,}", "churn"),
        ("Retenidos con oferta", f"{int(summary['retained']):,}", ""),
        ("Gasto en ofertas", f"{float(summary['offer_spend']):,.0f}", ""),
        ("Valor protegido", f"{float(summary['value_protected']):,.0f}", ""),
    ]
    tiles = "".join(
        f'<div class="kpi {css}"><div class="k-accent"></div>'
        f'<div class="k-label">{label}</div>'
        f'<div class="k-value">{value}</div></div>'
        for label, value, css in cards
    )
    st.markdown(f'<div class="kpi-grid">{tiles}</div>', unsafe_allow_html=True)


def _render_watchlist(table: list[dict[str, Any]]) -> None:
    """Render the top churn-risk customers as an animated watchlist."""
    ranked = sorted(table, key=lambda row: _risk_rank(row.get("risk_level")), reverse=True)
    top = [row for row in ranked if _risk_rank(row.get("risk_level")) >= 3][:8]
    if not top:
        return

    _section("Clientes en riesgo · watchlist", "Prioridad de retención")
    cards = ""
    for row in top:
        rank = _risk_rank(row.get("risk_level"))
        color = _RISK_COLORS[rank]
        prob = _churn_prob(row)
        prob_txt = f"{prob:.0f}% churn" if prob is not None else "&nbsp;"
        width = int(rank / 4 * 100)
        cards += (
            '<div class="watch"><div class="watch-top">'
            f'<span class="watch-id">{row.get("customer_id", "—")}</span>'
            f'<span class="chip" style="background:{color}">'
            f'{row.get("risk_level", "—")}</span></div>'
            '<div class="watch-meter">'
            f'<i style="width:{width}%;background:{color}"></i></div>'
            f'<div class="watch-foot"><span>{row.get("action", "—")}</span>'
            f"<span>{prob_txt}</span></div></div>"
        )
    st.markdown(f'<div class="watch-grid">{cards}</div>', unsafe_allow_html=True)


def _dist_panel(title: str, counts: pd.Series, by_risk: bool) -> str:
    """Build the HTML for a single distribution panel."""
    total = int(counts.sum()) or 1
    rows = ""
    for name, value in counts.items():
        pct = round(100 * int(value) / total)
        color = _RISK_COLORS[_risk_rank(name)] if by_risk else "#38bdf8"
        rows += (
            '<div class="bar-row">'
            f'<div class="bar-name">{name}</div>'
            '<div class="bar-track">'
            f'<div class="bar-fill" style="width:{pct}%;background:{color}"></div>'
            "</div>"
            f'<div class="bar-val">{int(value)}</div>'
            "</div>"
        )
    return f'<div class="dist-panel"><div class="dist-title">{title}</div>{rows}</div>'


def _render_distributions(table: list[dict[str, Any]]) -> None:
    """Render risk and action distributions as animated glass bar panels."""
    frame = pd.DataFrame(table)
    risk_counts = frame["risk_level"].value_counts()
    action_counts = frame["action"].value_counts()
    _section("Distribuciones", "Panorama de cartera")
    st.markdown(
        '<div class="dist-wrap">'
        + _dist_panel("Nivel de riesgo de abandono", risk_counts, True)
        + _dist_panel("Acción recomendada", action_counts, False)
        + "</div>",
        unsafe_allow_html=True,
    )


def _render_gauge(results: list[WorkflowResult]) -> None:
    """Render the core-efficiency speedometer (Plotly gauge)."""
    eff = efficiency_metrics(results)
    figure = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=eff["efficiency_pct"],
            number={"suffix": "%", "font": {"color": "#eaf2ff", "size": 40}},
            gauge={
                "axis": {"range": [0, 100], "tickcolor": "#8aa0c8"},
                "bar": {"color": "#2dd4bf", "thickness": 0.28},
                "bgcolor": "rgba(255,255,255,0.04)",
                "borderwidth": 0,
                "steps": [
                    {"range": [0, 60], "color": "rgba(248,113,113,.25)"},
                    {"range": [60, 85], "color": "rgba(251,191,36,.22)"},
                    {"range": [85, 100], "color": "rgba(45,212,191,.22)"},
                ],
            },
        )
    )
    figure.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        height=240,
        margin={"l": 24, "r": 24, "t": 18, "b": 4},
        font={"color": "#eaf2ff"},
    )
    st.plotly_chart(figure, use_container_width=True)
    st.markdown(
        f'<div class="gauge-cap">Aprobación en primera pasada: '
        f'{eff["approved_first_pass"]:,}/{eff["processed"]:,} · '
        f'Latencia media: {eff["avg_latency_ms"]:.0f} ms · '
        f'Errores de agentes: {eff["agent_error_count"]}</div>',
        unsafe_allow_html=True,
    )


def _render_recommendations(results: list[WorkflowResult], use_ollama: bool) -> None:
    """Render up to five qualitative churn-mitigation recommendations."""
    engine = build_recommendation_engine(use_ollama=use_ollama)
    bullets = engine.recommend(results)
    items = "".join(f'<div class="reco">{bullet}</div>' for bullet in bullets[:5])
    st.markdown(f'<div class="reco-wrap">{items}</div>', unsafe_allow_html=True)
    st.caption(f"Motor de recomendaciones: {engine.name}")


def _render_alert_report(results: list[WorkflowResult]) -> None:
    """Render the human-audit alert report with JSON / PDF / XLSX export."""
    alerts = alerted_rows(results)
    _section("Informe de clientes con alertamiento", "Auditoría humana")
    if not alerts:
        st.success("Sin alertas en este lote: ninguna oferta superó el umbral de la política.")
        return

    st.markdown(
        f'<div class="audit">El núcleo procesó el <b>100%</b> de los casos y marcó '
        f"<b>{len(alerts)} ofertas</b> que superan el umbral de la política para "
        "revisión posterior del auditor. Descarga el informe en el formato que "
        "prefieras.</div>",
        unsafe_allow_html=True,
    )
    col_fmt, col_btn = st.columns([1, 2])
    with col_fmt:
        fmt = st.radio(
            "Formato del informe",
            options=["json", "pdf", "xlsx"],
            format_func=str.upper,
            horizontal=True,
        )
    with col_btn:
        st.write("")
        st.download_button(
            f"📥 Generar informe de alertas ({fmt.upper()})",
            data=build_alert_report(alerts, fmt),
            file_name=f"alertas_retencion.{fmt}",
            mime=_MIME[fmt],
            type="primary",
        )


def _render_results_table(table: list[dict[str, Any]]) -> None:
    """Render the decisions dataframe, highest churn risk first."""
    _section("Decisiones por cliente", "Detalle operativo")
    frame = pd.DataFrame(table)
    if "risk_level" in frame.columns:
        frame = (
            frame.assign(_rank=frame["risk_level"].map(_risk_rank))
            .sort_values("_rank", ascending=False)
            .drop(columns="_rank")
        )
    st.dataframe(frame, use_container_width=True, hide_index=True)


def _render_trainer() -> None:
    """Render the model-training tab: fit a classifier and export a .pkl."""
    _section("Entrenar modelo de predicción de churn", "Machine Learning")
    st.caption(
        "Sube un dataset etiquetado (columna `churn` = 0/1), entrena, evalúa "
        "y exporta un .pkl que el Núcleo usará como modelo predictivo."
    )

    train_file = st.file_uploader(
        "Dataset etiquetado (CSV/XLSX)", type=["csv", "xlsx"], key="train"
    )
    default_csv = Path("data/customers.csv")
    if train_file is None:
        if not default_csv.exists():
            st.warning("No hay dataset. Genera uno con `make data` o sube un archivo.")
            return
        st.info(f"Se usará el dataset sintético incluido: `{default_csv}`.")
        train_path: Path = default_csv
    else:
        train_path = Path(tempfile.gettempdir()) / f"crw_train{Path(train_file.name).suffix}"
        train_path.write_bytes(train_file.getvalue())

    col_a, col_b = st.columns(2)
    with col_a:
        algorithm = st.selectbox(
            "Algoritmo", ["Random Forest", "Gradient Boosting", "Logistic Regression"]
        )
    with col_b:
        test_size = st.slider("Test set (%)", 10, 40, 20, 5)

    if not st.button("🚀 Entrenar modelo", type="primary"):
        return

    # pylint: disable-next=import-outside-toplevel
    from customer_retention.infrastructure.model_trainer import train_model

    try:
        with st.spinner(f"Entrenando {algorithm}…"):
            result = train_model(
                csv_path=train_path,
                algorithm_name=algorithm,
                test_size=test_size / 100.0,
                model_dir="models",
            )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        st.error(f"Error durante el entrenamiento: {exc}")
        return

    st.success(f"✅ {result.summary()}")
    met1, met2, met3 = st.columns(3)
    met1.metric("AUC-ROC", f"{result.auc_roc:.4f}")
    met2.metric("CV AUC (5-fold)", f"{result.cv_auc_mean:.4f} ± {result.cv_auc_std:.4f}")
    met3.metric("Accuracy", f"{result.accuracy:.4f}")

    if result.feature_importance:
        importance = (
            pd.DataFrame(result.feature_importance.items(), columns=["Variable", "Importancia"])
            .sort_values("Importancia", ascending=False)
            .set_index("Variable")
        )
        st.bar_chart(importance)

    st.session_state["trained_model_path"] = str(result.model_path)
    st.code(str(result.model_path))
    st.info(
        "Ruta copiada al campo de modelo del panel lateral. Vuelve a la pestaña "
        "Núcleo y pulsa **Ejecutar workflow** para usarla."
    )
    with open(result.model_path, "rb") as handle:
        st.download_button(
            f"⬇️ Descargar {result.model_path.name}",
            data=handle,
            file_name=result.model_path.name,
            mime="application/octet-stream",
        )


def _render_download(results: list[WorkflowResult]) -> None:
    """Render a JSON report download button."""
    payload = json.dumps([r.as_dict() for r in results], indent=2, ensure_ascii=False)
    st.download_button(
        "⬇️ Descargar reporte JSON",
        data=payload,
        file_name="retention_report.json",
        mime="application/json",
    )


def _render_start_panel() -> None:
    """Render the animated pre-run 'getting started' panel."""
    st.markdown(
        """
        <div class="start">
          <h3>Listo para analizar tu cartera</h3>
          <p>Configura la fuente de datos en el panel lateral y pulsa
          <b>Ejecutar workflow</b>. El núcleo desplegará a los agentes para
          estimar el riesgo de abandono de cada cliente y proponer la acción
          de retención óptima.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_nucleus(policy_path: Path, model_source: str | None, use_ollama: bool) -> None:
    """Render the main nucleus dashboard tab."""
    records = st.session_state.get("records")
    if not records:
        _render_start_panel()
        return

    with st.spinner("El núcleo está procesando la cartera completa…"):
        results, gateway = _run_workflow(records, policy_path, model_source)
    st.session_state["results"] = results

    table = build_table(results)
    alerts = alerted_rows(results)

    _render_kpis(results, alert_count=len(alerts))
    st.divider()

    col_gauge, col_reco = st.columns([1, 1.35])
    with col_gauge:
        _section("Eficiencia del núcleo", "Procesamiento automático")
        _render_gauge(results)
    with col_reco:
        _section("Recomendaciones del modelo", "Mitigación de abandono")
        _render_recommendations(results, use_ollama)

    st.divider()
    _render_watchlist(table)
    st.divider()
    _render_distributions(table)
    _render_alert_report(results)
    _render_results_table(table)
    st.divider()
    _render_download(results)
    st.caption(
        f"Trazabilidad completa disponible en el informe descargable · "
        f"{len(gateway.alerts)} alertas registradas por el gateway de auditoría."
    )


def main() -> None:
    """Streamlit application entry point."""
    st.set_page_config(
        page_title="Retención de Clientes — Multiagente",
        page_icon="🛰️",
        layout="wide",
    )
    _init_state()
    _inject_theme()
    _inject_neural_background()
    _render_hero()

    uploaded, policy_path, model_source, use_ollama = _render_sidebar()

    if st.sidebar.button("▶️ Ejecutar workflow", type="primary"):
        st.session_state["records"] = _load_records(uploaded)

    tab_nucleus, tab_train = st.tabs(["🧠 Núcleo", "🎓 Entrenar Modelo"])
    with tab_nucleus:
        _render_nucleus(policy_path, model_source, use_ollama)
    with tab_train:
        _render_trainer()


if __name__ == "__main__":
    main()

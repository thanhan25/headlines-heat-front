import html
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

import requests
import streamlit as st

# --- Page Configuration ---
st.set_page_config(
    page_title="SENTINEL // Market Regime & Sentiment Terminal",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- Theme State & Toggle Logic ---
if "theme" not in st.session_state:
    st.session_state.theme = "dark"

def toggle_theme():
    st.session_state.theme = "light" if st.session_state.theme == "dark" else "dark"

dark_theme = """
    --bg-base: #07090E;
    --bg-panel: #0D111A;
    --bg-card: #111622;
    --bg-input: #090C14;
    --border-subtle: #1E2638;
    --border-focus: #3B82F6;
    --text-primary: #F1F5F9;
    --text-secondary: #94A3B8;
    --text-muted: #64748B;
    --emerald: #10B981;
    --rose: #F43F5E;
    --amber: #F59E0B;
    --cyan: #38BDF8;
    --cobalt: #2563EB;
"""

light_theme = """
    --bg-base: #F8FAFC;
    --bg-panel: #FFFFFF;
    --bg-card: #FFFFFF;
    --bg-input: #F1F5F9;
    --border-subtle: #E2E8F0;
    --border-focus: #3B82F6;
    --text-primary: #0F172A;
    --text-secondary: #475569;
    --text-muted: #94A3B8;
    --emerald: #059669;
    --rose: #E11D48;
    --amber: #D97706;
    --cyan: #0284C7;
    --cobalt: #2563EB;
"""

active_theme = dark_theme if st.session_state.theme == "dark" else light_theme

# Inject dynamic colors
st.markdown(f"<style>:root {{ {active_theme} }}</style>", unsafe_allow_html=True)

# --- Institutional Quant Terminal CSS ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

html, body, .stApp {
    background-color: var(--bg-base);
    background-image: radial-gradient(circle at 50% 0%, rgba(37, 99, 235, 0.06), transparent 55%);
    color: var(--text-primary);
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    transition: background-color 0.3s ease, color 0.3s ease;
}

.main .block-container {
    padding-top: 1.5rem;
    padding-bottom: 3rem;
    max-width: 1360px;
}

header, #MainMenu, footer { visibility: hidden; }

* { font-variant-numeric: tabular-nums; }

/* --- Top System Telemetry Bar --- */
.telemetry-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 18px;
    background: var(--bg-panel);
    border: 1px solid var(--border-subtle);
    border-radius: 6px;
    margin-bottom: 24px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--text-secondary);
    letter-spacing: 0.4px;
    flex-wrap: wrap;
    gap: 10px;
    transition: all 0.3s ease;
}
.telemetry-group { display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }
.status-indicator {
    display: inline-flex; align-items: center; gap: 8px;
    color: var(--emerald); font-weight: 600;
}
.status-dot {
    width: 6px; height: 6px; background: var(--emerald);
    border-radius: 50%; box-shadow: 0 0 6px rgba(16,185,129,0.7);
}
.telemetry-kv span { color: var(--text-primary); font-weight: 600; }

/* --- Terminal Header --- */
.terminal-header {
    display: flex; justify-content: space-between; align-items: flex-end;
    padding-bottom: 24px; margin-bottom: 28px;
    border-bottom: 1px solid var(--border-subtle);
    flex-wrap: wrap; gap: 20px;
}
.eyebrow {
    font-family: 'JetBrains Mono', monospace; font-size: 11px;
    text-transform: uppercase; letter-spacing: 1.5px;
    color: var(--cyan); margin-bottom: 8px; font-weight: 600;
}
.terminal-title {
    font-size: 2.25rem; font-weight: 700; color: var(--text-primary);
    letter-spacing: -0.8px; margin: 0; line-height: 1.15;
}
.terminal-subtitle {
    font-size: 0.95rem; color: var(--text-secondary);
    margin: 8px 0 0 0; max-width: 640px; line-height: 1.5;
}
.header-specs {
    display: flex; gap: 24px; background: var(--bg-panel);
    border: 1px solid var(--border-subtle); padding: 12px 18px; border-radius: 6px;
    transition: all 0.3s ease;
}
.spec-item { display: flex; flex-direction: column; }
.spec-label {
    font-size: 10px; font-family: 'JetBrains Mono', monospace;
    text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.8px;
}
.spec-value {
    font-size: 13px; font-family: 'JetBrains Mono', monospace;
    color: var(--text-primary); font-weight: 600; margin-top: 2px;
}

/* --- Panel & Section Headers --- */
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.panel-title {
    font-size: 12px; font-family: 'JetBrains Mono', monospace; font-weight: 600;
    text-transform: uppercase; letter-spacing: 1px; color: var(--text-secondary);
    display: flex; align-items: center; gap: 8px;
}
.panel-title::before { content: ''; display: inline-block; width: 3px; height: 12px; background: var(--cobalt); }
.panel-meta { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--text-muted); }

/* --- Streamlit Input Overrides --- */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea {
    background-color: var(--bg-input) !important;
    border: 1px solid var(--border-subtle) !important;
    color: var(--text-primary) !important;
    border-radius: 6px !important;
    font-size: 14px !important;
    padding: 11px 14px !important;
    font-family: 'Inter', sans-serif !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease, background-color 0.3s ease;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: var(--border-focus) !important;
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15) !important;
}
.stSelectbox > div > div > div {
    background-color: var(--bg-input) !important;
    border: 1px solid var(--border-subtle) !important;
    color: var(--text-primary) !important;
    border-radius: 6px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 13px !important;
    transition: background-color 0.3s ease, border-color 0.3s ease;
}
.stTextInput label, .stTextArea label, .stSelectbox label {
    color: var(--text-secondary) !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 500 !important;
    font-size: 11px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.6px !important;
}

/* --- Field label for the segmented control --- */
.field-label {
    color: var(--text-secondary);
    font-family: 'JetBrains Mono', monospace;
    font-weight: 500; font-size: 11px;
    text-transform: uppercase; letter-spacing: 0.6px;
    margin-bottom: 6px;
}

/* --- Buttons --- */
.stButton > button {
    border-radius: 6px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 600 !important;
    font-size: 12px !important;
    letter-spacing: 0.5px !important;
    text-transform: uppercase !important;
    padding: 11px 18px !important;
    transition: all 0.15s ease !important;
}
.stButton > button[kind="primary"] {
    background: var(--cobalt) !important;
    color: #FFFFFF !important;
    border: 1px solid #3B82F6 !important;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.4) !important;
}
.stButton > button[kind="primary"]:hover {
    background: #1D4ED8 !important;
    border-color: #60A5FA !important;
}
.stButton > button[kind="secondary"] {
    background: var(--bg-panel) !important;
    color: var(--text-secondary) !important;
    border: 1px solid var(--border-subtle) !important;
}
.stButton > button[kind="secondary"]:hover {
    color: var(--text-primary) !important;
    border-color: #334155 !important;
}
/* small segmented variant for the neural branch switch */
.seg-a > button, .seg-b > button {
    padding: 8px 10px !important;
    font-size: 11px !important;
}

/* --- Consensus Strip --- */
.consensus-strip {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px;
    background: var(--border-subtle); border: 1px solid var(--border-subtle);
    border-radius: 6px; overflow: hidden; margin-bottom: 24px;
}
.consensus-cell { background: var(--bg-panel); padding: 14px 18px; transition: background-color 0.3s ease; }
.c-label {
    font-family: 'JetBrains Mono', monospace; font-size: 10px;
    text-transform: uppercase; letter-spacing: 0.8px;
    color: var(--text-muted); margin-bottom: 4px;
}
.c-val { font-family: 'JetBrains Mono', monospace; font-size: 15px; font-weight: 700; color: var(--text-primary); }

/* --- Institutional Telemetry Cards --- */
.quant-card {
    background: var(--bg-card); border: 1px solid var(--border-subtle);
    border-radius: 8px; padding: 24px; height: 100%; position: relative;
    transition: all 0.3s ease;
}
.quant-card-header {
    display: flex; justify-content: space-between; align-items: flex-start;
    padding-bottom: 16px; margin-bottom: 20px; border-bottom: 1px solid var(--border-subtle);
}
.model-name { font-size: 15px; font-weight: 600; color: var(--text-primary); margin: 0; }
.model-arch { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--text-muted); margin-top: 3px; }
.latency-tag {
    font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--text-secondary);
    background: var(--bg-input); border: 1px solid var(--border-subtle);
    padding: 4px 8px; border-radius: 4px; white-space: nowrap;
}

/* --- Regime Readout Box --- */
.regime-box {
    padding: 16px 20px; border-radius: 6px; margin-bottom: 22px;
    display: flex; justify-content: space-between; align-items: center;
}
.regime-hot    { background: rgba(245,158,11,0.07); border: 1px solid rgba(245,158,11,0.3);  border-left: 3px solid var(--amber); }
.regime-bull   { background: rgba(16,185,129,0.07); border: 1px solid rgba(16,185,129,0.3);  border-left: 3px solid var(--emerald); }
.regime-bear   { background: rgba(244,63,94,0.07);  border: 1px solid rgba(244,63,94,0.3);   border-left: 3px solid var(--rose); }
.regime-cold   { background: rgba(56,189,248,0.06); border: 1px solid rgba(56,189,248,0.25); border-left: 3px solid var(--cyan); }
.regime-label {
    font-family: 'JetBrains Mono', monospace; font-size: 10px;
    text-transform: uppercase; letter-spacing: 1px; color: var(--text-secondary); margin-bottom: 4px;
}
.regime-title { font-family: 'JetBrains Mono', monospace; font-size: 18px; font-weight: 700; letter-spacing: 0.3px; }
.text-amber { color: var(--amber); }
.text-emerald { color: var(--emerald); }
.text-rose { color: var(--rose); }
.text-cyan { color: var(--cyan); }
.regime-score { text-align: right; font-family: 'JetBrains Mono', monospace; }
.regime-score-val { font-size: 22px; font-weight: 700; color: var(--text-primary); }
.regime-score-sub { font-size: 10px; color: var(--text-muted); text-transform: uppercase; }

/* --- Stacked Multi-Class Bar --- */
.spectrum-wrapper { margin-bottom: 22px; }
.spectrum-header {
    display: flex; justify-content: space-between;
    font-family: 'JetBrains Mono', monospace; font-size: 11px;
    color: var(--text-secondary); margin-bottom: 8px;
}
.spectrum-bar {
    display: flex; height: 8px; width: 100%;
    background: var(--bg-input); border-radius: 4px; overflow: hidden; gap: 2px;
}
.seg-cold { background: var(--cyan); height: 100%; }
.seg-rising { background: var(--emerald); height: 100%; }
.seg-falling { background: var(--rose); height: 100%; }

/* --- Precision Probability Rows --- */
.prob-grid { display: flex; flex-direction: column; gap: 14px; }
.prob-row { display: flex; flex-direction: column; gap: 6px; }
.prob-meta { display: flex; justify-content: space-between; font-family: 'JetBrains Mono', monospace; font-size: 12px; }
.prob-name { color: var(--text-secondary); }
.prob-pct { color: var(--text-primary); font-weight: 600; }
.prob-track { width: 100%; height: 5px; background: rgba(148, 163, 184, 0.2); border-radius: 2px; overflow: hidden; }
.prob-fill-cyan { background: var(--cyan); height: 100%; }
.prob-fill-emerald { background: var(--emerald); height: 100%; }
.prob-fill-rose { background: var(--rose); height: 100%; }

/* --- Metadata Grid --- */
.meta-table { width: 100%; border-collapse: collapse; margin-top: 14px; font-family: 'JetBrains Mono', monospace; font-size: 12px; }
.meta-table tr { border-bottom: 1px solid var(--border-subtle); }
.meta-table td { padding: 10px 0; }
.meta-table td:first-child { color: var(--text-muted); }
.meta-table td:last-child { color: var(--text-primary); text-align: right; font-weight: 500; }

/* --- Placeholder / pending-calibration state --- */
.placeholder-box {
    border: 1px dashed var(--border-subtle);
    background: var(--bg-panel);
    border-radius: 6px;
    padding: 18px 20px;
    margin-top: 18px;
}
.ph-title {
    font-family: 'JetBrains Mono', monospace; font-size: 11px;
    text-transform: uppercase; letter-spacing: 1px;
    color: var(--amber); font-weight: 600; margin-bottom: 8px;
}
.ph-body { font-size: 12.5px; color: var(--text-secondary); line-height: 1.55; margin-bottom: 6px; }
.ph-route { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--text-muted); }
.skeleton {
    height: 6px; border-radius: 3px; margin-top: 12px;
    background: linear-gradient(90deg, var(--bg-input) 25%, var(--border-subtle) 50%, var(--bg-input) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.8s infinite linear;
}
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

/* --- Ingest manifest --- */
.manifest { width: 100%; border-collapse: collapse; font-family: 'JetBrains Mono', monospace; font-size: 11.5px; }
.manifest td { padding: 7px 4px; border-bottom: 1px solid var(--border-subtle); color: var(--text-secondary); vertical-align: top; }
.manifest td:first-child { color: var(--text-muted); width: 46px; }
.manifest td:last-child { text-align: right; width: 70px; color: var(--text-muted); }

/* --- Footnote --- */
.footnote {
    font-family: 'JetBrains Mono', monospace; font-size: 10.5px;
    color: var(--text-muted); text-align: center;
    padding: 28px 0 6px; letter-spacing: 0.4px; line-height: 1.7;
}

hr { border: none !important; height: 1px !important; background: var(--border-subtle) !important; margin: 26px 0 !important; }
</style>
""", unsafe_allow_html=True)


def safe_text(value: Any, limit: int = 500) -> str:
    """Escape untrusted text before embedding it in custom HTML."""
    return html.escape(str(value)[:limit], quote=True)


def parse_prediction_response(response: requests.Response) -> tuple[bool, dict, str]:
    """Validate HTTP status and JSON shape without disguising failures as class 0."""
    if response.status_code != 200:
        body = safe_text(response.text, 300)
        return False, {}, f"HTTP {response.status_code}: {body}"
    try:
        payload = response.json()
    except ValueError:
        return False, {}, "Endpoint returned invalid JSON."
    if not isinstance(payload, dict):
        return False, {}, "Endpoint response must be a JSON object."
    if "prediction" not in payload:
        return False, payload, "Endpoint response is missing the required 'prediction' field."
    try:
        prediction = float(payload["prediction"])
    except (TypeError, ValueError):
        return False, payload, "The 'prediction' field must be numeric."
    if prediction != prediction or prediction in (float("inf"), float("-inf")):
        return False, payload, "The 'prediction' field must be finite."
    payload["prediction"] = prediction
    return True, payload, ""


def call_svc(url: str, headline: str, model_code: float | int, timeout: int = 15) -> dict:
    started = time.perf_counter()
    result = {"ok": False, "val": None, "latency_ms": 0, "error": "", "data": {}}
    try:
        response = requests.get(
            f"{url}/predict",
            params={"headline": headline, "model_choice": model_code},
            timeout=(3.05, timeout),
        )
        result["latency_ms"] = int((time.perf_counter() - started) * 1000)
        ok, payload, error = parse_prediction_response(response)
        result.update(ok=ok, data=payload, error=error)
        if ok:
            result["val"] = payload["prediction"]
    except requests.RequestException as exc:
        result["latency_ms"] = int((time.perf_counter() - started) * 1000)
        result["error"] = f"{type(exc).__name__}: {safe_text(exc, 250)}"
    return result


def call_finbert(url: str, headline: str, summary: str, timeout: int = 20) -> dict:
    started = time.perf_counter()
    result = {"ok": False, "val": None, "latency_ms": 0, "error": "", "data": {}}
    try:
        response = requests.post(
            f"{url}/dl_predict",
            json={"headline": headline, "summary": summary},
            timeout=(3.05, timeout),
        )
        result["latency_ms"] = int((time.perf_counter() - started) * 1000)
        ok, payload, error = parse_prediction_response(response)
        result.update(ok=ok, data=payload, error=error)
        if ok:
            result["val"] = payload["prediction"]
            probs = payload.get("probabilities")
            if probs is not None and not isinstance(probs, dict):
                result.update(ok=False, error="'probabilities' must be a JSON object.")
    except requests.RequestException as exc:
        result["latency_ms"] = int((time.perf_counter() - started) * 1000)
        result["error"] = f"{type(exc).__name__}: {safe_text(exc, 250)}"
    return result


def get_secret(key: str) -> str:
    """
    Retrieves a secret from Streamlit.
    If missing, displays a UI error and halts the app safely.
    """
    try:
        value = st.secrets.get(key)
    except (FileNotFoundError, KeyError, AttributeError):
        value = None
    if not value:
        st.error(f"⚠️ **Missing Configuration:** `{key}` was not found in your secrets.")
        st.info(f"Please add `{key} = \"https://...\"` to your local `.streamlit/secrets.toml` file or your Streamlit Cloud dashboard.")
        st.stop()  # Gracefully stops the Streamlit app execution

    return str(value).rstrip("/")

# Load URLs securely (No hardcoded defaults in your code!)
SVC_API_URL = get_secret("SVC_API_URL")
DL_API_URL = get_secret("DL_API_URL")

# LSTM lives behind the SVC service, routed by model_choice=7 (see fast.py)
LSTM_MODEL_CODE = 7

# --- Session State & Callbacks ---
st.session_state.setdefault("num_inputs", 3)
st.session_state.setdefault("summary_input", "")
st.session_state.setdefault("dl_branch", "FINBERT-TONE")
st.session_state.setdefault("sid", uuid.uuid4().hex[:8].upper())

UTC_NOW = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def check_last_input():
    last_index = st.session_state.num_inputs - 2
    if st.session_state.get(f"input_{last_index}", "").strip() and st.session_state.num_inputs < 21:
        st.session_state.num_inputs += 1


def reset_all_inputs():
    for i in range(st.session_state.num_inputs):
        st.session_state[f"input_{i}"] = ""
    st.session_state.summary_input = ""
    st.session_state.num_inputs = 3


def load_preset(headlines: list, summary: str):
    reset_all_inputs()
    st.session_state.num_inputs = max(3, len(headlines) + 1)
    for idx, text in enumerate(headlines):
        st.session_state[f"input_{idx}"] = text
    st.session_state.summary_input = summary


# --- Top System Telemetry Bar & Theme Toggle ---
t_col1, t_col2 = st.columns([1, 0.15])
with t_col2:
    st.toggle("☀️ Light Mode",
              value=(st.session_state.theme == "light"),
              on_change=toggle_theme,
              key="theme_toggle")

st.markdown(f"""
<div class="telemetry-bar">
    <div class="telemetry-group">
        <div class="status-indicator"><span class="status-dot"></span> DUAL-INFERENCE ENGINE READY</div>
        <div class="telemetry-kv">ENV: <span>PRODUCTION</span></div>
        <div class="telemetry-kv">REGION: <span>GCP // EUROPE-WEST1</span></div>
    </div>
    <div class="telemetry-group">
        <div class="telemetry-kv">SESSION: <span>{st.session_state.sid}</span></div>
        <div class="telemetry-kv"><span>{UTC_NOW}</span></div>
    </div>
</div>
""", unsafe_allow_html=True)

# --- Executive Terminal Header ---
st.markdown("""
<div class="terminal-header">
    <div>
        <div class="eyebrow">Quantitative NLP &amp; Event Volatility Engine</div>
        <h1 class="terminal-title">Market Regime &amp; Sentiment Terminal</h1>
        <p class="terminal-subtitle">
            Routes wire headlines to two production endpoints: a TF-IDF / LinearSVC volatility
            baseline, and a neural branch running either FinBERT-Tone (3-class softmax) or the
            frozen-Word2Vec LSTM. Research signals only — not investment advice.
        </p>
    </div>
    <div class="header-specs">
        <div class="spec-item">
            <span class="spec-label">Transformer Corpus</span>
            <span class="spec-value">200,000 Samples</span>
        </div>
        <div class="spec-item">
            <span class="spec-label">Neural Branches</span>
            <span class="spec-value">FinBERT-Tone / LSTM-W2V</span>
        </div>
        <div class="spec-item">
            <span class="spec-label">Baseline Regimes</span>
            <span class="spec-value">0.2σ / 0.5σ / 1.0σ</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# --- Quick-Load Scenario Presets ---
st.markdown("""
<div class="panel-header">
    <div class="panel-title">01 // Event Stream Ingestion</div>
    <div class="panel-meta">LOAD BENCHMARK SCENARIO OR ENTER CUSTOM WIRE HEADLINES</div>
</div>
""", unsafe_allow_html=True)

p_col1, p_col2, p_col3, _ = st.columns([1.2, 1.2, 1.2, 2.4])
with p_col1:
    st.button("Preset: Earnings Breakout", type="secondary", use_container_width=True,
              on_click=load_preset,
              args=(["NVIDIA reports Q4 revenue surge of 78% YoY, crushing institutional consensus.",
                     "Management raises full-year data center guidance amid unprecedented AI chip demand."],
                    "Strong gross margin expansion and record backlog drive immediate after-hours rally."))
with p_col2:
    st.button("Preset: Guidance Shock", type="secondary", use_container_width=True,
              on_click=load_preset,
              args=(["Company slashes full-year operating margin outlook citing severe supply chain bottlenecks.",
                     "CFO steps down unexpectedly as SEC opens inquiry into revenue recognition practices."],
                    "Institutional desks downgrade equity rating following unexpected Q3 earnings miss."))
with p_col3:
    st.button("Preset: Routine Filing", type="secondary", use_container_width=True,
              on_click=load_preset,
              args=(["Board of directors declares regular quarterly cash dividend of $0.25 per share.",
                     "Annual shareholder meeting scheduled for next month with standard proxy proposals."],
                    "Operations remain in line with multi-year historical averages with no guidance changes."))

# --- Dynamic Headline Inputs + Model Configuration ---
input_col, config_col = st.columns([2.2, 1], gap="large")

with input_col:
    for i in range(st.session_state.num_inputs):
        is_last = i == st.session_state.num_inputs - 2
        st.text_input(
            label=f"WIRE HEADLINE {i + 1:02d}",
            key=f"input_{i}",
            placeholder=f"[Wire {i + 1:02d}] Enter financial headline or press release title...",
            on_change=check_last_input if is_last else None,
        )

with config_col:
    MODEL_MAP = {
        "LinearSVC // |ΔP| > 1.0σ (High Threshold)": (1, "1.0σ", "Strict tail-volatility filter"),
        "LinearSVC // |ΔP| > 0.5σ (Medium Threshold)": (0.5, "0.5σ", "Balanced regime sensitivity"),
        "LinearSVC // |ΔP| > 0.2σ (Low Threshold)": (0.2, "0.2σ", "High sensitivity to minor moves"),
    }
    selected_svc_label = st.selectbox("Baseline Volatility Threshold", options=list(MODEL_MAP.keys()))

    # --- Neural branch segmented selector (FinBERT vs LSTM) ---
    st.markdown('<div class="field-label">Neural Branch Selector</div>', unsafe_allow_html=True)
    seg_a, seg_b = st.columns(2, gap="small")
    with seg_a:
        st.markdown('<div class="seg-a">', unsafe_allow_html=True)
        if st.button("FinBERT-Tone", type="primary" if st.session_state.dl_branch == "FINBERT-TONE" else "secondary",
                     use_container_width=True, key="seg_finbert"):
            st.session_state.dl_branch = "FINBERT-TONE"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    with seg_b:
        st.markdown('<div class="seg-b">', unsafe_allow_html=True)
        if st.button("LSTM // W2V", type="primary" if st.session_state.dl_branch == "LSTM-W2V" else "secondary",
                     use_container_width=True, key="seg_lstm"):
            st.session_state.dl_branch = "LSTM-W2V"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    summary_input = st.text_area(
        label="Extended Wire Context (FinBERT Segment B)",
        key="summary_input",
        placeholder="Optional 1-3 sentence abstract or analyst note passed to the FinBERT tokenizer...",
        height=132,
    )

# Gather clean headline list (keep original wire indices for the manifest)
active_wires = [
    (i, st.session_state.get(f"input_{i}", "").strip())
    for i in range(st.session_state.num_inputs)
    if st.session_state.get(f"input_{i}", "").strip()
]
active_headlines = [text for _, text in active_wires]
concatenated_headlines = " ".join(active_headlines)

# --- Execution Bar ---
st.markdown("<div style='height: 8px'></div>", unsafe_allow_html=True)
act_col1, act_col2, act_col3 = st.columns([1.4, 0.8, 3.8])
with act_col1:
    predict_clicked = st.button("Execute Dual Inference", type="primary", use_container_width=True)
with act_col2:
    st.button("Clear Workspace", type="secondary", on_click=reset_all_inputs, use_container_width=True)
with act_col3:
    char_count = len(concatenated_headlines) + len(summary_input.strip())
    branch_tag = "FINBERT-TONE" if st.session_state.dl_branch == "FINBERT-TONE" else "LSTM-W2V (code 7)"
    st.markdown(
        f"<div style='font-family: JetBrains Mono, monospace; font-size: 11px; color: var(--text-muted); padding-top: 12px;'>"
        f"ACTIVE WIRES: <strong style='color:var(--text-secondary)'>{len(active_headlines)}</strong> &nbsp;|&nbsp; "
        f"PAYLOAD: <strong style='color:var(--text-secondary)'>{char_count} CHARS</strong> &nbsp;|&nbsp; "
        f"NEURAL BRANCH: <strong style='color:var(--text-secondary)'>{branch_tag}</strong>"
        f"</div>",
        unsafe_allow_html=True,
    )

st.markdown("---")

# --- Inference Dispatch & Telemetry Output ---
if predict_clicked:
    if not concatenated_headlines:
        st.warning("Input stream empty. Provide at least one headline, or load a benchmark preset above.")
    elif len(concatenated_headlines) > 12000 or len(summary_input.strip()) > 12000:
        st.error("Input exceeds the 12,000-character request limit. Shorten the headlines or context and retry.")
    else:
        model_code, sigma_str, sigma_desc = MODEL_MAP[selected_svc_label]
        dl_branch = st.session_state.dl_branch

        # Run the two independent services concurrently; each endpoint has its own timeout.
        with st.spinner("Dispatching payload to inference endpoints…"):
            with ThreadPoolExecutor(max_workers=2) as pool:
                svc_future = pool.submit(call_svc, SVC_API_URL, concatenated_headlines, model_code)
                if dl_branch == "FINBERT-TONE":
                    neural_future = pool.submit(
                        call_finbert, DL_API_URL, concatenated_headlines, summary_input.strip()
                    )
                else:
                    neural_future = pool.submit(
                        call_svc, SVC_API_URL, concatenated_headlines, LSTM_MODEL_CODE, 20
                    )
                svc_result = svc_future.result()
                neural_result = neural_future.result()
                neural_result["branch"] = dl_branch
                neural_result["data"] = neural_result.get("data", {})

        st.markdown("""
        <div class="panel-header">
            <div class="panel-title">02 // Dual-Model Telemetry &amp; Regime Classification</div>
            <div class="panel-meta">LIVE INFERENCE RESULTS</div>
        </div>
        """, unsafe_allow_html=True)

        # --- Consensus Synthesis Strip ---
        if not (svc_result["ok"] and neural_result["ok"]):
            st.warning("Consensus is unavailable unless both models return valid responses. Review the endpoint errors below; a failed call is not treated as a negative signal.")
        if svc_result["ok"] and neural_result["ok"]:
            svc_is_hot = int(svc_result["val"]) == 1
            # Neural outputs are endpoint-defined class labels; do not infer probability from a raw score.
            nn_is_hot = int(neural_result["val"]) == 1

            if dl_branch == "FINBERT-TONE":
                probs = neural_result["data"].get("probabilities", {})
                p_rising = float(probs.get("hot_rising", 0.0))
                p_falling = float(probs.get("hot_falling", 0.0))
                p_hot = float(neural_result["data"].get("prob_hot", p_rising + p_falling))
                net_skew = (p_rising - p_falling) * 100
                cell2_label, cell2_val, cell2_color = "FinBERT Event Volatility P(Hot)", f"{p_hot * 100:.1f}%", "var(--text-primary)"
                skew_label = f"+{net_skew:.1f}% BULLISH" if net_skew >= 0 else f"{net_skew:.1f}% BEARISH"
                skew_color = "var(--emerald)" if net_skew > 5 else ("var(--rose)" if net_skew < -5 else "var(--text-secondary)")
                cell3_val = f"<span style='color:{skew_color}'>{skew_label}</span>"
            else:
                cell2_label = "LSTM Branch Output"
                cell2_val = "HOT (1)" if nn_is_hot else "COLD (0)"
                cell2_color = "var(--amber)" if nn_is_hot else "var(--cyan)"
                cell3_val = "<span style='color:var(--text-muted)'>N/A — BINARY HEAD</span>"

            if svc_is_hot == nn_is_hot:
                agreement_text = "CONVERGENT // HIGH" if svc_is_hot else "CONVERGENT // STABLE"
                agreement_color = "var(--amber)" if svc_is_hot else "var(--cyan)"
            else:
                agreement_text = "DIVERGENT // SPLIT SIGNAL"
                agreement_color = "var(--rose)"

            st.markdown(f"""
<div class="consensus-strip">
    <div class="consensus-cell">
        <div class="c-label">Cross-Model Consensus</div>
        <div class="c-val" style="color: {agreement_color};">{agreement_text}</div>
    </div>
    <div class="consensus-cell">
        <div class="c-label">{cell2_label}</div>
        <div class="c-val" style="color: {cell2_color};">{cell2_val}</div>
    </div>
    <div class="consensus-cell">
        <div class="c-label">Net Directional Skew (Rising - Falling)</div>
        <div class="c-val">{cell3_val}</div>
    </div>
    <div class="consensus-cell">
        <div class="c-label">Combined Round-Trip Latency</div>
        <div class="c-val">{svc_result['latency_ms'] + neural_result['latency_ms']} ms</div>
    </div>
</div>
""", unsafe_allow_html=True)

        # --- Side-by-Side Model Cards (slightly asymmetric on purpose) ---
        col_svc, col_dl = st.columns([1, 1.12], gap="large")

        # ==================== LEFT CARD: LINEAR SVC ====================
        with col_svc:
            if svc_result["ok"]:
                is_hot = int(svc_result["val"]) == 1
                box_cls = "regime-hot" if is_hot else "regime-cold"
                txt_cls = "text-amber" if is_hot else "text-cyan"
                regime_title = "▲ VOLATILE REGIME (HOT)" if is_hot else "◆ STABLE REGIME (COLD)"
                regime_desc = (
                    f"TF-IDF + LinearSVC hyperplane projects abnormal price dispersion exceeding {sigma_str}."
                    if is_hot
                    else f"Lexical vector falls within normal market noise bounds (< {sigma_str})."
                )
                st.markdown(f"""
<div class="quant-card">
    <div class="quant-card-header">
        <div>
            <h3 class="model-name">Econometric Baseline // LinearSVC</h3>
            <div class="model-arch">TF-IDF Vectorizer + Support Vector Classifier</div>
        </div>
        <div class="latency-tag">{svc_result['latency_ms']} ms</div>
    </div>
    <div class="regime-box {box_cls}">
        <div>
            <div class="regime-label">Predicted Volatility Regime</div>
            <div class="regime-title {txt_cls}">{regime_title}</div>
        </div>
        <div class="regime-score">
            <div class="regime-score-val">{int(svc_result['val'])}</div>
            <div class="regime-score-sub">Binary Class</div>
        </div>
    </div>
    <p style="color: var(--text-secondary); font-size: 13px; line-height: 1.5; margin-bottom: 18px;">{regime_desc}</p>
    <table class="meta-table">
        <tr><td>DECISION BOUNDARY</td><td>|ΔPrice| &gt; {sigma_str}</td></tr>
        <tr><td>SENSITIVITY PROFILE</td><td>{sigma_desc}</td></tr>
        <tr><td>FEATURE REPRESENTATION</td><td>Unigram / Bigram TF-IDF</td></tr>
        <tr><td>OUTPUT CALIBRATION</td><td>Deterministic Hyperplane (Hard Margin)</td></tr>
    </table>
</div>
""", unsafe_allow_html=True)
            else:
                st.error(f"LinearSVC Endpoint Failure: {svc_result['error']}")

        # ==================== RIGHT CARD: NEURAL BRANCH ====================
        with col_dl:
            if neural_result["ok"]:
                nn_is_hot = int(neural_result["val"]) == 1

                if dl_branch == "FINBERT-TONE":
                    data = neural_result["data"]
                    probs = data.get("probabilities", {})
                    p_cold = float(probs.get("cold", 0.0))
                    p_rising = float(probs.get("hot_rising", 0.0))
                    p_falling = float(probs.get("hot_falling", 0.0))
                    p_hot = float(data.get("prob_hot", p_rising + p_falling))
                    native_3class = data.get("native_3class", "cold").upper().replace("_", " ")
                    cold_pct, rising_pct, falling_pct, hot_pct = p_cold * 100, p_rising * 100, p_falling * 100, p_hot * 100

                    if nn_is_hot:
                        if p_rising >= p_falling:
                            box_cls, txt_cls, regime_title = "regime-bull", "text-emerald", "▲ HOT // BULLISH EXPANSION"
                        else:
                            box_cls, txt_cls, regime_title = "regime-bear", "text-rose", "▼ HOT // BEARISH CONTRACTION"
                        score_display, score_sub = f"{hot_pct:.1f}%", "P(Hot) Conviction"
                    else:
                        box_cls, txt_cls, regime_title = "regime-cold", "text-cyan", "◆ COLD // EQUILIBRIUM REGIME"
                        score_display, score_sub = f"{cold_pct:.1f}%", "P(Cold) Conviction"

                    st.markdown(f"""
<div class="quant-card">
    <div class="quant-card-header">
        <div>
            <h3 class="model-name">Neural Transformer // FinBERT-Tone</h3>
            <div class="model-arch">yiyanghkust/finbert-tone · 3-Class Softmax Aggregation</div>
        </div>
        <div class="latency-tag">{neural_result['latency_ms']} ms</div>
    </div>
    <div class="regime-box {box_cls}">
        <div>
            <div class="regime-label">Aggregated Regime Verdict (Hot &gt; Cold)</div>
            <div class="regime-title {txt_cls}">{regime_title}</div>
        </div>
        <div class="regime-score">
            <div class="regime-score-val">{score_display}</div>
            <div class="regime-score-sub">{score_sub}</div>
        </div>
    </div>
    <div class="spectrum-wrapper">
        <div class="spectrum-header">
            <span>3-CLASS SOFTMAX SPECTRUM</span>
            <span>DOMINANT CLASS: <strong style="color:var(--text-primary)">{native_3class}</strong></span>
        </div>
        <div class="spectrum-bar">
            <div class="seg-cold" style="width: {cold_pct:.2f}%"></div>
            <div class="seg-rising" style="width: {rising_pct:.2f}%"></div>
            <div class="seg-falling" style="width: {falling_pct:.2f}%"></div>
        </div>
    </div>
    <div class="prob-grid">
        <div class="prob-row">
            <div class="prob-meta"><span class="prob-name">◆ COLD // STABLE BASELINE</span><span class="prob-pct">{cold_pct:.2f}%</span></div>
            <div class="prob-track"><div class="prob-fill-cyan" style="width: {cold_pct:.2f}%"></div></div>
        </div>
        <div class="prob-row">
            <div class="prob-meta"><span class="prob-name">▲ HOT // RISING IMPULSE (BULLISH)</span><span class="prob-pct">{rising_pct:.2f}%</span></div>
            <div class="prob-track"><div class="prob-fill-emerald" style="width: {rising_pct:.2f}%"></div></div>
        </div>
        <div class="prob-row">
            <div class="prob-meta"><span class="prob-name">▼ HOT // FALLING IMPULSE (BEARISH)</span><span class="prob-pct">{falling_pct:.2f}%</span></div>
            <div class="prob-track"><div class="prob-fill-rose" style="width: {falling_pct:.2f}%"></div></div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

                else:
                    # ---------- LSTM branch (binary head, calibration pending) ----------
                    box_cls = "regime-hot" if nn_is_hot else "regime-cold"
                    txt_cls = "text-amber" if nn_is_hot else "text-cyan"
                    regime_title = "▲ EVENT-DRIVEN VOLATILITY (HOT)" if nn_is_hot else "◆ QUIET TAPE (COLD)"
                    regime_desc = (
                        "Frozen Word2Vec embeddings fed through the it-13 LSTM stack; recurrent state crosses the volatility threshold."
                        if nn_is_hot
                        else "Recurrent state remains inside the low-dispersion band; no event-driven volatility flagged."
                    )
                    st.markdown(f"""
<div class="quant-card">
    <div class="quant-card-header">
        <div>
            <h3 class="model-name">Recurrent Baseline // LSTM (Frozen W2V)</h3>
            <div class="model-arch">best_lstm_it13_w2v_frozen · binary volatility head</div>
        </div>
        <div class="latency-tag">{neural_result['latency_ms']} ms</div>
    </div>
    <div class="regime-box {box_cls}">
        <div>
            <div class="regime-label">Predicted Volatility Regime</div>
            <div class="regime-title {txt_cls}">{regime_title}</div>
        </div>
        <div class="regime-score">
            <div class="regime-score-val">{int(neural_result['val'])}</div>
            <div class="regime-score-sub">Binary Class</div>
        </div>
    </div>
    <p style="color: var(--text-secondary); font-size: 13px; line-height: 1.5; margin-bottom: 4px;">{regime_desc}</p>
    <table class="meta-table">
        <tr><td>EMBEDDINGS</td><td>Word2Vec (frozen, it=13)</td></tr>
        <tr><td>ENCODER</td><td>LSTM recurrent stack</td></tr>
        <tr><td>OUTPUT HEAD</td><td>Binary (hard threshold)</td></tr>
        <tr><td>ROUTING</td><td>SVC service · model_choice=7</td></tr>
    </table>
    <div class="placeholder-box">
        <div class="ph-title">Softmax calibration pending</div>
        <div class="ph-body">
            The /predict endpoint currently returns a hard binary logit for model_choice=7, so
            class-probability telemetry cannot be rendered yet. Once a calibrated probability head
            is deployed, the 3-row distribution and spectrum bar will populate here automatically.
        </div>
        <div class="ph-route">AWAITING: GET /predict?model_choice=7 → probabilities[]</div>
        <div class="skeleton" style="width: 92%"></div>
        <div class="skeleton" style="width: 71%"></div>
        <div class="skeleton" style="width: 46%"></div>
    </div>
</div>
""", unsafe_allow_html=True)
            else:
                st.error(f"Neural Branch Endpoint Failure: {neural_result['error']}")

        # --- Raw Telemetry Inspector + Ingest Manifest ---
        st.markdown("<div style='height: 14px'></div>", unsafe_allow_html=True)
        with st.expander("INSPECT RAW API TELEMETRY, JSON PAYLOADS & INGEST MANIFEST"):
            insp_col1, insp_col2 = st.columns(2)
            with insp_col1:
                st.caption("GET /predict (LinearSVC baseline)")
                st.json({
                    "endpoint": f"{SVC_API_URL}/predict",
                    "latency_ms": svc_result["latency_ms"],
                    "query_params": {"headline": concatenated_headlines, "model_choice": model_code},
                    "prediction": svc_result["val"],
                })
            with insp_col2:
                if dl_branch == "FINBERT-TONE":
                    st.caption("POST /dl_predict (FinBERT-Tone)")
                    st.json({
                        "endpoint": f"{DL_API_URL}/dl_predict",
                        "latency_ms": neural_result["latency_ms"],
                        "response_payload": neural_result["data"],
                    })
                else:
                    st.caption("GET /predict (LSTM-W2V, model_choice=7)")
                    st.json({
                        "endpoint": f"{SVC_API_URL}/predict",
                        "latency_ms": neural_result["latency_ms"],
                        "query_params": {"headline": concatenated_headlines, "model_choice": LSTM_MODEL_CODE},
                        "prediction": neural_result["val"],
                        "probabilities": "NOT_EXPOSED_BY_ENDPOINT",
                    })
            st.caption("Ingest manifest")
            rows = "".join(
                f"<tr><td>W{idx + 1:02d}</td><td>{safe_text(text, 96)}{'…' if len(text) > 96 else ''}</td><td>{len(text)} ch</td></tr>"
                for idx, text in active_wires
            )
            if summary_input.strip():
                rows += f"<tr><td>SUM</td><td>{safe_text(summary_input.strip(), 96)}{'…' if len(summary_input.strip()) > 96 else ''}</td><td>{len(summary_input.strip())} ch</td></tr>"
            st.markdown(f"<table class='manifest'>{rows}</table>", unsafe_allow_html=True)

# --- Footnote ---
st.markdown(f"""
<div class="footnote">
SENTINEL terminal · build 2.4.1-rc · session {st.session_state.sid}<br>
endpoints hosted on Cloud Run (europe-west1) · outputs are research signals, not investment advice
</div>
""", unsafe_allow_html=True)

import html
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any
import requests
import streamlit as st

st.set_page_config(page_title="SENTINEL | Market Sentiment", layout="wide", initial_sidebar_state="collapsed")

# --- High-End Glassmorphism CSS ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --bg-main: #0B0E14;
    --bg-card: rgba(19, 23, 34, 0.65);
    --border-glass: rgba(255, 255, 255, 0.08);
    --text-primary: #E2E8F0;
    --text-muted: #64748B;
    --accent-blue: #3B82F6;
    --accent-hot: #F43F5E;
    --accent-cold: #0EA5E9;
    --gradient-glow: linear-gradient(135deg, rgba(59, 130, 246, 0.15) 0%, rgba(139, 92, 246, 0.15) 100%);
}

.stApp {
    background-color: var(--bg-main);
    background-image:
        radial-gradient(circle at 15% 50%, rgba(59, 130, 246, 0.04), transparent 50%),
        radial-gradient(circle at 85% 30%, rgba(244, 63, 94, 0.03), transparent 50%);
    color: var(--text-primary);
    font-family: 'Inter', sans-serif;
}
.main .block-container { max-width: 1400px; padding: 2rem; }
header, footer { display: none !important; }

/* Dashboard Header */
.dash-header {
    background: var(--bg-card);
    backdrop-filter: blur(12px);
    border: 1px solid var(--border-glass);
    border-radius: 12px;
    padding: 24px 32px;
    margin-bottom: 2rem;
    box-shadow: 0 8px 32px rgba(0,0,0,0.2);
}
.dash-title {
    font-size: 2.5rem;
    font-weight: 700;
    background: linear-gradient(90deg, #FFFFFF, #94A3B8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0 0 8px 0;
    letter-spacing: -1px;
}
.dash-subtitle { font-size: 1rem; color: var(--text-muted); margin: 0; }
.sys-status {
    display: inline-flex; align-items: center; gap: 8px;
    font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #10B981;
    background: rgba(16, 185, 129, 0.1); padding: 4px 12px; border-radius: 20px;
    border: 1px solid rgba(16, 185, 129, 0.2);
}
.sys-dot { width: 6px; height: 6px; background: #10B981; border-radius: 50%; box-shadow: 0 0 8px #10B981; }

/* Glass Cards */
.glass-card {
    background: var(--bg-card);
    backdrop-filter: blur(12px);
    border: 1px solid var(--border-glass);
    border-radius: 12px;
    padding: 24px;
    height: 100%;
    transition: transform 0.2s ease, border-color 0.2s ease;
}
.glass-card:hover { border-color: rgba(255, 255, 255, 0.15); }
.card-header {
    font-size: 1.1rem; font-weight: 600; color: #FFFFFF;
    margin-bottom: 16px; display: flex; justify-content: space-between;
}
.card-arch { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--text-muted); }

/* Regime Indicators */
.regime-box {
    padding: 20px; border-radius: 8px; margin: 16px 0;
    display: flex; justify-content: space-between; align-items: center;
}
.hot-regime { background: rgba(244, 63, 94, 0.1); border: 1px solid rgba(244, 63, 94, 0.3); border-left: 4px solid var(--accent-hot); }
.cold-regime { background: rgba(14, 165, 233, 0.1); border: 1px solid rgba(14, 165, 233, 0.3); border-left: 4px solid var(--accent-cold); }
.regime-lbl { font-family: 'JetBrains Mono', monospace; font-size: 11px; text-transform: uppercase; color: var(--text-muted); }
.regime-txt { font-size: 1.25rem; font-weight: 700; margin-top: 4px; }
.regime-hot-txt { color: #FDA4AF; }
.regime-cold-txt { color: #7DD3FC; }

/* Prob Bars */
.prob-row { margin-bottom: 12px; }
.prob-labels { display: flex; justify-content: space-between; font-family: 'JetBrains Mono', monospace; font-size: 12px; margin-bottom: 4px; color: var(--text-primary); }
.bar-bg { width: 100%; height: 6px; background: rgba(255, 255, 255, 0.05); border-radius: 3px; overflow: hidden; }
.bar-fill-hot { height: 100%; background: linear-gradient(90deg, #E11D48, #F43F5E); box-shadow: 0 0 10px rgba(244, 63, 94, 0.5); }
.bar-fill-cold { height: 100%; background: linear-gradient(90deg, #0284C7, #0EA5E9); box-shadow: 0 0 10px rgba(14, 165, 233, 0.5); }

/* Inputs & Buttons Override */
.stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
    background: rgba(0, 0, 0, 0.3) !important;
    border: 1px solid var(--border-glass) !important;
    color: white !important;
    border-radius: 8px !important;
}
.stButton button[kind="primary"] {
    background: linear-gradient(90deg, #2563EB, #4F46E5) !important;
    border: none !important; color: white !important; font-weight: 600 !important;
    border-radius: 8px !important; transition: all 0.3s ease !important;
}
.stButton button[kind="primary"]:hover { box-shadow: 0 0 15px rgba(59, 130, 246, 0.5) !important; transform: translateY(-1px) !important; }
</style>
""", unsafe_allow_html=True)

# --- Logic & API Calls ---
def get_secret(key: str, default: str) -> str:
    try:
        return st.secrets.get(key, default).rstrip("/")
    except Exception:
        return default.rstrip("/")

# Target the specific APIs
SVC_API_URL = get_secret("SVC_API_URL", "https://stockapi3linsvm-241812484319.europe-west1.run.app")
FINBERT_API_URL = get_secret("DL_API_URL", "https://trading-heat-api-398091546603.europe-west1.run.app")

def safe_text(value: Any) -> str:
    return html.escape(str(value)[:500], quote=True)

def parse_res(response: requests.Response) -> tuple[bool, dict, str]:
    if response.status_code != 200:
        return False, {}, f"HTTP {response.status_code}: {safe_text(response.text)}"
    try:
        return True, response.json(), ""
    except Exception:
        return False, {}, "Invalid JSON response"

def fetch_inference(url: str, endpoint: str, json_payload: dict = None, params: dict = None) -> dict:
    started = time.perf_counter()
    res = {"ok": False, "data": {}, "latency": 0, "error": ""}
    try:
        if json_payload:
            r = requests.post(f"{url}{endpoint}", json=json_payload, timeout=20)
        else:
            r = requests.get(f"{url}{endpoint}", params=params, timeout=15)
        res["latency"] = int((time.perf_counter() - started) * 1000)
        ok, data, err = parse_res(r)
        res.update(ok=ok, data=data, error=err)
    except Exception as e:
        res["latency"] = int((time.perf_counter() - started) * 1000)
        res["error"] = str(e)
    return res

# --- State ---
st.session_state.setdefault("num_inputs", 3)
st.session_state.setdefault("dl_branch", "FINBERT-TONE")

def add_input(): st.session_state.num_inputs += 1
def clear_inputs():
    for i in range(st.session_state.num_inputs): st.session_state[f"in_{i}"] = ""
    st.session_state.num_inputs = 3

# --- Header ---
st.markdown("""
<div class="dash-header">
    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
        <div>
            <h1 class="dash-title">SENTINEL Engine</h1>
            <p class="dash-subtitle">Real-time Dual-Model Market Volatility Prediction</p>
        </div>
        <div class="sys-status"><div class="sys-dot"></div> SYSTEMS ONLINE</div>
    </div>
</div>
""", unsafe_allow_html=True)

# --- UI Controls ---
col_in, col_conf = st.columns([2, 1], gap="large")

with col_in:
    st.markdown("##### 📰 Financial Wire Stream")
    for i in range(st.session_state.num_inputs):
        st.text_input(f"Headline {i+1}", key=f"in_{i}", label_visibility="collapsed", placeholder="Enter news headline...")
    st.button("+ Add Headline", on_click=add_input, size="small")

with col_conf:
    st.markdown("##### ⚙️ Model Configuration")

    MODEL_MAP = {
        "LinearSVC | > 1.0σ": (1, "1.0σ (High)"),
        "LinearSVC | > 0.5σ": (5, "0.5σ (Medium)"),
        "LinearSVC | > 0.2σ": (2, "0.2σ (Low)")
    }
    svc_choice = st.selectbox("Baseline Regressor", list(MODEL_MAP.keys()))

    st.markdown("<div style='margin-top: 15px; margin-bottom: 5px; font-size:14px;'>Neural Architecture</div>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    if c1.button("FinBERT-Tone", type="primary" if st.session_state.dl_branch == "FINBERT-TONE" else "secondary", use_container_width=True):
        st.session_state.dl_branch = "FINBERT-TONE"
        st.rerun()
    if c2.button("LSTM Word2Vec", type="primary" if st.session_state.dl_branch == "LSTM-W2V" else "secondary", use_container_width=True):
        st.session_state.dl_branch = "LSTM-W2V"
        st.rerun()

    summary_text = st.text_area("Optional Context Summary", placeholder="Analyst notes...")

# Fetch inputs
active_lines = [st.session_state.get(f"in_{i}", "").strip() for i in range(st.session_state.num_inputs) if st.session_state.get(f"in_{i}", "").strip()]
concat_text = " ".join(active_lines)

st.markdown("<hr style='border-color: rgba(255,255,255,0.1);'>", unsafe_allow_html=True)
c_exec1, c_exec2, _ = st.columns([2, 1, 5])
exec_btn = c_exec1.button("⚡ Execute Dual Inference", type="primary", use_container_width=True)
c_exec2.button("Clear", on_click=clear_inputs, use_container_width=True)

# --- Results ---
if exec_btn:
    if not concat_text:
        st.warning("⚠️ Provide at least one headline.")
    else:
        model_int, sigma_lbl = MODEL_MAP[svc_choice]
        dl_branch = st.session_state.dl_branch

        with st.spinner("Dispatching payloads..."):
            with ThreadPoolExecutor(max_workers=2) as pool:
                f_svc = pool.submit(fetch_inference, SVC_API_URL, "/predict", None, {"headline": concat_text, "model_choice": model_int})
                if dl_branch == "FINBERT-TONE":
                    f_dl = pool.submit(fetch_inference, FINBERT_API_URL, "/dl_predict", {"headline": concat_text, "summary": summary_text})
                else:
                    f_dl = pool.submit(fetch_inference, SVC_API_URL, "/lstm_predict", {"headline": concat_text})

                res_svc = f_svc.result()
                res_dl = f_dl.result()

        st.markdown("### 📊 Inference Telemetry")
        col_res1, col_res2 = st.columns(2, gap="large")

        # --- SVC CARD ---
        with col_res1:
            if res_svc["ok"]:
                is_hot = float(res_svc["data"].get("prediction", 0)) >= 1.0
                st.markdown(f"""
                <div class="glass-card">
                    <div class="card-header">
                        <div>Econometric Baseline</div>
                        <div class="card-arch">{res_svc['latency']}ms</div>
                    </div>
                    <div style="color: var(--text-muted); font-size: 13px;">TF-IDF + LinearSVC</div>

                    <div class="regime-box {'hot-regime' if is_hot else 'cold-regime'}">
                        <div>
                            <div class="regime-lbl">Volatility Projection ({sigma_lbl})</div>
                            <div class="regime-txt {'regime-hot-txt' if is_hot else 'regime-cold-txt'}">{'🔥 HOT (VOLATILE)' if is_hot else '❄️ COLD (STABLE)'}</div>
                        </div>
                    </div>
                    <div style="font-family: monospace; color: var(--text-muted); font-size: 12px; margin-top: 20px;">
                        ROUTE: GET /predict?model_choice={model_int}<br>
                        THRESHOLD: |ΔP| > {sigma_lbl}
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.error(f"SVC Error: {res_svc['error']}")

        # --- NEURAL CARD ---
        with col_res2:
            if res_dl["ok"]:
                data = res_dl["data"]
                is_hot = float(data.get("prediction", 0)) >= 1.0

                probs = data.get("probabilities", {})
                p_hot = data.get("prob_hot", probs.get("hot", 1.0 if is_hot else 0.0))
                p_cold = data.get("prob_cold", probs.get("cold", 1.0 - p_hot))

                arch_title = "FinBERT-Tone Transformer" if dl_branch == "FINBERT-TONE" else "LSTM (Frozen Word2Vec)"
                ep_route = "POST /dl_predict" if dl_branch == "FINBERT-TONE" else "POST /lstm_predict"

                st.markdown(f"""
                <div class="glass-card">
                    <div class="card-header">
                        <div>{arch_title}</div>
                        <div class="card-arch">{res_dl['latency']}ms</div>
                    </div>
                    <div style="color: var(--text-muted); font-size: 13px;">Neural Sequence Classification</div>

                    <div class="regime-box {'hot-regime' if is_hot else 'cold-regime'}">
                        <div>
                            <div class="regime-lbl">Aggregated Sentiment</div>
                            <div class="regime-txt {'regime-hot-txt' if is_hot else 'regime-cold-txt'}">{'🔥 HOT (VOLATILE)' if is_hot else '❄️ COLD (STABLE)'}</div>
                        </div>
                    </div>

                    <div style="margin-top: 20px;">
                        <div class="prob-row">
                            <div class="prob-labels"><span>P(Hot) Confidence</span><span>{p_hot*100:.1f}%</span></div>
                            <div class="bar-bg"><div class="bar-fill-hot" style="width: {p_hot*100}%;"></div></div>
                        </div>
                        <div class="prob-row">
                            <div class="prob-labels"><span>P(Cold) Confidence</span><span>{p_cold*100:.1f}%</span></div>
                            <div class="bar-bg"><div class="bar-fill-cold" style="width: {p_cold*100}%;"></div></div>
                        </div>
                    </div>

                    <div style="font-family: monospace; color: var(--text-muted); font-size: 12px; margin-top: 20px;">
                        ROUTE: {ep_route}
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.error(f"Neural Error: {res_dl['error']}")

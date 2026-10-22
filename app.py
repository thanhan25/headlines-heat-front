from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from string import Template
from typing import Any, Optional

import requests
import streamlit as st

from sentinel_hardening import call_finbert, call_svc, safe_text

# ═══════════════════════════════════════════════════════════════════════
# Headlines Heat Prediction — financial headline classification workbench.
# Requires: streamlit, requests, pandas, and the sibling sentinel_hardening.py module.
# ═══════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Headlines Heat Prediction | Financial News Signal Lab",
    page_icon="◉",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Configuration ─────────────────────────────────────────────────────
MAX_WIRES = 21
MAX_CHARS = 12_000
MAX_GET_URL_CHARS = 7_000  # conservative protection for GET /predict query strings
PING_TTL_S = 120
HISTORY_LEN = 20
LOG_LEN = 12
LSTM_MODEL_CODE = 7
MARKET_QUOTES_TTL_S = 90
MARKET_HTTP_TIMEOUT = (1.2, 2.2)

# ── Session state and theme ────────────────────────────────────────────
st.session_state.setdefault("theme", "dark")
st.session_state.setdefault("theme_toggle", st.session_state.theme == "light")
st.session_state.setdefault("num_inputs", 3)
st.session_state.setdefault("summary_input", "")
st.session_state.setdefault("dl_branch", "FINBERT-TONE")
st.session_state.setdefault("sid", uuid.uuid4().hex[:8].upper())
st.session_state.setdefault("active_preset", None)
st.session_state.setdefault("last_results", None)
st.session_state.setdefault("previous_results", None)
st.session_state.setdefault("run_log", [])
st.session_state.setdefault("run_history", [])
st.session_state.setdefault("csv_loaded_fingerprint", "")
st.session_state.setdefault("csv_import_message", None)


def toggle_theme() -> None:
    st.session_state.theme = "light" if st.session_state.theme_toggle else "dark"


DARK_TOKENS = {
    "bg": "#07090E", "panel": "#0D111A", "card": "#111622", "input_bg": "#0B0F16",
    "elevated": "#161C2A", "border": "#1E2638", "border_active": "rgba(59,130,246,.55)",
    "focus": "#3B82F6", "ring": "rgba(59,130,246,.25)", "text1": "#F1F5F9",
    "text2": "#CBD5E1", "text3": "#94A3B8", "muted": "#7C8BA1", "placeholder": "#566274",
    "btn2_bg": "#141A28", "btn2_fg": "#CBD5E1", "btn2_border": "#232C40", "btn2_hover": "#1B2334",
    "prim_grad": "linear-gradient(135deg,#3B82F6 0%,#8B5CF6 100%)",
    "prim_shadow": "0 6px 20px rgba(59,130,246,.28)",
    "prim_shadow_hover": "0 10px 28px rgba(59,130,246,.40)", "shadow_sm": "0 1px 2px rgba(0,0,0,.3)",
    "shadow_md": "0 4px 16px rgba(0,0,0,.35)", "cobalt": "#3B82F6", "noise": ".22",
    "emerald": "#10B981", "rose": "#F43F5E", "amber": "#F59E0B", "cyan": "#38BDF8",
    "emerald_glow": "rgba(16,185,129,.14)", "rose_glow": "rgba(244,63,94,.14)",
    "amber_glow": "rgba(245,158,11,.14)", "cyan_glow": "rgba(56,189,248,.14)",
    "gradient_accent": "linear-gradient(135deg,#3B82F6 0%,#8B5CF6 100%)",
    "gradient_hot": "linear-gradient(135deg,#FB7185 0%,#E11D48 100%)",
    "gradient_cold": "linear-gradient(135deg,#38BDF8 0%,#0284C7 100%)",
    "gradient_bull": "linear-gradient(135deg,#34D399 0%,#059669 100%)",
    "gradient_bear": "linear-gradient(135deg,#F87171 0%,#DC2626 100%)",
    "heat2": "rgba(148,163,184,.10)", "heat3": "rgba(245,158,11,.12)",
    "heat4": "rgba(245,158,11,.22)", "heat5": "rgba(245,158,11,.34)",
}
LIGHT_TOKENS = {
    "bg": "#F5F7FA", "panel": "#FFFFFF", "card": "#FFFFFF", "input_bg": "#FFFFFF",
    "elevated": "#F1F5F9", "border": "#D7DFE9", "border_active": "rgba(37,99,235,.50)",
    "focus": "#2563EB", "ring": "rgba(37,99,235,.16)", "text1": "#0B1220",
    "text2": "#293648", "text3": "#46566B", "muted": "#5C6B80", "placeholder": "#8494A7",
    "btn2_bg": "#FFFFFF", "btn2_fg": "#33415C", "btn2_border": "#CBD5E1", "btn2_hover": "#EEF2F7",
    "prim_grad": "linear-gradient(135deg,#2563EB 0%,#7C3AED 100%)",
    "prim_shadow": "0 6px 20px rgba(37,99,235,.20)",
    "prim_shadow_hover": "0 10px 28px rgba(37,99,235,.28)",
    "shadow_sm": "0 1px 2px rgba(15,23,42,.06)",
    "shadow_md": "0 2px 6px rgba(15,23,42,.05), 0 12px 28px rgba(15,23,42,.08)",
    "cobalt": "#2563EB", "noise": "0", "emerald": "#047857", "rose": "#BE123C",
    "amber": "#B45309", "cyan": "#0369A1", "emerald_glow": "rgba(4,120,87,.10)",
    "rose_glow": "rgba(190,18,60,.09)", "amber_glow": "rgba(180,83,9,.12)",
    "cyan_glow": "rgba(3,105,161,.10)",
    "gradient_accent": "linear-gradient(135deg,#2563EB 0%,#7C3AED 100%)",
    "gradient_hot": "linear-gradient(135deg,#F43F5E 0%,#BE123C 100%)",
    "gradient_cold": "linear-gradient(135deg,#0EA5E9 0%,#0369A1 100%)",
    "gradient_bull": "linear-gradient(135deg,#10B981 0%,#047857 100%)",
    "gradient_bear": "linear-gradient(135deg,#F43F5E 0%,#B91C1C 100%)",
    "heat2": "rgba(100,116,139,.08)", "heat3": "rgba(180,83,9,.07)",
    "heat4": "rgba(180,83,9,.12)", "heat5": "rgba(180,83,9,.18)",
}
THEME = DARK_TOKENS if st.session_state.theme == "dark" else LIGHT_TOKENS

# The CSS deliberately uses a small set of theme tokens so the visual design
# stays consistent without having to interpolate braces throughout the CSS.
OVERRIDE_CSS = Template(r"""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&family=Instrument+Serif:ital@0;1&display=swap');
:root {
 --bg-base:$bg; --bg-panel:$panel; --bg-card:$card; --bg-input:$input_bg; --bg-elevated:$elevated;
 --border-subtle:$border; --border-active:$border_active; --border-focus:$focus;
 --text-primary:$text1; --text-secondary:$text2; --text-tertiary:$text3; --text-muted:$muted;
 --text-faint:$placeholder; --cobalt:$cobalt; --emerald:$emerald; --rose:$rose; --amber:$amber; --cyan:$cyan;
 --emerald-glow:$emerald_glow; --rose-glow:$rose_glow; --amber-glow:$amber_glow; --cyan-glow:$cyan_glow;
 --gradient-accent:$gradient_accent; --gradient-hot:$gradient_hot; --gradient-cold:$gradient_cold;
 --gradient-bull:$gradient_bull; --gradient-bear:$gradient_bear; --heat-2:$heat2; --heat-3:$heat3;
 --heat-4:$heat4; --heat-5:$heat5; --shadow-sm:$shadow_sm; --shadow-md:$shadow_md; --noise-opacity:$noise;
 color-scheme:COLOR_SCHEME;
}
html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stMainFrame"],section.main {
 background:var(--bg-base)!important;color:var(--text-primary)!important;
 font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;-webkit-font-smoothing:antialiased;
}
.stApp::before{content:"";position:fixed;inset:0;z-index:0;pointer-events:none;background-image:
 radial-gradient(ellipse 80% 60% at 20% 0%,rgba(59,130,246,.07),transparent 60%),
 radial-gradient(ellipse 60% 50% at 80% 100%,rgba(139,92,246,.05),transparent 60%)}
.stApp::after{content:"";position:fixed;inset:0;z-index:0;pointer-events:none;opacity:var(--noise-opacity);background-image:url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.4'/%3E%3C/svg%3E")}
[data-testid="stAppViewContainer"]>section{position:relative;z-index:1}
.main .block-container{padding-top:1.25rem;padding-bottom:2.6rem;max-width:1440px}
header,#MainMenu,footer{visibility:hidden}[data-testid="stHeader"]{background:transparent!important}
*{font-variant-numeric:tabular-nums}
input[type="text"],input[type="number"],input:not([type]),textarea{background:var(--bg-input)!important;color:var(--text-primary)!important;border:1px solid var(--border-subtle)!important;border-radius:9px!important;font-size:13px!important;padding:10px 13px!important;font-family:'Inter',sans-serif!important}
input::placeholder,textarea::placeholder{color:var(--text-faint)!important;opacity:1!important}
input:focus,textarea:focus{border-color:$focus!important;box-shadow:0 0 0 3px $ring!important;outline:none!important}
div[data-baseweb="select"]>div{background:var(--bg-input)!important;border:1px solid var(--border-subtle)!important;border-radius:9px!important;box-shadow:none!important}
div[data-baseweb="select"],div[data-baseweb="select"] span{color:var(--text-primary)!important}
[role="listbox"]{background:var(--bg-card)!important;border:1px solid var(--border-subtle)!important;border-radius:10px!important}
[role="option"]{color:var(--text-primary)!important}[role="option"]:hover,[role="option"][aria-selected="true"]{background:var(--bg-elevated)!important}
label,.stTextInput label,.stTextArea label,.stSelectbox label{color:var(--text-tertiary)!important;font-family:'JetBrains Mono',monospace!important;font-weight:600!important;font-size:10px!important;text-transform:uppercase!important;letter-spacing:.09em!important}
small,.stCaption,[data-testid="stCaption"]{color:var(--text-muted)!important}
.stButton>button{border-radius:9px!important;font-family:'Inter',sans-serif!important;font-weight:600!important;font-size:12.5px!important;padding:10px 14px!important;min-height:40px;transition:all .18s ease!important}
.stButton>button[kind="primary"]{background:$prim_grad!important;color:#fff!important;border:none!important;box-shadow:$prim_shadow!important}
.stButton>button[kind="primary"]:hover{box-shadow:$prim_shadow_hover!important;transform:translateY(-1px)!important}
.stButton>button[kind="secondary"],.stButton>button:not([kind="primary"]){background:$btn2_bg!important;color:$btn2_fg!important;border:1px solid $btn2_border!important;box-shadow:$shadow_sm!important}
.stButton>button[kind="secondary"]:hover,.stButton>button:not([kind="primary"]):hover{background:$btn2_hover!important;color:var(--text-primary)!important;border-color:var(--border-active)!important}
[data-testid="stVerticalBlockBorderWrapper"]{background:var(--bg-panel)!important;border:1px solid var(--border-subtle)!important;border-radius:14px!important;box-shadow:var(--shadow-sm)!important;padding:14px 16px!important}
[data-testid="stExpander"] details{background:var(--bg-card)!important;border:1px solid var(--border-subtle)!important;border-radius:12px!important}
[data-testid="stExpander"] summary,[data-testid="stExpander"] summary p,[data-testid="stExpander"] summary span{color:var(--text-primary)!important}
[data-testid="stJson"]{background:var(--bg-elevated)!important;border-radius:10px!important}pre,code{background:var(--bg-elevated)!important;color:var(--text-secondary)!important}
.stSpinner>div{border-top-color:$cobalt!important}hr{border:none!important;height:1px!important;background:var(--border-subtle)!important;margin:24px 0!important}
.topbar{display:flex;justify-content:space-between;align-items:center;gap:14px;padding:14px 20px;background:var(--bg-panel);border:1px solid var(--border-subtle);border-radius:12px;margin-bottom:18px;box-shadow:var(--shadow-sm)}
.topbar-left{display:flex;align-items:center;gap:13px}.brand-mark{width:36px;height:36px;border-radius:10px;background:var(--gradient-accent);display:flex;align-items:center;justify-content:center;font-family:'Instrument Serif',serif;font-size:21px;font-style:italic;color:#fff;box-shadow:0 4px 14px rgba(59,130,246,.25)}
.brand-title{font-size:14px;font-weight:800;letter-spacing:.02em;color:var(--text-primary)}.brand-tag{font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--text-muted);letter-spacing:.1em;text-transform:uppercase;margin-top:3px}
.topbar-right{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.chip{display:inline-flex;align-items:center;gap:7px;padding:6px 10px;border-radius:20px;font-family:'JetBrains Mono',monospace;font-size:9.5px;font-weight:700;letter-spacing:.04em;border:1px solid var(--border-subtle)}
.chip.ok{color:var(--emerald);background:var(--emerald-glow)}.chip.bad{color:var(--rose);background:var(--rose-glow)}.chip.unk{color:var(--text-muted);background:var(--bg-elevated)}.chip-dot{width:6px;height:6px;border-radius:50%;background:currentColor;box-shadow:0 0 6px currentColor}
.hero-stack{display:flex;justify-content:space-between;align-items:flex-end;padding:8px 4px 28px;gap:24px;flex-wrap:wrap}.hero-title{font-size:clamp(2rem,3.8vw,2.8rem);font-weight:800;letter-spacing:-.045em;line-height:1.04;margin:0 0 13px;color:var(--text-primary)}
.hero-title .accent{font-family:'Instrument Serif',serif;font-style:italic;font-weight:400;background:var(--gradient-accent);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.hero-sub{font-size:.93rem;color:var(--text-secondary);max-width:680px;line-height:1.65;margin:0}.hero-specs{display:grid;grid-template-columns:repeat(3,auto);gap:10px;background:var(--bg-panel);border:1px solid var(--border-subtle);padding:13px 15px;border-radius:10px;box-shadow:var(--shadow-sm)}
.spec-cell{display:flex;flex-direction:column;padding:0 10px;border-right:1px solid var(--border-subtle)}.spec-cell:last-child{border-right:none}.spec-lbl{font-family:'JetBrains Mono',monospace;font-size:8px;text-transform:uppercase;letter-spacing:.1em;color:var(--text-muted);margin-bottom:5px;font-weight:700}.spec-val{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-primary);font-weight:700}
.section-label{display:flex;align-items:center;gap:10px;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.16em;font-weight:700;margin:8px 0 14px}.section-label:before{content:"";width:22px;height:1px;background:var(--gradient-accent)}.section-label:after{content:attr(data-num);font-size:9px;padding:2px 7px;border-radius:3px;background:var(--bg-elevated);color:var(--cobalt);border:1px solid var(--border-subtle);margin-left:auto}
.preset-note{font-family:'JetBrains Mono',monospace;font-size:9px;letter-spacing:.07em;text-transform:uppercase;font-weight:700;margin:9px 1px 0}.preset-note.bull{color:var(--emerald)}.preset-note.bear{color:var(--rose)}.preset-note.neutral{color:var(--cyan)}.preset-hint{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);margin:10px 0 24px 2px}
.verdict-banner{background:var(--bg-card);border:1px solid var(--border-subtle);border-radius:15px;padding:25px 28px;margin-bottom:22px;display:grid;grid-template-columns:auto 1fr;gap:22px;align-items:center;box-shadow:var(--shadow-md);position:relative;overflow:hidden}
.verdict-banner:before{content:"";position:absolute;top:0;left:0;right:0;height:2px}.verdict-hot{background:linear-gradient(135deg,var(--amber-glow),var(--bg-card) 72%);border-color:rgba(245,158,11,.3)}.verdict-hot:before{background:var(--gradient-hot)}.verdict-cold{background:linear-gradient(135deg,var(--cyan-glow),var(--bg-card) 72%);border-color:rgba(56,189,248,.3)}.verdict-cold:before{background:var(--gradient-cold)}.verdict-bull{background:linear-gradient(135deg,var(--emerald-glow),var(--bg-card) 72%);border-color:rgba(16,185,129,.3)}.verdict-bull:before{background:var(--gradient-bull)}.verdict-bear{background:linear-gradient(135deg,var(--rose-glow),var(--bg-card) 72%);border-color:rgba(244,63,94,.3)}.verdict-bear:before{background:var(--gradient-bear)}.verdict-split{background:linear-gradient(135deg,rgba(148,163,184,.09),var(--bg-card) 72%);border-color:rgba(148,163,184,.3)}.verdict-split:before{background:linear-gradient(90deg,var(--cyan),var(--amber),var(--rose))}.verdict-partial{background:linear-gradient(135deg,rgba(244,63,94,.07),var(--bg-card) 72%);border-color:rgba(244,63,94,.26)}.verdict-partial:before{background:var(--gradient-bear)}
.verdict-eyebrow{font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.13em;font-weight:700;margin-bottom:7px}.verdict-title{font-size:clamp(1.2rem,2vw,1.55rem);font-weight:800;letter-spacing:-.025em;margin:0 0 7px;line-height:1.2;color:var(--text-primary)}.verdict-sub{font-size:.87rem;color:var(--text-secondary);margin:0;line-height:1.55}.verdict-meta-row{display:flex;gap:14px;margin-top:13px;font-family:'JetBrains Mono',monospace;font-size:9.5px;color:var(--text-muted);flex-wrap:wrap;align-items:center}.verdict-meta-k{color:var(--text-tertiary);margin-right:4px;font-weight:700}.verdict-delta{font-family:'JetBrains Mono',monospace;font-size:9px;padding:3px 7px;border-radius:4px;margin-left:6px}.verdict-delta.up{background:var(--emerald-glow);color:var(--emerald)}.verdict-delta.down{background:var(--rose-glow);color:var(--rose)}.verdict-delta.flat{background:var(--bg-elevated);color:var(--text-muted)}
.v-hot{color:var(--amber);font-weight:700}.v-cold{color:var(--cyan);font-weight:700}.v-bull{color:var(--emerald);font-weight:700}.v-bear{color:var(--rose);font-weight:700}.v-err{color:var(--rose);font-weight:700}.v-na{color:var(--text-faint);font-weight:700}
.glass-card{background:var(--bg-card);border:1px solid var(--border-subtle);border-radius:15px;padding:22px;position:relative;overflow:hidden;box-shadow:var(--shadow-md);height:100%}.regime-hot{border-color:rgba(245,158,11,.3);background:linear-gradient(160deg,var(--amber-glow),var(--bg-card) 48%)}.regime-cold{border-color:rgba(56,189,248,.3);background:linear-gradient(160deg,var(--cyan-glow),var(--bg-card) 48%)}.regime-bull{border-color:rgba(16,185,129,.3);background:linear-gradient(160deg,var(--emerald-glow),var(--bg-card) 48%)}.regime-bear{border-color:rgba(244,63,94,.3);background:linear-gradient(160deg,var(--rose-glow),var(--bg-card) 48%)}
.card-title-row{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:16px;padding-bottom:15px;border-bottom:1px solid var(--border-subtle)}.card-eyebrow{font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.13em;margin-bottom:6px;font-weight:700}.card-title{font-size:1.08rem;font-weight:750;color:var(--text-primary);letter-spacing:-.02em;margin:0}.card-subtitle{font-size:10px;color:var(--text-muted);font-family:'JetBrains Mono',monospace;margin-top:4px}.latency-pill{font-family:'JetBrains Mono',monospace;font-size:9.5px;padding:5px 8px;border-radius:20px;background:var(--bg-elevated);color:var(--cobalt);border:1px solid var(--border-subtle);font-weight:700;white-space:nowrap}
.regime-display{background:var(--bg-elevated);border:1px solid var(--border-subtle);border-radius:11px;padding:17px;margin:16px 0;display:flex;align-items:center;gap:14px}.regime-display.hot{background:linear-gradient(135deg,var(--amber-glow),var(--bg-elevated) 80%);border-color:rgba(245,158,11,.3)}.regime-display.cold{background:linear-gradient(135deg,var(--cyan-glow),var(--bg-elevated) 80%);border-color:rgba(56,189,248,.3)}.regime-display.bull{background:linear-gradient(135deg,var(--emerald-glow),var(--bg-elevated) 80%);border-color:rgba(16,185,129,.3)}.regime-display.bear{background:linear-gradient(135deg,var(--rose-glow),var(--bg-elevated) 80%);border-color:rgba(244,63,94,.3)}.regime-icon{width:48px;height:48px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:23px;flex-shrink:0;color:#fff}.regime-icon.hot{background:var(--gradient-hot)}.regime-icon.cold{background:var(--gradient-cold)}.regime-icon.bull{background:var(--gradient-bull)}.regime-icon.bear{background:var(--gradient-bear)}.regime-text-block{flex:1;min-width:0}.regime-label{font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.1em;margin-bottom:5px;font-weight:700}.regime-title{font-size:1rem;font-weight:800;letter-spacing:-.02em;margin:0}.regime-title.hot{color:var(--amber)}.regime-title.cold{color:var(--cyan)}.regime-title.bull{color:var(--emerald)}.regime-title.bear{color:var(--rose)}
.metrics-strip{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:16px;padding-top:15px;border-top:1px solid var(--border-subtle)}.metric-cell{background:var(--bg-elevated);border:1px solid var(--border-subtle);border-radius:8px;padding:10px 8px;text-align:center}.metric-val{font-family:'JetBrains Mono',monospace;font-size:1rem;font-weight:700;color:var(--text-primary)}.metric-lbl{font-family:'JetBrains Mono',monospace;font-size:8px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;margin-top:4px;font-weight:700}
.hard-badge{display:inline-flex;align-items:center;gap:7px;padding:8px 11px;border-radius:8px;background:var(--bg-elevated);border:1px solid var(--border-subtle);font-family:'JetBrains Mono',monospace;font-size:9.5px;font-weight:600;color:var(--text-tertiary);margin-top:5px}.hard-dot{width:7px;height:7px;border-radius:50%;background:var(--cyan)}.hard-badge.hot .hard-dot{background:var(--amber)}.hard-badge.cold .hard-dot{background:var(--cyan)}.hard-val{color:var(--text-primary)}
.token-heatmap{margin-top:18px;padding-top:15px;border-top:1px solid var(--border-subtle)}.token-heatmap-head{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px}.token-heatmap-label{font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.08em;font-weight:700}.heat-legend{font-family:'JetBrains Mono',monospace;font-size:8px;color:var(--text-muted)}.heat-swatch{display:inline-block;width:12px;height:8px;border-radius:2px;margin:0 2px;border:1px solid var(--border-subtle)}.hs-1{background:transparent}.hs-2{background:var(--heat-2)}.hs-3{background:var(--heat-3)}.hs-4{background:var(--heat-4)}.hs-5{background:var(--heat-5)}.token-row{display:flex;flex-wrap:wrap;gap:5px}.token{font-size:11px;padding:4px 7px;border-radius:5px;font-weight:500;color:var(--text-secondary)}.token.weight-5{background:var(--heat-5);color:var(--amber);font-weight:700}.token.weight-4{background:var(--heat-4);color:var(--text-primary);font-weight:600}.token.weight-3{background:var(--heat-3);color:var(--text-secondary)}.token.weight-2{background:var(--heat-2);color:var(--text-tertiary)}.token.weight-1{background:transparent;color:var(--text-muted)}
.spectrum-wrapper{margin:16px 0}.spectrum-header{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.07em;margin-bottom:8px;font-weight:600}.spectrum-bar{display:flex;height:9px;width:100%;background:var(--bg-input);border-radius:5px;overflow:hidden;gap:1px;border:1px solid var(--border-subtle)}.seg-cold{background:var(--gradient-cold)}.seg-rising{background:var(--gradient-bull)}.seg-falling{background:var(--gradient-bear)}.prob-grid{display:flex;flex-direction:column;gap:8px;margin-top:15px}.prob-row{background:var(--bg-elevated);border:1px solid var(--border-subtle);border-radius:8px;padding:9px 11px}.prob-meta{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:6px;font-family:'JetBrains Mono',monospace;font-size:10px}.prob-name{color:var(--text-tertiary)}.prob-pct{color:var(--text-primary);font-weight:700}.prob-track{width:100%;height:5px;background:var(--bg-input);border:1px solid var(--border-subtle);border-radius:3px;overflow:hidden}.prob-fill{height:100%;border-radius:3px}.prob-fill-cold{background:var(--gradient-cold)}.prob-fill-bull{background:var(--gradient-bull)}.prob-fill-bear{background:var(--gradient-bear)}
.route-tag{display:inline-flex;align-items:center;gap:8px;padding:6px 10px;border-radius:6px;background:var(--bg-elevated);border:1px solid var(--border-subtle);font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--text-tertiary);margin-top:14px}.route-method{padding:2px 6px;border-radius:4px;font-weight:700;font-size:8.5px}.route-method.get{background:var(--emerald-glow);color:var(--emerald)}.route-method.post{background:rgba(59,130,246,.15);color:var(--cobalt)}
.meta-table,.manifest,.log-table{width:100%;border-collapse:collapse;font-family:'JetBrains Mono',monospace;font-size:10px}.meta-table{margin-top:12px}.meta-table tr,.manifest tr,.log-table td{border-bottom:1px solid var(--border-subtle)}.meta-table tr:last-child,.manifest tr:last-child,.log-table tr:last-child td{border-bottom:none}.meta-table td,.manifest td{padding:8px 4px}.meta-table td:first-child{color:var(--text-muted)}.meta-table td:last-child{text-align:right;color:var(--text-primary);font-weight:600}.manifest td{color:var(--text-tertiary);vertical-align:top}.manifest td:first-child{width:45px;color:var(--text-muted);font-weight:700}.manifest td:last-child{text-align:right;white-space:nowrap;color:var(--text-muted)}.log-table th{text-align:left;color:var(--text-muted);font-weight:700;text-transform:uppercase;letter-spacing:.08em;font-size:8.5px;padding:6px 7px;border-bottom:1px solid var(--border-subtle)}.log-table td{padding:8px 7px;color:var(--text-secondary)}
.placeholder-box{border:1px dashed var(--border-subtle);background:var(--bg-elevated);border-radius:9px;padding:14px 16px;margin-top:12px}.ph-title{font-family:'JetBrains Mono',monospace;font-size:9.5px;text-transform:uppercase;letter-spacing:.1em;color:var(--amber);font-weight:700;margin-bottom:6px}.ph-body{font-size:11px;color:var(--text-tertiary);line-height:1.55}.empty-state{text-align:center;padding:42px 22px;background:var(--bg-card);border:1px dashed var(--border-subtle);border-radius:15px}.empty-icon{font-size:34px;margin-bottom:11px}.empty-title{font-size:1.1rem;font-weight:750;color:var(--text-primary);margin-bottom:7px}.empty-desc{font-size:.85rem;color:var(--text-tertiary);max-width:510px;margin:0 auto;line-height:1.6}.footnote{text-align:center;padding:32px 0 8px;font-family:'JetBrains Mono',monospace;font-size:9px;color:var(--text-faint);letter-spacing:.04em;line-height:1.8}.footnote-brand{color:var(--text-muted);font-weight:700}

/* Market ticker: sourced values and demo fallback are always explicitly labeled. */
.ticker-wrap{background:var(--bg-panel);border:1px solid var(--border-subtle);border-radius:11px;margin:0 0 22px;overflow:hidden;box-shadow:var(--shadow-sm);}
.ticker-meta{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap;padding:8px 13px 7px;border-bottom:1px solid var(--border-subtle);font-family:'JetBrains Mono',monospace;font-size:8.5px;letter-spacing:.08em;font-weight:700;}
.ticker-source{display:inline-flex;align-items:center;gap:6px;line-height:1.4;}
.ticker-source.live{color:var(--emerald)!important}.ticker-source.demo{color:var(--amber)!important}
.ticker-updated{color:var(--text-muted)!important;font-weight:500}
.ticker-viewport{overflow:hidden;position:relative;padding:10px 0;}
.ticker-viewport:before,.ticker-viewport:after{content:'';position:absolute;top:0;bottom:0;width:34px;z-index:2;pointer-events:none;}
.ticker-viewport:before{left:0;background:linear-gradient(90deg,var(--bg-panel),transparent)}
.ticker-viewport:after{right:0;background:linear-gradient(-90deg,var(--bg-panel),transparent)}
.ticker-track{display:flex;width:max-content;animation:tickerScroll 75s linear infinite;will-change:transform}
.ticker-wrap:hover .ticker-track{animation-play-state:paused}
.ticker-item{display:inline-flex;align-items:center;gap:8px;padding:0 18px;border-right:1px solid var(--border-subtle);font-family:'JetBrains Mono',monospace;font-size:10.5px;white-space:nowrap;}
.ticker-sym{color:var(--text-primary)!important;font-weight:800;letter-spacing:.03em}
.ticker-price{color:var(--text-secondary)!important;font-weight:500}
.ticker-up{color:var(--emerald)!important;font-weight:700}.ticker-down{color:var(--rose)!important;font-weight:700}.ticker-flat{color:var(--text-muted)!important}
.ticker-demo-tag{font-size:7px;letter-spacing:.05em;border:1px solid var(--amber);border-radius:3px;padding:1px 3px;color:var(--amber)!important}
@keyframes tickerScroll{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}
.st-key-refresh_market_quotes button{min-height:78px!important;width:100%;padding:8px!important}
/* Scenario cards explicitly use theme tokens so text remains readable in light mode. */
.preset-kicker{font-family:'JetBrains Mono',monospace;font-size:9px;font-weight:800;letter-spacing:.12em;color:var(--cobalt)!important;margin:0 0 8px;text-transform:uppercase}
.preset-card-title{font-size:1.02rem;line-height:1.25;font-weight:800;color:var(--text-primary)!important;margin:0 0 8px}
.preset-description{font-size:12px;line-height:1.5;color:var(--text-secondary)!important;min-height:54px;margin:0 0 12px}
[data-testid="stVerticalBlockBorderWrapper"] .preset-kicker,[data-testid="stVerticalBlockBorderWrapper"] .preset-card-title,[data-testid="stVerticalBlockBorderWrapper"] .preset-description{opacity:1!important;visibility:visible!important}
@media(max-width:900px){.hero-stack{flex-direction:column;align-items:flex-start}.hero-specs{width:100%;grid-template-columns:repeat(3,minmax(0,1fr));gap:2px}.spec-cell{padding:0 5px}.verdict-banner{grid-template-columns:1fr;text-align:center;padding:22px 18px}.verdict-meta-row{justify-content:center}.metrics-strip{grid-template-columns:repeat(3,1fr)}.topbar{align-items:flex-start;flex-wrap:wrap}.preset-description{min-height:unset}.ticker-item{padding:0 12px}}
@media(prefers-reduced-motion:reduce){.ticker-track{animation:none!important;transform:none!important}.ticker-viewport{overflow-x:auto}.ticker-viewport:before,.ticker-viewport:after{display:none}}

@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.001s!important;transition-duration:.001s!important;scroll-behavior:auto!important}}
""")
CSS = OVERRIDE_CSS.substitute(THEME).replace("COLOR_SCHEME", "dark" if st.session_state.theme == "dark" else "light")
# Template substitutes literal '$focus', '$ring', etc. as separate tokens.
st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════
# Hardened inference helpers are imported from sentinel_hardening.py.
# This keeps production behavior and the offline unit tests on one code path.
# ═══════════════════════════════════════════════════════════════════════


@st.cache_data(ttl=PING_TTL_S, show_spinner=False)
def ping_service(url: str) -> tuple[bool, Optional[int]]:
    """Reachability check. Any response below 500 means the service responded."""
    started = time.perf_counter()
    try:
        response = requests.get(url.rstrip("/"), timeout=4)
        return response.status_code < 500, int((time.perf_counter() - started) * 1000)
    except requests.RequestException:
        return False, None


def get_secret(key: str) -> str:
    try:
        value = st.secrets.get(key)
    except (FileNotFoundError, KeyError, AttributeError):
        value = None
    if not value:
        st.error(f"Missing configuration: `{key}` was not found in Streamlit secrets.")
        st.info(f'Add `{key} = "https://your-service-url"` to `.streamlit/secrets.toml` or your Streamlit Cloud app secrets.')
        st.stop()
    value = str(value).strip().rstrip("/")
    if not value.startswith(("https://", "http://")):
        st.error(f"`{key}` must be a full HTTP(S) URL.")
        st.stop()
    return value


# ── Deep-linking and editor callbacks ──────────────────────────────────
def qp_get(key: str, default: str = "") -> str:
    try:
        value = st.query_params.get(key, default)
        return value if isinstance(value, str) else default
    except (AttributeError, TypeError):
        return default


def qp_set(**kwargs: str) -> None:
    try:
        for key, value in kwargs.items():
            if value:
                st.query_params[key] = value
            elif key in st.query_params:
                del st.query_params[key]
    except (AttributeError, TypeError):
        pass


def check_last_input() -> None:
    """Append a new empty wire when the current final visible wire is filled."""
    count = int(st.session_state.get("num_inputs", 3))
    last_index = count - 1
    if (count < MAX_WIRES and st.session_state.get(f"input_{last_index}", "").strip()):
        st.session_state.num_inputs = count + 1


def reset_all_inputs() -> None:
    for index in range(MAX_WIRES):
        key = f"input_{index}"
        if key in st.session_state:
            st.session_state[key] = ""
    st.session_state.summary_input = ""
    st.session_state.num_inputs = 3
    st.session_state.active_preset = None
    qp_set(preset="")


def reset_workspace() -> None:
    reset_all_inputs()
    st.session_state.last_results = None
    st.session_state.previous_results = None
    st.session_state.run_history = []


def add_wire() -> None:
    if st.session_state.num_inputs < MAX_WIRES:
        st.session_state.num_inputs += 1


def remove_wire(idx: int) -> None:
    count = int(st.session_state.num_inputs)
    if not (0 <= idx < count) or count <= 3:
        return
    for index in range(idx, count - 1):
        st.session_state[f"input_{index}"] = st.session_state.get(f"input_{index + 1}", "")
    st.session_state[f"input_{count - 1}"] = ""
    st.session_state.num_inputs = max(3, count - 1)


def clear_log() -> None:
    st.session_state.run_log = []
    st.session_state.run_history = []


PRESETS = [
    {
        "icon": "📊", "tag": "SCENARIO 01", "key": "bullish", "title": "Quarterly Results",
        "desc": "Quarterly performance figures, forward guidance, and margin updates.",
        "headlines": [
            "NVIDIA reports Q4 revenue surge of 78% YoY, exceeding institutional consensus",
            "Management raises full-year data center guidance amid AI chip demand",
            "Gross margins expand sequentially as pricing power accelerates",
        ],
        "summary": "The story combines quarterly results, backlog commentary, and forward guidance.",
    },
    {
        "icon": "🧾", "tag": "SCENARIO 02", "key": "bearish", "title": "Guidance & Leadership",
        "desc": "An outlook revision, an executive transition, and a regulatory inquiry.",
        "headlines": [
            "Company cuts full-year operating margin outlook citing supply chain bottlenecks",
            "CFO steps down unexpectedly as regulator opens an inquiry into revenue recognition",
            "Institutional desks downgrade equity following an unexpected earnings miss",
        ],
        "summary": "The story combines an outlook revision, leadership turnover, and a regulatory inquiry.",
    },
    {
        "icon": "📋", "tag": "SCENARIO 03", "key": "neutral", "title": "Routine Filing",
        "desc": "A dividend declaration, shareholder-meeting agenda, and operations update.",
        "headlines": [
            "Board declares regular quarterly cash dividend of $0.25 per share",
            "Annual shareholder meeting scheduled for next month with standard proxy proposals",
            "Operations remain in line with multi-year historical averages",
        ],
        "summary": "The story combines a routine dividend declaration, proxy agenda, and operations update.",
    },
]

def load_preset(idx: int, apply_query: bool = True) -> None:
    preset = PRESETS[idx]
    reset_all_inputs()
    visible_count = min(MAX_WIRES, max(3, len(preset["headlines"])))
    st.session_state.num_inputs = visible_count
    for index, headline in enumerate(preset["headlines"][:MAX_WIRES]):
        st.session_state[f"input_{index}"] = headline
    st.session_state.summary_input = preset.get("summary", "")
    st.session_state.active_preset = idx
    if apply_query:
        qp_set(preset=preset["key"])


def handle_csv_upload() -> None:
    """CSV callback runs before widgets are rendered, allowing safe state updates."""
    uploaded = st.session_state.get("headline_csv_upload")
    if uploaded is None:
        st.session_state.csv_loaded_fingerprint = ""
        return
    try:
        raw_bytes = uploaded.getvalue()
        fingerprint = hashlib.sha256(raw_bytes).hexdigest()
        if fingerprint == st.session_state.get("csv_loaded_fingerprint", ""):
            return
        text = raw_bytes.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        fieldnames = reader.fieldnames or []
        headline_column = next((name for name in fieldnames if name and name.strip().lower() == "headline"), None)
        if headline_column is None:
            st.session_state.csv_import_message = ("error", "CSV must contain a column named 'headline'.")
            return
        headlines = [
            (row.get(headline_column) or "").strip()
            for row in reader
            if (row.get(headline_column) or "").strip()
        ]
        if not headlines:
            st.session_state.csv_import_message = ("warning", "No non-empty headlines were found in this CSV.")
            return
        count = min(len(headlines), MAX_WIRES)
        reset_all_inputs()
        st.session_state.num_inputs = max(3, count)
        for index, headline in enumerate(headlines[:MAX_WIRES]):
            st.session_state[f"input_{index}"] = headline
        st.session_state.csv_loaded_fingerprint = fingerprint
        suffix = f" of {len(headlines)} rows (limit {MAX_WIRES})" if len(headlines) > MAX_WIRES else ""
        st.session_state.csv_import_message = ("success", f"Loaded {count} headline(s){suffix}.")
    except (csv.Error, UnicodeError, OSError, AttributeError) as exc:
        st.session_state.csv_import_message = ("error", f"CSV import failed: {safe_text(exc, 200)}")


HOT5 = {
    "surge", "surges", "crash", "crashes", "slashes", "slash", "spike", "spikes", "jumps", "jump",
    "soars", "soar", "plunges", "plunge", "hike", "hikes", "warning", "warns", "miss", "misses",
    "inquiry", "probe", "steps", "record", "breaks", "shock", "shocks", "cut", "cuts", "rally",
    "rallies", "sinks", "tumbles", "escalate", "escalates", "slashed", "spiked",
}
HOT4 = {
    "guidance", "outlook", "margins", "margin", "yields", "yield", "inflation", "fed", "reserve",
    "powell", "etf", "inflows", "outflows", "downgrade", "upgrades", "volatility", "vix", "supply",
    "demand", "revenue", "earnings", "bitcoin", "btc", "crude", "opec", "treasury", "sec", "cfo",
    "dividend", "backlog", "pricing", "target", "ratings", "exposure",
}


def token_weight(token: str) -> int:
    cleaned = token.strip(".,;:!?()\"'").lower()
    if cleaned in HOT5:
        return 5
    if cleaned in HOT4:
        return 4
    if len(cleaned) > 8:
        return 3
    if len(cleaned) > 4:
        return 2
    return 1


def _gauge_svg(value: Optional[float], kind: str, size: int, vb: float, radius: float,
               fs_value: float, fs_label: float, label: str) -> str:
    palettes = {
        "hot": ("#FB7185", "#E11D48"), "cold": ("#38BDF8", "#0284C7"),
        "bull": ("#34D399", "#059669"), "bear": ("#F87171", "#DC2626"),
        "accent": (THEME["cobalt"], "#8B5CF6"), "split": ("#38BDF8", "#F59E0B"),
        "partial": ("#F87171", "#DC2626"),
    }
    color1, color2 = palettes.get(kind, palettes["accent"])
    center = vb / 2
    circumference = 2 * math.pi * radius
    arc = circumference * 0.75
    if value is None:
        return f'''<svg width="{size}" height="{size}" viewBox="0 0 {vb} {vb}" role="img" aria-label="{safe_text(label)} unavailable">
        <circle cx="{center}" cy="{center}" r="{radius}" fill="none" stroke="{THEME['border']}" stroke-width="6" stroke-dasharray="{arc} {circumference}" transform="rotate(135 {center} {center})" stroke-linecap="round"/>
        <text x="{center}" y="{center-2}" text-anchor="middle" font-family="Inter" font-weight="800" font-size="{fs_value}" fill="{THEME['text3']}">—</text>
        <text x="{center}" y="{center+13}" text-anchor="middle" font-family="JetBrains Mono" font-weight="600" font-size="{fs_label}" fill="{THEME['muted']}" letter-spacing="1">{safe_text(label)}</text></svg>'''
    numeric = max(0.0, min(1.0, float(value)))
    offset = arc * (1.0 - numeric)
    gradient_id = f"g{kind}{size}{uuid.uuid4().hex[:6]}"
    return f'''<svg width="{size}" height="{size}" viewBox="0 0 {vb} {vb}" role="img" aria-label="{safe_text(label)}: {numeric*100:.0f}%">
    <defs><linearGradient id="{gradient_id}" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="{color1}"/><stop offset="100%" stop-color="{color2}"/></linearGradient></defs>
    <circle cx="{center}" cy="{center}" r="{radius}" fill="none" stroke="{THEME['border']}" stroke-width="6" stroke-dasharray="{arc} {circumference}" transform="rotate(135 {center} {center})" stroke-linecap="round"/>
    <circle cx="{center}" cy="{center}" r="{radius}" fill="none" stroke="url(#{gradient_id})" stroke-width="6" stroke-dasharray="{arc} {circumference}" stroke-dashoffset="{offset}" transform="rotate(135 {center} {center})" stroke-linecap="round"/>
    <text x="{center}" y="{center-2}" text-anchor="middle" font-family="Inter" font-weight="800" font-size="{fs_value}" fill="{THEME['text1']}">{numeric*100:.0f}%</text>
    <text x="{center}" y="{center+13}" text-anchor="middle" font-family="JetBrains Mono" font-weight="600" font-size="{fs_label}" fill="{THEME['muted']}" letter-spacing="1">{safe_text(label)}</text></svg>'''


def svg_gauge(value: Optional[float], kind: str = "accent", size: int = 86, label: str = "AGREEMENT") -> str:
    return _gauge_svg(value, kind, size, 88, 33, 29, 7.5, label)


def make_get_url(url: str, headline: str, model_code: int | float) -> str:
    prepared = requests.Request(
        "GET", f"{url.rstrip('/')}/predict",
        params={"headline": headline, "model_choice": model_code},
    ).prepare()
    return prepared.url or ""


def inference_error(branch: str, exc: BaseException) -> dict[str, Any]:
    return {"ok": False, "val": None, "latency_ms": 0, "last_attempt_latency_ms": 0,
            "error": f"Unexpected {branch} client error: {safe_text(exc, 220)}",
            "data": {}, "attempts": 0, "status": None, "branch": branch}


# ═══════════════════════════════════════════════════════════════════════
# Market ticker — Yahoo Finance chart snapshot, with explicit demo fallback
# ═══════════════════════════════════════════════════════════════════════
TICKER_UNIVERSE = [
    {"label": "SPX", "symbol": "^GSPC", "kind": "index"},
    {"label": "NDX", "symbol": "^NDX", "kind": "index"},
    {"label": "DJI", "symbol": "^DJI", "kind": "index"},
    {"label": "VIX", "symbol": "^VIX", "kind": "index"},
    {"label": "TNX", "symbol": "^TNX", "kind": "yield"},
    {"label": "BTC", "symbol": "BTC-USD", "kind": "usd"},
    {"label": "ETH", "symbol": "ETH-USD", "kind": "usd"},
    {"label": "GOLD", "symbol": "GC=F", "kind": "usd"},
    {"label": "OIL", "symbol": "CL=F", "kind": "usd"},
    {"label": "EUR/USD", "symbol": "EURUSD=X", "kind": "fx4"},
    {"label": "GBP/USD", "symbol": "GBPUSD=X", "kind": "fx4"},
    {"label": "USD/JPY", "symbol": "JPY=X", "kind": "fx2"},
    {"label": "AAPL", "symbol": "AAPL", "kind": "usd"},
    {"label": "MSFT", "symbol": "MSFT", "kind": "usd"},
    {"label": "NVDA", "symbol": "NVDA", "kind": "usd"},
    {"label": "TSLA", "symbol": "TSLA", "kind": "usd"},
]

# Historical values are intentionally used ONLY when the market feed is unreachable.
# Every fallback quote is labeled DEMO; values are not represented as current prices.
DEMO_TICKERS = [
    ("SPX", "5,842.16", "+0.82%", True), ("NDX", "20,341.55", "+1.24%", True),
    ("DJI", "42,118.91", "-0.18%", False), ("VIX", "14.32", "-3.21%", False),
    ("TNX", "4.281%", "+0.14%", True), ("BTC", "$92,418.00", "+3.41%", True),
    ("ETH", "$3,842.00", "+5.12%", True), ("GOLD", "$2,741.00", "-0.64%", False),
    ("OIL", "$78.42", "+2.18%", True), ("EUR/USD", "1.0842", "+0.14%", True),
    ("GBP/USD", "1.2961", "-0.08%", False), ("USD/JPY", "149.82", "+0.32%", True),
    ("AAPL", "$229.41", "+1.90%", True), ("MSFT", "$424.82", "+2.30%", True),
    ("NVDA", "$141.22", "+4.70%", True), ("TSLA", "$262.55", "-1.40%", False),
]


def _finite_number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _fetch_one_ticker(item: dict[str, str]) -> Optional[dict[str, Any]]:
    """Fetch a no-API-key Yahoo chart snapshot for one instrument."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(item['symbol'], safe='=')}"
    try:
        response = requests.get(
            url,
            params={"range": "1d", "interval": "1m"},
            headers={"User-Agent": "Mozilla/5.0 HeadlinesHeatPrediction/1.0"},
            timeout=MARKET_HTTP_TIMEOUT,
        )
        response.raise_for_status()
        body = response.json()
        result_list = ((body.get("chart") or {}).get("result") or [])
        if not result_list:
            return None
        result = result_list[0]
        meta = result.get("meta") or {}
        price = _finite_number(meta.get("regularMarketPrice"))
        if price is None:
            closes = (((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or [])
            price = next((_finite_number(v) for v in reversed(closes) if _finite_number(v) is not None), None)
        previous = _finite_number(meta.get("chartPreviousClose"))
        if previous is None:
            previous = _finite_number(meta.get("previousClose"))
        if price is None:
            return None
        change_pct = ((price / previous) - 1.0) * 100.0 if previous and previous > 0 else None
        return {
            "label": item["label"], "symbol": item["symbol"], "kind": item["kind"],
            "price": price, "change_pct": change_pct,
            "market_timestamp": meta.get("regularMarketTime"),
        }
    except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
        return None


@st.cache_data(ttl=MARKET_QUOTES_TTL_S, show_spinner=False)
def fetch_market_quotes() -> dict[str, dict[str, Any]]:
    """Fetch quotes concurrently; cache results briefly to protect the free feed."""
    from concurrent.futures import as_completed

    found: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(16, len(TICKER_UNIVERSE))) as pool:
        future_items = {pool.submit(_fetch_one_ticker, item): item for item in TICKER_UNIVERSE}
        for future in as_completed(future_items):
            quote = future.result()
            if quote is not None:
                found[quote["label"]] = quote
    # Preserve the order defined in TICKER_UNIVERSE.
    return {item["label"]: found[item["label"]] for item in TICKER_UNIVERSE if item["label"] in found}


def _format_quote_price(quote: dict[str, Any]) -> str:
    price = float(quote["price"])
    kind = quote["kind"]
    if kind == "yield":
        # Yahoo's ^TNX quote is already expressed as the yield percentage.
        return f"{price:.3f}%"
    if kind == "fx4":
        return f"{price:.4f}"
    if kind == "fx2":
        return f"{price:.2f}"
    if kind == "usd":
        return f"${price:,.2f}"
    return f"{price:,.2f}"


def _ticker_html(quotes: dict[str, dict[str, Any]], use_demo: bool) -> str:
    if use_demo:
        items = [
            (label, price, delta, is_up, True)
            for label, price, delta, is_up in DEMO_TICKERS
        ]
        source_badge = "DEMO MODE · ILLUSTRATIVE VALUES · LIVE FEED UNAVAILABLE"
        source_class = "demo"
    else:
        items = []
        for spec in TICKER_UNIVERSE:
            quote = quotes.get(spec["label"])
            if quote is None:
                continue
            change = quote.get("change_pct")
            if change is None:
                delta_label, is_up = "—", False
            else:
                delta_label = f"{change:+.2f}%"
                is_up = change >= 0
            items.append((quote["label"], _format_quote_price(quote), delta_label, is_up, False))
        source_badge = (
            "YAHOO FINANCE SNAPSHOT · MAY BE DELAYED"
            if len(items) == len(TICKER_UNIVERSE)
            else f"PARTIAL YAHOO FINANCE SNAPSHOT · {len(items)}/{len(TICKER_UNIVERSE)} QUOTES · MAY BE DELAYED"
        )
        source_class = "live"

    rendered_items = []
    for label, price, delta, is_up, is_demo in items:
        movement_cls = "ticker-up" if is_up else ("ticker-down" if delta != "—" else "ticker-flat")
        arrow = "▲" if is_up else ("▼" if delta != "—" else "•")
        demo_tag = '<span class="ticker-demo-tag">DEMO</span>' if is_demo else ""
        rendered_items.append(
            f'<div class="ticker-item"><span class="ticker-sym">{safe_text(label, 20)}</span>'
            f'<span class="ticker-price">{safe_text(price, 30)}</span>'
            f'<span class="{movement_cls}">{arrow} {safe_text(delta, 20)}</span>{demo_tag}</div>'
        )
    track = "".join(rendered_items)
    retrieved = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    return (
        '<div class="ticker-wrap" role="region" aria-label="Market ticker">'
        f'<div class="ticker-meta"><span class="ticker-source {source_class}">{source_badge}</span>'
        f'<span class="ticker-updated">RETRIEVED {retrieved}</span></div>'
        f'<div class="ticker-viewport"><div class="ticker-track">{track}{track}</div></div>'
        '</div>'
    )


# ═══════════════════════════════════════════════════════════════════════
# API configuration and health probes
# ═══════════════════════════════════════════════════════════════════════
SVC_API_URL = get_secret("SVC_API_URL")
FINBERT_API_URL = get_secret("FINBERT_API_URL")
svc_online, svc_ping_ms = ping_service(SVC_API_URL)
fin_online, fin_ping_ms = ping_service(FINBERT_API_URL)
svc_chip = ("ok", f"SVC · {svc_ping_ms}ms") if svc_online else ("bad", "SVC · UNREACHABLE")
fin_chip = ("ok", f"FINBERT · {fin_ping_ms}ms") if fin_online else ("bad", "FINBERT · UNREACHABLE")

# Deep-link preset on first load, before headline widgets are created.
if st.session_state.active_preset is None and not st.session_state.get("input_0"):
    query_preset = qp_get("preset")
    for preset_index, preset in enumerate(PRESETS):
        if preset["key"] == query_preset:
            load_preset(preset_index, apply_query=False)
            break

# ═══════════════════════════════════════════════════════════════════════
# TOP BAR + DATA STATUS + HERO
# ═══════════════════════════════════════════════════════════════════════
head_left, head_right = st.columns([5, 1])
with head_left:
    st.markdown(f"""
    <div class="topbar"><div class="topbar-left"><div class="brand-mark">H</div><div>
    <div class="brand-title">HEADLINES HEAT</div><div class="brand-tag">Financial Event Classification · v5.0</div></div></div>
    <div class="topbar-right"><div class="chip {svc_chip[0]}"><span class="chip-dot"></span>{svc_chip[1]}</div>
    <div class="chip {fin_chip[0]}"><span class="chip-dot"></span>{fin_chip[1]}</div></div></div>
    """, unsafe_allow_html=True)
with head_right:
    st.toggle("☀️ Light" if st.session_state.theme == "dark" else "🌙 Dark",
              key="theme_toggle", on_change=toggle_theme)

market_quotes = fetch_market_quotes()
# Prefer real provider results; when none are reachable, render clearly marked demo values.
using_demo_quotes = not bool(market_quotes)
ticker_col, refresh_col = st.columns([12, 1], gap="small")
with ticker_col:
    st.markdown(_ticker_html(market_quotes, using_demo_quotes), unsafe_allow_html=True)
with refresh_col:
    refresh_quotes = st.button("↻ Refresh", key="refresh_market_quotes", help="Fetch a fresh Yahoo Finance snapshot")
if refresh_quotes:
    fetch_market_quotes.clear()
    st.rerun()
if using_demo_quotes:
    st.caption("Demo prices are illustrative placeholders only; they are not current market quotes.")
else:
    st.caption("Yahoo Finance chart snapshots may be delayed, incomplete, or unavailable for some markets. Hover over the ticker to pause it.")
st.markdown("""
<div class="hero-stack"><div>
<h1 class="hero-title">Headlines Heat <span class="accent">Prediction</span></h1>
<p class="hero-sub">A research workbench for financial headlines. Compare a TF-IDF / LinearSVC baseline with FinBERT tone classes or a frozen-Word2Vec LSTM. Outputs are model classifications—not guaranteed forecasts, calibrated confidence, or investment advice.</p>
</div><div class="hero-specs">
<div class="spec-cell"><span class="spec-lbl">Inference branches</span><span class="spec-val">2 parallel calls</span></div>
<div class="spec-cell"><span class="spec-lbl">Neural options</span><span class="spec-val">FinBERT / LSTM</span></div>
<div class="spec-cell"><span class="spec-lbl">Payload cap</span><span class="spec-val">12,000 chars</span></div>
</div></div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════
# 01 · PRESETS
# ═══════════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label" data-num="01">Scenario Library · synthetic examples</div>', unsafe_allow_html=True)
preset_cols = st.columns(3, gap="large")
for index, preset in enumerate(PRESETS):
    with preset_cols[index]:
        with st.container(border=True):
            st.markdown(
                f'<div class="preset-kicker">{safe_text(preset["tag"])}</div>'
                f'<div class="preset-card-title">{safe_text(preset["icon"])} &nbsp; {safe_text(preset["title"])}</div>'
                f'<div class="preset-description">{safe_text(preset["desc"])}</div>',
                unsafe_allow_html=True,
            )
            active = st.session_state.active_preset == index
            if st.button(
                "✓ Loaded · select again" if active else "Load scenario →",
                key=f"preset_{index}", use_container_width=True,
                type="primary" if active else "secondary",
                help="Populate the headline editor with this synthetic example. The model outcome is not shown in advance.",
            ):
                load_preset(index)
                st.rerun()
st.markdown('<div class="preset-hint">Synthetic test inputs only · no expected label is shown · selecting a scenario only fills the editor; it does not run inference.</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════
# 02 / 03 · INPUT + CONFIG
# ═══════════════════════════════════════════════════════════════════════
panel_left, panel_right = st.columns([2.4, 1], gap="large")
with panel_left:
    st.markdown('<div class="section-label" data-num="02">Event Stream Ingestion</div>', unsafe_allow_html=True)
    with st.container(border=True):
        visible_wires = min(MAX_WIRES, max(3, int(st.session_state.num_inputs)))
        st.session_state.num_inputs = visible_wires
        for index in range(visible_wires):
            is_last = index == visible_wires - 1
            wire_col, remove_col = st.columns([20, 1], gap="small")
            with wire_col:
                st.text_input(
                    label=f"WIRE HEADLINE {index + 1:02d}", key=f"input_{index}",
                    placeholder=f"[Wire {index + 1:02d}] Enter a financial headline or press release…",
                    on_change=check_last_input if is_last else None,
                )
            with remove_col:
                if visible_wires > 3:
                    st.button("×", key=f"rm_{index}", help=f"Remove wire {index + 1}",
                              use_container_width=True, on_click=remove_wire, args=(index,))
                else:
                    st.write("")
        action_cols = st.columns([1, 1, 1.6, 1.7])
        with action_cols[0]:
            st.button("＋ Add Wire", type="secondary", use_container_width=True,
                      disabled=visible_wires >= MAX_WIRES, on_click=add_wire)
        with action_cols[1]:
            st.button("✕ Clear All", type="secondary", use_container_width=True, on_click=reset_all_inputs)
        with action_cols[2]:
            st.file_uploader(
                "Batch CSV (headline column)", type=["csv"], key="headline_csv_upload",
                label_visibility="collapsed", on_change=handle_csv_upload,
                help="CSV must contain a column named 'headline'. Imports are fingerprinted to avoid duplicate reruns.",
            )
        with action_cols[3]:
            st.caption(f"{visible_wires}/{MAX_WIRES} wire slots · last slot auto-expands")
        import_message = st.session_state.get("csv_import_message")
        if import_message:
            level, message = import_message
            if level == "success":
                st.success(message)
            elif level == "warning":
                st.warning(message)
            else:
                st.error(message)
            st.session_state.csv_import_message = None

with panel_right:
    st.markdown('<div class="section-label" data-num="03">Model Configuration</div>', unsafe_allow_html=True)
    with st.container(border=True):
        MODEL_MAP = {
            "LinearSVC · σ > 1.0 (High)": (1, "1.0σ", "Strict tail-volatility filter"),
            "LinearSVC · σ > 0.5 (Medium)": (0.5, "0.5σ", "Balanced regime sensitivity"),
            "LinearSVC · σ > 0.2 (Low)": (0.2, "0.2σ", "High sensitivity to smaller moves"),
        }
        selected_svc_label = st.selectbox(
            "Baseline volatility threshold", options=list(MODEL_MAP.keys()), index=1,
            key="svc_threshold_label",
        )
        st.caption(MODEL_MAP[selected_svc_label][2])
        st.markdown('<div style="font-family:JetBrains Mono,monospace;font-size:9px;color:var(--text-tertiary);text-transform:uppercase;letter-spacing:.1em;margin:16px 0 8px;font-weight:700">Neural branch</div>', unsafe_allow_html=True)
        neural_cols = st.columns(2, gap="small")
        with neural_cols[0]:
            if st.button("FinBERT-Tone", use_container_width=True, key="choose_finbert",
                         type="primary" if st.session_state.dl_branch == "FINBERT-TONE" else "secondary"):
                st.session_state.dl_branch = "FINBERT-TONE"
        with neural_cols[1]:
            if st.button("LSTM · W2V", use_container_width=True, key="choose_lstm",
                         type="primary" if st.session_state.dl_branch == "LSTM-W2V" else "secondary"):
                st.session_state.dl_branch = "LSTM-W2V"
        if st.session_state.dl_branch == "LSTM-W2V":
            st.caption("LSTM is routed through SVC API at model_choice=7.")
        else:
            st.caption("FinBERT uses POST /dl_predict and requires 3 normalized class probabilities.")
        st.text_area(
            "Extended context · FinBERT only", key="summary_input",
            placeholder="Optional 1–3 sentence analyst synthesis…", height=110,
        )

active_wires = [
    (index, (st.session_state.get(f"input_{index}", "") or "").strip())
    for index in range(min(MAX_WIRES, int(st.session_state.num_inputs)))
    if (st.session_state.get(f"input_{index}", "") or "").strip()
]
active_headlines = [headline for _, headline in active_wires]
concatenated_headlines = " ".join(active_headlines)
summary = (st.session_state.get("summary_input", "") or "").strip()
request_char_count = len(concatenated_headlines) + len(summary)
branch_tag = st.session_state.dl_branch

st.markdown('<div style="height:5px"></div>', unsafe_allow_html=True)
run_cols = st.columns([1.45, 1.05, 3.25])
with run_cols[0]:
    predict_clicked = st.button("⚡ Execute Dual Inference", type="primary", use_container_width=True)
with run_cols[1]:
    st.button("Clear Workspace", type="secondary", use_container_width=True, on_click=reset_workspace)
with run_cols[2]:
    st.markdown(
        f'<div style="font-family:JetBrains Mono,monospace;font-size:10px;color:var(--text-muted);padding:13px 4px 0">'
        f'ACTIVE WIRES: <strong style="color:var(--text-secondary)">{len(active_headlines)}</strong> · '
        f'PAYLOAD: <strong style="color:var(--text-secondary)">{request_char_count:,}/{MAX_CHARS:,} CHARS</strong> · '
        f'BRANCH: <strong style="color:var(--cobalt)">{safe_text(branch_tag)}</strong></div>',
        unsafe_allow_html=True,
    )

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════
# DISPATCH · calls execute concurrently and elapsed time is measured as wall time
# ═══════════════════════════════════════════════════════════════════════
if predict_clicked:
    if not concatenated_headlines:
        st.session_state.last_results = None
        st.markdown('''<div class="empty-state"><div class="empty-icon">📡</div><div class="empty-title">No signal detected</div><div class="empty-desc">Provide at least one headline or select a scenario preset before running inference.</div></div>''', unsafe_allow_html=True)
    elif request_char_count > MAX_CHARS:
        st.session_state.last_results = None
        st.error(f"Complete request exceeds {MAX_CHARS:,} characters. Shorten the headlines or optional context and retry.")
    else:
        model_code, sigma_str, sigma_desc = MODEL_MAP[selected_svc_label]
        try:
            prepared_url = make_get_url(SVC_API_URL, concatenated_headlines, model_code)
        except (ValueError, requests.RequestException) as exc:
            prepared_url = ""
            st.session_state.last_results = None
            st.error(f"Could not prepare SVC request: {safe_text(exc, 200)}")
        if prepared_url and len(prepared_url) > MAX_GET_URL_CHARS:
            st.session_state.last_results = None
            st.error(
                f"The encoded GET request URL is {len(prepared_url):,} characters, above the safe app limit "
                f"of {MAX_GET_URL_CHARS:,}. Remove some headlines or migrate `/predict` to POST JSON. "
                "The Streamlit payload limit alone cannot prevent proxy URL-length errors."
            )
        elif prepared_url:
            dl_branch = st.session_state.dl_branch
            run_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            req_id = uuid.uuid4().hex[:8].upper()
            dispatch_started = time.perf_counter()
            with st.spinner("Dispatching payloads across inference endpoints…"):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    svc_future = pool.submit(call_svc, SVC_API_URL, concatenated_headlines, model_code, 15)
                    if dl_branch == "FINBERT-TONE":
                        neural_future = pool.submit(call_finbert, FINBERT_API_URL, concatenated_headlines, summary, 20)
                    else:
                        neural_future = pool.submit(call_svc, SVC_API_URL, concatenated_headlines, LSTM_MODEL_CODE, 20)
                    try:
                        svc_result = svc_future.result()
                    except Exception as exc:  # Defensive boundary around unforeseen client exceptions
                        svc_result = inference_error("SVC", exc)
                    try:
                        neural_result = neural_future.result()
                    except Exception as exc:
                        neural_result = inference_error(dl_branch, exc)
            wall_ms = int((time.perf_counter() - dispatch_started) * 1000)
            neural_result["branch"] = dl_branch

            # Snapshot exact request inputs so later edits cannot alter this report.
            previous = st.session_state.get("last_results")
            st.session_state.previous_results = previous
            st.session_state.last_results = {
                "svc_result": svc_result,
                "neural_result": neural_result,
                "model_code": model_code,
                "sigma_str": sigma_str,
                "sigma_desc": sigma_desc,
                "dl_branch": dl_branch,
                "headlines": list(active_headlines),
                "wires": list(active_wires),
                "summary": summary,
                "concatenated_headlines": concatenated_headlines,
                "wall_ms": wall_ms,
                "run_utc": run_utc,
                "req_id": req_id,
            }

            svc_label = "HOT" if svc_result["ok"] and svc_result["val"] == 1 else (
                "COLD" if svc_result["ok"] else "ERR")
            neural_label = "HOT" if neural_result["ok"] and neural_result["val"] == 1 else (
                "COLD" if neural_result["ok"] else "ERR")
            st.session_state.run_log.append({
                "req_id": req_id,
                "ts": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                "branch": "FINBERT" if dl_branch == "FINBERT-TONE" else "LSTM",
                "svc": svc_label,
                "nn": neural_label,
                "ms": wall_ms,
                "svc_ms": svc_result.get("latency_ms", 0),
                "nn_ms": neural_result.get("latency_ms", 0),
                "svc_attempts": svc_result.get("attempts", 0),
                "nn_attempts": neural_result.get("attempts", 0),
            })
            st.session_state.run_log = st.session_state.run_log[-LOG_LEN:]

            p_hot_snap: Optional[float] = None
            if neural_result["ok"] and dl_branch == "FINBERT-TONE":
                probs_snapshot = neural_result["data"].get("probabilities", {})
                p_hot_snap = float(probs_snapshot["hot_rising"] + probs_snapshot["hot_falling"])
            st.session_state.run_history.append({
                "ts": st.session_state.run_log[-1]["ts"],
                "label": st.session_state.run_log[-1]["ts"],
                "p_hot": p_hot_snap,
                "svc_hot": 1 if svc_label == "HOT" else (0 if svc_label == "COLD" else None),
                "nn_hot": 1 if neural_label == "HOT" else (0 if neural_label == "COLD" else None),
            })
            st.session_state.run_history = st.session_state.run_history[-HISTORY_LEN:]

            if svc_result["ok"] and neural_result["ok"]:
                st.toast(f"Inference complete · {wall_ms} ms wall time · req {req_id}", icon="✅")
            elif svc_result["ok"] or neural_result["ok"]:
                st.toast("Partial inference — one endpoint failed", icon="⚠️")
            else:
                st.toast("Both endpoints failed — inspect the telemetry panel", icon="❌")

# ═══════════════════════════════════════════════════════════════════════
# RESULTS
# ═══════════════════════════════════════════════════════════════════════
last = st.session_state.get("last_results")
if last:
    svc_result = last["svc_result"]
    neural_result = last["neural_result"]
    model_code = last["model_code"]
    sigma_str = last["sigma_str"]
    sigma_desc = last["sigma_desc"]
    dl_branch = last["dl_branch"]
    concat_snapshot = last["concatenated_headlines"]
    wires_snapshot = last["wires"]
    wall_ms = last["wall_ms"]
    run_utc = last["run_utc"]
    req_id = last["req_id"]

    st.markdown('<div class="section-label" data-num="04">Cross-Model Classification Agreement</div>', unsafe_allow_html=True)
    if not (svc_result["ok"] and neural_result["ok"]):
        agreement_pct: Optional[float] = None
        verdict_kind, verdict_title = "partial", "⚠ PARTIAL INFERENCE"
        verdict_sub = "At least one endpoint failed. A failed request is not a COLD or negative signal; inspect the endpoint errors below."
    else:
        svc_is_hot = svc_result["val"] == 1
        nn_is_hot = neural_result["val"] == 1
        if svc_is_hot == nn_is_hot:
            agreement_pct = 1.0
            if svc_is_hot:
                if dl_branch == "FINBERT-TONE":
                    probs = neural_result["data"]["probabilities"]
                    if probs["hot_rising"] >= probs["hot_falling"]:
                        verdict_kind, verdict_title = "bull", "CONCORDANT HOT · POSITIVE TONE"
                    else:
                        verdict_kind, verdict_title = "bear", "CONCORDANT HOT · NEGATIVE TONE"
                    verdict_sub = (
                        "Both binary outputs are HOT. The FinBERT probabilities show the relative tone classes; "
                        "sentiment is not a calibrated volatility forecast or proof of future price direction."
                    )
                else:
                    verdict_kind, verdict_title = "hot", "CONCORDANT HOT CLASSIFICATION"
                    verdict_sub = "Both endpoints classify the input as HOT. Agreement is not calibrated confidence and does not guarantee realized volatility."
            else:
                verdict_kind, verdict_title = "cold", "CONCORDANT COLD CLASSIFICATION"
                verdict_sub = "Both endpoints classify the input as COLD. Agreement does not guarantee low future volatility or market stability."
        else:
            agreement_pct = 0.5
            verdict_kind, verdict_title = "split", "DIVERGENT MODEL CLASSIFICATIONS"
            verdict_sub = "The binary outputs disagree. Review source headlines, target definitions and model diagnostics before interpreting the result."

    svc_chip_txt = ("<span class='v-hot'>HOT</span>" if svc_result["val"] == 1 else "<span class='v-cold'>COLD</span>") if svc_result["ok"] else "<span class='v-err'>ERR</span>"
    nn_chip_txt = ("<span class='v-hot'>HOT</span>" if neural_result["val"] == 1 else "<span class='v-cold'>COLD</span>") if neural_result["ok"] else "<span class='v-err'>ERR</span>"

    delta_html = ""
    previous = st.session_state.get("previous_results")
    if previous and previous["svc_result"]["ok"] and previous["neural_result"]["ok"] and svc_result["ok"] and neural_result["ok"]:
        prev_agree = 1.0 if previous["svc_result"]["val"] == previous["neural_result"]["val"] else 0.5
        if agreement_pct is not None and agreement_pct != prev_agree:
            cls = "up" if agreement_pct > prev_agree else "down"
            delta_html = f"<span class='verdict-delta {cls}'>Δ {(agreement_pct-prev_agree)*100:+.0f}% vs prior</span>"
        else:
            delta_html = "<span class='verdict-delta flat'>Δ flat</span>"

    st.markdown(f"""
    <div class="verdict-banner verdict-{verdict_kind}">
      <div>{svg_gauge(agreement_pct, verdict_kind, label="AGREEMENT")}</div>
      <div><div class="verdict-eyebrow">Model output agreement {delta_html}</div>
      <div class="verdict-title">{safe_text(verdict_title)}</div>
      <div class="verdict-sub">{safe_text(verdict_sub)}</div>
      <div class="verdict-meta-row">
        <div><span class="verdict-meta-k">SVC:</span>{svc_chip_txt}</div>
        <div><span class="verdict-meta-k">NEURAL:</span>{nn_chip_txt}</div>
        <div><span class="verdict-meta-k">WALL TIME:</span>{wall_ms} ms</div>
        <div><span class="verdict-meta-k">REQUEST:</span>{safe_text(req_id)}</div>
        <div><span class="verdict-meta-k">RUN UTC:</span>{safe_text(run_utc)}</div>
      </div></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-label" data-num="05">Model Telemetry</div>', unsafe_allow_html=True)
    svc_col, neural_col = st.columns([1, 1.12], gap="large")

    with svc_col:
        if svc_result["ok"]:
            svc_hot = svc_result["val"] == 1
            svc_kind = "hot" if svc_hot else "cold"
            svc_icon = "🔥" if svc_hot else "❄️"
            regime_title = "VOLATILE · HOT" if svc_hot else "STABLE · COLD"
            regime_desc = (
                f"TF-IDF + LinearSVC returned HOT for the selected {sigma_str} threshold."
                if svc_hot else f"TF-IDF + LinearSVC returned COLD for the selected {sigma_str} threshold."
            )
            tokens_html = "".join(
                f'<span class="token weight-{token_weight(token)}">{safe_text(token, 40)}</span>'
                for token in concat_snapshot.split()[:24]
            )
            st.markdown(f"""
            <div class="glass-card regime-{svc_kind}">
              <div class="card-title-row"><div><div class="card-eyebrow">Model 01 · ML baseline</div>
              <div class="card-title">LinearSVC Baseline</div><div class="card-subtitle">TF-IDF + Support Vector Classifier</div></div>
              <div class="latency-pill">{svc_result['latency_ms']} ms</div></div>
              <div class="regime-display {svc_kind}"><div class="regime-icon {svc_kind}">{svc_icon}</div><div class="regime-text-block">
              <div class="regime-label">Predicted regime</div><div class="regime-title {svc_kind}">{regime_title}</div></div></div>
              <div class="hard-badge {svc_kind}"><span class="hard-dot"></span>HARD CLASSIFIER · <span class="hard-val">{svc_kind.upper()}</span></div>
              <p style="color:var(--text-secondary);font-size:12px;line-height:1.55;margin:13px 0 0">{safe_text(regime_desc)}</p>
              <div class="metrics-strip"><div class="metric-cell"><div class="metric-val">{svc_result['val']}</div><div class="metric-lbl">Binary class</div></div>
              <div class="metric-cell"><div class="metric-val">{safe_text(sigma_str)}</div><div class="metric-lbl">Threshold</div></div>
              <div class="metric-cell"><div class="metric-val">{safe_text(model_code)}</div><div class="metric-lbl">Model ID</div></div></div>
              <div class="token-heatmap"><div class="token-heatmap-head"><div class="token-heatmap-label">Token weighting · heuristic only</div>
              <div class="heat-legend">LOW <span class="heat-swatch hs-1"></span><span class="heat-swatch hs-2"></span><span class="heat-swatch hs-3"></span><span class="heat-swatch hs-4"></span><span class="heat-swatch hs-5"></span> HIGH</div></div>
              <div class="token-row">{tokens_html}</div></div>
              <div class="route-tag"><span class="route-method get">GET</span><span>/predict?model_choice={safe_text(model_code)}</span></div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.error(f"LinearSVC endpoint failure: {svc_result.get('error') or 'Unknown error'}")

    with neural_col:
        if neural_result["ok"] and dl_branch == "FINBERT-TONE":
            data = neural_result["data"]
            probs = data["probabilities"]
            p_cold = probs["cold"]
            p_rising = probs["hot_rising"]
            p_falling = probs["hot_falling"]
            p_hot = p_rising + p_falling
            nn_hot = neural_result["val"] == 1
            if nn_hot:
                if p_rising >= p_falling:
                    nn_kind, nn_icon, nn_title = "bull", "▲", "HOT · POSITIVE TONE"
                else:
                    nn_kind, nn_icon, nn_title = "bear", "▼", "HOT · NEGATIVE TONE"
                gauge_value = p_hot
                gauge_label = "P(HOT)"
            else:
                nn_kind, nn_icon, nn_title = "cold", "❄️", "COLD · STABLE TONE"
                gauge_value = p_cold
                gauge_label = "P(COLD)"
            native = safe_text(str(data.get("native_3class", "not supplied")).upper().replace("_", " "), 50)
            cold_pct, rising_pct, falling_pct = p_cold * 100, p_rising * 100, p_falling * 100
            st.markdown(f"""
            <div class="glass-card regime-{nn_kind}">
              <div class="card-title-row"><div><div class="card-eyebrow">Model 02 · Neural</div>
              <div class="card-title">FinBERT-Tone Transformer</div><div class="card-subtitle">yiyanghkust/finbert-tone · 3-class probabilities</div></div>
              <div class="latency-pill">{neural_result['latency_ms']} ms</div></div>
              <div class="regime-display {nn_kind}"><div class="regime-icon {nn_kind}">{nn_icon}</div><div class="regime-text-block">
              <div class="regime-label">API binary label + sentiment distribution</div><div class="regime-title {nn_kind}">{safe_text(nn_title)}</div></div>
              <div>{_gauge_svg(gauge_value, nn_kind, 86, 88, 31, 27, 7.5, gauge_label)}</div></div>
              <div class="spectrum-wrapper"><div class="spectrum-header"><span>3-class softmax</span><span>API dominant: <strong style="color:var(--text-primary)">{native}</strong></span></div>
              <div class="spectrum-bar"><div class="seg-cold" style="width:{cold_pct:.3f}%"></div><div class="seg-rising" style="width:{rising_pct:.3f}%"></div><div class="seg-falling" style="width:{falling_pct:.3f}%"></div></div></div>
              <div class="prob-grid">
                <div class="prob-row"><div class="prob-meta"><span class="prob-name">◆ COLD · NEUTRAL</span><span class="prob-pct">{cold_pct:.2f}%</span></div><div class="prob-track"><div class="prob-fill prob-fill-cold" style="width:{cold_pct:.3f}%"></div></div></div>
                <div class="prob-row"><div class="prob-meta"><span class="prob-name">▲ POSITIVE TONE</span><span class="prob-pct">{rising_pct:.2f}%</span></div><div class="prob-track"><div class="prob-fill prob-fill-bull" style="width:{rising_pct:.3f}%"></div></div></div>
                <div class="prob-row"><div class="prob-meta"><span class="prob-name">▼ NEGATIVE TONE</span><span class="prob-pct">{falling_pct:.2f}%</span></div><div class="prob-track"><div class="prob-fill prob-fill-bear" style="width:{falling_pct:.3f}%"></div></div></div>
              </div>
              <p style="color:var(--text-tertiary);font-size:11px;line-height:1.55;margin:13px 0 0">Probability values are model outputs, not necessarily calibrated. Positive/negative tone is not a direct forecast of returns or volatility.</p>
              <div class="route-tag"><span class="route-method post">POST</span><span>/dl_predict</span></div>
            </div>
            """, unsafe_allow_html=True)
        elif neural_result["ok"]:
            nn_hot = neural_result["val"] == 1
            nn_kind = "hot" if nn_hot else "cold"
            nn_icon = "🔥" if nn_hot else "❄️"
            nn_title = "EVENT-DRIVEN VOLATILITY" if nn_hot else "QUIET TAPE"
            nn_desc = (
                "Frozen Word2Vec embeddings feed the LSTM binary classifier; this result is a hard label, not a probability."
                if nn_hot else "The LSTM returned its COLD binary label. This is not a guarantee of low future volatility."
            )
            st.markdown(f"""
            <div class="glass-card regime-{nn_kind}">
              <div class="card-title-row"><div><div class="card-eyebrow">Model 02 · Neural</div>
              <div class="card-title">LSTM · Frozen Word2Vec</div><div class="card-subtitle">best_lstm_it13_w2v_frozen · binary head</div></div>
              <div class="latency-pill">{neural_result['latency_ms']} ms</div></div>
              <div class="regime-display {nn_kind}"><div class="regime-icon {nn_kind}">{nn_icon}</div><div class="regime-text-block">
              <div class="regime-label">Predicted regime</div><div class="regime-title {nn_kind}">{safe_text(nn_title)}</div></div></div>
              <div class="hard-badge {nn_kind}"><span class="hard-dot"></span>HARD CLASSIFIER · <span class="hard-val">{nn_kind.upper()}</span></div>
              <p style="color:var(--text-secondary);font-size:12px;line-height:1.55;margin:13px 0 0">{safe_text(nn_desc)}</p>
              <table class="meta-table"><tr><td>EMBEDDINGS</td><td>Word2Vec · frozen</td></tr><tr><td>ENCODER</td><td>LSTM recurrent stack</td></tr><tr><td>OUTPUT HEAD</td><td>Binary hard label</td></tr><tr><td>ROUTING</td><td>SVC service · model_choice=7</td></tr></table>
              <div class="route-tag"><span class="route-method get">GET</span><span>/predict?model_choice=7</span></div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.error(f"Neural endpoint failure: {neural_result.get('error') or 'Unknown error'}")

    st.caption(
        "Interpretation guardrail: only treat the two binary labels as directly comparable if both endpoints were trained and evaluated against the same HOT/COLD target. FinBERT's 3-class tone distribution by itself is a sentiment output, not a volatility forecast."
    )

    # Probability trend: keep only runs where numeric FinBERT probabilities exist.
    probability_history = [item for item in st.session_state.get("run_history", []) if item.get("p_hot") is not None]
    if len(probability_history) >= 2:
        st.markdown('<div class="section-label" data-num="05B">Probability Trend</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="card-eyebrow">P(HOT) derived from FinBERT tone classes · last {len(probability_history)} successful runs</div>', unsafe_allow_html=True)
        try:
            import pandas as pd
            trend_df = pd.DataFrame([{"run": item["label"], "P(HOT)": item["p_hot"]} for item in probability_history])
            st.line_chart(trend_df.set_index("run"), height=180)
        except Exception:
            st.caption("Trend chart unavailable in this environment.")

    # Export report uses immutable run snapshots (not whatever the user edits later).
    report = {
        "session": st.session_state.sid,
        "request_id": req_id,
        "timestamp_utc": run_utc,
        "elapsed_wall_ms": wall_ms,
        "config": {"svc_threshold": sigma_str, "model_choice": model_code, "neural_branch": dl_branch},
        "inputs": {"headlines": last["headlines"], "summary": last["summary"]},
        "svc_result": {key: svc_result.get(key) for key in ("ok", "val", "latency_ms", "last_attempt_latency_ms", "error", "data", "attempts", "status")},
        "neural_result": {key: neural_result.get(key) for key in ("ok", "val", "latency_ms", "last_attempt_latency_ms", "error", "data", "branch", "attempts", "status")},
        "interpretation_note": "Binary agreement is not calibrated confidence. Verify both model binary labels target the same construct before interpreting consensus.",
    }
    report_json = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)
    export_cols = st.columns([3.2, 1.35, 1.15])
    with export_cols[1]:
        st.download_button(
            "⬇ Export JSON", type="secondary", use_container_width=True,
            data=report_json,
            file_name=f"sentinel_{st.session_state.sid}_{datetime.now(timezone.utc).strftime('%H%M%S')}.json",
            mime="application/json",
        )
    with export_cols[2]:
        with st.popover("Inspect report", use_container_width=True):
            st.code(report_json, language="json")

    with st.expander("🔍 INSPECT RAW API TELEMETRY & INGEST MANIFEST"):
        raw_a, raw_b = st.columns(2)
        with raw_a:
            st.caption("GET /predict — LinearSVC baseline (SVC_API_URL)")
            if svc_result["ok"]:
                st.json({
                    "route": "/predict", "latency_ms": svc_result["latency_ms"],
                    "last_attempt_latency_ms": svc_result.get("last_attempt_latency_ms"),
                    "attempts": svc_result.get("attempts"), "model_choice": model_code,
                    "headline_preview": concat_snapshot[:200] + ("…" if len(concat_snapshot) > 200 else ""),
                    "prediction": svc_result["val"],
                })
            else:
                st.error(svc_result.get("error") or "Unknown error")
        with raw_b:
            if dl_branch == "FINBERT-TONE":
                st.caption("POST /dl_predict — FinBERT-Tone (FINBERT_API_URL)")
                if neural_result["ok"]:
                    st.json({"route": "/dl_predict", "latency_ms": neural_result["latency_ms"],
                             "last_attempt_latency_ms": neural_result.get("last_attempt_latency_ms"),
                             "attempts": neural_result.get("attempts"), "response_payload": neural_result["data"]})
                else:
                    st.error(neural_result.get("error") or "Unknown error")
            else:
                st.caption("GET /predict — LSTM-W2V, model_choice=7 (SVC_API_URL)")
                if neural_result["ok"]:
                    st.json({"route": "/predict", "latency_ms": neural_result["latency_ms"],
                             "last_attempt_latency_ms": neural_result.get("last_attempt_latency_ms"),
                             "attempts": neural_result.get("attempts"), "model_choice": LSTM_MODEL_CODE,
                             "prediction": neural_result["val"]})
                else:
                    st.error(neural_result.get("error") or "Unknown error")
        st.caption("Headline ingest manifest")
        manifest_rows = "".join(
            f"<tr><td>W{index+1:02d}</td><td>{safe_text(headline[:96])}{'…' if len(headline)>96 else ''}</td><td>{len(headline)} ch</td></tr>"
            for index, headline in wires_snapshot
        )
        st.markdown(f'<table class="manifest">{manifest_rows}</table>', unsafe_allow_html=True)

    if st.session_state.run_log:
        st.markdown('<div class="section-label" data-num="06">Signal Log</div>', unsafe_allow_html=True)
        log_rows = ""
        for entry in reversed(st.session_state.run_log[-6:]):
            svc_class = {"HOT": "v-hot", "COLD": "v-cold"}.get(entry["svc"], "v-err")
            nn_class = {"HOT": "v-hot", "COLD": "v-cold"}.get(entry["nn"], "v-err")
            retry_note = ""
            if entry.get("svc_attempts", 0) > 1 or entry.get("nn_attempts", 0) > 1:
                retry_note = f" ↻{max(entry.get('svc_attempts', 0), entry.get('nn_attempts', 0))}"
            log_rows += (
                f"<tr><td>{safe_text(entry['ts'])} UTC</td><td>{safe_text(entry['branch'])}</td>"
                f"<td class='{svc_class}'>{safe_text(entry['svc'])}</td><td class='{nn_class}'>{safe_text(entry['nn'])}</td>"
                f"<td>{entry['ms']} ms{retry_note}</td><td>{entry.get('svc_ms', 0)}/{entry.get('nn_ms', 0)} ms</td></tr>"
            )
        st.markdown(
            f'<table class="log-table"><tr><th>Time</th><th>Neural</th><th>SVC</th><th>Neural output</th><th>Wall time</th><th>Endpoint ms</th></tr>{log_rows}</table>',
            unsafe_allow_html=True,
        )
        st.button("Clear signal log", type="secondary", on_click=clear_log)

elif not predict_clicked:
    st.markdown('''<div class="empty-state"><div class="empty-icon">🎯</div><div class="empty-title">Ready when you are</div><div class="empty-desc">Select a synthetic scenario or enter your own headlines, then execute Dual Inference to dispatch both model calls concurrently.</div></div>''', unsafe_allow_html=True)

st.markdown(f"""
<div class="footnote"><span class="footnote-brand">HEADLINES HEAT PREDICTION</span> · Financial News Signal Lab · build 5.0.0 · session {safe_text(st.session_state.sid)}<br>
Inference endpoints are loaded from Streamlit secrets · market quotes are Yahoo Finance snapshots when available or clearly labeled demo placeholders · research signals only, not investment advice
</div>
""", unsafe_allow_html=True)

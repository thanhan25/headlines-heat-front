import csv
import html
import io
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from string import Template
from typing import Any, Optional

import requests
import streamlit as st

# ═══════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════
MAX_WIRES = 21
MAX_CHARS = 12_000
RETRY_ATTEMPTS = 2
RETRY_BACKOFF_S = 0.5
CIRCUIT_COOLDOWN_S = 30
PING_TTL_S = 120
HISTORY_LEN = 20
LOG_LEN = 12

st.set_page_config(
    page_title="SENTINEL // Market Regime & Sentiment Terminal",
    page_icon="◉",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ═══════════════════════════════════════════════════════════════════
#  THEME SYSTEM
# ═══════════════════════════════════════════════════════════════════
st.session_state.setdefault("theme", "dark")


def toggle_theme() -> None:
    st.session_state.theme = "light" if st.session_state.theme == "dark" else "dark"


DARK_TOKENS = """
    --bg-base:#07090E; --bg-panel:rgba(13,17,26,.85); --bg-card:rgba(17,22,34,.72);
    --bg-card-solid:#111622; --bg-input:rgba(9,12,20,.85); --bg-elevated:rgba(22,28,42,.6);
    --border-subtle:rgba(30,38,56,.9); --border-active:rgba(59,130,246,.5); --border-focus:#3B82F6;
    --text-primary:#F1F5F9; --text-secondary:#CBD5E1; --text-tertiary:#94A3B8;
    --text-muted:#7C8BA1; --text-faint:#566274;
    --emerald:#10B981; --rose:#F43F5E; --amber:#F59E0B; --cyan:#38BDF8; --cobalt:#3B82F6;
    --emerald-glow:rgba(16,185,129,.14); --rose-glow:rgba(244,63,94,.14);
    --amber-glow:rgba(245,158,11,.14); --cyan-glow:rgba(56,189,248,.14);
    --gradient-accent:linear-gradient(135deg,#3B82F6 0%,#8B5CF6 100%);
    --gradient-hot:linear-gradient(135deg,#FB7185 0%,#E11D48 100%);
    --gradient-cold:linear-gradient(135deg,#38BDF8 0%,#0284C7 100%);
    --gradient-bull:linear-gradient(135deg,#34D399 0%,#059669 100%);
    --gradient-bear:linear-gradient(135deg,#F87171 0%,#DC2626 100%);
    --heat-5:rgba(245,158,11,.34); --heat-4:rgba(245,158,11,.22); --heat-3:rgba(245,158,11,.12); --heat-2:rgba(148,163,184,.10);
    --heat-cold-5:rgba(56,189,248,.32); --heat-cold-4:rgba(56,189,248,.20); --heat-cold-3:rgba(56,189,248,.10);
    --shadow-sm:0 1px 2px rgba(0,0,0,.3); --shadow-md:0 4px 16px rgba(0,0,0,.35); --shadow-lg:0 20px 40px rgba(0,0,0,.45);
    --noise-opacity:.25;
"""

LIGHT_TOKENS = """
    --bg-base:#F5F7FA; --bg-panel:#FFFFFF; --bg-card:#FFFFFF;
    --bg-card-solid:#FFFFFF; --bg-input:#FFFFFF; --bg-elevated:#F1F5F9;
    --border-subtle:#D7DFE9; --border-active:rgba(37,99,235,.45); --border-focus:#2563EB;
    --text-primary:#0B1220; --text-secondary:#293648; --text-tertiary:#46566B;
    --text-muted:#5C6B80; --text-faint:#8494A7;
    --emerald:#047857; --rose:#BE123C; --amber:#B45309; --cyan:#0369A1; --cobalt:#2563EB;
    --emerald-glow:rgba(4,120,87,.10); --rose-glow:rgba(190,18,60,.09);
    --amber-glow:rgba(180,83,9,.12); --cyan-glow:rgba(3,105,161,.10);
    --gradient-accent:linear-gradient(135deg,#2563EB 0%,#7C3AED 100%);
    --gradient-hot:linear-gradient(135deg,#F43F5E 0%,#BE123C 100%);
    --gradient-cold:linear-gradient(135deg,#0EA5E9 0%,#0369A1 100%);
    --gradient-bull:linear-gradient(135deg,#10B981 0%,#047857 100%);
    --gradient-bear:linear-gradient(135deg,#F43F5E 0%,#B91C1C 100%);
    --heat-5:rgba(180,83,9,.18); --heat-4:rgba(180,83,9,.12); --heat-3:rgba(180,83,9,.07); --heat-2:rgba(100,116,139,.08);
    --heat-cold-5:rgba(3,105,161,.16); --heat-cold-4:rgba(3,105,161,.11); --heat-cold-3:rgba(3,105,161,.06);
    --shadow-sm:0 1px 2px rgba(15,23,42,.06);
    --shadow-md:0 2px 6px rgba(15,23,42,.05), 0 12px 28px rgba(15,23,42,.08);
    --shadow-lg:0 8px 20px rgba(15,23,42,.08), 0 24px 48px rgba(15,23,42,.10);
    --noise-opacity:0;
"""

DARK_LITERAL = dict(
    bg="#07090E", panel="#0D111A", card="#111622", input_bg="#0B0F16", elevated="#161C2A",
    border="#1E2638", border_active="rgba(59,130,246,.55)", focus="#3B82F6", ring="rgba(59,130,246,.25)",
    text1="#F1F5F9", text2="#CBD5E1", text3="#94A3B8", muted="#7C8BA1", placeholder="#566274",
    btn2_bg="#141A28", btn2_fg="#CBD5E1", btn2_border="#232C40", btn2_hover="#1B2334",
    prim_grad="linear-gradient(135deg,#3B82F6 0%,#8B5CF6 100%)",
    prim_shadow="0 6px 20px rgba(59,130,246,.28)", prim_shadow_hover="0 10px 28px rgba(59,130,246,.40)",
    shadow_sm="0 1px 2px rgba(0,0,0,.3)", shadow_md="0 4px 16px rgba(0,0,0,.35)",
    cobalt="#3B82F6",
    grads={"hot": ("#FB7185", "#E11D48"), "cold": ("#38BDF8", "#0284C7"),
           "bull": ("#34D399", "#059669"), "bear": ("#F87171", "#DC2626"),
           "accent": ("#3B82F6", "#8B5CF6")},
)

LIGHT_LITERAL = dict(
    bg="#F5F7FA", panel="#FFFFFF", card="#FFFFFF", input_bg="#FFFFFF", elevated="#F1F5F9",
    border="#D7DFE9", border_active="rgba(37,99,235,.50)", focus="#2563EB", ring="rgba(37,99,235,.16)",
    text1="#0B1220", text2="#293648", text3="#46566B", muted="#5C6B80", placeholder="#8494A7",
    btn2_bg="#FFFFFF", btn2_fg="#33415C", btn2_border="#CBD5E1", btn2_hover="#EEF2F7",
    prim_grad="linear-gradient(135deg,#2563EB 0%,#7C3AED 100%)",
    prim_shadow="0 6px 20px rgba(37,99,235,.25)", prim_shadow_hover="0 10px 28px rgba(37,99,235,.35)",
    shadow_sm="0 1px 2px rgba(15,23,42,.06)", shadow_md="0 2px 6px rgba(15,23,42,.05), 0 12px 28px rgba(15,23,42,.08)",
    cobalt="#2563EB",
    grads={"hot": ("#F43F5E", "#BE123C"), "cold": ("#0EA5E9", "#0369A1"),
           "bull": ("#10B981", "#047857"), "bear": ("#F43F5E", "#B91C1C"),
           "accent": ("#2563EB", "#7C3AED")},
)

is_dark = st.session_state.theme == "dark"
THEME = DARK_LITERAL if is_dark else LIGHT_LITERAL

st.markdown(f"""
<style>
:root, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMainFrame"], section.main {{
    {DARK_TOKENS if is_dark else LIGHT_TOKENS}
}}
:root {{ color-scheme: {"dark" if is_dark else "light"}; }}
</style>
""", unsafe_allow_html=True)

OVERRIDE_CSS = Template("""
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMainFrame"] {
    background-color: $bg !important; color: $text1 !important;
}
input[type="text"], input[type="number"], input:not([type]), textarea {
    background-color: $input_bg !important; color: $text1 !important;
    border: 1px solid $border !important; border-radius: 9px !important;
    font-size: 13.5px !important; padding: 12px 15px !important;
    font-family: 'Inter', sans-serif !important;
}
input::placeholder, textarea::placeholder { color: $placeholder !important; opacity: 1 !important; }
input:focus, textarea:focus { border-color: $focus !important; box-shadow: 0 0 0 3px $ring !important; outline: none !important; }
div[data-baseweb="select"] > div { background-color: $input_bg !important; border: 1px solid $border !important; border-radius: 9px !important; box-shadow: none !important; }
div[data-baseweb="select"], div[data-baseweb="select"] span { color: $text1 !important; }
div[data-baseweb="select"] svg { color: $muted !important; }
[role="listbox"] { background-color: $card !important; border: 1px solid $border !important; border-radius: 10px !important; box-shadow: $shadow_md !important; }
[role="option"] { color: $text1 !important; background-color: transparent !important; }
[role="option"]:hover, [role="option"][aria-selected="true"] { background-color: $elevated !important; }
label, .stTextInput label, .stTextArea label, .stSelectbox label {
    color: $text3 !important; font-family: 'JetBrains Mono', monospace !important;
    font-weight: 600 !important; font-size: 10.5px !important;
    text-transform: uppercase !important; letter-spacing: .1em !important;
}
small, .stCaption, [data-testid="stCaption"] { color: $muted !important; }
[data-testid="stToggle"] label, [data-testid="stToggle"] label p, [data-testid="stToggle"] label span {
    color: $text2 !important; font-family: 'JetBrains Mono', monospace !important; font-size: 11px !important;
}
.stButton > button {
    border-radius: 9px !important; font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important; font-size: 13px !important; padding: 12px 20px !important;
    transition: all .22s ease !important;
}
.stButton > button p, .stButton > button span { color: inherit !important; }
.stButton > button[kind="primary"] {
    background: $prim_grad !important; color: #FFFFFF !important;
    border: none !important; box-shadow: $prim_shadow !important;
}
.stButton > button[kind="primary"]:hover { box-shadow: $prim_shadow_hover !important; transform: translateY(-1px) !important; }
.stButton > button[kind="secondary"], .stButton > button:not([kind="primary"]) {
    background-color: $btn2_bg !important; color: $btn2_fg !important;
    border: 1px solid $btn2_border !important; box-shadow: $shadow_sm !important;
}
.stButton > button[kind="secondary"]:hover, .stButton > button:not([kind="primary"]):hover {
    background-color: $btn2_hover !important; color: $text1 !important; border-color: $border_active !important;
}
[data-testid="stExpander"] details { background-color: $card !important; border: 1px solid $border !important; border-radius: 12px !important; }
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary p, [data-testid="stExpander"] summary span { color: $text1 !important; }
[data-testid="stExpander"] svg { color: $muted !important; }
[data-testid="stJson"] { background-color: $elevated !important; border-radius: 10px !important; }
[data-testid="stJson"] div, [data-testid="stJson"] span { color: $text2 !important; }
pre, code { background-color: $elevated !important; color: $text2 !important; }
[data-testid="stVerticalBlockBorderWrapper"] {
    background-color: $panel !important; border: 1px solid $border !important;
    border-radius: 14px !important; box-shadow: $shadow_sm !important; padding: 20px 22px !important;
}
.stSpinner > div { border-top-color: $cobalt !important; }
hr { background-color: $border !important; }
/* Reduced-motion + a11y */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation-duration: .001s !important; transition-duration: .001s !important; }
}
""")
st.markdown(f"<style>{OVERRIDE_CSS.substitute(THEME)}</style>", unsafe_allow_html=True)

# ── Master stylesheet ──
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&family=Instrument+Serif:ital@0;1&display=swap');

html, body, .stApp { font-family: 'Inter', -apple-system, sans-serif; -webkit-font-smoothing: antialiased; }
.stApp::before {
    content: ""; position: fixed; inset: 0; z-index: -2; pointer-events: none;
    background-image:
        radial-gradient(ellipse 80% 60% at 20% 0%, rgba(59,130,246,.06), transparent 60%),
        radial-gradient(ellipse 60% 50% at 80% 100%, rgba(139,92,246,.05), transparent 60%);
}
.stApp::after {
    content: ""; position: fixed; inset: 0; z-index: -1; pointer-events: none;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.4'/%3E%3C/svg%3E");
    opacity: var(--noise-opacity);
}
.main .block-container { padding-top: 1.25rem; padding-bottom: 3rem; max-width: 1440px; }
header, #MainMenu, footer { visibility: hidden; }
[data-testid="stHeader"] { background: transparent !important; }
* { font-variant-numeric: tabular-nums; }

@keyframes tickerScroll { 0% {transform:translateX(0);} 100% {transform:translateX(-50%);} }
@keyframes pulseGlow { 0%,100% {opacity:.55; transform:scale(1);} 50% {opacity:1; transform:scale(1.15);} }
@keyframes shimmer { 0% {background-position:200% 0;} 100% {background-position:-200% 0;} }
@keyframes gradientFlow { 0%,100% {background-position:0% 50%;} 50% {background-position:100% 50%;} }
@keyframes fadeInScale { from {opacity:0; transform:scale(.97);} to {opacity:1; transform:scale(1);} }
@keyframes slideDown { from {opacity:0; transform:translateY(-8px);} to {opacity:1; transform:translateY(0);} }
@keyframes pulseDot { 0%,100% {transform:scale(1); opacity:.7;} 50% {transform:scale(1.4); opacity:1;} }

.topbar {
    display: flex; justify-content: space-between; align-items: center; gap: 16px;
    padding: 14px 22px; background: var(--bg-panel); backdrop-filter: blur(20px) saturate(180%);
    border: 1px solid var(--border-subtle); border-radius: 10px; margin-bottom: 18px;
    box-shadow: var(--shadow-sm);
}
.topbar-left { display: flex; align-items: center; gap: 14px; }
.brand-mark {
    width: 34px; height: 34px; border-radius: 9px; background: var(--gradient-accent);
    display: flex; align-items: center; justify-content: center;
    font-family: 'Instrument Serif', serif; font-size: 18px; font-style: italic; color: #FFFFFF;
    box-shadow: 0 4px 14px rgba(59,130,246,.3); position: relative;
}
.brand-mark::after { content: ""; position: absolute; inset: -3px; border-radius: 12px; background: var(--gradient-accent); filter: blur(14px); opacity: .45; z-index: -1; }
.brand-title { font-size: 14px; font-weight: 700; letter-spacing: -.02em; color: var(--text-primary); }
.brand-tag { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--text-muted); letter-spacing: .12em; text-transform: uppercase; margin-top: 1px; }
.topbar-right { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.chip {
    display: inline-flex; align-items: center; gap: 7px; padding: 5px 12px; border-radius: 20px;
    font-family: 'JetBrains Mono', monospace; font-size: 10.5px; font-weight: 600; letter-spacing: .05em;
    border: 1px solid;
}
.chip.ok  { color: var(--emerald); background: var(--emerald-glow); border-color: var(--border-subtle); }
.chip.bad { color: var(--rose);    background: var(--rose-glow);    border-color: var(--border-subtle); }
.chip.unk { color: var(--text-muted); background: var(--bg-elevated); border-color: var(--border-subtle); }
.chip-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; box-shadow: 0 0 6px currentColor; animation: pulseGlow 1.8s infinite; }

.ticker-wrap { background: var(--bg-panel); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 8px 0; margin-bottom: 24px; overflow: hidden; position: relative; box-shadow: var(--shadow-sm); }
.ticker-wrap::before, .ticker-wrap::after { content: ""; position: absolute; top: 0; bottom: 0; width: 100px; z-index: 2; pointer-events: none; }
.ticker-wrap::before { left: 0; background: linear-gradient(90deg, var(--bg-panel) 0%, transparent 100%); }
.ticker-wrap::after { right: 0; background: linear-gradient(-90deg, var(--bg-panel) 0%, transparent 100%); }
.ticker-track { display: flex; white-space: nowrap; animation: tickerScroll 80s linear infinite; width: fit-content; }
.ticker-item { display: inline-flex; align-items: center; gap: 8px; padding: 0 22px; font-family: 'JetBrains Mono', monospace; font-size: 11.5px; color: var(--text-secondary); border-right: 1px solid var(--border-subtle); }
.ticker-sym { color: var(--text-primary); font-weight: 600; letter-spacing: .04em; font-size: 11px; }
.ticker-price { color: var(--text-tertiary); }
.ticker-up { color: var(--emerald); font-weight: 600; }
.ticker-down { color: var(--rose); font-weight: 600; }

.hero-stack { display: flex; justify-content: space-between; align-items: flex-end; padding: 8px 4px 32px 4px; gap: 28px; flex-wrap: wrap; }
.hero-title { font-size: clamp(2rem, 3.8vw, 2.85rem); font-weight: 800; letter-spacing: -.035em; line-height: 1.05; margin: 0 0 14px 0; color: var(--text-primary); }
.hero-title .accent {
    font-family: 'Instrument Serif', serif; font-style: italic; font-weight: 400;
    background: var(--gradient-accent); background-size: 200% 200%;
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
    animation: gradientFlow 6s ease infinite; font-size: 1.05em;
}
.hero-sub { font-size: 1rem; color: var(--text-secondary); max-width: 640px; line-height: 1.6; margin: 0; }
.hero-specs { display: grid; grid-template-columns: repeat(3, auto); gap: 14px; background: var(--bg-panel); border: 1px solid var(--border-subtle); padding: 14px 20px; border-radius: 10px; box-shadow: var(--shadow-sm); }
.spec-cell { display: flex; flex-direction: column; padding: 0 12px; border-right: 1px solid var(--border-subtle); }
.spec-cell:last-child { border-right: none; }
.spec-lbl { font-family: 'JetBrains Mono', monospace; font-size: 9.5px; text-transform: uppercase; letter-spacing: .12em; color: var(--text-muted); margin-bottom: 3px; font-weight: 600; }
.spec-val { font-family: 'JetBrains Mono', monospace; font-size: 12.5px; color: var(--text-primary); font-weight: 700; }

.section-label { display: flex; align-items: center; gap: 12px; font-family: 'JetBrains Mono', monospace; font-size: 10.5px; color: var(--text-muted); text-transform: uppercase; letter-spacing: .18em; font-weight: 700; margin: 8px 0 16px 0; }
.section-label::before { content: ""; width: 24px; height: 1px; background: var(--gradient-accent); }
.section-label::after { content: attr(data-num); font-size: 9px; padding: 2px 7px; border-radius: 3px; background: var(--bg-elevated); color: var(--cobalt); border: 1px solid var(--border-subtle); margin-left: auto; }

.preset-note { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: .12em; text-transform: uppercase; font-weight: 700; margin: 10px 2px 0 2px; }
.preset-note.bull { color: var(--emerald); }
.preset-note.bear { color: var(--rose); }
.preset-note.neutral { color: var(--cyan); }
.preset-hint { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--text-muted); margin: 10px 0 26px 4px; }

.verdict-banner {
    background: var(--bg-card); backdrop-filter: blur(24px) saturate(180%);
    border: 1px solid var(--border-subtle); border-radius: 16px; padding: 28px 32px; margin-bottom: 24px;
    display: grid; grid-template-columns: auto 1fr; gap: 28px; align-items: center;
    position: relative; overflow: hidden; box-shadow: var(--shadow-lg);
    animation: slideDown .5s cubic-bezier(.4,0,.2,1);
}
.verdict-banner::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; }
.verdict-banner.verdict-hot  { background: linear-gradient(135deg, var(--amber-glow), var(--bg-card) 70%);  border-color: rgba(245,158,11,.35); }
.verdict-banner.verdict-hot::before  { background: var(--gradient-hot); }
.verdict-banner.verdict-cold { background: linear-gradient(135deg, var(--cyan-glow), var(--bg-card) 70%);  border-color: rgba(56,189,248,.35); }
.verdict-banner.verdict-cold::before { background: var(--gradient-cold); }
.verdict-banner.verdict-bull { background: linear-gradient(135deg, var(--emerald-glow), var(--bg-card) 70%); border-color: rgba(16,185,129,.35); }
.verdict-banner.verdict-bull::before { background: var(--gradient-bull); }
.verdict-banner.verdict-bear { background: linear-gradient(135deg, var(--rose-glow), var(--bg-card) 70%);  border-color: rgba(244,63,94,.35); }
.verdict-banner.verdict-bear::before { background: var(--gradient-bear); }
.verdict-banner.verdict-split { background: linear-gradient(135deg, rgba(148,163,184,.10), var(--bg-card) 70%); border-color: rgba(148,163,184,.35); }
.verdict-banner.verdict-split::before { background: linear-gradient(90deg, var(--cyan), var(--amber), var(--rose)); }
.verdict-banner.verdict-partial { background: linear-gradient(135deg, rgba(244,63,94,.08), var(--bg-card) 70%); border-color: rgba(244,63,94,.30); }
.verdict-banner.verdict-partial::before { background: var(--gradient-bear); }
.verdict-eyebrow { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: .15em; font-weight: 700; margin-bottom: 6px; }
.verdict-title { font-size: 1.65rem; font-weight: 800; letter-spacing: -.025em; margin: 0 0 6px 0; line-height: 1.15; color: var(--text-primary); }
.verdict-sub { font-size: .95rem; color: var(--text-secondary); margin: 0; line-height: 1.5; }
.verdict-meta-row { display: flex; gap: 18px; margin-top: 14px; font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--text-muted); flex-wrap: wrap; align-items: center; }
.verdict-meta-k { color: var(--text-tertiary); margin-right: 5px; font-weight: 600; }
.verdict-delta { font-family: 'JetBrains Mono', monospace; font-size: 10px; padding: 2px 7px; border-radius: 3px; margin-left: 6px; }
.verdict-delta.up   { background: var(--emerald-glow); color: var(--emerald); }
.verdict-delta.down { background: var(--rose-glow); color: var(--rose); }
.verdict-delta.flat { background: var(--bg-elevated); color: var(--text-muted); }
.v-hot { color: var(--amber); font-weight: 700; } .v-cold { color: var(--cyan); font-weight: 700; }
.v-bull { color: var(--emerald); font-weight: 700; } .v-bear { color: var(--rose); font-weight: 700; }
.v-err { color: var(--rose); font-weight: 600; }
.v-na  { color: var(--text-faint); font-weight: 600; }

.glass-card {
    background: var(--bg-card); backdrop-filter: blur(24px) saturate(180%);
    border: 1px solid var(--border-subtle); border-radius: 16px; padding: 26px;
    position: relative; overflow: hidden; box-shadow: var(--shadow-md);
    animation: fadeInScale .5s cubic-bezier(.4,0,.2,1) backwards; height: 100%;
}
.glass-card.regime-hot  { border-color: rgba(245,158,11,.30); background: linear-gradient(160deg, var(--amber-glow), var(--bg-card) 45%); }
.glass-card.regime-cold { border-color: rgba(56,189,248,.30); background: linear-gradient(160deg, var(--cyan-glow), var(--bg-card) 45%); }
.glass-card.regime-bull { border-color: rgba(16,185,129,.30); background: linear-gradient(160deg, var(--emerald-glow), var(--bg-card) 45%); }
.glass-card.regime-bear { border-color: rgba(244,63,94,.30);  background: linear-gradient(160deg, var(--rose-glow), var(--bg-card) 45%); }
.card-eyebrow { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: .15em; margin-bottom: 6px; font-weight: 700; }
.card-title-row { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 18px; padding-bottom: 18px; border-bottom: 1px solid var(--border-subtle); }
.card-title { font-size: 1.15rem; font-weight: 700; color: var(--text-primary); letter-spacing: -.02em; margin: 0; }
.card-subtitle { font-size: 11.5px; color: var(--text-muted); font-family: 'JetBrains Mono', monospace; margin-top: 3px; }
.latency-pill { font-family: 'JetBrains Mono', monospace; font-size: 11px; padding: 5px 11px; border-radius: 20px; background: var(--bg-elevated); color: var(--cobalt); border: 1px solid var(--border-subtle); font-weight: 600; white-space: nowrap; }

.regime-display { background: var(--bg-elevated); border: 1px solid var(--border-subtle); border-radius: 12px; padding: 22px; margin: 18px 0; display: flex; align-items: center; gap: 18px; }
.regime-display.hot  { background: linear-gradient(135deg, var(--amber-glow), var(--bg-elevated) 80%);  border-color: rgba(245,158,11,.30); }
.regime-display.cold { background: linear-gradient(135deg, var(--cyan-glow), var(--bg-elevated) 80%);  border-color: rgba(56,189,248,.30); }
.regime-display.bull { background: linear-gradient(135deg, var(--emerald-glow), var(--bg-elevated) 80%); border-color: rgba(16,185,129,.30); }
.regime-display.bear { background: linear-gradient(135deg, var(--rose-glow), var(--bg-elevated) 80%);  border-color: rgba(244,63,94,.30); }
.regime-icon { width: 54px; height: 54px; border-radius: 13px; display: flex; align-items: center; justify-content: center; font-size: 26px; flex-shrink: 0; color: #FFFFFF; }
.regime-icon.hot  { background: var(--gradient-hot);  box-shadow: 0 8px 24px rgba(245,158,11,.30); }
.regime-icon.cold { background: var(--gradient-cold); box-shadow: 0 8px 24px rgba(56,189,248,.30); }
.regime-icon.bull { background: var(--gradient-bull); box-shadow: 0 8px 24px rgba(16,185,129,.30); }
.regime-icon.bear { background: var(--gradient-bear); box-shadow: 0 8px 24px rgba(244,63,94,.30); }
.regime-text-block { flex: 1; }
.regime-label { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: .12em; margin-bottom: 4px; font-weight: 700; }
.regime-title { font-size: 1.2rem; font-weight: 800; letter-spacing: -.02em; margin: 0; }
.regime-title.hot { color: var(--amber); } .regime-title.cold { color: var(--cyan); }
.regime-title.bull { color: var(--emerald); } .regime-title.bear { color: var(--rose); }
.regime-title.na   { color: var(--text-faint); }
.gauge-wrap { display: flex; flex-direction: column; align-items: center; flex-shrink: 0; }

.metrics-strip { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 18px; padding-top: 18px; border-top: 1px solid var(--border-subtle); }
.metric-cell { background: var(--bg-elevated); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 11px 13px; text-align: center; }
.metric-val { font-family: 'JetBrains Mono', monospace; font-size: 1.05rem; font-weight: 700; color: var(--text-primary); }
.metric-lbl { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: var(--text-muted); text-transform: uppercase; letter-spacing: .1em; margin-top: 2px; font-weight: 600; }

.prob-grid { display: flex; flex-direction: column; gap: 12px; margin-top: 18px; }
.prob-row { background: var(--bg-elevated); border: 1px solid var(--border-subtle); border-radius: 9px; padding: 11px 14px; }
.prob-meta { display: flex; justify-content: space-between; align-items: center; margin-bottom: 7px; font-family: 'JetBrains Mono', monospace; font-size: 11.5px; }
.prob-name { color: var(--text-tertiary); font-weight: 500; }
.prob-pct { color: var(--text-primary); font-weight: 700; font-size: 13px; }
.prob-track { width: 100%; height: 5px; background: var(--bg-input); border: 1px solid var(--border-subtle); border-radius: 3px; overflow: hidden; }
.prob-fill { height: 100%; border-radius: 3px; transition: width 1s cubic-bezier(.4,0,.2,1); }
.prob-fill-cold { background: var(--gradient-cold); } .prob-fill-bull { background: var(--gradient-bull); } .prob-fill-bear { background: var(--gradient-bear); }

.spectrum-wrapper { margin: 18px 0; }
.spectrum-header { display: flex; justify-content: space-between; font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: .1em; margin-bottom: 8px; font-weight: 600; }
.spectrum-bar { display: flex; height: 10px; width: 100%; background: var(--bg-input); border-radius: 5px; overflow: hidden; gap: 1px; border: 1px solid var(--border-subtle); }
.seg-cold { background: var(--gradient-cold); } .seg-rising { background: var(--gradient-bull); } .seg-falling { background: var(--gradient-bear); }

.token-heatmap { margin-top: 20px; padding-top: 18px; border-top: 1px solid var(--border-subtle); }
.token-heatmap-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.token-heatmap-label { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: .12em; font-weight: 700; }
.heat-legend { display: flex; align-items: center; gap: 5px; font-family: 'JetBrains Mono', monospace; font-size: 9px; color: var(--text-muted); letter-spacing: .08em; }
.heat-swatch { width: 16px; height: 10px; border-radius: 3px; border: 1px solid var(--border-subtle); }
.hs-1 { background: transparent; } .hs-2 { background: var(--heat-2); } .hs-3 { background: var(--heat-3); }
.hs-4 { background: var(--heat-4); } .hs-5 { background: var(--heat-5); }
.token-row { display: flex; flex-wrap: wrap; gap: 6px; }
.token { font-size: 12.5px; padding: 4px 9px; border-radius: 5px; font-weight: 500; color: var(--text-secondary); }
.token.weight-5 { background: var(--heat-5); color: var(--amber); font-weight: 700; }
.token.weight-4 { background: var(--heat-4); color: var(--text-primary); font-weight: 600; }
.token.weight-3 { background: var(--heat-3); color: var(--text-secondary); }
.token.weight-2 { background: var(--heat-2); color: var(--text-tertiary); }
.token.weight-1 { background: transparent; color: var(--text-muted); }
.regime-cold .token.weight-5 { background: var(--heat-cold-5); color: var(--cyan); }
.regime-cold .token.weight-4 { background: var(--heat-cold-4); }
.regime-cold .token.weight-3 { background: var(--heat-cold-3); }

.route-tag { display: inline-flex; align-items: center; gap: 8px; padding: 6px 12px; border-radius: 6px; background: var(--bg-elevated); border: 1px solid var(--border-subtle); font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--text-tertiary); margin-top: 16px; }
.route-method { padding: 2px 7px; border-radius: 4px; font-weight: 700; font-size: 9.5px; letter-spacing: .05em; }
.route-method.get { background: var(--emerald-glow); color: var(--emerald); }
.route-method.post { background: rgba(59,130,246,.15); color: var(--cobalt); }
.route-path { color: var(--text-secondary); font-weight: 500; }

.hard-badge { display: inline-flex; align-items: center; gap: 8px; padding: 10px 16px; border-radius: 9px; background: var(--bg-elevated); border: 1px solid var(--border-subtle); font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 600; color: var(--text-tertiary); margin-top: 8px; }
.hard-badge .hard-dot { width: 8px; height: 8px; border-radius: 50%; }
.hard-badge.hot  { border-color: rgba(245,158,11,.35); } .hard-badge.hot .hard-dot  { background: var(--amber); box-shadow: 0 0 8px var(--amber); }
.hard-badge.cold { border-color: rgba(56,189,248,.35); } .hard-badge.cold .hard-dot { background: var(--cyan);  box-shadow: 0 0 8px var(--cyan); }
.hard-badge .hard-val { color: var(--text-primary); }

.meta-table { width: 100%; border-collapse: collapse; margin-top: 14px; font-family: 'JetBrains Mono', monospace; font-size: 11.5px; }
.meta-table tr { border-bottom: 1px solid var(--border-subtle); }
.meta-table tr:last-child { border-bottom: none; }
.meta-table td { padding: 10px 4px; }
.meta-table td:first-child { color: var(--text-muted); font-weight: 500; }
.meta-table td:last-child { color: var(--text-primary); text-align: right; font-weight: 600; }

.manifest { width: 100%; border-collapse: collapse; font-family: 'JetBrains Mono', monospace; font-size: 11px; }
.manifest td { padding: 8px 6px; border-bottom: 1px solid var(--border-subtle); color: var(--text-tertiary); vertical-align: top; }
.manifest td:first-child { color: var(--text-muted); width: 52px; font-weight: 600; }
.manifest td:nth-child(2) { color: var(--text-secondary); }
.manifest td:last-child { text-align: right; color: var(--text-muted); width: 64px; }

.log-table { width: 100%; border-collapse: collapse; font-family: 'JetBrains Mono', monospace; font-size: 11px; }
.log-table th { text-align: left; color: var(--text-muted); font-weight: 700; text-transform: uppercase; letter-spacing: .1em; font-size: 9.5px; padding: 6px 8px; border-bottom: 1px solid var(--border-subtle); }
.log-table td { padding: 9px 8px; border-bottom: 1px solid var(--border-subtle); color: var(--text-secondary); }
.log-table tr:last-child td { border-bottom: none; }

.placeholder-box { border: 1px dashed var(--border-subtle); background: var(--bg-elevated); border-radius: 9px; padding: 16px 18px; margin-top: 14px; }
.ph-title { font-family: 'JetBrains Mono', monospace; font-size: 10.5px; text-transform: uppercase; letter-spacing: .12em; color: var(--amber); font-weight: 700; margin-bottom: 6px; }
.ph-body { font-size: 12px; color: var(--text-tertiary); line-height: 1.55; margin-bottom: 6px; }
.ph-route { font-family: 'JetBrains Mono', monospace; font-size: 10.5px; color: var(--text-muted); }
.skeleton { height: 8px; border-radius: 4px; margin-top: 12px; background: linear-gradient(90deg, var(--bg-input) 25%, var(--border-subtle) 50%, var(--bg-input) 75%); background-size: 200% 100%; animation: shimmer 1.8s infinite linear; }

.empty-state { text-align: center; padding: 60px 24px; background: var(--bg-card); border: 1px dashed var(--border-subtle); border-radius: 16px; animation: fadeInScale .5s ease; }
.empty-icon { font-size: 48px; margin-bottom: 16px; display: inline-block; }
.empty-title { font-size: 1.2rem; font-weight: 700; color: var(--text-primary); margin-bottom: 8px; }
.empty-desc { font-size: .92rem; color: var(--text-tertiary); max-width: 460px; margin: 0 auto; line-height: 1.6; }

.wire-remove { background: transparent !important; border: 1px solid transparent !important; color: var(--text-faint) !important; padding: 6px 10px !important; min-height: unset !important; font-size: 14px !important; }
.wire-remove:hover { color: var(--rose) !important; border-color: var(--border-subtle) !important; background: var(--bg-elevated) !important; }

.trend-wrap { background: var(--bg-card); border: 1px solid var(--border-subtle); border-radius: 14px; padding: 18px 20px; margin-top: 14px; box-shadow: var(--shadow-sm); }
.trend-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.trend-title { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: .14em; text-transform: uppercase; font-weight: 700; color: var(--text-muted); }

.footnote { text-align: center; padding: 40px 0 8px; font-family: 'JetBrains Mono', monospace; font-size: 10.5px; color: var(--text-faint); letter-spacing: .08em; line-height: 1.7; }
.footnote-brand { color: var(--text-muted); font-weight: 600; }
hr { border: none !important; height: 1px !important; margin: 26px 0 !important; }

@media (max-width: 900px) {
    .hero-stack { flex-direction: column; align-items: flex-start; }
    .hero-specs { width: 100%; }
    .verdict-banner { grid-template-columns: 1fr; text-align: center; }
    .metrics-strip { grid-template-columns: 1fr; }
}
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════
#  BACKEND: helpers, retry, circuit breaker
# ═══════════════════════════════════════════════════════════════════


def safe_text(value: Any, limit: int = 500) -> str:
    """HTML-escape a value to prevent injection in custom markdown."""
    return html.escape(str(value)[:limit], quote=True)


def _error_hint(status: Optional[int], exc: Optional[Exception]) -> str:
    """Return an actionable hint for a failed request."""
    if exc is not None:
        name = type(exc).__name__
        if "Timeout" in name:
            return "Request timed out — endpoint may be cold-starting or overloaded."
        if "Connection" in name:
            return "Could not reach endpoint — verify URL and network egress."
        return f"{name}: transient failure, retry advised."
    if status == 502:
        return "HTTP 502 — upstream container unhealthy or still starting."
    if status == 503:
        return "HTTP 503 — endpoint at capacity, consider retrying in 30s."
    if status == 504:
        return "HTTP 504 — gateway timeout; reduce input size or increase timeout."
    if status and 500 <= status < 600:
        return f"HTTP {status} — server-side error; check endpoint logs."
    return ""


def call_with_retry(url: str, method: str = "GET", retries: int = RETRY_ATTEMPTS,
                    backoff: float = RETRY_BACKOFF_S, **kwargs) -> dict:
    """Call an endpoint with exponential-backoff retry on transient failure."""
    last_exc: Optional[Exception] = None
    last_status: Optional[int] = None
    for attempt in range(retries + 1):
        started = time.perf_counter()
        try:
            fn = requests.get if method.upper() == "GET" else requests.post
            response = fn(url, **kwargs)
            latency = int((time.perf_counter() - started) * 1000)
            if response.status_code == 200:
                return {"ok": True, "response": response, "latency_ms": latency,
                        "attempts": attempt + 1, "error": "", "status": 200}
            last_status = response.status_code
            # Do not retry 4xx (client error)
            if 400 <= response.status_code < 500:
                break
        except requests.RequestException as exc:
            last_exc = exc
        if attempt < retries:
            time.sleep(backoff * (2 ** attempt))
    latency = int((time.perf_counter() - started) * 1000) if 'started' in dir() else 0
    hint = _error_hint(last_status, last_exc)
    err_msg = f"HTTP {last_status}" if last_status else (
        f"{type(last_exc).__name__}: {safe_text(last_exc, 250)}" if last_exc else "Unknown error")
    if hint:
        err_msg += f" — {hint}"
    return {"ok": False, "response": None, "latency_ms": latency,
            "attempts": retries + 1, "error": err_msg, "status": last_status}


def parse_prediction_response(response: requests.Response) -> tuple[bool, dict, str]:
    if response.status_code != 200:
        return False, {}, f"HTTP {response.status_code}: {safe_text(response.text, 300)}"
    try:
        payload = response.json()
    except ValueError:
        return False, {}, "Endpoint returned invalid JSON."
    if not isinstance(payload, dict):
        return False, {}, "Endpoint response must be a JSON object."
    if "prediction" not in payload:
        return False, payload, "Endpoint response missing 'prediction' field."
    try:
        prediction = float(payload["prediction"])
    except (TypeError, ValueError):
        return False, payload, "'prediction' field must be numeric."
    if prediction != prediction or prediction in (float("inf"), float("-inf")):
        return False, payload, "'prediction' field must be finite."
    payload["prediction"] = prediction
    return True, payload, ""


def call_svc(url: str, headline: str, model_code, timeout: int = 15) -> dict:
    result: dict[str, Any] = {"ok": False, "val": None, "latency_ms": 0, "error": "", "data": {}, "attempts": 0}
    r = call_with_retry(f"{url}/predict", method="GET",
                        params={"headline": headline, "model_choice": model_code},
                        timeout=(3.05, timeout))
    result["latency_ms"] = r["latency_ms"]
    result["attempts"] = r["attempts"]
    if not r["ok"]:
        result["error"] = r["error"]
        return result
    ok, payload, error = parse_prediction_response(r["response"])
    result.update(ok=ok, data=payload, error=error)
    if ok:
        result["val"] = payload["prediction"]
    return result


def call_finbert(url: str, headline: str, summary: str, timeout: int = 20) -> dict:
    result: dict[str, Any] = {"ok": False, "val": None, "latency_ms": 0, "error": "", "data": {}, "attempts": 0}
    r = call_with_retry(f"{url}/dl_predict", method="POST",
                        json={"headline": headline, "summary": summary},
                        timeout=(3.05, timeout))
    result["latency_ms"] = r["latency_ms"]
    result["attempts"] = r["attempts"]
    if not r["ok"]:
        result["error"] = r["error"]
        return result
    ok, payload, error = parse_prediction_response(r["response"])
    result.update(ok=ok, data=payload, error=error)
    if ok:
        result["val"] = payload["prediction"]
        probs = payload.get("probabilities")
        if probs is not None and not isinstance(probs, dict):
            result.update(ok=False, error="'probabilities' must be a JSON object.")
    return result


@st.cache_data(ttl=PING_TTL_S, show_spinner=False)
def ping_service(url: str) -> tuple[bool, Optional[int]]:
    """Reachability probe: any HTTP response < 500 counts as online. Returns (ok, latency_ms|None)."""
    started = time.perf_counter()
    try:
        r = requests.get(url, timeout=4)
        return (r.status_code < 500, int((time.perf_counter() - started) * 1000))
    except Exception:
        return (False, None)


def get_secret(key: str) -> str:
    try:
        value = st.secrets.get(key)
    except (FileNotFoundError, KeyError, AttributeError):
        value = None
    if not value:
        st.error(f"⚠️ **Missing Configuration:** `{key}` was not found in secrets.")
        st.info(f"Add `{key} = \"https://...\"` to `.streamlit/secrets.toml` or your Streamlit Cloud dashboard.")
        st.stop()
    return str(value).rstrip("/")


# ── Deep-linking helpers ──


def qp_get(key: str, default: str = "") -> str:
    try:
        v = st.query_params.get(key, default)
        return v if isinstance(v, str) else default
    except AttributeError:
        return default


def qp_set(**kwargs: str) -> None:
    try:
        for k, v in kwargs.items():
            if v:
                st.query_params[k] = v
            elif k in st.query_params:
                del st.query_params[k]
    except AttributeError:
        pass


SVC_API_URL = get_secret("SVC_API_URL")
FINBERT_API_URL = get_secret("FINBERT_API_URL")
LSTM_MODEL_CODE = 7

svc_online, svc_ping_ms = ping_service(SVC_API_URL)
fin_online, fin_ping_ms = ping_service(FINBERT_API_URL)

# ═══════════════════════════════════════════════════════════════════
#  SESSION STATE
# ═══════════════════════════════════════════════════════════════════
st.session_state.setdefault("num_inputs", 3)
st.session_state.setdefault("summary_input", "")
st.session_state.setdefault("dl_branch", "FINBERT-TONE")
st.session_state.setdefault("sid", uuid.uuid4().hex[:8].upper())
st.session_state.setdefault("active_preset", None)
st.session_state.setdefault("last_results", None)
st.session_state.setdefault("previous_results", None)
st.session_state.setdefault("run_log", [])
st.session_state.setdefault("run_history", [])
st.session_state.setdefault("pending_scroll", False)

UTC_NOW = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def check_last_input() -> None:
    """Auto-append a new empty wire when the second-to-last is filled."""
    last_index = st.session_state.num_inputs - 2
    if st.session_state.get(f"input_{last_index}", "").strip() and st.session_state.num_inputs < MAX_WIRES:
        st.session_state.num_inputs += 1


def reset_all_inputs() -> None:
    for i in range(MAX_WIRES):
        if f"input_{i}" in st.session_state:
            st.session_state[f"input_{i}"] = ""
    st.session_state.summary_input = ""
    st.session_state.num_inputs = 3
    st.session_state.active_preset = None
    qp_set(preset="")


def remove_wire(idx: int) -> None:
    """Remove a specific wire and shift subsequent ones up."""
    n = st.session_state.num_inputs
    for i in range(idx, n - 1):
        st.session_state[f"input_{i}"] = st.session_state.get(f"input_{i + 1}", "")
    if n > 1:
        st.session_state[f"input_{n - 1}"] = ""
        st.session_state.num_inputs = max(3, n - 1)


def load_preset(idx: int, apply_query: bool = True) -> None:
    preset = PRESETS[idx]
    reset_all_inputs()
    st.session_state.num_inputs = max(3, len(preset["headlines"]) + 1)
    for i, text in enumerate(preset["headlines"]):
        st.session_state[f"input_{i}"] = text
    st.session_state.summary_input = preset.get("summary", "")
    st.session_state.active_preset = idx
    if apply_query:
        qp_set(preset=preset["key"])


PRESETS = [
    {"icon": "📈", "tag": "BULLISH", "note_cls": "bull", "key": "bullish",
     "expected": "HOT · BULLISH IMPULSE", "title": "Earnings Breakout",
     "desc": "Blowout quarter, raised guidance, margin expansion — classic risk-on catalyst.",
     "headlines": [
         "NVIDIA reports Q4 revenue surge of 78% YoY, crushing institutional consensus",
         "Management raises full-year data center guidance amid unprecedented AI chip demand",
         "Gross margins expand 640bps sequentially as pricing power accelerates"],
     "summary": "Record backlog and AI demand drive the strongest quarterly print in company history."},
    {"icon": "📉", "tag": "BEARISH", "note_cls": "bear", "key": "bearish",
     "expected": "HOT · BEARISH IMPULSE", "title": "Guidance Shock",
     "desc": "Outlook slashed, executive departure and regulatory overhang — risk-off catalyst.",
     "headlines": [
         "Company slashes full-year operating margin outlook citing severe supply chain bottlenecks",
         "CFO steps down unexpectedly as SEC opens inquiry into revenue recognition practices",
         "Institutional desks downgrade equity following unexpected Q3 earnings miss"],
     "summary": "Guidance withdrawal combined with executive departure creates elevated event risk."},
    {"icon": "📋", "tag": "NEUTRAL", "note_cls": "neutral", "key": "neutral",
     "expected": "COLD · STABLE TAPE", "title": "Routine Filing",
     "desc": "Dividend declaration and standard proxy items — no material catalyst.",
     "headlines": [
         "Board declares regular quarterly cash dividend of $0.25 per share",
         "Annual shareholder meeting scheduled for next month with standard proxy proposals",
         "Operations remain in line with multi-year historical averages"],
     "summary": "No guidance changes or material catalysts; volatility expected to remain subdued."},
]

# Deep-link preset on first load
if st.session_state.active_preset is None and not st.session_state.get("input_0"):
    _qp_preset = qp_get("preset")
    for _i, _p in enumerate(PRESETS):
        if _p["key"] == _qp_preset:
            load_preset(_i, apply_query=False)
            break

HOT5 = {"surge", "surges", "crash", "crashes", "slashes", "slash", "spike", "spikes", "jumps", "jump",
        "soars", "soar", "plunges", "plunge", "hike", "hikes", "warning", "warns", "miss", "misses",
        "inquiry", "probe", "steps", "record", "breaks", "shock", "shocks", "cut", "cuts", "rally",
        "rallies", "sinks", "tumbles", "escalate", "escalates", "slashed", "spiked"}
HOT4 = {"guidance", "outlook", "margins", "margin", "yields", "yield", "inflation", "fed", "reserve",
        "powell", "etf", "inflows", "outflows", "downgrade", "upgrades", "volatility", "vix", "supply",
        "demand", "revenue", "earnings", "bitcoin", "btc", "crude", "opec", "treasury", "sec", "cfo",
        "dividend", "backlog", "pricing", "target", "ratings", "exposure"}


def token_weight(tok: str) -> int:
    t = tok.strip(".,;:!?()\"'").lower()
    if t in HOT5: return 5
    if t in HOT4: return 4
    if len(t) > 8: return 3
    if len(t) > 4: return 2
    return 1


# ── SVG helpers ──


def _gauge_svg(value: Optional[float], kind: str, size: int, vb: float, r: float,
               fs1: float, fs2: float, label: str) -> str:
    """Render a gauge. If value is None, renders an honest '—' / N/A state."""
    g1, g2 = THEME["grads"].get(kind if kind in THEME["grads"] else "accent", THEME["grads"]["accent"])
    gid = f"g{kind}{size}{id(value) % 1000}"
    circ = 2 * 3.14159 * r
    arc = circ * 0.75
    c = vb / 2
    if value is None:
        return f'''<svg width="{size}" height="{size}" viewBox="0 0 {vb} {vb}" aria-label="Agreement: not available">
          <circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="{THEME["border"]}" stroke-width="6"
                  stroke-dasharray="{arc} {circ}" transform="rotate(135 {c} {c})" stroke-linecap="round"/>
          <text x="{c}" y="{c-2}" text-anchor="middle" font-family="Inter" font-weight="800" font-size="{fs1}"
                fill="{THEME["text3"]}">—</text>
          <text x="{c}" y="{c+13}" text-anchor="middle" font-family="JetBrains Mono" font-weight="600"
                font-size="{fs2}" fill="{THEME["muted"]}" letter-spacing="1">{label}</text>
        </svg>'''
    v = max(0.0, min(1.0, float(value)))
    off = arc * (1 - v)
    return f'''<svg width="{size}" height="{size}" viewBox="0 0 {vb} {vb}" role="img" aria-label="{label}: {v*100:.0f}%">
      <defs><linearGradient id="{gid}" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="{g1}"/><stop offset="100%" stop-color="{g2}"/></linearGradient></defs>
      <circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="{THEME["border"]}" stroke-width="6"
              stroke-dasharray="{arc} {circ}" transform="rotate(135 {c} {c})" stroke-linecap="round"/>
      <circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="url(#{gid})" stroke-width="6"
              stroke-dasharray="{arc} {circ}" stroke-dashoffset="{off}" transform="rotate(135 {c} {c})"
              stroke-linecap="round" style="transition:stroke-dashoffset 1.2s cubic-bezier(.4,0,.2,1)"/>
      <text x="{c}" y="{c-2}" text-anchor="middle" font-family="Inter" font-weight="800" font-size="{fs1}"
            fill="{THEME["text1"]}">{v*100:.0f}%</text>
      <text x="{c}" y="{c+13}" text-anchor="middle" font-family="JetBrains Mono" font-weight="600"
            font-size="{fs2}" fill="{THEME["muted"]}" letter-spacing="1">{label}</text>
    </svg>'''


def svg_gauge(value: Optional[float], kind: str = "accent", size: int = 88) -> str:
    return _gauge_svg(value, kind, size, 88, 36, 20, 8.5, "CONSENSUS")


TICKER_ITEMS = [
    ("SPX", "5,842.16", "+0.82%", True), ("NDX", "20,341.55", "+1.24%", True), ("DJI", "42,118.91", "-0.18%", False),
    ("VIX", "14.32", "-3.21%", False), ("TNX", "4.281%", "+6bp", True), ("BTC", "$92,418", "+3.41%", True),
    ("ETH", "$3,842", "+5.12%", True), ("GC", "$2,741", "-0.64%", False), ("CL", "$78.42", "+2.18%", True),
    ("EUR/USD", "1.0842", "+0.14%", True), ("GBP/USD", "1.2961", "-0.08%", False), ("USD/JPY", "149.82", "+0.32%", True),
    ("AAPL", "$229.41", "+1.9%", True), ("MSFT", "$424.82", "+2.3%", True), ("NVDA", "$141.22", "+4.7%", True),
    ("TSLA", "$262.55", "-1.4%", False),
]

# ═══════════════════════════════════════════════════════════════════
#  TOP BAR + TICKER + HERO
# ═══════════════════════════════════════════════════════════════════

svc_chip = ("ok", f"SVC · {svc_ping_ms}ms") if svc_online else (
    ("bad", "SVC · UNREACHABLE") if svc_ping_ms is not None else ("unk", "SVC · UNKNOWN"))
fin_chip = ("ok", f"FINBERT · {fin_ping_ms}ms") if fin_online else (
    ("bad", "FINBERT · UNREACHABLE") if fin_ping_ms is not None else ("unk", "FINBERT · UNKNOWN"))

top_left, top_right = st.columns([5, 1])
with top_left:
    st.markdown(f"""
    <div class="topbar">
        <div class="topbar-left">
            <div class="brand-mark">S</div>
            <div>
                <div class="brand-title">SENTINEL</div>
                <div class="brand-tag">Market Regime Terminal · v4.0</div>
            </div>
        </div>
        <div class="topbar-right">
            <div class="chip {svc_chip[0]}"><span class="chip-dot"></span>{svc_chip[1]}</div>
            <div class="chip {fin_chip[0]}"><span class="chip-dot"></span>{fin_chip[1]}</div>
        </div>
    </div>""", unsafe_allow_html=True)
with top_right:
    st.toggle("☀️ Light" if is_dark else "🌙 Dark", value=(not is_dark),
              on_change=toggle_theme, key="theme_toggle")

ticker_html = '<div class="ticker-wrap"><div class="ticker-track">'
for _ in range(2):
    for sym, price, delta, up in TICKER_ITEMS:
        cls = "ticker-up" if up else "ticker-down"
        arrow = "▲" if up else "▼"
        ticker_html += (f'<div class="ticker-item"><span class="ticker-sym">{sym}</span>'
                        f'<span class="ticker-price">{price}</span>'
                        f'<span class="{cls}">{arrow} {delta}</span></div>')
ticker_html += '</div></div>'
st.markdown(ticker_html, unsafe_allow_html=True)

st.markdown("""
<div class="hero-stack">
    <div>
        <h1 class="hero-title">Market Regime & <span class="accent">Sentiment</span> Terminal</h1>
        <p class="hero-sub">
            Routes wire headlines to two production endpoints: a TF-IDF / LinearSVC volatility baseline,
            and a neural branch running either FinBERT-Tone (3-class softmax) or the frozen-Word2Vec LSTM.
            Research signals only — not investment advice.
        </p>
    </div>
    <div class="hero-specs">
        <div class="spec-cell"><span class="spec-lbl">Training Corpus</span><span class="spec-val">200,000 Samples</span></div>
        <div class="spec-cell"><span class="spec-lbl">Neural Branches</span><span class="spec-val">FinBERT / LSTM</span></div>
        <div class="spec-cell"><span class="spec-lbl">Volatility Bands</span><span class="spec-val">0.2σ · 0.5σ · 1.0σ</span></div>
    </div>
</div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════
#  01 · PRESETS
# ═══════════════════════════════════════════════════════════════════
st.markdown('<div class="section-label" data-num="01">Scenario Presets</div>', unsafe_allow_html=True)
p_cols = st.columns(3, gap="large")
for i, preset in enumerate(PRESETS):
    with p_cols[i]:
        active = st.session_state.active_preset == i
        if st.button(f"{preset['icon']}  {preset['tag']} · {preset['title']}",
                     key=f"preset_{i}", use_container_width=True,
                     type="primary" if active else "secondary",
                     help=preset["desc"]):
            load_preset(i)
            st.rerun()
        st.markdown(f"<div class='preset-note {preset['note_cls']}'>EXPECTED REGIME ▸ {preset['expected']}</div>",
                    unsafe_allow_html=True)
st.markdown("<div class='preset-hint'>3 benchmark scenarios · click to auto-populate the workspace</div>",
            unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════
#  02 / 03 · INPUT + CONFIG
# ═══════════════════════════════════════════════════════════════════
panel_left, panel_right = st.columns([2.4, 1], gap="large")

with panel_left:
    st.markdown('<div class="section-label" data-num="02">Event Stream Ingestion</div>', unsafe_allow_html=True)
    with st.container(border=True):
        for i in range(st.session_state.num_inputs):
            is_last = i == st.session_state.num_inputs - 2
            wire_c, wire_x = st.columns([20, 1], gap="small")
            with wire_c:
                st.text_input(label=f"WIRE HEADLINE {i + 1:02d}", key=f"input_{i}",
                              placeholder=f"[Wire {i + 1:02d}] Enter financial headline or press release...",
                              on_change=check_last_input if is_last else None)
            with wire_x:
                if st.session_state.num_inputs > 3:
                    if st.button("✕", key=f"rm_{i}", help=f"Remove wire {i + 1}",
                                 use_container_width=True):
                        remove_wire(i)
                        st.rerun()
                else:
                    st.write("")

        act1, act2, act3, _ = st.columns([1, 1, 1.4, 2])
        with act1:
            if st.button("＋ Add Wire", type="secondary", use_container_width=True,
                         disabled=st.session_state.num_inputs >= MAX_WIRES):
                st.session_state.num_inputs += 1
                st.rerun()
        with act2:
            if st.button("✕ Clear All", type="secondary", use_container_width=True):
                reset_all_inputs()
                st.rerun()
        with act3:
            uploaded = st.file_uploader("📥 Batch CSV (headline column)", type=["csv"],
                                        label_visibility="collapsed",
                                        help="Upload a CSV with a `headline` column to auto-populate wires")
        if uploaded is not None:
            try:
                raw = uploaded.read().decode("utf-8", errors="ignore")
                reader = csv.DictReader(io.StringIO(raw))
                rows = [r for r in reader if (r.get("headline") or "").strip()]
                if rows:
                    reset_all_inputs()
                    n = min(len(rows), MAX_WIRES)
                    st.session_state.num_inputs = max(3, n + 1)
                    for i, r in enumerate(rows[:MAX_WIRES]):
                        st.session_state[f"input_{i}"] = r["headline"].strip()
                    st.toast(f"Loaded {n} headlines from CSV", icon="📥")
                    st.rerun()
            except Exception as exc:
                st.error(f"CSV parse failed: {exc}")

with panel_right:
    st.markdown('<div class="section-label" data-num="03">Model Configuration</div>', unsafe_allow_html=True)
    with st.container(border=True):
        MODEL_MAP = {
            "LinearSVC · σ > 1.0 (High)":   (1, "1.0σ", "Strict tail-volatility filter"),
            "LinearSVC · σ > 0.5 (Medium)": (0.5, "0.5σ", "Balanced regime sensitivity"),
            "LinearSVC · σ > 0.2 (Low)":    (0.2, "0.2σ", "High sensitivity to minor moves"),
        }
        selected_svc_label = st.selectbox("Baseline Volatility Threshold", options=list(MODEL_MAP.keys()))
        st.markdown("<div style=\"font-size:10.5px;font-family:'JetBrains Mono',monospace;color:var(--text-tertiary);"
                    "text-transform:uppercase;letter-spacing:.12em;margin:18px 0 8px 0;font-weight:700;\">Neural Branch</div>",
                    unsafe_allow_html=True)
        c1, c2 = st.columns(2, gap="small")
        with c1:
            if st.button("FinBERT-Tone", use_container_width=True, key="seg_finbert",
                         type="primary" if st.session_state.dl_branch == "FINBERT-TONE" else "secondary"):
                st.session_state.dl_branch = "FINBERT-TONE"; st.rerun()
        with c2:
            if st.button("LSTM · W2V", use_container_width=True, key="seg_lstm",
                         type="primary" if st.session_state.dl_branch == "LSTM-W2V" else "secondary"):
                st.session_state.dl_branch = "LSTM-W2V"; st.rerun()
        if st.session_state.dl_branch == "LSTM-W2V":
            st.caption("ℹ️ LSTM branch is served by the SVC API at `model_choice=7`.")
        st.text_area(label="Extended Context (FinBERT only)", key="summary_input",
                     placeholder="Optional 1-3 sentence analyst synthesis...", height=110)

active_wires = [(i, st.session_state.get(f"input_{i}", "").strip())
                for i in range(st.session_state.num_inputs)
                if st.session_state.get(f"input_{i}", "").strip()]
active_headlines = [t for _, t in active_wires]
concatenated_headlines = " ".join(active_headlines)

st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
act1, act2, act3 = st.columns([1.4, 0.9, 3.7])
with act1:
    predict_clicked = st.button("⚡ Execute Dual Inference", type="primary", use_container_width=True)
with act2:
    st.button("Clear Workspace", type="secondary", use_container_width=True, on_click=reset_all_inputs)
with act3:
    char_count = len(concatenated_headlines) + len((st.session_state.get("summary_input", "") or "").strip())
    branch_tag = "FINBERT-TONE" if st.session_state.dl_branch == "FINBERT-TONE" else "LSTM-W2V"
    st.markdown(f"<div style=\"font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-muted);"
                f"padding-top:14px;padding-left:8px;\">ACTIVE WIRES: <strong style='color:var(--text-secondary)'>{len(active_headlines)}</strong> · "
                f"PAYLOAD: <strong style='color:var(--text-secondary)'>{char_count} CHARS</strong> · "
                f"BRANCH: <strong style='color:var(--cobalt)'>{branch_tag}</strong></div>", unsafe_allow_html=True)

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════
#  DISPATCH
# ═══════════════════════════════════════════════════════════════════
if predict_clicked:
    if not concatenated_headlines:
        st.session_state.last_results = None
        st.markdown("""
        <div class="empty-state">
            <div class="empty-icon">📡</div>
            <div class="empty-title">No signal detected</div>
            <div class="empty-desc">Provide at least one headline or select a scenario preset above to begin analysis.</div>
        </div>""", unsafe_allow_html=True)
    elif len(concatenated_headlines) > MAX_CHARS:
        st.error(f"Input exceeds {MAX_CHARS:,}-character limit. Shorten and retry.")
    else:
        model_code, sigma_str, sigma_desc = MODEL_MAP[selected_svc_label]
        dl_branch = st.session_state.dl_branch
        summary = (st.session_state.get("summary_input", "") or "").strip()
        req_id = uuid.uuid4().hex[:6].upper()
        with st.spinner("Dispatching payloads across inference endpoints…"):
            with ThreadPoolExecutor(max_workers=2) as pool:
                svc_future = pool.submit(call_svc, SVC_API_URL, concatenated_headlines, model_code)
                if dl_branch == "FINBERT-TONE":
                    neural_future = pool.submit(call_finbert, FINBERT_API_URL, concatenated_headlines, summary)
                else:
                    neural_future = pool.submit(call_svc, SVC_API_URL, concatenated_headlines, LSTM_MODEL_CODE, 20)
                svc_result = svc_future.result()
                neural_result = neural_future.result()
                neural_result["branch"] = dl_branch

        # Preserve previous results for delta rendering
        st.session_state.previous_results = st.session_state.last_results
        st.session_state.last_results = (svc_result, neural_result, model_code, sigma_str, sigma_desc,
                                         dl_branch, concatenated_headlines, active_wires)

        svc_v = ("HOT" if int(svc_result["val"]) == 1 else "COLD") if svc_result["ok"] else "ERR"
        nn_v = ("HOT" if int(neural_result["val"]) == 1 else "COLD") if neural_result["ok"] else "ERR"
        entry = {
            "req_id": req_id,
            "ts": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "branch": "FINBERT" if dl_branch == "FINBERT-TONE" else "LSTM",
            "svc": svc_v, "nn": nn_v,
            "ms": svc_result.get("latency_ms", 0) + neural_result.get("latency_ms", 0),
            "svc_attempts": svc_result.get("attempts", 1),
            "nn_attempts": neural_result.get("attempts", 1),
        }
        st.session_state.run_log.append(entry)
        st.session_state.run_log = st.session_state.run_log[-LOG_LEN:]

        # Capture a numeric snapshot for the trend chart
        p_hot_snap: Optional[float] = None
        if neural_result["ok"] and dl_branch == "FINBERT-TONE":
            probs = neural_result["data"].get("probabilities", {}) or {}
            pr = float(probs.get("hot_rising", 0.0))
            pf = float(probs.get("hot_falling", 0.0))
            p_hot_snap = float(neural_result["data"].get("prob_hot", pr + pf))
        st.session_state.run_history.append({
            "ts": entry["ts"], "label": f"{entry['ts']}",
            "p_hot": p_hot_snap, "svc_hot": 1 if svc_v == "HOT" else (0 if svc_v == "COLD" else None),
            "nn_hot":  1 if nn_v == "HOT"  else (0 if nn_v == "COLD" else None),
        })
        st.session_state.run_history = st.session_state.run_history[-HISTORY_LEN:]

        if svc_result["ok"] and neural_result["ok"]:
            st.toast(f"Inference complete · {entry['ms']} ms · req {req_id}", icon="✅")
        elif svc_result["ok"] or neural_result["ok"]:
            st.toast("Partial inference — one endpoint failed", icon="⚠️")
        else:
            st.toast("Both endpoints failed — see error panel", icon="❌")
        st.session_state.pending_scroll = True

# ═══════════════════════════════════════════════════════════════════
#  RESULTS
# ═══════════════════════════════════════════════════════════════════
if st.session_state.get("last_results"):
    (svc_result, neural_result, model_code, sigma_str, sigma_desc,
     dl_branch, concat_snapshot, wires_snapshot) = st.session_state.last_results

    # Auto-scroll on new execution
    if st.session_state.get("pending_scroll"):
        st.markdown('<div id="verdict-anchor"></div>', unsafe_allow_html=True)
        st.markdown(
            "<script>setTimeout(()=>{const e=document.getElementById('verdict-anchor');"
            "if(e)e.scrollIntoView({behavior:'smooth',block:'start'});},300);</script>",
            unsafe_allow_html=True)
        st.session_state.pending_scroll = False

    st.markdown('<div class="section-label" data-num="04">Consensus Verdict</div>', unsafe_allow_html=True)

    # Compute agreement / verdict
    if not (svc_result["ok"] and neural_result["ok"]):
        agreement_pct = None  # type: ignore[assignment]
        verdict_kind, verdict_title = "partial", "⚠️ Partial Inference"
        verdict_sub = "One endpoint failed. A failed call is NOT treated as a negative signal. Inspect errors below."
    else:
        svc_is_hot = int(svc_result["val"]) == 1
        nn_is_hot = int(neural_result["val"]) == 1
        p_rising = p_falling = 0.0
        if dl_branch == "FINBERT-TONE":
            probs = neural_result["data"].get("probabilities", {}) or {}
            p_rising = float(probs.get("hot_rising", 0.0))
            p_falling = float(probs.get("hot_falling", 0.0))
        if svc_is_hot == nn_is_hot:
            agreement_pct = 1.0
            if svc_is_hot:
                if dl_branch == "FINBERT-TONE" and p_rising >= p_falling:
                    verdict_kind, verdict_title = "bull", "▲ HIGH-CONFIDENCE BULLISH SIGNAL"
                elif dl_branch == "FINBERT-TONE":
                    verdict_kind, verdict_title = "bear", "▼ HIGH-CONFIDENCE BEARISH SIGNAL"
                else:
                    verdict_kind, verdict_title = "hot", "🔥 CONVERGENT VOLATILITY SIGNAL"
                verdict_sub = "Both models detect elevated dispersion — consider hedging tail exposure."
            else:
                verdict_kind, verdict_title = "cold", "◆ STABLE REGIME CONSENSUS"
                verdict_sub = "Both models within low-dispersion band — no regime transition flagged."
        else:
            agreement_pct = 0.5  # Honest 1-of-2 agreement
            verdict_kind, verdict_title = "split", "⚖️ DIVERGENT MODEL SIGNALS"
            verdict_sub = "Models disagree — manual review recommended before acting on either signal."

    svc_chip_txt = ("<span class='v-hot'>HOT</span>" if int(svc_result["val"]) == 1 else "<span class='v-cold'>COLD</span>") if svc_result["ok"] else "<span class='v-err'>ERR</span>"
    if neural_result["ok"]:
        nn_chip_txt = ("<span class='v-hot'>HOT</span>" if int(neural_result["val"]) == 1 else "<span class='v-cold'>COLD</span>")
    else:
        nn_chip_txt = "<span class='v-err'>ERR</span>"
    total_lat = svc_result.get("latency_ms", 0) + neural_result.get("latency_ms", 0)

    # Delta vs previous run
    delta_html = ""
    prev = st.session_state.get("previous_results")
    if prev and prev[0]["ok"] and prev[1]["ok"] and svc_result["ok"] and neural_result["ok"]:
        prev_agree = 1.0 if int(prev[0]["val"]) == int(prev[1]["val"]) else 0.5
        if agreement_pct is not None and agreement_pct != prev_agree:
            cls = "up" if agreement_pct > prev_agree else "down"
            delta_html = f"<span class='verdict-delta {cls}'>Δ {(agreement_pct-prev_agree)*100:+.0f}% vs prior</span>"
        else:
            delta_html = "<span class='verdict-delta flat'>Δ flat</span>"

    st.markdown(f"""
    <div class="verdict-banner verdict-{verdict_kind}">
        <div>{svg_gauge(agreement_pct, verdict_kind if verdict_kind in THEME["grads"] else "accent")}</div>
        <div>
            <div class="verdict-eyebrow">Cross-Model Consensus {delta_html}</div>
            <div class="verdict-title">{verdict_title}</div>
            <div class="verdict-sub">{verdict_sub}</div>
            <div class="verdict-meta-row">
                <div><span class="verdict-meta-k">SVC:</span>{svc_chip_txt}</div>
                <div><span class="verdict-meta-k">NEURAL:</span>{nn_chip_txt}</div>
                <div><span class="verdict-meta-k">ROUND-TRIP:</span>{total_lat} ms</div>
                <div><span class="verdict-meta-k">SESSION:</span>{st.session_state.sid}</div>
                <div><span class="verdict-meta-k">UTC:</span>{UTC_NOW}</div>
            </div>
        </div>
    </div>""", unsafe_allow_html=True)

    # ── 05 · Model Telemetry ──
    st.markdown('<div class="section-label" data-num="05">Model Telemetry</div>', unsafe_allow_html=True)
    col_svc, col_dl = st.columns([1, 1.12], gap="large")

    with col_svc:
        if svc_result["ok"]:
            is_hot = int(svc_result["val"]) == 1
            kind = "hot" if is_hot else "cold"
            icon = "🔥" if is_hot else "❄️"
            regime_title = "▲ VOLATILE (HOT)" if is_hot else "◆ STABLE (COLD)"
            regime_desc = (f"TF-IDF + LinearSVC projects dispersion exceeding the {sigma_str} threshold."
                           if is_hot else f"Lexical vector within normal bounds (< {sigma_str}).")
            tokens_html = "".join(f'<span class="token weight-{token_weight(t)}">{safe_text(t, 40)}</span>'
                                  for t in concat_snapshot.split()[:24])
            st.markdown(f"""
            <div class="glass-card regime-{kind}">
                <div class="card-title-row">
                    <div>
                        <div class="card-eyebrow">Model 01 · Econometric</div>
                        <div class="card-title">LinearSVC Baseline</div>
                        <div class="card-subtitle">TF-IDF + Support Vector Classifier</div>
                    </div>
                    <div class="latency-pill">{svc_result['latency_ms']} ms</div>
                </div>
                <div class="regime-display {kind}">
                    <div class="regime-icon {kind}">{icon}</div>
                    <div class="regime-text-block">
                        <div class="regime-label">Predicted Regime</div>
                        <div class="regime-title {kind}">{regime_title}</div>
                    </div>
                </div>
                <div class="hard-badge {kind}">
                    <span class="hard-dot"></span>
                    HARD CLASSIFIER · no probability returned ·
                    <span class="hard-val">{'HOT' if is_hot else 'COLD'}</span>
                </div>
                <p style="color:var(--text-secondary);font-size:13px;line-height:1.55;margin:14px 0 0;">{regime_desc}</p>
                <div class="metrics-strip">
                    <div class="metric-cell"><div class="metric-val">{int(svc_result['val'])}</div><div class="metric-lbl">Binary Class</div></div>
                    <div class="metric-cell"><div class="metric-val">{sigma_str}</div><div class="metric-lbl">Threshold</div></div>
                    <div class="metric-cell"><div class="metric-val">{model_code}</div><div class="metric-lbl">Model ID</div></div>
                </div>
                <div class="token-heatmap">
                    <div class="token-heatmap-head">
                        <div class="token-heatmap-label">Token Influence (heuristic · length + keyword)</div>
                        <div class="heat-legend">LOW
                            <span class="heat-swatch hs-1"></span><span class="heat-swatch hs-2"></span>
                            <span class="heat-swatch hs-3"></span><span class="heat-swatch hs-4"></span>
                            <span class="heat-swatch hs-5"></span> HIGH
                        </div>
                    </div>
                    <div class="token-row">{tokens_html}</div>
                </div>
                <div class="route-tag"><span class="route-method get">GET</span><span class="route-path">/predict?model_choice={model_code}</span></div>
            </div>""", unsafe_allow_html=True)
        else:
            st.error(f"LinearSVC endpoint failure: {svc_result['error']}")

    with col_dl:
        if neural_result["ok"]:
            nn_is_hot = int(neural_result["val"]) == 1
            if dl_branch == "FINBERT-TONE":
                data = neural_result["data"]
                probs = data.get("probabilities", {}) or {}
                p_cold = float(probs.get("cold", 0.0))
                p_rising = float(probs.get("hot_rising", 0.0))
                p_falling = float(probs.get("hot_falling", 0.0))
                p_hot = float(data.get("prob_hot", p_rising + p_falling))
                native = str(data.get("native_3class", "cold")).upper().replace("_", " ")
                cold_pct, rising_pct, falling_pct = p_cold * 100, p_rising * 100, p_falling * 100
                if nn_is_hot:
                    if p_rising >= p_falling:
                        kind, icon, regime_title, conf = "bull", "▲", "HOT · BULLISH EXPANSION", p_hot
                    else:
                        kind, icon, regime_title, conf = "bear", "▼", "HOT · BEARISH CONTRACTION", p_hot
                else:
                    kind, icon, regime_title, conf = "cold", "❄️", "COLD · EQUILIBRIUM", p_cold
                st.markdown(f"""
                <div class="glass-card regime-{kind}">
                    <div class="card-title-row">
                        <div>
                            <div class="card-eyebrow">Model 02 · Neural</div>
                            <div class="card-title">FinBERT-Tone Transformer</div>
                            <div class="card-subtitle">yiyanghkust/finbert-tone · 3-Class Softmax</div>
                        </div>
                        <div class="latency-pill">{neural_result['latency_ms']} ms</div>
                    </div>
                    <div class="regime-display {kind}">
                        <div class="regime-icon {kind}">{icon}</div>
                        <div class="regime-text-block">
                            <div class="regime-label">Aggregated Sentiment</div>
                            <div class="regime-title {kind}">{regime_title}</div>
                        </div>
                        <div class="gauge-wrap">{_gauge_svg(conf, kind, 100, 100, 40, 22, 9, "CONFIDENCE")}</div>
                    </div>
                    <div class="spectrum-wrapper">
                        <div class="spectrum-header"><span>3-CLASS SOFTMAX</span><span>DOMINANT: <strong style="color:var(--text-primary)">{native}</strong></span></div>
                        <div class="spectrum-bar">
                            <div class="seg-cold" style="width:{cold_pct:.2f}%"></div>
                            <div class="seg-rising" style="width:{rising_pct:.2f}%"></div>
                            <div class="seg-falling" style="width:{falling_pct:.2f}%"></div>
                        </div>
                    </div>
                    <div class="prob-grid">
                        <div class="prob-row"><div class="prob-meta"><span class="prob-name">◆ COLD · STABLE</span><span class="prob-pct">{cold_pct:.2f}%</span></div><div class="prob-track"><div class="prob-fill prob-fill-cold" style="width:{cold_pct:.2f}%"></div></div></div>
                        <div class="prob-row"><div class="prob-meta"><span class="prob-name">▲ HOT · BULLISH</span><span class="prob-pct">{rising_pct:.2f}%</span></div><div class="prob-track"><div class="prob-fill prob-fill-bull" style="width:{rising_pct:.2f}%"></div></div></div>
                        <div class="prob-row"><div class="prob-meta"><span class="prob-name">▼ HOT · BEARISH</span><span class="prob-pct">{falling_pct:.2f}%</span></div><div class="prob-track"><div class="prob-fill prob-fill-bear" style="width:{falling_pct:.2f}%"></div></div></div>
                    </div>
                    <div class="route-tag"><span class="route-method post">POST</span><span class="route-path">/dl_predict</span></div>
                </div>""", unsafe_allow_html=True)
            else:
                kind = "hot" if nn_is_hot else "cold"
                icon = "🔥" if nn_is_hot else "❄️"
                regime_title = "▲ EVENT-DRIVEN VOLATILITY" if nn_is_hot else "◆ QUIET TAPE"
                regime_desc = ("Frozen W2V embeddings through the LSTM stack; recurrent state crosses the volatility threshold."
                               if nn_is_hot else "Recurrent state remains inside the low-dispersion band.")
                st.markdown(f"""
                <div class="glass-card regime-{kind}">
                    <div class="card-title-row">
                        <div>
                            <div class="card-eyebrow">Model 02 · Neural</div>
                            <div class="card-title">LSTM (Frozen W2V)</div>
                            <div class="card-subtitle">best_lstm_it13_w2v_frozen · binary head</div>
                        </div>
                        <div class="latency-pill">{neural_result['latency_ms']} ms</div>
                    </div>
                    <div class="regime-display {kind}">
                        <div class="regime-icon {kind}">{icon}</div>
                        <div class="regime-text-block">
                            <div class="regime-label">Predicted Regime</div>
                            <div class="regime-title {kind}">{regime_title}</div>
                        </div>
                    </div>
                    <div class="hard-badge {kind}">
                        <span class="hard-dot"></span>
                        HARD CLASSIFIER · binary head ·
                        <span class="hard-val">{'HOT' if nn_is_hot else 'COLD'}</span>
                    </div>
                    <p style="color:var(--text-secondary);font-size:13px;line-height:1.55;margin:14px 0 0;">{regime_desc}</p>
                    <table class="meta-table">
                        <tr><td>EMBEDDINGS</td><td>Word2Vec (frozen, it=13)</td></tr>
                        <tr><td>ENCODER</td><td>LSTM recurrent stack</td></tr>
                        <tr><td>OUTPUT HEAD</td><td>Binary (hard threshold)</td></tr>
                        <tr><td>ROUTING</td><td>SVC service · model_choice=7</td></tr>
                    </table>
                    <div class="route-tag"><span class="route-method get">GET</span><span class="route-path">/predict?model_choice=7</span></div>
                </div>""", unsafe_allow_html=True)
        else:
            st.error(f"Neural endpoint failure: {neural_result['error']}")

    # ── Trend chart (only if we have ≥2 runs with numeric data) ──
    history = [h for h in st.session_state.get("run_history", []) if h.get("p_hot") is not None]
    if len(history) >= 2:
        st.markdown('<div class="section-label" data-num="05b">Probability Trend</div>', unsafe_allow_html=True)
        st.markdown('<div class="trend-wrap"><div class="trend-head"><span class="trend-title">P(HOT) · LAST '
                    f'{len(history)} RUNS (FinBERT branch only)</span></div>', unsafe_allow_html=True)
        try:
            import pandas as pd
            df = pd.DataFrame([{"run": h["label"], "p_hot": h["p_hot"]} for h in history])
            st.line_chart(df.set_index("run")["p_hot"], height=160, color="#3B82F6")
        except Exception:
            st.caption("Chart unavailable.")
        st.markdown("</div>", unsafe_allow_html=True)

    # ── Export + raw inspector ──
    report = {
        "session": st.session_state.sid,
        "timestamp_utc": UTC_NOW,
        "config": {"svc_threshold": sigma_str, "model_choice": model_code, "neural_branch": dl_branch},
        "inputs": {"headlines": [t for _, t in wires_snapshot],
                   "summary": (st.session_state.get("summary_input", "") or "").strip()},
        "svc_result": {k: svc_result.get(k) for k in ("ok", "val", "latency_ms", "error", "data", "attempts")},
        "neural_result": {k: neural_result.get(k) for k in ("ok", "val", "latency_ms", "error", "data", "branch", "attempts")},
    }
    report_json = json.dumps(report, indent=2, default=str)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    e1, e2, e3 = st.columns([3, 1.2, 1.2])
    with e2:
        st.download_button("⬇ Export JSON Report", type="secondary", use_container_width=True,
                           data=report_json,
                           file_name=f"sentinel_{st.session_state.sid}_{datetime.now(timezone.utc).strftime('%H%M%S')}.json")
    with e3:
        with st.popover("📋 Copy report", use_container_width=True):
            st.code(report_json, language="json")

    with st.expander("🔍 INSPECT RAW API TELEMETRY & INGEST MANIFEST"):
        i1, i2 = st.columns(2)
        with i1:
            st.caption("GET /predict — LinearSVC baseline (SVC_API_URL)")
            if svc_result["ok"]:
                st.json({"endpoint": f"{SVC_API_URL}/predict", "latency_ms": svc_result["latency_ms"],
                         "query_params": {"headline": concat_snapshot[:200] + "…", "model_choice": model_code},
                         "prediction": svc_result["val"]})
            else:
                st.error(svc_result.get("error") or "Unknown error")
        with i2:
            if dl_branch == "FINBERT-TONE":
                st.caption("POST /dl_predict — FinBERT-Tone (FINBERT_API_URL)")
                if neural_result["ok"]:
                    st.json({"endpoint": f"{FINBERT_API_URL}/dl_predict", "latency_ms": neural_result["latency_ms"],
                             "response_payload": neural_result["data"]})
                else:
                    st.error(neural_result.get("error") or "Unknown error")
            else:
                st.caption("GET /predict — LSTM-W2V, model_choice=7 (SVC_API_URL)")
                if neural_result["ok"]:
                    st.json({"endpoint": f"{SVC_API_URL}/predict", "latency_ms": neural_result["latency_ms"],
                             "query_params": {"headline": concat_snapshot[:200] + "…", "model_choice": LSTM_MODEL_CODE},
                             "prediction": neural_result["val"]})
                else:
                    st.error(neural_result.get("error") or "Unknown error")
        st.caption("Ingest manifest")
        rows = "".join(
            f"<tr><td>W{idx+1:02d}</td><td>{safe_text(t, 96)}{'…' if len(t) > 96 else ''}</td><td>{len(t)} ch</td></tr>"
            for idx, t in wires_snapshot)
        st.markdown(f"<table class='manifest'>{rows}</table>", unsafe_allow_html=True)

    # ── 06 · Signal log ──
    if st.session_state.run_log:
        st.markdown('<div class="section-label" data-num="06">Signal Log</div>', unsafe_allow_html=True)
        log_rows = ""
        for entry in reversed(st.session_state.run_log[-6:]):
            svc_cls = {"HOT": "v-hot", "COLD": "v-cold"}.get(entry["svc"], "v-err")
            nn_cls = {"HOT": "v-hot", "COLD": "v-cold"}.get(entry["nn"], "v-err")
            retry_note = ""
            if entry.get("svc_attempts", 1) > 1 or entry.get("nn_attempts", 1) > 1:
                retry_note = f" ↻{max(entry.get('svc_attempts', 1), entry.get('nn_attempts', 1))}"
            log_rows += (f"<tr><td>{entry['ts']} UTC</td><td>{entry['branch']}</td>"
                         f"<td class='{svc_cls}'>{entry['svc']}</td><td class='{nn_cls}'>{entry['nn']}</td>"
                         f"<td>{entry['ms']} ms{retry_note}</td></tr>")
        st.markdown(f"""
        <table class="log-table">
            <tr><th>Time</th><th>Neural Branch</th><th>SVC</th><th>Neural</th><th>Round-Trip</th></tr>
            {log_rows}
        </table>""", unsafe_allow_html=True)
        if st.button("Clear log", type="secondary"):
            st.session_state.run_log = []
            st.session_state.run_history = []
            st.rerun()

elif not predict_clicked:
    st.markdown("""
    <div class="empty-state">
        <div class="empty-icon">🎯</div>
        <div class="empty-title">Ready when you are</div>
        <div class="empty-desc">Select a scenario preset or craft your own headlines above, then execute
        <strong> Dual Inference</strong> to run both models in parallel.</div>
    </div>""", unsafe_allow_html=True)

st.markdown(f"""
<div class="footnote">
    <span class="footnote-brand">SENTINEL</span> · Market Regime Terminal · build 4.0.0 · session {st.session_state.sid}<br>
    SVC_API_URL + FINBERT_API_URL hosted on Cloud Run (europe-west1) · outputs are research signals, not investment advice
</div>""", unsafe_allow_html=True)

"""Reusable Streamlit UI components."""
from __future__ import annotations

from typing import Any

import numpy as np
import plotly.graph_objects as go
import streamlit as st


# ---------------------------------------------------------------------------
# Brand colours
# ---------------------------------------------------------------------------
RED = "#E4002B"
DARK = "#1A1A2E"
SLATE = "#4A4A68"
LIGHT = "#F5F5F7"
SUCCESS = "#28A745"
WARNING = "#FFC107"
ERROR = "#DC3545"
INFO = "#0D6EFD"


# ---------------------------------------------------------------------------
# Global CSS injection
# ---------------------------------------------------------------------------

def inject_css() -> None:
    st.markdown(
        """
        <style>
        /* =====================================================================
           AUTHENTIC GLASSMORPHISM THEME
           Background: deep space gradient + 3 floating colour orbs
           Glass formula: white-alpha + backdrop-blur/saturate + blue-tinted shadow
                          + inset top-edge highlight (the key glass "light catch")
           ===================================================================== */

        /* ── Page background ─────────────────────────────────────────────── */
        /* Paint html/body BEFORE .stApp renders → eliminates white flash    */
        html, body {
            background: #080818 !important;
        }
        .stApp, [data-testid="stAppViewContainer"] {
            background: linear-gradient(135deg, #0a0818 0%, #130826 45%, #0c1035 100%) !important;
            background-attachment: fixed !important;
        }

        /* ── Three floating colour orbs (pure CSS, no extra DOM) ─────────── */
        /* Purple/violet orb — top-left  (matches reference card glow) */
        body::before {
            content: '';
            position: fixed;
            top: -160px; left: 5%;
            width: 640px; height: 640px;
            background: radial-gradient(circle, rgba(120,0,220,0.55) 0%, rgba(80,0,160,0.20) 45%, transparent 70%);
            border-radius: 50%;
            pointer-events: none;
            z-index: 0;
        }
        /* Red/pink orb — bottom-left (vivid like reference) */
        body::after {
            content: '';
            position: fixed;
            bottom: -120px; left: 15%;
            width: 520px; height: 520px;
            background: radial-gradient(circle, rgba(228,0,80,0.45) 0%, rgba(180,0,40,0.18) 45%, transparent 70%);
            border-radius: 50%;
            pointer-events: none;
            z-index: 0;
        }
        /* Gold/amber orb — top-right (matches reference yellow-gold accent) */
        .stApp::before {
            content: '';
            position: fixed;
            top: -80px; right: 5%;
            width: 480px; height: 480px;
            background: radial-gradient(circle, rgba(220,160,0,0.38) 0%, rgba(200,100,0,0.14) 45%, transparent 70%);
            border-radius: 50%;
            pointer-events: none;
            z-index: 0;
        }

        /* ── ANTI-BLINK ──────────────────────────────────────────────────── */
        /* 1) Kill the stale-fade: Streamlit dims fragment content while       */
        /*    it reruns. Force full opacity + no filter on every stale elem.   */
        [data-stale],[data-stale="true"] {
            opacity: 1 !important;
            filter: none !important;
            transition: none !important;
            transition-duration: 0ms !important;
            transition-delay: 0ms !important;
            animation: none !important;
            animation-duration: 0ms !important;
        }
        [data-stale] *,[data-stale="true"] * {
            filter: none !important;
            transition: none !important;
            animation: none !important;
        }
        /* 2) Kill the animated blue "running" border Streamlit draws around  */
        /*    the active fragment wrapper.                                     */
        [data-testid="stVerticalBlockBorderWrapper"] {
            border: none !important;
            outline: none !important;
            box-shadow: none !important;
            transition: none !important;
            transition-duration: 0ms !important;
            animation: none !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"][data-stale],
        [data-testid="stVerticalBlockBorderWrapper"][data-stale="true"],
        [data-testid="stVerticalBlockBorderWrapper"][data-running],
        [data-testid="stVerticalBlockBorderWrapper"][data-running="true"] {
            opacity: 1 !important;
            filter: none !important;
            border: none !important;
            outline: none !important;
            box-shadow: none !important;
            animation: none !important;
        }
        /* 3) Kill any Streamlit keyframe animation that drives the blue pulse */
        * { animation-duration: 0ms !important; }
        /* 4) Misc Streamlit update indicators */
        iframe[title="streamlit_plotly_events"] { display: none !important; }
        [data-testid="stStatusWidget"] { display: none !important; }
        [data-testid="stSpinner"]      { display: none !important; }
        [data-testid="stDecoration"]   { display: none !important; }
        /* 5) Plotly: no internal trace-update transition */
        .js-plotly-plot .plotly,
        .js-plotly-plot .plotly * { transition: none !important; animation: none !important; }

        /* ── Main content block — authentic glass panel ──────────────────── */
        .main .block-container,
        section[data-testid="stMainBlockContainer"] {
            position: relative;
            z-index: 1;
            background: rgba(255,255,255,0.07) !important;
            backdrop-filter: blur(28px) saturate(180%) !important;
            -webkit-backdrop-filter: blur(28px) saturate(180%) !important;
            border-radius: 20px !important;
            border: 1px solid rgba(255,255,255,0.18) !important;
            box-shadow:
                0 8px 32px rgba(31,38,135,0.30),
                inset 0 1px 0 rgba(255,255,255,0.28) !important;
            color: #E8E8F0;
            max-width: 100%;
        }

        /* ── Text defaults ───────────────────────────────────────────────── */
        .main p, .main span, .main div, .main label,
        [data-testid="stMarkdownContainer"] p,
        [data-testid="stMarkdownContainer"] span { color: #D0D0E8; }
        h1, h2, h3, h4, h5 { color: #F5F5F7 !important; }
        .stMetric label { color: #aaa !important; }

        /* ── SIDEBAR ─────────────────────────────────────────────────────── */
        [data-testid="stSidebar"] {
            background: rgba(10,6,28,0.72) !important;
            backdrop-filter: blur(32px) saturate(160%) !important;
            -webkit-backdrop-filter: blur(32px) saturate(160%) !important;
            border-right: 1px solid rgba(255,255,255,0.12) !important;
            box-shadow: inset -1px 0 0 rgba(255,255,255,0.06),
                        4px 0 24px rgba(31,38,135,0.15) !important;
        }
        [data-testid="stSidebar"],
        [data-testid="stSidebar"] * { color: #E8E8F0 !important; }

        [data-testid="stSidebar"] button {
            background: rgba(255,255,255,0.09) !important;
            backdrop-filter: blur(10px) !important;
            color: #E8E8F0 !important;
            border: 1px solid rgba(255,255,255,0.20) !important;
            border-radius: 9px !important;
            box-shadow: 0 2px 12px rgba(31,38,135,0.18),
                        inset 0 1px 0 rgba(255,255,255,0.16) !important;
        }
        [data-testid="stSidebar"] button:hover {
            background: rgba(255,255,255,0.18) !important;
            border-color: rgba(255,255,255,0.38) !important;
        }
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] select,
        [data-testid="stSidebar"] textarea {
            background: rgba(255,255,255,0.07) !important;
            color: #E8E8F0 !important;
            border: 1px solid rgba(255,255,255,0.16) !important;
            border-radius: 8px !important;
        }
        [data-testid="stSidebarNav"] a p { text-transform: capitalize; }
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 { color: #F5F5F7 !important; }

        /* ── BUTTONS (main area) ─────────────────────────────────────────── */
        [data-testid="baseButton-primary"] {
            background: linear-gradient(135deg, rgba(228,0,43,0.78), rgba(160,0,80,0.78)) !important;
            backdrop-filter: blur(12px) !important;
            border: 1px solid rgba(255,80,100,0.42) !important;
            box-shadow: 0 4px 18px rgba(228,0,43,0.32),
                        inset 0 1px 0 rgba(255,150,150,0.28) !important;
            color: #fff !important;
            border-radius: 10px !important;
            font-weight: 600 !important;
        }
        [data-testid="baseButton-primary"]:hover {
            background: linear-gradient(135deg, rgba(228,0,43,0.95), rgba(160,0,80,0.95)) !important;
            box-shadow: 0 6px 26px rgba(228,0,43,0.52),
                        inset 0 1px 0 rgba(255,150,150,0.38) !important;
        }
        [data-testid="baseButton-secondary"] {
            background: rgba(255,255,255,0.09) !important;
            backdrop-filter: blur(12px) !important;
            border: 1px solid rgba(255,255,255,0.22) !important;
            box-shadow: 0 2px 12px rgba(31,38,135,0.16),
                        inset 0 1px 0 rgba(255,255,255,0.18) !important;
            color: #E8E8F0 !important;
            border-radius: 10px !important;
        }
        [data-testid="baseButton-secondary"]:hover {
            background: rgba(255,255,255,0.18) !important;
            border-color: rgba(255,255,255,0.38) !important;
        }
        button { border-radius: 10px !important; }

        /* ── INPUTS / FORMS ──────────────────────────────────────────────── */
        input[type="text"],
        input[type="password"],
        input[type="email"],
        input[type="number"],
        input[type="search"] {
            background: rgba(12,8,32,0.75) !important;
            color: #E8E8F0 !important;
            border: 1px solid rgba(255,255,255,0.20) !important;
            border-radius: 8px !important;
            caret-color: #E8E8F0 !important;
            backdrop-filter: blur(8px) !important;
        }
        input::placeholder { color: rgba(200,200,210,0.40) !important; }
        .stTextInput input, .stTextArea textarea,
        [data-testid="stTextInput"] input,
        [data-testid="stTextAreaRootElement"] textarea {
            background: rgba(12,8,32,0.75) !important;
            color: #E8E8F0 !important;
            border: 1px solid rgba(255,255,255,0.20) !important;
        }
        .stTextArea textarea { color: #E8E8F0 !important; }
        .stSelectbox > div > div,
        [data-baseweb="select"] > div {
            background: rgba(12,8,32,0.75) !important;
            border: 1px solid rgba(255,255,255,0.20) !important;
            color: #E8E8F0 !important;
            backdrop-filter: blur(8px) !important;
        }
        [data-testid="stNumberInput"] input {
            color: #E8E8F0 !important;
            background: rgba(12,8,32,0.75) !important;
        }

        /* ── TABS ────────────────────────────────────────────────────────── */
        [data-testid="stTabs"] button {
            background: rgba(255,255,255,0.06) !important;
            backdrop-filter: blur(10px) !important;
            border-bottom: 1px solid rgba(255,255,255,0.10) !important;
            color: #aaa !important;
            font-weight: 500 !important;
        }
        [data-testid="stTabs"] button[aria-selected="true"] {
            background: rgba(228,0,43,0.22) !important;
            backdrop-filter: blur(10px) !important;
            border-bottom: 2px solid #E4002B !important;
            box-shadow: inset 0 1px 0 rgba(255,80,80,0.28) !important;
            color: #fff !important;
        }

        /* ── CARDS ───────────────────────────────────────────────────────── */
        .mp-card {
            background: rgba(255,255,255,0.10) !important;
            backdrop-filter: blur(22px) saturate(155%) !important;
            -webkit-backdrop-filter: blur(22px) saturate(155%) !important;
            border: 1px solid rgba(255,255,255,0.22) !important;
            border-radius: 18px !important;
            box-shadow:
                0 8px 32px rgba(31,38,135,0.30),
                inset 0 1px 0 rgba(255,255,255,0.28) !important;
            padding: 20px;
            margin-bottom: 16px;
            color: #E8E8F0 !important;
        }
        .mp-kpi {
            background: rgba(255,255,255,0.08) !important;
            backdrop-filter: blur(16px) saturate(140%) !important;
            -webkit-backdrop-filter: blur(16px) saturate(140%) !important;
            border: 1px solid rgba(255,255,255,0.18) !important;
            border-radius: 14px !important;
            padding: 16px 20px;
            border-left: 3px solid #E4002B !important;
            box-shadow:
                0 4px 20px rgba(31,38,135,0.24),
                inset 0 1px 0 rgba(255,255,255,0.22) !important;
            margin-bottom: 8px;
        }
        .mp-kpi-value { font-size: 28px; font-weight: 700; color: #F5F5F7 !important; }
        .mp-kpi-label { font-size: 13px; color: #9090b0 !important; margin-top: 2px; }

        /* ── STATUS BADGES ───────────────────────────────────────────────── */
        .mp-status-badge {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
            backdrop-filter: blur(8px);
        }
        .status-connected    { background:rgba(40,200,100,0.18)!important; color:#7fff7f!important; border:1px solid rgba(40,200,100,0.40)!important; }
        .status-disconnected { background:rgba(220,53,69,0.18)!important;  color:#ff9999!important; border:1px solid rgba(220,53,69,0.40)!important; }
        .status-scanning     { background:rgba(255,193,7,0.18)!important;  color:#ffe066!important; border:1px solid rgba(255,193,7,0.40)!important; }
        .status-error        { background:rgba(220,53,69,0.18)!important;  color:#ff9999!important; border:1px solid rgba(220,53,69,0.40)!important; }

        /* ── EXPANDERS ────────────────────────────────────────────────────- */
        [data-testid="stExpander"] {
            background: rgba(255,255,255,0.07) !important;
            backdrop-filter: blur(16px) !important;
            border: 1px solid rgba(255,255,255,0.16) !important;
            border-radius: 14px !important;
            box-shadow: 0 4px 20px rgba(31,38,135,0.18),
                        inset 0 1px 0 rgba(255,255,255,0.14) !important;
        }
        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] [data-testid="stExpanderToggleIcon"],
        .streamlit-expanderHeader {
            background: rgba(255,255,255,0.05) !important;
            color: #E8E8F0 !important;
            border-radius: 12px !important;
        }
        [data-testid="stExpander"] p,
        [data-testid="stExpander"] li,
        [data-testid="stExpander"] ul,
        [data-testid="stExpander"] ol,
        [data-testid="stExpander"] span,
        [data-testid="stExpander"] div,
        [data-testid="stExpander"] label { color: #D0D0E8 !important; }

        /* ── UNIVERSAL TEXT ─────────────────────────────────────────────── */
        .main li, .main ul, .main ol { color: #D0D0E8 !important; }
        label, .stLabel { color: #D0D0E8 !important; }
        [data-testid="stWidgetLabel"] p,
        [data-testid="stWidgetLabel"] span { color: #D0D0E8 !important; }
        [data-testid="stCheckbox"] span, [data-testid="stCheckbox"] p,
        [data-testid="stRadio"] span,    [data-testid="stRadio"] p,
        [data-testid="stToggle"] span,   [data-testid="stToggle"] p { color: #D0D0E8 !important; }
        [data-testid="stSlider"] label,
        [data-testid="stSlider"] span,
        [data-testid="stSlider"] p { color: #D0D0E8 !important; }
        [data-testid="stTickBarMin"],
        [data-testid="stTickBarMax"] { color: #9090b0 !important; }
        [data-testid="stSelectbox"] span,
        [data-testid="stSelectbox"] div { color: #D0D0E8 !important; }
        [data-baseweb="select"] span,
        [data-baseweb="select"] div { color: #D0D0E8 !important; }
        [data-baseweb="popover"] li,
        [data-baseweb="popover"] span,
        [data-baseweb="menu"] li,
        [data-baseweb="menu"] span,
        [data-baseweb="select"] [role="option"] span { color: #E8E8F0 !important; }
        [data-baseweb="popover"],
        [data-baseweb="menu"] { background: rgba(15,10,38,0.98) !important; }
        [data-baseweb="menu"] li:hover,
        [data-baseweb="popover"] li:hover { background: rgba(255,255,255,0.10) !important; }
        [data-baseweb="select"] [role="listbox"] { background: rgba(15,10,38,0.98) !important; }
        [data-testid="stCaptionContainer"] p { color: #9090b0 !important; }
        [data-testid="stMarkdownContainer"] li { color: #D0D0E8 !important; }
        [data-testid="stMarkdownContainer"] a { color: #a0b8ff !important; }
        [data-testid="stMarkdownContainer"] code {
            background: rgba(255,255,255,0.12) !important;
            color: #FFD700 !important;
            border-radius: 4px !important;
        }
        [data-testid="stMetricValue"] { color: #F5F5F7 !important; }
        [data-testid="stMetricLabel"] { color: #9090b0 !important; }
        .stSelectSlider span { color: #D0D0E8 !important; }

        /* ── FORMS ───────────────────────────────────────────────────────── */
        [data-testid="stForm"] {
            background: rgba(255,255,255,0.07) !important;
            backdrop-filter: blur(16px) !important;
            border: 1px solid rgba(255,255,255,0.16) !important;
            border-radius: 14px !important;
            box-shadow: 0 4px 20px rgba(31,38,135,0.18),
                        inset 0 1px 0 rgba(255,255,255,0.16) !important;
        }

        /* ── MISC ────────────────────────────────────────────────────────── */
        [data-testid="stDivider"] { border-color: rgba(255,255,255,0.10) !important; }
        .glass-panel {
            background: rgba(255,255,255,0.09);
            backdrop-filter: blur(22px) saturate(150%);
            -webkit-backdrop-filter: blur(22px) saturate(150%);
            border: 1px solid rgba(255,255,255,0.22);
            border-radius: 18px;
            box-shadow: 0 8px 32px rgba(31,38,135,0.26),
                        inset 0 1px 0 rgba(255,255,255,0.26);
            padding: 16px;
            margin-bottom: 12px;
        }
        [data-testid="stAlert"] {
            background: rgba(255,255,255,0.08) !important;
            backdrop-filter: blur(14px) !important;
            border: 1px solid rgba(255,255,255,0.18) !important;
            border-radius: 12px !important;
            box-shadow: 0 4px 16px rgba(31,38,135,0.18) !important;
        }
        [data-testid="stAlert"] p,
        [data-testid="stAlert"] span,
        [data-testid="stAlert"] div { color: #E8E8F0 !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# KPI card
# ---------------------------------------------------------------------------

def kpi_card(
    label: str,
    value: Any,
    unit: str = "",
    border_color: str = RED,
    fmt: str = "",
) -> None:
    if isinstance(value, float) and fmt:
        display = f"{value:{fmt}}{unit}"
    elif value is None:
        display = "—"
    else:
        display = f"{value}{unit}"
    st.markdown(
        f"""
        <div class="mp-kpi" style="border-left-color:{border_color}">
            <div class="mp-kpi-value">{display}</div>
            <div class="mp-kpi-label">{label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Sensor status widget
# ---------------------------------------------------------------------------

def sensor_status_widget(state: str, sensor_name: str = "", battery: int = -1) -> None:
    css_class = {
        "connected": "status-connected",
        "scanning": "status-scanning",
        "connecting": "status-scanning",
        "disconnected": "status-disconnected",
        "error": "status-error",
    }.get(state, "status-disconnected")

    badge = f'<span class="mp-status-badge {css_class}">{state.upper()}</span>'
    name_html = f"<strong>{sensor_name}</strong> &nbsp;" if sensor_name else ""
    batt_html = f"🔋 {battery}%" if battery >= 0 else ""

    batt_color = SUCCESS if battery > 20 else (WARNING if battery > 10 else ERROR)
    batt_style = f"color:{batt_color}; font-weight:600;" if battery >= 0 else ""

    st.markdown(
        f"""
        <div class="mp-card" style="padding:12px 20px;">
            {badge} &nbsp; {name_html}
            <span style="{batt_style}">{batt_html}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Live power bar
# ---------------------------------------------------------------------------

def power_bar(
    current_power: float,
    max_power: float = 0.005,
    label: str = "Muscle Power",
    height: int = 180,
) -> None:
    """Vertical colour-gradient power bar showing current muscle activation."""
    pct = min(1.0, float(current_power) / float(max_power) if max_power > 0 else 0.0)
    if pct < 0.33:
        bar_color = SUCCESS
    elif pct < 0.66:
        bar_color = WARNING
    else:
        bar_color = RED

    fig = go.Figure(
        go.Bar(
            x=["Power"],
            y=[pct * 100],
            marker=dict(color=bar_color, line=dict(width=0)),
            width=[0.5],
            text=[f"{pct*100:.1f}%"],
            textposition="outside",
        )
    )
    fig.update_layout(
        height=height,
        paper_bgcolor="white",
        plot_bgcolor=LIGHT,
        margin=dict(l=20, r=20, t=30, b=20),
        yaxis=dict(range=[0, 110], showgrid=True, gridcolor="#E0E0E0", title=""),
        xaxis=dict(showticklabels=True),
        title=dict(text=label, font=dict(color=DARK, size=13)),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=False)


# ---------------------------------------------------------------------------
# Live signal chart
# ---------------------------------------------------------------------------

def signal_chart(
    raw_times: list[float],
    raw_values: list[float],
    envelope_times: list[float],
    envelope_values: list[float],
    show_raw: bool = True,
    show_envelope: bool = True,
    height: int = 280,
    title: str = "Live EMG Signal",
) -> None:
    """Real-time scrolling chart with raw EMG and amplitude envelope."""
    traces = []
    if show_raw and raw_times:
        traces.append(
            go.Scatter(
                x=raw_times,
                y=raw_values,
                mode="lines",
                name="Raw EMG",
                line=dict(color="#0D6EFD", width=1),
                opacity=0.7,
            )
        )
    if show_envelope and envelope_times:
        traces.append(
            go.Scatter(
                x=envelope_times,
                y=envelope_values,
                mode="lines",
                name="Envelope",
                line=dict(color=RED, width=2.5),
                fill="tozeroy",
                fillcolor="rgba(228,0,43,0.10)",
            )
        )

    fig = go.Figure(data=traces)
    fig.update_layout(
        height=height,
        paper_bgcolor="white",
        plot_bgcolor=LIGHT,
        margin=dict(l=50, r=20, t=35, b=35),
        title=dict(text=title, font=dict(color=DARK, size=13)),
        xaxis=dict(title="Time (s)", color=DARK, showgrid=True, gridcolor="#E0E0E0"),
        yaxis=dict(title="Amplitude (V)", color=DARK, showgrid=True, gridcolor="#E0E0E0"),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# History comparison chart
# ---------------------------------------------------------------------------

def comparison_chart(
    sessions: list[dict[str, Any]],
    metric: str = "avg_power",
    height: int = 320,
) -> None:
    """Overlay multiple sessions for comparison."""
    if not sessions:
        st.info("No sessions to compare.")
        return

    colors = [RED, INFO, SUCCESS, WARNING, SLATE, DARK]
    traces = []
    for i, sess in enumerate(sessions):
        label = f"{sess.get('date', '')[:10]} — {sess.get('muscle_group', '')}"
        traces.append(
            go.Bar(
                name=label,
                x=[label],
                y=[sess.get(metric) or 0],
                marker_color=colors[i % len(colors)],
            )
        )

    fig = go.Figure(data=traces)
    fig.update_layout(
        height=height,
        paper_bgcolor="white",
        plot_bgcolor=LIGHT,
        margin=dict(l=50, r=20, t=35, b=35),
        title=dict(text=f"Comparison — {metric.replace('_', ' ').title()}", font=dict(color=DARK, size=13)),
        yaxis=dict(title=metric.replace("_", " ").title(), color=DARK, showgrid=True, gridcolor="#E0E0E0"),
        xaxis=dict(showticklabels=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
        barmode="group",
    )
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# FFT Frequency spectrum chart
# ---------------------------------------------------------------------------

def fft_chart(
    freqs: list[float],
    magnitudes: list[float],
    median_freq: float = 0.0,
    height: int = 220,
) -> None:
    traces = [
        go.Scatter(
            x=freqs,
            y=magnitudes,
            mode="lines",
            name="Spectrum",
            line=dict(color=INFO, width=1.5),
            fill="tozeroy",
            fillcolor=f"rgba(13,110,253,0.12)",
        )
    ]
    if median_freq > 0:
        traces.append(
            go.Scatter(
                x=[median_freq, median_freq],
                y=[0, max(magnitudes) if magnitudes else 1],
                mode="lines",
                name=f"Median Freq {median_freq:.1f} Hz",
                line=dict(color=RED, width=2, dash="dash"),
            )
        )
    fig = go.Figure(data=traces)
    fig.update_layout(
        height=height,
        paper_bgcolor="white",
        plot_bgcolor=LIGHT,
        margin=dict(l=50, r=20, t=35, b=35),
        title=dict(text="Frequency Spectrum (FFT)", font=dict(color=DARK, size=13)),
        xaxis=dict(title="Frequency (Hz)", range=[0, 500], color=DARK, showgrid=True, gridcolor="#E0E0E0"),
        yaxis=dict(title="Magnitude", color=DARK, showgrid=True, gridcolor="#E0E0E0"),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
    )
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Trend line chart
# ---------------------------------------------------------------------------

def trend_chart(
    sessions: list[dict[str, Any]],
    metric: str = "avg_power",
    height: int = 280,
) -> None:
    if not sessions:
        return
    dates = [s.get("date", "")[:10] for s in sessions]
    values = [s.get(metric) or 0 for s in sessions]

    traces = [
        go.Scatter(
            x=dates,
            y=values,
            mode="lines+markers",
            name=metric.replace("_", " ").title(),
            line=dict(color=RED, width=2),
            marker=dict(size=7, color=RED),
        )
    ]
    # Trendline
    if len(values) >= 3:
        x_num = list(range(len(values)))
        coeffs = np.polyfit(x_num, values, 1)
        trend = np.polyval(coeffs, x_num)
        traces.append(
            go.Scatter(
                x=dates,
                y=list(trend),
                mode="lines",
                name="Trend",
                line=dict(color=SLATE, width=1.5, dash="dot"),
            )
        )

    fig = go.Figure(data=traces)
    fig.update_layout(
        height=height,
        paper_bgcolor="white",
        plot_bgcolor=LIGHT,
        margin=dict(l=50, r=20, t=35, b=35),
        title=dict(
            text=f"Progress — {metric.replace('_', ' ').title()}",
            font=dict(color=DARK, size=13),
        ),
        xaxis=dict(title="Date", color=DARK, showgrid=True, gridcolor="#E0E0E0"),
        yaxis=dict(
            title=metric.replace("_", " ").title(),
            color=DARK,
            showgrid=True,
            gridcolor="#E0E0E0",
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
    )
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Toast / alert helpers
# ---------------------------------------------------------------------------

def toast_success(msg: str) -> None:
    st.toast(f"✅ {msg}", icon="✅")


def toast_error(msg: str) -> None:
    st.toast(f"❌ {msg}", icon="❌")


def toast_warning(msg: str) -> None:
    st.toast(f"⚠️ {msg}", icon="⚠️")


def show_error_card(msg: str, correlation_id: str = "") -> None:
    cid_html = f"<br><small style='color:#999'>Error ID: {correlation_id}</small>" if correlation_id else ""
    st.markdown(
        f"""
        <div style="background:#f8d7da;border-left:4px solid {ERROR};
                    border-radius:6px;padding:12px 16px;margin:8px 0;">
            ❌ {msg}{cid_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_warning_card(msg: str) -> None:
    st.markdown(
        f"""
        <div style="background:rgba(180,40,40,0.22);border-left:4px solid {ERROR};
                    border:1px solid rgba(220,53,69,0.45);
                    border-radius:8px;padding:12px 16px;margin:8px 0;
                    color:#ffaaaa;">
            ⚠️ {msg}
        </div>
        """,
        unsafe_allow_html=True,
    )


def electrode_quality_indicator(state: str) -> None:
    color_map = {
        "Normal": (SUCCESS, "🟢 Normal — good contact"),
        "Detached": (WARNING, "🟡 Detached — poor contact"),
        "HighResistance": (ERROR, "🔴 High Resistance — no contact"),
        "Unknown": (SLATE, "⚪ Unknown"),
    }
    color, label = color_map.get(state, (SLATE, f"⚪ {state}"))
    st.markdown(
        f'<span style="color:{color};font-weight:600">{label}</span>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# User sidebar widget (shows who is logged in + logout button)
# ---------------------------------------------------------------------------

def user_sidebar_widget() -> None:
    """Render the logged-in user badge and logout button inside a st.sidebar block."""
    display = st.session_state.get("current_display_name") or st.session_state.get("current_username", "")
    if not display:
        return
    st.markdown(
        f"<div style='padding:8px 0'>"
        f"<span style='font-size:20px'>👤</span> "
        f"<strong>{display}</strong>"
        f"</div>",
        unsafe_allow_html=True,
    )
    if st.button("🚪 Logout", use_container_width=True, key="_sidebar_logout"):
        for key in ("current_user_id", "current_username", "current_display_name"):
            st.session_state.pop(key, None)
        st.rerun()


# ---------------------------------------------------------------------------
# Login / Register form  (shown when user is not authenticated)
# ---------------------------------------------------------------------------

def show_auth_page() -> None:
    """Render the account-selector form and call st.stop() until the user picks an account.

    No password is required — users simply select their name from a list.
    """
    if st.session_state.get("current_user_id"):
        return  # Already logged in — nothing to do

    # Allow scrolling on the login page
    st.markdown(
        "<style>html,body,[data-testid='stMain'],.main{overflow:auto!important;}</style>",
        unsafe_allow_html=True,
    )

    from muscle_power.services.auth_service import (
        UserExistsError, list_users, register_user,
    )
    from muscle_power.services.user_settings import (
        load_user_settings,
        PANEL_DEFAULTS,
    )

    st.markdown(
        f"<h1 style='color:{RED};text-align:center'>💪 Muscle Power</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='text-align:center;color:#aaa'>Choose your account to continue.</p>",
        unsafe_allow_html=True,
    )
    st.divider()

    users = list_users()

    if users:
        st.markdown("#### Select account")
        label_to_user = {u["display_name"]: u for u in users}
        selected_label = st.selectbox(
            "Account",
            list(label_to_user.keys()),
            label_visibility="collapsed",
        )
        selected = label_to_user[selected_label]

        if st.button(f"▶  Enter as {selected_label}", use_container_width=True, type="primary"):
            st.session_state["current_user_id"] = selected["id"]
            st.session_state["current_username"] = selected["username"]
            st.session_state["current_display_name"] = selected["display_name"]
            # Restore user-specific settings — use PANEL_DEFAULTS as fallback so
            # a new user never inherits another user's session state.
            for k, v in load_user_settings(selected["id"], PANEL_DEFAULTS).items():
                st.session_state[k] = v
            # Clear _prev_settings so the auto-save diff starts fresh for this user.
            st.session_state.pop("_prev_settings", None)
            st.rerun()

        st.divider()
    else:
        st.info("No accounts exist yet. Create one below to get started.")

    with st.expander("➕  Create new account", expanded=not bool(users)):
        with st.form("create_account_form", clear_on_submit=True):
            new_uname = st.text_input("Username", placeholder="e.g. alex")
            new_display = st.text_input("Display name (optional)", placeholder="e.g. Alex")
            submitted = st.form_submit_button("Create Account", use_container_width=True, type="primary")
        if submitted:
            if not new_uname:
                st.error("Username is required.")
            else:
                try:
                    user = register_user(new_uname.strip(), display_name=new_display.strip())
                    st.session_state["current_user_id"] = user["id"]
                    st.session_state["current_username"] = user["username"]
                    st.session_state["current_display_name"] = user["display_name"]
                    # New user — seed their settings with canonical defaults
                    from muscle_power.services.user_settings import save_user_settings as _save
                    _save(user["id"], PANEL_DEFAULTS)
                    for k, v in PANEL_DEFAULTS.items():
                        st.session_state[k] = v
                    st.session_state.pop("_prev_settings", None)
                    st.success(f"Account created! Welcome, {user['display_name']}.")
                    st.rerun()
                except UserExistsError as exc:
                    st.error(str(exc))
                except ValueError as exc:
                    st.error(str(exc))

    st.stop()  # Block the rest of the page until logged in


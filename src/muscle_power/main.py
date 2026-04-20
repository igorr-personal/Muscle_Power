"""Muscle Power — home page and app bootstrap."""
from __future__ import annotations

import streamlit as st

from muscle_power.components.ui import inject_css, kpi_card, RED, show_auth_page, user_sidebar_widget
from muscle_power.db.database import init_db
from muscle_power.db.migrations import run_migrations
from muscle_power.utils.config import get_config
from muscle_power.utils.logger import setup_logging

# ---------------------------------------------------------------------------
# Bootstrap (runs once per process)
# ---------------------------------------------------------------------------

cfg = get_config()
setup_logging(cfg.log_level)

try:
    run_migrations()
except Exception as _exc:
    pass  # non-fatal on startup; error shown in UI if needed

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Muscle Power",
    page_icon="💪",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()

# ---------------------------------------------------------------------------
# Authentication gate
# ---------------------------------------------------------------------------
show_auth_page()  # stops here and shows login form if not logged in

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
if "initialized" not in st.session_state:
    st.session_state.initialized = True
    st.session_state.sensor_state = "disconnected"
    st.session_state.session_state = "IDLE"
    st.session_state.current_session_id = None
    st.session_state.filters = {}
    st.session_state.cache_timestamp = None
    st.session_state.last_refresh = None

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        f"<h2 style='color:{RED};margin-bottom:4px'>💪 Muscle Power</h2>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<small style='color:#888'>Callibri EMG Sensor Dashboard</small>",
        unsafe_allow_html=True,
    )
    st.divider()
    user_sidebar_widget()
    st.divider()

    sensor_state = st.session_state.get("sensor_state", "disconnected")
    badge_color = {
        "connected": "#28A745",
        "scanning": "#FFC107",
        "connecting": "#FFC107",
        "disconnected": "#DC3545",
        "error": "#DC3545",
    }.get(sensor_state, "#DC3545")
    st.markdown(
        f"<span style='color:{badge_color};font-weight:700'>&#9679; {sensor_state.upper()}</span>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------
st.title("Main")
st.markdown("Real-time EMG muscle activation monitoring powered by the Callibri sensor.")

st.divider()

col1, col2, col3, col4 = st.columns(4)
with col1:
    kpi_card(
        "Sensor Status",
        st.session_state.get("sensor_state", "disconnected").upper(),
        border_color=RED,
    )
with col2:
    kpi_card(
        "Session Status",
        st.session_state.get("session_state", "IDLE"),
        border_color="#0D6EFD",
    )
with col3:
    kpi_card(
        "Current Power",
        st.session_state.get("current_power"),
        unit=" V",
        fmt=".5f",
        border_color="#28A745",
    )
with col4:
    kpi_card(
        "Battery",
        st.session_state.get("battery_pct", -1),
        unit="%",
        border_color="#FFC107",
    )

st.divider()

# Quick action cards
c1, c2, c3 = st.columns(3)
with c1:
    st.markdown(
        """
        <div class="mp-card">
            <h4>💪 Start a Workout</h4>
            <p>Connect your Callibri sensor and begin a real-time EMG recording session.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("→ Go to Live Session", key="home_live"):
        st.switch_page("pages/1_Live_Session.py")

with c2:
    st.markdown(
        """
        <div class="mp-card">
            <h4>📊 View History</h4>
            <p>Browse past sessions, compare muscle power across days or weeks.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("→ Go to History", key="home_history"):
        st.switch_page("pages/2_Workout_History.py")

with c3:
    st.markdown(
        """
        <div class="mp-card">
            <h4>📤 Export Data</h4>
            <p>Download your workout data as CSV, Excel, or PDF report.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("→ Go to Export", key="home_export"):
        st.switch_page("pages/3_Export.py")

# Getting-started guide
with st.expander("ℹ️ Getting Started", expanded=True):
    st.markdown(
        """
        **Quick setup steps:**
        1. Power on your Callibri sensor (check the LED).
        2. Enable Bluetooth on this computer.
        3. Go to **💪 Live Session** and click **Scan for Sensors**.
        4. Select your sensor from the list and click **Connect**.
        5. Attach the electrodes to the target muscle.
        6. Click **Start Recording** — watch the live power bar!

        **Sensor LED meanings:**
        - 🔵 Blue slow blink — ready to pair
        - 🟢 Green — connected and recording
        - 🔴 Red — low battery

        **Supported platforms:** Windows 10+, macOS 10.14+
        """
    )

st.caption(f"Configuration: env={cfg.env}  |  db={cfg.database.url.split('///')[-1]}")

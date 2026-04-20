"""Workout History page — browse, compare, and analyse past sessions."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from muscle_power.components.ui import (
    RED, comparison_chart, inject_css, kpi_card, show_auth_page, show_error_card,
    toast_success, toast_warning, trend_chart, user_sidebar_widget,
)
from muscle_power.services.workout_tracking import get_tracker
from muscle_power.utils.errors import DatabaseError

# ---------------------------------------------------------------------------
# Page set-up
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Workout History · Muscle Power", page_icon="📊", layout="wide")
inject_css()

tracker = get_tracker()

# Auth gate
show_auth_page()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(f"<h2 style='color:{RED}'>💪 Muscle Power</h2>", unsafe_allow_html=True)
    st.divider()
    user_sidebar_widget()
    st.divider()

    st.subheader("Filters")
    date_range = st.date_input(
        "Date range",
        value=(datetime.now(tz=timezone.utc).date() - timedelta(days=30),
               datetime.now(tz=timezone.utc).date()),
        key="hist_date_range",
    )
    muscle_filter = st.text_input("Muscle group", placeholder="leave blank for all", key="muscle_filter")
    days_filter = None
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start_d, end_d = date_range
        days_filter = (end_d - start_d).days + 1

    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
@st.cache_data(ttl=900)
def _load_sessions(muscle_group: str, days: int | None, user_id: int | None) -> list[dict]:
    try:
        return tracker.get_sessions(
            muscle_group=muscle_group or None,
            days=days,
            user_id=user_id,
        )
    except Exception:
        return []


try:
    sessions = _load_sessions(muscle_filter, days_filter, st.session_state.get("current_user_id"))
except Exception as e:
    show_error_card(f"Failed to load sessions: {e}")
    sessions = []

# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------
st.title("📊 Workout History")

if not sessions:
    st.info("No workout sessions found. Go to **💪 Live Session** to record your first session!")
    st.stop()

df = pd.DataFrame(sessions)
df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d %H:%M")

# --- Summary KPIs ---
c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("Total Sessions", len(sessions))
with c2:
    avg_p = df["avg_power"].dropna()
    kpi_card("Avg Power (V)", float(avg_p.mean()) if len(avg_p) else None, fmt=".5f")
with c3:
    peak_p = df["peak_power"].dropna()
    kpi_card("Peak Power (V)", float(peak_p.max()) if len(peak_p) else None, fmt=".5f")
with c4:
    dur = df["duration_seconds"].dropna()
    kpi_card("Avg Duration (s)", float(dur.mean()) if len(dur) else None, fmt=".0f")

st.divider()

# --- Trend chart ---
tab1, tab2, tab3 = st.tabs(["📈 Progress Trend", "📊 Session Comparison", "📋 Session Table"])

with tab1:
    metric_choice = st.selectbox(
        "Metric",
        ["avg_power", "peak_power", "duration_seconds", "fatigue_index", "rep_count"],
        format_func=lambda x: x.replace("_", " ").title(),
        key="trend_metric",
    )
    trend_chart(sessions, metric=metric_choice)

with tab2:
    st.markdown("Select sessions to compare (up to 6):")
    session_labels = [
        f"{s.get('date','')[:10]} — {s.get('muscle_group','')} ({s.get('sensor_id','')[:8]})"
        for s in sessions
    ]
    compare_sel = st.multiselect(
        "Sessions to compare",
        options=session_labels,
        max_selections=6,
        key="compare_sel",
    )
    if compare_sel:
        indices = [session_labels.index(l) for l in compare_sel if l in session_labels]
        selected_for_compare = [sessions[i] for i in indices]
        metric_cmp = st.selectbox(
            "Comparison metric",
            ["avg_power", "peak_power", "duration_seconds", "rep_count"],
            format_func=lambda x: x.replace("_", " ").title(),
            key="cmp_metric",
        )
        comparison_chart(selected_for_compare, metric=metric_cmp)
    else:
        st.info("Select sessions above to compare them side-by-side.")

with tab3:
    # Sortable / filterable table
    display_cols = ["date", "muscle_group", "duration_seconds", "avg_power", "peak_power",
                    "fatigue_index", "rep_count", "notes"]
    display_cols = [c for c in display_cols if c in df.columns]
    disp_df = df[display_cols].copy()
    disp_df.columns = [c.replace("_", " ").title() for c in display_cols]

    st.dataframe(
        disp_df,
        use_container_width=True,
        height=400,
        column_config={
            "Avg Power": st.column_config.NumberColumn(format="%.6f"),
            "Peak Power": st.column_config.NumberColumn(format="%.6f"),
            "Duration Seconds": st.column_config.NumberColumn(format="%.0f"),
            "Fatigue Index": st.column_config.NumberColumn(format="%.3f"),
        },
    )

    # ── Drill-down ──
    if "id" in df.columns:
        _sess_labels = [
            f"#{s.get('id')}  {s.get('date','')[:16]}  —  {s.get('muscle_group','(no name)')}"
            for s in sessions
        ]
        sel_label = st.selectbox(
            "Session details",
            options=["— select —"] + _sess_labels,
            key="drill_id",
        )
        if sel_label and sel_label != "— select —":
            _sel_idx = _sess_labels.index(sel_label)
            sess_row = sessions[_sel_idx]
            sel_id_str = str(sess_row.get("id"))

            st.divider()
            # ── Rename row ──
            _rc1, _rc2 = st.columns([4, 1])
            with _rc1:
                _new_name = st.text_input(
                    "Recording name",
                    value=sess_row.get("muscle_group", ""),
                    key=f"rename_{sel_id_str}",
                    placeholder="Enter new name",
                )
            with _rc2:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                if st.button("✏️ Rename", key=f"rename_btn_{sel_id_str}", use_container_width=True):
                    if _new_name.strip():
                        tracker.rename_session(int(sel_id_str), _new_name.strip())
                        toast_success(f"Renamed to '{_new_name.strip()}'")
                        st.cache_data.clear()
                        st.rerun()

            # ── Measured values ──
            st.markdown("**Measured values**")
            _mv1, _mv2, _mv3, _mv4, _mv5 = st.columns(5)
            def _fmt(v, fmt="%.5f"):
                return fmt % v if v is not None else "—"
            with _mv1:
                kpi_card("Duration", _fmt(sess_row.get("duration_seconds"), "%.0f s"))
            with _mv2:
                kpi_card("Avg Power (V)", _fmt(sess_row.get("avg_power")))
            with _mv3:
                kpi_card("Peak Power (V)", _fmt(sess_row.get("peak_power")))
            with _mv4:
                kpi_card("Fatigue Index", _fmt(sess_row.get("fatigue_index"), "%.3f"))
            with _mv5:
                kpi_card("Rep Count", str(sess_row.get("rep_count") or "—"))

            if sess_row.get("notes"):
                st.info(f"📝 {sess_row['notes']}")

            # ── Delete ──
            with st.expander("⚠️ Delete this session"):
                _confirm = st.checkbox("Confirm permanent deletion", key=f"conf_{sel_id_str}")
                if st.button("🗑️ Delete", key=f"del_{sel_id_str}", type="primary"):
                    if _confirm:
                        try:
                            tracker.soft_delete_session(int(sel_id_str))
                            toast_success(f"Session #{sel_id_str} deleted.")
                            st.cache_data.clear()
                            st.rerun()
                        except DatabaseError as exc:
                            show_error_card(str(exc))
                    else:
                        toast_warning("Check the confirmation box first.")

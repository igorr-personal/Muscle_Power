"""Export page — download sessions as CSV, Excel, or PDF."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import streamlit as st

from muscle_power.components.ui import RED, inject_css, show_auth_page, show_error_card, toast_success, user_sidebar_widget
from muscle_power.services.data_io import get_export_bytes, import_sessions_csv, import_sessions_excel
from muscle_power.services.workout_tracking import get_tracker
from muscle_power.utils.errors import DataImportError, ExportError

# ---------------------------------------------------------------------------
# Page set-up
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Export · Muscle Power", page_icon="📤", layout="wide")
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

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
st.title("📤 Export & Import")

tab_export, tab_import = st.tabs(["📤 Export", "📥 Import"])

# =========================================================================
# EXPORT
# =========================================================================
with tab_export:
    st.subheader("Export Workout Sessions")

    col1, col2 = st.columns(2)
    with col1:
        date_range = st.date_input(
            "Date range",
            value=(
                datetime.now(tz=timezone.utc).date() - timedelta(days=90),
                datetime.now(tz=timezone.utc).date(),
            ),
            key="export_dates",
        )
    with col2:
        muscle_filter = st.text_input("Muscle group (leave blank = all)", key="exp_muscle")

    fmt = st.radio("Export format", ["CSV", "Excel (.xlsx)", "PDF"], horizontal=True, key="exp_fmt")
    fmt_map = {"CSV": "csv", "Excel (.xlsx)": "xlsx", "PDF": "pdf"}
    ext = fmt_map[fmt]

    days_filter = None
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        days_filter = (date_range[1] - date_range[0]).days + 1

    if st.button("📦 Prepare Export", type="primary"):
        with st.spinner("Preparing export…"):
            try:
                sessions = tracker.get_sessions(
                    muscle_group=muscle_filter or None,
                    days=days_filter,
                    user_id=st.session_state.get("current_user_id"),
                )
                if not sessions:
                    st.warning("No sessions match the selected filters.")
                else:
                    data = get_export_bytes(sessions, fmt=ext)
                    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
                    filename = f"muscle_power_{ts}.{ext}"
                    mime_map = {
                        "csv": "text/csv",
                        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "pdf": "application/pdf",
                    }
                    st.download_button(
                        label=f"⬇ Download {filename}",
                        data=data,
                        file_name=filename,
                        mime=mime_map[ext],
                    )
                    st.success(f"✅ {len(sessions)} sessions ready to download.")
            except ExportError as exc:
                show_error_card(str(exc))

# =========================================================================
# IMPORT
# =========================================================================
with tab_import:
    st.subheader("Import Historical Sessions")
    st.markdown(
        "Upload a **CSV or Excel** file with columns: "
        "`date`, `muscle_group`, `sensor_id`, `duration_seconds`, "
        "`avg_power`, `peak_power`, `notes`."
    )

    uploaded = st.file_uploader(
        "Choose a CSV or Excel file",
        type=["csv", "xlsx"],
        key="import_file",
    )
    deduplicate = st.checkbox("Remove duplicate rows", value=True, key="import_dedup")

    if uploaded is not None:
        import tempfile, pathlib
        suffix = pathlib.Path(uploaded.name).suffix.lower()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(uploaded.read())
            tmp_path = tmp.name

        with st.spinner("Validating file…"):
            try:
                if suffix == ".csv":
                    rows = import_sessions_csv(tmp_path, deduplicate=deduplicate)
                else:
                    rows = import_sessions_excel(tmp_path, deduplicate=deduplicate)

                st.success(f"✅ {len(rows)} valid session(s) ready to import.")
                if rows:
                    import pandas as pd
                    st.dataframe(
                        pd.DataFrame(rows).head(10),
                        use_container_width=True,
                    )
                    if st.button("💾 Save to Database", type="primary"):
                        saved = 0
                        errors = []
                        progress = st.progress(0)
                        for i, row in enumerate(rows):
                            try:
                                tracker.save_session(row)
                                saved += 1
                            except Exception as e:
                                errors.append(str(e))
                            progress.progress((i + 1) / len(rows))
                        st.success(f"Imported {saved} of {len(rows)} sessions.")
                        if errors:
                            st.warning(f"{len(errors)} row(s) skipped: {errors[:3]}")
                        st.cache_data.clear()
            except DataImportError as exc:
                show_error_card(str(exc))
            finally:
                pathlib.Path(tmp_path).unlink(missing_ok=True)

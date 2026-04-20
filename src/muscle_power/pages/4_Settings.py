"""Settings page — sensor config, preferences, and knowledge base management."""
from __future__ import annotations

import streamlit as st

from muscle_power.components.ui import RED, inject_css, show_auth_page, show_error_card, toast_success, toast_warning, user_sidebar_widget
from muscle_power.services.knowledge_base import get_knowledge_base
from muscle_power.utils.config import get_config, reset_config
from muscle_power.utils.errors import ConfigError

# ---------------------------------------------------------------------------
# Page set-up
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Settings · Muscle Power", page_icon="⚙️", layout="wide")
inject_css()

cfg = get_config()

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
st.title("⚙️ Settings")

tab_sensor, tab_app, tab_kb, tab_account, tab_about = st.tabs(
    ["🔵 Sensor", "🖥️ Application", "🧠 Knowledge Base", "👤 Account", "ℹ️ About"]
)

# =========================================================================
# SENSOR SETTINGS
# =========================================================================
with tab_sensor:
    st.subheader("Sensor Configuration")
    with st.form("sensor_form"):
        pref_addr = st.text_input(
            "Preferred sensor address (auto-connect)",
            value=cfg.sensor.preferred_address,
            placeholder="AA:BB:CC:DD:EE:FF — leave blank to select manually",
            help="The sensor with this address will be connected automatically on scan.",
        )
        fs = st.selectbox(
            "Sampling frequency (Hz)",
            options=[125, 250, 500, 1000, 2000],
            index=[125, 250, 500, 1000, 2000].index(cfg.sensor.sampling_frequency)
            if cfg.sensor.sampling_frequency in [125, 250, 500, 1000, 2000]
            else 1,
        )
        sig_type = st.selectbox(
            "Signal type",
            options=["EMG", "EEG", "ECG", "EDA"],
            index=["EMG", "EEG", "ECG", "EDA"].index(cfg.sensor.signal_type)
            if cfg.sensor.signal_type in ["EMG", "EEG", "ECG", "EDA"]
            else 0,
        )
        display_w = st.slider("Live display window (s)", 2, 30, cfg.sensor.display_window_seconds)
        rms_w = st.slider("RMS envelope window (ms)", 50, 1000, cfg.sensor.rms_window_ms, step=25)

        st.markdown("**Battery warnings**")
        batt_warn = st.slider("Yellow warning at (%)", 10, 50, cfg.sensor.battery_warn_pct)
        batt_alert = st.slider("Red alert at (%)", 5, 20, cfg.sensor.battery_alert_pct)

        submitted = st.form_submit_button("💾 Save Sensor Settings")
        if submitted:
            # Persist to config.yaml
            import yaml, pathlib
            try:
                with open("config.yaml", "r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f) or {}
                raw.setdefault("sensor", {}).update({
                    "preferred_address": pref_addr,
                    "sampling_frequency": fs,
                    "signal_type": sig_type,
                    "display_window_seconds": display_w,
                    "rms_window_ms": rms_w,
                    "battery_warn_pct": batt_warn,
                    "battery_alert_pct": batt_alert,
                })
                with open("config.yaml", "w", encoding="utf-8") as f:
                    yaml.dump(raw, f, default_flow_style=False)
                reset_config()
                toast_success("Sensor settings saved.")
                st.cache_data.clear()
            except Exception as exc:
                show_error_card(f"Failed to save settings: {exc}")

# =========================================================================
# APPLICATION SETTINGS
# =========================================================================
with tab_app:
    st.subheader("Application Settings")
    with st.form("app_form"):
        log_level = st.selectbox(
            "Log level",
            ["DEBUG", "INFO", "WARNING", "ERROR"],
            index=["DEBUG", "INFO", "WARNING", "ERROR"].index(cfg.log_level)
            if cfg.log_level in ["DEBUG", "INFO", "WARNING", "ERROR"] else 1,
        )
        db_url = st.text_input("Database URL", value=cfg.database.url)
        min_session_dur = st.number_input(
            "Minimum session duration (s) — shorter sessions flagged as duplicate",
            min_value=5, max_value=300,
            value=cfg.session.min_duration_seconds,
        )

        app_submitted = st.form_submit_button("💾 Save App Settings")
        if app_submitted:
            import yaml
            try:
                with open("config.yaml", "r", encoding="utf-8") as f:
                    raw = yaml.safe_load(f) or {}
                raw["log_level"] = log_level
                raw.setdefault("database", {})["url"] = db_url
                raw.setdefault("session", {})["min_duration_seconds"] = int(min_session_dur)
                with open("config.yaml", "w", encoding="utf-8") as f:
                    yaml.dump(raw, f, default_flow_style=False)
                reset_config()
                toast_success("Application settings saved. Restart to apply log-level change.")
                st.cache_data.clear()
            except Exception as exc:
                show_error_card(f"Failed to save: {exc}")

# =========================================================================
# KNOWLEDGE BASE
# =========================================================================
with tab_kb:
    st.subheader("Knowledge Base (RAG)")
    kb_enabled = cfg.kb.enabled

    if not kb_enabled:
        st.info(
            "Knowledge Base is **disabled**. Enable it in `config.yaml` by setting "
            "`kb.enabled: true` and install the optional dependency: "
            "`pip install pyneurosdk2[kb]`"
        )

    try:
        kb = get_knowledge_base()
        stats = kb.get_stats()
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Indexed chunks", stats["chunks"])
            st.metric("Documents", stats["documents"])
        with col2:
            st.metric("Embedding model", stats["embedding_model"])
            st.metric("Index exists", "Yes" if stats["index_exists"] else "No")

        st.markdown("**Document types supported:** `test-results`, `issues`, `baselines`")
        st.markdown(f"Drop files into the **`{cfg.kb.documents_dir}/`** folder, then re-index.")

        if st.button("🔄 Re-index Documents"):
            with st.spinner("Indexing documents…"):
                count = kb.index_documents()
            toast_success(f"Indexed {count} chunks from documents folder.")

        # Search
        st.divider()
        st.subheader("Semantic Search")
        query = st.text_input("Search query", placeholder="e.g. bicycle peak power fatigue", key="kb_query")
        if query and st.button("🔍 Search"):
            results = kb.search(query)
            if results:
                for i, r in enumerate(results, 1):
                    with st.expander(f"#{i} — {r['filename']} (score: {r['score']:.3f})"):
                        st.text(r["chunk"][:800])
            else:
                st.info("No results found. Try indexing documents first.")
    except Exception as exc:
        show_error_card(f"Knowledge base error: {exc}")

# =========================================================================
# ABOUT
# =========================================================================
with tab_account:
    from muscle_power.services.auth_service import (
        UserExistsError, update_display_name, delete_user, list_users,
    )

    user_id = st.session_state.get("current_user_id")
    username = st.session_state.get("current_username", "")
    display_name = st.session_state.get("current_display_name", "")

    # ── My Account ──
    st.subheader("My Account")
    st.markdown(f"**Username:** `{username}`  &nbsp;&nbsp; **Display name:** {display_name}")
    with st.form("display_name_form"):
        new_display = st.text_input("New display name", value=display_name)
        if st.form_submit_button("💾 Save Name", type="primary"):
            if new_display.strip():
                try:
                    update_display_name(user_id, new_display)
                    st.session_state["current_display_name"] = new_display.strip()
                    toast_success("Display name updated.")
                    st.rerun()
                except Exception as exc:
                    show_error_card(str(exc))
            else:
                show_error_card("Display name cannot be empty.")

    st.divider()

    # ── All Users ──
    st.subheader("All Users")
    try:
        all_users = list_users()
    except Exception as _ue:
        all_users = []
        show_error_card(f"Could not load users: {_ue}")

    for _u in all_users:
        _uid2 = _u["id"]
        _uname = _u["username"]
        _udisp = _u.get("display_name", _uname)
        _is_me = (_uid2 == user_id)
        _uc1, _uc2, _uc3, _uc4 = st.columns([3, 3, 1, 1])
        with _uc1:
            st.markdown(f"`{_uname}`" + (" 👤 **(you)**" if _is_me else ""))
        with _uc2:
            _new_dn = st.text_input(
                "Display name",
                value=_udisp,
                key=f"dn_{_uid2}",
                label_visibility="collapsed",
            )
        with _uc3:
            if st.button("✏️", key=f"edit_{_uid2}", help="Save display name"):
                if _new_dn.strip():
                    update_display_name(_uid2, _new_dn.strip())
                    if _is_me:
                        st.session_state["current_display_name"] = _new_dn.strip()
                    toast_success(f"Updated '{_uname}'")
                    st.rerun()
        with _uc4:
            if not _is_me:
                if st.button("🗑️", key=f"del_{_uid2}", help=f"Delete {_uname}"):
                    delete_user(_uid2)
                    toast_success(f"User '{_uname}' deleted.")
                    st.rerun()
            else:
                st.markdown("&nbsp;")  # placeholder so columns stay aligned


with tab_about:
    st.subheader("About Muscle Power")
    st.markdown(
        """
        **Muscle Power** is a real-time EMG muscle activation dashboard built for
        the [Callibri sensor](https://store.brainbit.com/products/callibri-sdk) by BrainBit.

        **Version:** 0.1.0 &nbsp;|&nbsp; **Platform:** Windows, macOS (Python/Streamlit)

        **SDK Documentation:**
        - [Overview](https://sdk.callibri.com/sdk-2/overview/)
        - [Python Installation](https://sdk.callibri.com/sdk-2/installation/python/)
        - [Signal Reference](https://sdk.callibri.com/sdk-2/callibri-mf/)

        **Data privacy:** All workout data is stored **locally only**.
        No data is sent to any server without your explicit consent.

        ---
        ### Cross-platform roadmap
        | Phase | Platform | Technology |
        |-------|----------|------------|
        | ✅ 1 | **Windows desktop** | Python + Streamlit + pyneurosdk2 |
        | 🔜 2 | **macOS** | Python + Streamlit + pyneurosdk2 (macOS 10.14+) |
        | 🔜 3 | **Android** | Kotlin + Callibri Android SDK |
        | 🔜 4 | **iOS** | Swift + Callibri iOS SDK |
        """
    )

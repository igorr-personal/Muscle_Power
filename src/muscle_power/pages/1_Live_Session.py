from __future__ import annotations  # <--- MUST BE LINE 1


import streamlit as st
import time
from streamlit_autorefresh import st_autorefresh


import json
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots


from muscle_power.components.ui import (
    RED, inject_css, electrode_quality_indicator, fft_chart,
    kpi_card, power_bar, sensor_status_widget, show_auth_page, show_error_card,
    show_warning_card, signal_chart, toast_error, toast_success, toast_warning,
    user_sidebar_widget,
)
from muscle_power.services.sensor_service import (
    CallibriService, SensorInfoDTO, get_sensor_service,
)
from muscle_power.services.signal_processing import (
    compute_fft, compute_fatigue_index, compute_median_frequency,
    compute_rms_envelope, decimate_for_display, detect_reps,
    validate_signal_quality,
)
from muscle_power.services.workout_tracking import WorkoutTracker, get_tracker
from muscle_power.services.user_settings import save_user_settings, PERSISTED_KEYS
from muscle_power.services.sim_generator import next_chunk as _sim_next_chunk, SIM_CHUNK as _SIM_CHUNK, SIM_FS as _SIM_FS
from muscle_power.db.migrations import run_migrations
from muscle_power.utils.config import get_config
from muscle_power.utils.errors import (
    SDKNotInstalledError, SensorConnectionError, SensorNotFoundError,
    SessionConflictError,
)

# ---------------------------------------------------------------------------
# Bootstrap — ensure migrations have run (page may be opened directly)
# ---------------------------------------------------------------------------
try:
    run_migrations()
except Exception:
    pass

# ---------------------------------------------------------------------------
# Page set-up
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Live Session  Muscle Power", page_icon="", layout="wide")
inject_css()
# Prevent the body from scrolling on this page — everything fits the viewport
st.markdown(
    "<style>"
    "html,body,[data-testid='stMain'],.main{overflow:hidden!important;}"
    ".main .block-container{padding-top:0!important;padding-bottom:0!important;max-width:100%!important;}"
    "header[data-testid='stHeader']{height:0!important;min-height:0!important;padding:0!important;visibility:hidden!important;}"
    "[data-testid='stMainBlockContainer']{padding-top:0!important;}"
    ".stMainBlockContainer{padding-top:0!important;}"
    "[data-testid='stVerticalBlock']{gap:0.25rem!important;}"
    "[data-testid='stSidebar'] [data-testid='stVerticalBlock']{gap:0.5rem!important;}"
    "[data-baseweb='popover'] li,"
    "[data-baseweb='popover'] span,"
    "[data-baseweb='menu'] li,"
    "[data-baseweb='menu'] span,"
    "[data-baseweb='select'] [role='option'] span"
    "{color:#E8E8F0!important;background:rgba(15,10,38,0.95)!important;}"
    "[data-baseweb='popover'],[data-baseweb='menu']"
    "{background:rgba(15,10,38,0.98)!important;}"
    "</style>",
    unsafe_allow_html=True,
)



cfg = get_config()
svc: CallibriService = get_sensor_service()
tracker: WorkoutTracker = get_tracker()

# Auth gate  must be logged in
show_auth_page()

# ---------------------------------------------------------------------------
# Sensor colour & name config
# ---------------------------------------------------------------------------
SENSOR_SLOTS = [
    {"id": "red",   "default_color": "#FF4444", "label": "Red"},    # red trace
    {"id": "blue",  "default_color": "#00BFFF", "label": "Blue"},   # cyan-blue trace
    {"id": "green", "default_color": "#39FF14", "label": "Green"},  # neon green
    {"id": "white", "default_color": "#FFFFFF", "label": "White"},
]

# ---------------------------------------------------------------------------
# Oscilloscope scale steps  (Volts per division)
# Standard steps matching Keysight / Rigol oscilloscopes
# ---------------------------------------------------------------------------
VDIV_STEPS = [
    0.0001, 0.0002, 0.0005,          # 0.1 mV, 0.2 mV, 0.5 mV
    0.001,  0.002,  0.005,           # 1 mV,   2 mV,   5 mV
    0.01,   0.02,   0.05,            # 10 mV,  20 mV,  50 mV
    0.1,    0.2,    0.5,             # 100 mV, 200 mV, 500 mV
    1.0,    2.0,    5.0,             # 1 V,    2 V,    5 V
]
VDIV_LABELS = [
    "0.1 mV", "0.2 mV", "0.5 mV",
    "1 mV",   "2 mV",   "5 mV",
    "10 mV",  "20 mV",  "50 mV",
    "100 mV", "200 mV", "500 mV",
    "1 V",    "2 V",    "5 V",
]
N_DIVISIONS = 10                     # 10 vertical divisions, like a real scope
DEFAULT_VDIV_IDX = 4                 # default 2 mV/div


def _auto_vdiv(max_abs_v: float) -> float:
    """Pick the smallest V/div so max_abs fits within 80% of half-screen (4/5 divs)."""
    if max_abs_v <= 0:
        return VDIV_STEPS[DEFAULT_VDIV_IDX]
    target = max_abs_v / (N_DIVISIONS / 2 * 0.8)   # 80 % of half-screen
    for vdiv in VDIV_STEPS:
        if vdiv >= target:
            return vdiv
    return VDIV_STEPS[-1]


def _vdiv_label(vdiv: float) -> str:
    idx = _nearest_vdiv_idx(vdiv)
    return VDIV_LABELS[idx]


def _nearest_vdiv_idx(vdiv: float) -> int:
    return min(range(len(VDIV_STEPS)), key=lambda i: abs(VDIV_STEPS[i] - vdiv))


# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
_DEFAULTS: dict = {
    "found_sensors": [],
    "selected_sensor_idx": 0,
    "streaming": False,
    "recording": False,
    "show_raw": True,
    "show_envelope": False,
    "show_fft": False,
    "sig_display_running": False,
    "muscle_group": "",
    "notes": "",
    "session_id": None,
    "battery_warned": False,
    "sim_mode": False,
    "sim_recording": False,
    "sim_rec_data": {},
    "sim_rec_start": 0,
    "sim_rec_session_id": None,
    "sim_rec_label": "",
    "rec_name": "Recording",
    "scan_timeout": 10,
    "wave_buf_red":   [],
    "wave_buf_blue":  [],
    "wave_buf_green": [],
    "wave_buf_white": [],
    "slot_active_red":   True,
    "slot_active_blue":  True,
    "slot_active_green": False,
    "slot_active_white": False,
    "muscle_en_red":   "Bicep",
    "muscle_en_blue":  "Tricep",
    "muscle_en_green": "Deltoid",
    "muscle_en_white": "Custom",
    "muscle_he_red":   "×‘×™×¦×¤",
    "muscle_he_blue":  "×˜×¨×™×¦×¤×¡",
    "muscle_he_green": "×“×œ×˜×•××™×“",
    "muscle_he_white": "×ž×•×ª××",
    "muscle_lang":     "English",
    "white_color": "#FFFFFF",
    "_sim_frame": 0,
    # --- oscilloscope scale ---
    "scope_scale_mode": "Auto",          # "Auto" or "Manual"
    "scope_vdiv_idx": DEFAULT_VDIV_IDX,  # index into VDIV_STEPS for manual mode
    # per-slot computed vdiv (used in auto mode  updated each frame)
    "scope_vdiv_red":   VDIV_STEPS[DEFAULT_VDIV_IDX],
    "scope_vdiv_blue":  VDIV_STEPS[DEFAULT_VDIV_IDX],
    "scope_vdiv_green": VDIV_STEPS[DEFAULT_VDIV_IDX],
    "scope_vdiv_white": VDIV_STEPS[DEFAULT_VDIV_IDX],
    # 0.5-second RMS average accumulation buffers and computed values
    "avg_acc_red": [],   "avg_acc_blue": [],   "avg_acc_green": [],   "avg_acc_white": [],
    "avg_val_red": 0.0,  "avg_val_blue": 0.0,  "avg_val_green": 0.0,  "avg_val_white": 0.0,
    # oscilloscope window and fullscreen
    "scope_window": 800,
    "scope_fullscreen": False,
    # average window (seconds) and wave smoothing kernel size
    "avg_window_sec": 0.5,
    "wave_smooth": 1,
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _build_summary(raw: np.ndarray, fs: float) -> dict:
    from muscle_power.services.signal_processing import (
        bandpass_filter, compute_rms_envelope as rms_env,
    )
    filtered = bandpass_filter(raw, fs=fs) if len(raw) > int(fs * 0.1) else raw
    env = rms_env(filtered, fs=fs)
    reps = detect_reps(env, fs=fs)
    fatigue = compute_fatigue_index(env)
    duration = len(raw) / fs
    return {
        "peak_amplitude": float(np.max(env)),
        "mean_amplitude": float(np.mean(env)),
        "duration_seconds": duration,
        "fatigue_index": fatigue,
        "rep_count": len(reps),
    }


def _slot_color(slot_id: str) -> str:
    defaults = {s["id"]: s["default_color"] for s in SENSOR_SLOTS}
    if slot_id == "white":
        return st.session_state.get("white_color", "#FFFFFF")
    return defaults.get(slot_id, "#AAAAAA")


def _muscle_name(slot_id: str) -> str:
    return st.session_state.get(f"muscle_en_{slot_id}", slot_id)


def _effective_vdiv(slot_id: str) -> float:
    """Return the V/div to use for this slot given the current scale mode."""
    if st.session_state["scope_scale_mode"] == "Manual":
        return VDIV_STEPS[st.session_state["scope_vdiv_idx"]]
    return st.session_state.get(f"scope_vdiv_{slot_id}", VDIV_STEPS[DEFAULT_VDIV_IDX])


def _fmt_v(v: float) -> str:
    """Format a voltage value as a human-readable string."""
    mv = v * 1000
    if abs(mv) >= 1000:
        return f"{v:.2g} V"
    if abs(mv) >= 1:
        return f"{mv:.4g} mV"
    return f"{mv * 1000:.4g} ÂµV"


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------
_SIM_WINDOW = 800      # default window â€” overridden by scope_window session state


def _sim_frame_for_slot(slot_id: str, frame: int) -> np.ndarray:
    return _sim_next_chunk(slot_id, frame)


def _update_wave_buffers() -> None:
    frame = st.session_state["_sim_frame"]
    st.session_state["_sim_frame"] = frame + 1
    for slot in SENSOR_SLOTS:
        sid = slot["id"]
        if not st.session_state.get(f"slot_active_{sid}", False):
            continue
        buf_key = f"wave_buf_{sid}"
        buf: list = list(st.session_state[buf_key])
        if st.session_state["sim_mode"]:
            new_samples = _sim_frame_for_slot(sid, frame).tolist()
        else:
            if svc.state == "connected":
                ch_map = {"red": 0, "blue": 1, "green": 2, "white": 3}
                ch_idx = ch_map.get(sid, 0)

                raw_samples = svc.get_raw_samples(max_samples=_SIM_CHUNK, channel=ch_idx)
                new_samples = [s.raw_value for s in raw_samples[-_SIM_CHUNK:]]
                
                # If no samples arrived yet, draw a flat baseline
                if not new_samples:
                    new_samples = [0.0] * _SIM_CHUNK

            else:
                new_samples = [0.0] * _SIM_CHUNK
        buf.extend(new_samples)
        scope_window = st.session_state.get("scope_window", _SIM_WINDOW)
        st.session_state[buf_key] = buf[-scope_window:]
        # update auto vdiv for this slot
        if st.session_state["scope_scale_mode"] == "Auto" and buf:
            max_abs = float(np.max(np.abs(buf)))
            st.session_state[f"scope_vdiv_{sid}"] = _auto_vdiv(max_abs)
        # RMS average: accumulate samples, flush when bucket is full
        acc_key = f"avg_acc_{sid}"
        avg_acc: list = list(st.session_state.get(acc_key, []))
        avg_acc.extend(new_samples)
        avg_window_samples = max(1, int(round(st.session_state.get("avg_window_sec", 0.5) * _SIM_FS)))
        if len(avg_acc) >= avg_window_samples:
            st.session_state[f"avg_val_{sid}"] = float(
                np.sqrt(np.mean(np.square(avg_acc[:avg_window_samples])))
            )
            avg_acc = avg_acc[avg_window_samples:]
        st.session_state[acc_key] = avg_acc


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
# ── Top bar: User + Fullscreen + Logout — compact row ──
_user_display = st.session_state.get("current_display_name") or st.session_state.get("current_username", "")
if _user_display:
    _fs_state = st.session_state.get("scope_fullscreen", False)
    _tb_c1, _tb_c2, _tb_c3 = st.columns([1, 1, 6])
    with _tb_c1:
        if st.button("\u26f6 Full", key="_topbar_fs", use_container_width=True):
            st.session_state["scope_fullscreen"] = not _fs_state
            st.rerun()
    with _tb_c2:
        if st.button("Logout", key="_topbar_logout", use_container_width=True):
            for key in ("current_user_id", "current_username", "current_display_name"):
                st.session_state.pop(key, None)
            st.rerun()
    with _tb_c3:
        st.markdown(
            f"<div style='text-align:right;padding:5px 0;font-size:13px;font-family:monospace'>"
            f"\U0001F464 <b style='color:#E8E8F0'>{_user_display}</b></div>",
            unsafe_allow_html=True,
        )

with st.sidebar:
    st.markdown(f"<h2 style='color:{RED};margin:0'> Muscle Power</h2>", unsafe_allow_html=True)

    # ── SIMULATION ──
    st.markdown(
        "<div style='background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.12);"
        "border-radius:10px;padding:10px 12px;margin:8px 0'>",
        unsafe_allow_html=True,
    )
    st.session_state["sim_mode"] = st.toggle(
        " Simulation Mode",
        value=st.session_state["sim_mode"],
        help="Enable offline wave visualisation using synthetic EMG  no real sensor needed.",
    )
    st.markdown("</div>", unsafe_allow_html=True)

    # ── SENSOR CONNECTION (glass frame) ──
    if not st.session_state["sim_mode"]:
        st.markdown(
            "<div style='background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.12);"
            "border-radius:10px;padding:10px 12px;margin:8px 0'>"
            "<div style='font-weight:700;font-size:13px;color:#E8E8F0;margin-bottom:6px'>"
            "Sensor Connection</div>",
            unsafe_allow_html=True,
        )
        sensor_status_widget(svc.state, svc.sensor_info.name if svc.sensor_info else "", svc.battery)

        if svc.state in ("disconnected", "error"):
            st.slider(
                "Scan timeout (s)", 5, 30,
                key="scan_timeout",
                help="How long to scan for Bluetooth devices (BLE + Classic).",
            )
            if st.button(
                " Scan for Devices",
                use_container_width=True,
                help="Scan for ALL nearby Bluetooth devices (BLE + Classic). Callibri sensors are highlighted.",
            ):
                _scan_bar = st.progress(0, text="Scanning for Bluetooth devices...")
                _scan_timeout = float(st.session_state.get("scan_timeout", 10))
                import threading as _th
                _scan_result: list = []
                _scan_error: list = []

                def _do_scan() -> None:
                    try:
                        _scan_result.extend(svc.scan_all_ble(timeout=_scan_timeout))
                    except Exception as _e:
                        _scan_error.append(_e)

                _t = _th.Thread(target=_do_scan, daemon=True)
                _t.start()
                _elapsed = 0.0
                while _t.is_alive() and _elapsed < _scan_timeout + 5:
                    time.sleep(0.3)
                    _elapsed += 0.3
                    pct = min(int((_elapsed / _scan_timeout) * 100), 99)
                    _scan_bar.progress(pct, text=f"Scanning... {pct}%")
                _t.join(timeout=10)
                _scan_bar.progress(100, text="Scan complete")
                time.sleep(0.3)
                _scan_bar.empty()

                if _scan_error:
                    _exc = _scan_error[0]
                    if isinstance(_exc, SDKNotInstalledError):
                        show_error_card(str(_exc))
                    elif isinstance(_exc, SensorConnectionError):
                        show_error_card(str(_exc))
                    else:
                        show_error_card(str(_exc))
                else:
                    found_list = _scan_result
                   
                    st.session_state.found_sensors = found_list
                    callibri_count = sum(1 for d in found_list if d.is_callibri)
                    if found_list:
                        toast_success(f"Found {len(found_list)} device(s)  {callibri_count} Callibri sensor(s)")
                        # Auto-assign found sensors to channels (up to 4)
                        for i, dev in enumerate(found_list[:4]):
                            slot = SENSOR_SLOTS[i]
                            sid = slot["id"]
                            st.session_state[f"slot_active_{sid}"] = True
                            # Use device name as muscle/channel name if user hasn't customised it
                            st.session_state[f"muscle_en_{sid}"] = dev.name or f"Device {i+1}"
                            st.session_state[f"sensor_addr_{sid}"] = dev.address
                    else:
                        _err_detail = svc.error_message or ""
                        show_warning_card(
                            "No Bluetooth devices found. Ensure Bluetooth is enabled "
                            "and the sensor is powered on and within 5 m."
                            + (f"\\n\\nDetails: {_err_detail}" if _err_detail else "")
                        )
            # --- Find the selection logic in 1_Live_Session.py ---

            found: list[SensorInfoDTO] = st.session_state.found_sensors
            if found:
                def _device_label(d: SensorInfoDTO) -> str:
                    # Check for "Callibri" in the name to handle "Callibri_Red"
                    is_valid = d.is_callibri or "Callibri" in d.name
                    tag = "" if is_valid else "    not a Callibri Sensor"
                    return f"{d.name} ({d.address}){tag}"

                sensor_labels = [_device_label(d) for d in found]
                selected = st.selectbox(
                    "Select device",
                    sensor_labels,
                    key="sensor_select",
                    help="Only Callibri devices can be connected.",
                )
                idx = sensor_labels.index(selected) if selected in sensor_labels else 0
                st.session_state.selected_sensor_idx = idx
                selected_device = found[idx]

                # Use the same flexible check here
                is_valid_selection = selected_device.is_callibri or "Callibri" in selected_device.name

                if not is_valid_selection:
                    st.warning("Selected device is not a Callibri sensor.", icon="⚠️")
                else:
                    if st.button(" Connect", use_container_width=True):
                        # The svc._scanner returns raw SDK objects which use PascalCase
                         with st.spinner("Connecting... (this may take ~10 seconds)"):
                            try:
                                with ThreadPoolExecutor() as ex:
                                    fut = ex.submit(
                                        svc.connect_by_address,
                                        selected_device.address
                                    )
                                    fut.result(timeout=60)
                                svc.set_emg_defaults()
                                st.session_state["sensor_state"] = svc.state
                                st.session_state["battery_pct"] = svc.battery
                                st.toast(f"Connected to {selected_device.name}", icon="✅")
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Connection failed: {exc}")

        # --- Find this line around line 465 ---
        elif svc.state == "connected":
    

            # 2. ADD THE CHART LOGIC HERE
            st.subheader("Live Muscle Power (Envelope)")
    
            if len(svc._envelope_buffer) > 0:
                # We take the last 100 points for a smooth scrolling effect
                # 'v' is the value we saved in the callback earlier
                env_data = [s.envelope_value for s in list(svc._envelope_buffer)[-100:]
                    if s.envelope_value is not None]
                st.area_chart(env_data)
            else:
                st.info("Waiting for data... Ensure you clicked 'Start' and the sensor has skin contact.")


            if st.button(" Disconnect", use_container_width=True):
                if st.session_state.recording:
                    _raw = np.array([s.raw_value for s in svc.get_raw_samples()])
                    summary = _build_summary(_raw, cfg.sensor.sampling_frequency) if len(_raw) > 10 else None
                    tracker.stop_session(summary)
                svc.disconnect()
                st.session_state["streaming"] = False
                st.session_state["recording"] = False
                st.session_state["sensor_state"] = "disconnected"
                toast_warning("Disconnected from sensor")
                st.rerun()

            batt = svc.battery
            if batt >= 0:
                st.session_state["battery_pct"] = batt
                if batt <= 5 and st.session_state.recording and not st.session_state.battery_warned:
                    st.session_state["battery_warned"] = True
                    show_warning_card(f" Battery critically low ({batt}%)  auto-saving!")
                    _raw = np.array([s.raw_value for s in svc.get_raw_samples()])
                    if len(_raw) > 10:
                        tracker.stop_session(_build_summary(_raw, cfg.sensor.sampling_frequency))
                    st.session_state["recording"] = False
                    st.session_state["streaming"] = False
                elif batt <= 10:
                    show_warning_card(f" Battery critically low ({batt}%)! Save now.")
                elif batt <= 20:
                    show_warning_card(f" Battery at {batt}%  ~30 min remaining.")
        st.markdown("</div>", unsafe_allow_html=True)

    # ==================================================================
    #  SENSOR CHANNELS — 4 separate coloured panels
    # ==================================================================
    # ── SENSOR CHANNELS (glass frame) ──
    st.markdown(
        "<div style='background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.12);"
        "border-radius:10px;padding:10px 12px;margin:8px 0'>"
        "<div style='font-weight:700;font-size:13px;color:#E8E8F0;margin-bottom:6px'>"
        "Sensor Channels</div>",
        unsafe_allow_html=True,
    )

    # Inject CSS — channel cards: hide default checkbox chrome, style toggle & input
    st.markdown("""<style>
    .ch-card { position:relative; }
    .ch-card .stCheckbox { position:absolute; top:8px; right:10px; z-index:2; }
    .ch-card .stCheckbox label p,
    .ch-card .stCheckbox label span:last-child { display:none!important; }
    .ch-card .stTextInput { margin:0!important; }
    .ch-card .stTextInput > div { margin:0!important; }
    .ch-card .stTextInput input {
        font-size:13px!important; padding:2px 0!important; height:auto!important;
        background:transparent!important; border:none!important; border-bottom:1px solid rgba(255,255,255,0.15)!important;
        border-radius:0!important; color:#E8E8F0!important; outline:none!important;
        box-shadow:none!important;
    }
    .ch-card .stTextInput input:focus { border-bottom-color:rgba(255,255,255,0.4)!important; }
    .ch-card .stColorPicker label p { font-size:13px!important; }
    .ch-card [data-testid="stVerticalBlock"] { gap:0!important; }
    </style>""", unsafe_allow_html=True)

    for slot in SENSOR_SLOTS:
        sid = slot["id"]
        color = _slot_color(sid)
        is_active = st.session_state.get(f"slot_active_{sid}", False)
        key_name = f"muscle_en_{sid}"

        bg_a  = "22" if is_active else "0c"
        bdr_a = "88" if is_active else "33"
        conn_label = "Connected" if (not st.session_state["sim_mode"] and svc.state == "connected") else ("Sim" if st.session_state["sim_mode"] else "---")
        conn_color = "#3ddc84" if conn_label in ("Connected", "Sim") else "#888"
        act_text = "Activated" if is_active else "Inactivated"
        muscle_name = st.session_state.get(key_name, sid)

        # Glassmorphism channel card — all 3 rows as HTML, checkbox overlaid at top-right
        st.markdown(
            f"<div class='ch-card' style='"
            f"background:linear-gradient(135deg,{color}{bg_a},{color}08);"
            f"backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);"
            f"border:1.5px solid {color}{bdr_a};"
            f"border-radius:10px;"
            f"padding:10px 14px;"
            f"margin:6px 0'>"
            # Row 1: channel label + status
            f"<div style='font-size:13px;color:{color};font-weight:600;line-height:1.6'>"
            f"{slot['label']}: {act_text}</div>"
            # Row 2: BT status
            f"<div style='font-size:13px;color:{conn_color};line-height:1.6'>"
            f"BT: {conn_label}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # Hidden checkbox (positioned absolute top-right via CSS)
        # key = storage key so there's no separate copy that can diverge
        st.checkbox(
            " ",
            key=f"slot_active_{sid}",
        )

        # Row 3: editable muscle name (inline underline style via CSS)
        st.session_state[key_name] = st.text_input(
            "name",
            value=st.session_state[key_name],
            key=f"mname_{sid}",
            placeholder="Muscle name",
            label_visibility="collapsed",
        )

        if sid == "white":
            st.session_state["white_color"] = st.color_picker(
                "Channel color",
                value=st.session_state["white_color"],
                key="white_color_picker",
            )

    st.markdown("</div>", unsafe_allow_html=True)

    # ── DISPLAY OPTIONS (glass frame) ──
    st.markdown(
        "<div style='background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.12);"
        "border-radius:10px;padding:10px 12px;margin:8px 0'>"
        "<div style='font-weight:700;font-size:13px;color:#E8E8F0;margin-bottom:6px'>"
        "Display Options</div>",
        unsafe_allow_html=True,
    )

    # Amplitude scale
    st.radio(
        "Amplitude scale",
        ["Auto", "Manual"],
        key="scope_scale_mode",
        horizontal=True,
        help=(
            "**Auto**: scale adjusts automatically so the signal always fits in view.\n\n"
            "**Manual**: you set the V/div like a Keysight oscilloscope."
        ),
    )
    if st.session_state["scope_scale_mode"] == "Manual":
        st.select_slider(
            "V/div",
            options=list(range(len(VDIV_STEPS))),
            key="scope_vdiv_idx",
            format_func=lambda i: VDIV_LABELS[i],
            help="Voltage per division. 10 divisions total (5 from centre).",
        )
        selected_vdiv = VDIV_STEPS[st.session_state["scope_vdiv_idx"]]
        st.markdown(
            f"<div style='text-align:center;font-size:13px;font-weight:700;color:#FFD700'>"
            f"Range: ±{selected_vdiv * N_DIVISIONS / 2 * 1000:.3g} mV "
            f"({VDIV_LABELS[st.session_state['scope_vdiv_idx']]}/div)"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.slider(
        "Time window (samples)",
        min_value=200,
        max_value=2000,
        key="scope_window",
        step=50,
        help="Number of samples shown in the oscilloscope window.",
    )

    st.checkbox(
        "Show envelope",
        key="show_envelope",
        help="Overlay the smoothed amplitude envelope (muscle activation) as a dim dotted line.",
    )
    st.markdown("</div>", unsafe_allow_html=True)

    # ── SIGNAL PROCESSING (glass frame) ──
    st.markdown(
        "<div style='background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.12);"
        "border-radius:10px;padding:10px 12px;margin:8px 0'>"
        "<div style='font-weight:700;font-size:13px;color:#E8E8F0;margin-bottom:6px'>"
        "Signal Processing</div>",
        unsafe_allow_html=True,
    )
    st.slider(
        "Avg window (s)",
        min_value=0.1,
        max_value=2.0,
        key="avg_window_sec",
        step=0.05,
        format="%.2f s",
        help="RMS average is recomputed over this many seconds of samples.",
    )
    st.slider(
        "Wave smoothing",
        min_value=1,
        max_value=8,
        key="wave_smooth",
        step=1,
        help=(
            "Simple moving-average of nearby samples (display only).\n\n"
            "**1** = raw signal (no smoothing)  \n"
            "**2** = average ±1 sample (3-point)  \n"
            "**4** = average ±2 samples (5-point)  \n"
            "**8** = average ±4 samples (9-point)"
        ),
    )
    st.markdown("</div>", unsafe_allow_html=True)

# --- Auto-save user settings on every sidebar interaction ---
_uid = st.session_state.get("current_user_id")
if _uid:
    _cur = {k: st.session_state[k] for k in PERSISTED_KEYS if k in st.session_state}
    _prev = st.session_state.get("_prev_settings")
    if _prev != _cur:
        save_user_settings(_uid, st.session_state)
        st.session_state["_prev_settings"] = dict(_cur)


# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------
if not st.session_state["sim_mode"] and svc.state != "connected":
    st.info(" Use the sidebar to scan and connect your Callibri sensor, or enable **Simulation Mode**.")
    if svc.error_message:
        show_error_card(svc.error_message)
    st.stop()

# ---------------------------------------------------------------------------
# Session recording controls (real sensor only)
# ---------------------------------------------------------------------------

stats = svc.stream_stats()
st.caption(
    f"stream: packets={stats['sig_packets']} samples={stats['sig_samples']} "
    f"last={stats['last_sig_ms']} electrode={stats['electrode']} battery={stats['battery']}"
)

if not st.session_state["sim_mode"]:
    st.subheader("Session Recording")
    ctrl1, ctrl2, ctrl3, ctrl4 = st.columns(4)
    with ctrl1:
        muscle_group = st.text_input(
            "Muscle group",
            value=st.session_state.muscle_group,
            placeholder="e.g. biceps",
            key="mg_input",
            help="Name the muscle group being trained.",
        )
        st.session_state.muscle_group = muscle_group
    with ctrl2:
        notes_in = st.text_input(
            "Notes",
            value=st.session_state.notes,
            key="notes_input",
            help="Optional session notes.",
        )
        st.session_state.notes = notes_in
    with ctrl3:
        if not st.session_state.recording:
            if st.button(" Start Recording", use_container_width=True, type="primary",
                          help="Begin a new timed recording session."):
                try:
                    sid = tracker.start_session(
                        sensor_address=svc.sensor_info.address,
                        sensor_name=svc.sensor_info.name,
                        sampling_rate=cfg.sensor.sampling_frequency,
                        muscle_group=muscle_group,
                        notes=notes_in,
                        user_id=st.session_state.get("current_user_id"),
                    )
                    st.session_state.session_id = sid
                    st.session_state.recording = True
                    if not st.session_state.get("streaming", False):
                        svc.start_streaming(session_start_ms=int(time.time() * 1000))
                    st.session_state.streaming = True
                    toast_success("Recording started!")
                except SessionConflictError as exc:
                    show_error_card(str(exc))
        else:
            if tracker.state == "RECORDING":
                if st.button(" Pause", use_container_width=True,
                              help="Pause data collection without ending the session."):
                    tracker.pause_session()
                    svc.stop_streaming()
                    st.session_state.streaming = False
                    toast_warning("Session paused")
            elif tracker.state == "PAUSED":
                if st.button(" Resume", use_container_width=True):
                    tracker.resume_session()
                    if not st.session_state.get("streaming", False):
                        svc.start_streaming()
                    st.session_state.streaming = True
                    toast_success("Session resumed")
    with ctrl4:
        if st.session_state.recording:
            if st.button(" Stop & Save", use_container_width=True,
                          help="Stop recording and save to the database."):
                raw_arr = np.array([s.raw_value for s in svc.get_raw_samples()])
                summary = _build_summary(raw_arr, cfg.sensor.sampling_frequency) if len(raw_arr) > 10 else None
                svc.stop_streaming()
                tracker.stop_session(summary)
                st.session_state.recording = False
                st.session_state.streaming = False
                st.session_state.session_id = None
                toast_success("Session saved!")
                st.rerun()
    st.divider()

    # --- KPI row ---
    fs = float(cfg.sensor.sampling_frequency)
    window_samples = int(10 * fs)
    raw_samples = svc.get_raw_samples(max_samples=window_samples)
    env_samples = svc.get_envelope_samples(max_samples=200)
    raw_vals = np.array([s.raw_value for s in raw_samples])
    env_vals = np.array([s.envelope_value or s.raw_value for s in env_samples])
    current_power = svc.get_current_power()

    if len(raw_vals) > int(fs * 0.5):
        quality_ok, quality_msg = validate_signal_quality(raw_vals, fs=fs)
        if not quality_ok:
            show_warning_card(quality_msg)

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        kpi_card("Current Power (V)", current_power, fmt=".5f")
    with kpi2:
        peak = float(np.max(env_vals)) if len(env_vals) > 0 else 0.0
        kpi_card("Peak Power (V)", peak, fmt=".5f")
    with kpi3:
        mean_p = float(np.mean(env_vals)) if len(env_vals) > 0 else 0.0
        kpi_card("Mean Power (V)", mean_p, fmt=".5f")
    with kpi4:
        electrode_quality_indicator(svc.get_signal_quality())
        st.markdown("<div class='mp-kpi-label'>Electrode Contact</div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Oscilloscope controls row
# ---------------------------------------------------------------------------
osc_c1, osc_c2, osc_c3, osc_c4 = st.columns([2, 2, 2, 3])
with osc_c1:
    if not st.session_state["sig_display_running"]:
        if st.button(" Start", use_container_width=True, type="primary",
                      help="Begin continuous waveform scrolling."):
            st.session_state["sig_display_running"] = True
            if svc.state == "connected" and not st.session_state.get("streaming", False):
                try:
                    svc.start_streaming()
                    st.session_state["streaming"] = True
                except Exception as exc:
                    st.error(f"Could not start streaming: {exc}")
            st.rerun()
    else:
        if st.button(" Stop", use_container_width=True,
                      help="Freeze the display."):
            st.session_state["sig_display_running"] = False
            st.rerun()
with osc_c2:
    if st.button(" Clear", use_container_width=True,
                  help="Clear all waveform buffers."):
        for slot in SENSOR_SLOTS:
            st.session_state[f"wave_buf_{slot['id']}"] = []
        st.session_state["_sim_frame"] = 0
        st.rerun()
with osc_c3:
    if not st.session_state.get("sim_recording", False):
        if st.button("\u23fa REC", use_container_width=True,
                     help="Start recording channel data for later review."):
            # Auto-number: count existing sessions for this user + 1
            _uid = st.session_state.get("current_user_id")
            _existing = tracker.get_sessions(user_id=_uid) if _uid else []
            _num = len(_existing) + 1
            _base = st.session_state.get("rec_name", "").strip()
            if not _base:
                _base = "Recording"
            _rec_label = f"{_base} {_num:02d}"
            # Start a real DB session
            _sid = tracker.start_session(
                sensor_address="SIM",
                sensor_name="Simulation",
                sampling_rate=250,
                muscle_group=_rec_label,
                notes="Simulation recording",
                user_id=_uid,
            )
            st.session_state["sim_recording"] = True
            st.session_state["sim_rec_session_id"] = _sid
            st.session_state["sim_rec_label"] = _rec_label
            st.session_state["sim_rec_data"] = {s["id"]: [] for s in SENSOR_SLOTS}
            st.session_state["sim_rec_start"] = time.time()
            st.rerun()
    else:
        if st.button("\u23f9 STOP REC", use_container_width=True, type="primary",
                     help="Stop recording and save data."):
            _duration = time.time() - st.session_state.get("sim_rec_start", time.time())
            _rec_data = st.session_state.get("sim_rec_data", {})
            # Compute summary from recorded buffers
            _all_vals = []
            for _ch_vals in _rec_data.values():
                _all_vals.extend(_ch_vals)
            _arr = np.array(_all_vals) if _all_vals else np.array([0.0])
            _summary = {
                "peak_amplitude": float(np.max(np.abs(_arr))) if len(_arr) > 1 else 0.0,
                "mean_amplitude": float(np.mean(np.abs(_arr))) if len(_arr) > 1 else 0.0,
                "duration_seconds": _duration,
                "fatigue_index": 0.0,
                "rep_count": 0,
            }
            tracker.stop_session(_summary)
            st.session_state["sim_recording"] = False
            toast_success(f"Recording '{st.session_state.get('sim_rec_label', '')}' saved!")
            st.rerun()
with osc_c4:
    if st.session_state.get("sim_recording", False):
        _rec_start_ts = st.session_state.get("sim_rec_start", time.time())
        # Self-updating REC timer via JS — works even when Streamlit doesn't rerun
        import streamlit.components.v1 as _stc_rec
        _stc_rec.html(
            f"""<div id="rec-timer" style="padding:8px;text-align:center;background:#330000;
            border:1px solid #FF0000;border-radius:6px;font-family:monospace">
            <span style="color:#FF4444;font-weight:700;font-size:13px">
            &#9210; REC 0s</span></div>
            <script>
            (function(){{
              const start = {_rec_start_ts};
              const el = document.getElementById('rec-timer').querySelector('span');
              function tick(){{ const s = Math.floor(Date.now()/1000 - start);
                el.textContent = '\\u23FA REC ' + s + 's'; }}
              tick(); setInterval(tick, 1000);
            }})();
            </script>""",
            height=42,
        )
    else:
        st.session_state["rec_name"] = st.text_input(
            "Recording name",
            value=st.session_state.get("rec_name", "Recording"),
            key="rec_name_input",
            placeholder="Enter recording name",
            label_visibility="collapsed",
        )
# ---------------------------------------------------------------------------
# Canvas-based oscilloscope (sim mode) — 60 fps, zero Streamlit reruns
# ---------------------------------------------------------------------------

def _build_canvas_scope(
    active_slots: list[dict],
    scope_window: int,
    scope_height: int,
    smooth_k: int,
    avg_window_sec: float,
    is_running: bool,
    n_divisions: int,
    scale_mode: str,
    manual_vdiv_idx: int,
) -> str:
    """Return self-contained HTML/CSS/JS for a Canvas oscilloscope."""
    channels = []
    for slot in active_slots:
        sid = slot["id"]
        channels.append({
            "id": sid,
            "color": _slot_color(sid),
            "name": _muscle_name(sid),
            "phase": {"red": 0.0, "blue": 0.35, "green": 0.65, "white": 1.0}.get(sid, 0.0),
        })
    config_json = json.dumps({
        "channels": channels,
        "scopeWindow": scope_window,
        "scopeHeight": scope_height,
        "smoothK": smooth_k,
        "avgWindowSec": avg_window_sec,
        "isRunning": is_running,
        "nDivisions": n_divisions,
        "scaleMode": scale_mode,
        "manualVdivIdx": manual_vdiv_idx,
        "sampleRate": get_config().sensor.sampling_frequency,
        "vdivSteps": list(VDIV_STEPS),
        "vdivLabels": list(VDIV_LABELS),
        "defaultVdivIdx": DEFAULT_VDIV_IDX,
    })
    return _CANVAS_HTML.replace("/*__CONFIG__*/", config_json)


_CANVAS_HTML = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:transparent;overflow:hidden;font-family:'Segoe UI',Tahoma,monospace}
#w{border-radius:0 0 10px 10px;overflow:hidden;position:relative}
canvas{display:block}
</style></head><body>
<div id="w"><canvas id="c"></canvas></div>
<script>
(function(){
"use strict";
var C=/*__CONFIG__*/;
var cv=document.getElementById("c"),cx=cv.getContext("2d"),wp=document.getElementById("w");
var BF=0.16;
/* ── PRNG Mulberry32 ── */
function m32(a){return function(){a=(a+0x6D2B79F5)|0;var t=Math.imul(a^(a>>>15),1|a);t=(t+Math.imul(t^(t>>>7),61|t))^t;return((t^(t>>>14))>>>0)/4294967296}}
function hs(s){var h=0;for(var i=0;i<s.length;i++)h=((h<<5)-h+s.charCodeAt(i))|0;return Math.abs(h)}
function ga(r){var u=r()+1e-10,v=r();return Math.sqrt(-2*Math.log(u))*Math.cos(6.2831853*v)}
/* ── Channels ── */
var nCh=C.channels.length;
var chs=C.channels.map(function(c){return{id:c.id,color:c.color,name:c.name,phase:c.phase,
buf:[],rA:[],rV:0,rW:Math.max(1,Math.round(C.avgWindowSec*C.sampleRate)),
vd:C.vdivSteps[C.defaultVdivIdx],rng:m32(hs(c.id))}});
/* ── EMG generator: cubic envelope interpolation ── */
var _env=chs.map(function(){return{cur:0,tgt:0,dur:0,el:0}});
function _nt(ch){return 0.0005+ch.rng()*0.003}
function _nd(ch){return 0.3+ch.rng()*1.8}
function _cs(t){return t*t*(3-2*t)}
function gen(ch,t){
var ci=chs.indexOf(ch),es=_env[ci];es.el+=1/C.sampleRate;
if(es.el>=es.dur){es.cur=es.tgt;es.tgt=_nt(ch);es.dur=_nd(ch);es.el=0}
var f=Math.min(1,es.el/es.dur),amp=es.cur+(es.tgt-es.cur)*_cs(f);
var n=ga(ch.rng)*0.00012;
n+=amp*Math.sin(6.2831853*85*t+ch.phase*2);
n+=amp*0.3*Math.sin(6.2831853*42*t+ch.phase);
n+=0.0001*Math.sin(6.2831853*2.5*t+ch.phase*6.2831853);
return n}
/* ── Moving-average smooth ── */
function sm(d,k){if(k<=1||d.length<3)return d;var o=new Array(d.length);
for(var i=0;i<d.length;i++){var lo=Math.max(0,i-k),hi=Math.min(d.length-1,i+k),s=0;
for(var j=lo;j<=hi;j++)s+=d[j];o[i]=s/(hi-lo+1)}return o}
/* ── Auto V/div ── */
function aV(mx){if(mx<=0)return C.vdivSteps[C.defaultVdivIdx];
var t=mx/(C.nDivisions/2*0.8);for(var i=0;i<C.vdivSteps.length;i++)if(C.vdivSteps[i]>=t)return C.vdivSteps[i];
return C.vdivSteps[C.vdivSteps.length-1]}
/* ── Format voltage ── */
function fV(v){v=Math.abs(v);var mv=v*1000;
if(mv>=1000)return v.toPrecision(3)+" V";
if(mv>=1)return mv.toPrecision(4)+" mV";
return(mv*1000).toPrecision(4)+" \u00b5V"}
/* ── Hex → "r,g,b" for rgba() ── */
function h2r(hex){hex=hex.replace('#','');
return parseInt(hex.slice(0,2),16)+','+parseInt(hex.slice(2,4),16)+','+parseInt(hex.slice(4,6),16)}
/* ── Rounded rect path ── */
function rr(x,y,w,h,r){cx.beginPath();cx.moveTo(x+r,y);cx.lineTo(x+w-r,y);cx.arcTo(x+w,y,x+w,y+r,r);
cx.lineTo(x+w,y+h-r);cx.arcTo(x+w,y+h,x+w-r,y+h,r);cx.lineTo(x+r,y+h);cx.arcTo(x,y+h,x,y+h-r,r);
cx.lineTo(x,y+r);cx.arcTo(x,y,x+r,y,r);cx.closePath()}
/* ── Draw the wave path (quadratic midpoint — smooth continuous curve) ── */
function wavePath(sd,si,x0,sx,yM,sy){
var li=sd.length-1;
cx.moveTo(x0,yM-sd[si]*sy);
for(var i=si+1;i<li;i++){
var xi=x0+(i-si)*sx,yi=yM-sd[i]*sy,xi1=x0+(i+1-si)*sx,yi1=yM-sd[i+1]*sy;
cx.quadraticCurveTo(xi,yi,(xi+xi1)/2,(yi+yi1)/2)}
cx.lineTo(x0+(li-si)*sx,yM-sd[li]*sy)}
/* ── Pre-fill buffers ── */
var tg=0;
(function(){for(var i=0;i<C.scopeWindow;i++){var t=i/C.sampleRate;
for(var ci=0;ci<nCh;ci++){var ch=chs[ci],v=gen(ch,t);ch.buf.push(v);
ch.rA.push(v);if(ch.rA.length>=ch.rW){var sq=0;for(var jj=0;jj<ch.rA.length;jj++)sq+=ch.rA[jj]*ch.rA[jj];
ch.rV=Math.sqrt(sq/ch.rA.length);ch.rA=[]}}tg++}})();
/* ── Resize ── */
function rsz(){var dpr=window.devicePixelRatio||1,w=wp.clientWidth,h=C.scopeHeight;
cv.width=w*dpr;cv.height=h*dpr;cv.style.width=w+"px";cv.style.height=h+"px";cx.setTransform(dpr,0,0,dpr,0,0)}
rsz();
/* ════════════════ RENDER ════════════════ */
function render(){
var w=wp.clientWidth,h=C.scopeHeight;
/* Radial-gradient background — matching the reference */
var rbg=cx.createRadialGradient(w/2,h/2,0,w/2,h/2,Math.max(w,h)*0.75);
rbg.addColorStop(0,"#1a1a2e");rbg.addColorStop(1,"#0a0a14");
cx.fillStyle=rbg;cx.fillRect(0,0,w,h);

var bW=Math.floor(w*BF),sW=w-bW-6,chH=h/nCh,lW=58,pW=sW-lW-6;
var ci,ch,d,gy,gx;

/* V/div per channel */
for(ci=0;ci<nCh;ci++){ch=chs[ci];
if(C.scaleMode==="Manual")ch.vd=C.vdivSteps[C.manualVdivIdx];
else{var mx=0;for(var i=0;i<ch.buf.length;i++){var a=Math.abs(ch.buf[i]);if(a>mx)mx=a}ch.vd=aV(mx)}}
var dV=0;for(ci=0;ci<nCh;ci++)if(chs[ci].vd>dV)dV=chs[ci].vd;
var yH=dV*(C.nDivisions/2);

/* ── Each channel panel ── */
for(ci=0;ci<nCh;ci++){ch=chs[ci];
var gap=14,y0=ci*chH+gap/2,ph=chH-gap,x0=lW;
var rgb=h2r(ch.color);

/* Glassmorphism card clip */
cx.save();rr(x0,y0,pW,ph,10);cx.clip();

/* Card background: very dark, semi-transparent */
cx.fillStyle="rgba(0,0,0,0.35)";cx.fillRect(x0,y0,pW,ph);

/* Subtle inner glow at top edge */
var topGlow=cx.createLinearGradient(0,y0,0,y0+ph*0.25);
topGlow.addColorStop(0,"rgba("+rgb+",0.06)");topGlow.addColorStop(1,"rgba("+rgb+",0)");
cx.fillStyle=topGlow;cx.fillRect(x0,y0,pW,ph);

/* Grid lines: very faint white */
cx.strokeStyle="rgba(255,255,255,0.04)";cx.lineWidth=0.5;cx.setLineDash([]);
for(d=0;d<=C.nDivisions;d++){gy=y0+d*(ph/C.nDivisions);cx.beginPath();cx.moveTo(x0,gy);cx.lineTo(x0+pW,gy);cx.stroke()}
for(d=0;d<=C.nDivisions;d++){gx=x0+d*(pW/C.nDivisions);cx.beginPath();cx.moveTo(gx,y0);cx.lineTo(gx,y0+ph);cx.stroke()}

/* Zero line — soft neon cyan */
var zY=y0+ph/2;
cx.strokeStyle="rgba(0,243,255,0.15)";cx.lineWidth=1;
cx.beginPath();cx.moveTo(x0,zY);cx.lineTo(x0+pW,zY);cx.stroke();

/* Y-axis labels */
cx.fillStyle="rgba(200,210,230,0.40)";cx.font="10px monospace";cx.textAlign="right";cx.textBaseline="middle";
for(d=0;d<=C.nDivisions;d+=2){cx.fillText(fV(yH-d*dV),x0-4,y0+d*(ph/C.nDivisions))}

/* ── Wave ── */
var sd=sm(ch.buf,C.smoothK);
if(sd.length>1){
var sx=pW/C.scopeWindow,yM=zY,sy=(ph/2)/yH;
var si=Math.max(0,sd.length-C.scopeWindow);
var li=sd.length-1,lx=x0+(li-si)*sx,ly=yM-sd[li]*sy;

/* 1. Gradient fill: wave → zero line → back (area between signal and zero) */
cx.beginPath();wavePath(sd,si,x0,sx,yM,sy);
cx.lineTo(lx,zY);cx.lineTo(x0,zY);cx.closePath();
var gf=cx.createLinearGradient(0,y0,0,y0+ph);
gf.addColorStop(0,"rgba("+rgb+",0.25)");
gf.addColorStop(0.45,"rgba("+rgb+",0.10)");
gf.addColorStop(1,"rgba("+rgb+",0.0)");
cx.fillStyle=gf;cx.fill();

/* 2. Neon stroke — same quadratic-midpoint curve with glow */
cx.beginPath();wavePath(sd,si,x0,sx,yM,sy);
cx.strokeStyle=ch.color;cx.lineWidth=2.5;cx.lineJoin="round";cx.lineCap="round";
cx.shadowBlur=15;cx.shadowColor=ch.color;
cx.stroke();cx.shadowBlur=0;

/* 3. ±RMS guide dashes */
if(ch.rV>0){cx.setLineDash([6,4]);cx.strokeStyle=ch.color;cx.lineWidth=0.8;cx.globalAlpha=0.28;
var r1=zY-ch.rV*sy,r2=zY+ch.rV*sy;
cx.beginPath();cx.moveTo(x0,r1);cx.lineTo(x0+pW,r1);cx.stroke();
cx.beginPath();cx.moveTo(x0,r2);cx.lineTo(x0+pW,r2);cx.stroke();
cx.setLineDash([]);cx.globalAlpha=1}
}

cx.restore(); /* end clip */

/* Glass border */
cx.strokeStyle="rgba(255,255,255,0.10)";cx.lineWidth=1;
rr(x0,y0,pW,ph,10);cx.stroke();

/* Channel name — glowing badge top-left */
cx.shadowBlur=12;cx.shadowColor=ch.color;
cx.fillStyle=ch.color;cx.font="bold 14px 'Segoe UI',monospace";
cx.textAlign="left";cx.textBaseline="top";
cx.fillText(ch.name.toUpperCase(),x0+12,y0+8);cx.shadowBlur=0;

/* RMS live value — top-right */
cx.fillStyle="rgba(230,240,255,0.80)";cx.font="bold 14px monospace";
cx.textAlign="right";cx.textBaseline="top";
cx.fillText(fV(ch.rV),x0+pW-12,y0+8);
} /* end channel loop */

/* ── RMS Power bar panel ── */
var bx=sW+6,bW2=bW-4;
cx.fillStyle="rgba(0,0,0,0.45)";cx.strokeStyle="rgba(255,255,255,0.10)";cx.lineWidth=1;
rr(bx,4,bW2,h-8,8);cx.fill();rr(bx,4,bW2,h-8,8);cx.stroke();
cx.fillStyle="rgba(180,200,255,0.55)";cx.font="bold 10px monospace";
cx.textAlign="center";cx.textBaseline="top";cx.fillText("RMS",bx+bW2/2,14);
var bt=30,bb=h-22,bph=bb-bt,bw=Math.max(4,Math.floor((bW2-16)/nCh)-4);
for(ci=0;ci<nCh;ci++){ch=chs[ci];
var bxx=bx+8+ci*(bw+4),barHt=Math.max(1,(ch.rV/yH)*bph);
var rgb2=h2r(ch.color);
var barG=cx.createLinearGradient(0,bb,0,bb-barHt);
barG.addColorStop(0,ch.color);barG.addColorStop(1,"rgba("+rgb2+",0.3)");
cx.shadowBlur=6;cx.shadowColor=ch.color;
cx.fillStyle=barG;cx.fillRect(bxx,bb-barHt,bw,barHt);cx.shadowBlur=0;
cx.fillStyle="rgba(200,215,235,0.55)";cx.font="9px monospace";
cx.textAlign="center";cx.textBaseline="top";
cx.fillText(ch.name[0].toUpperCase(),bxx+bw/2,bb+4)}

/* ── Status line ── */
cx.fillStyle="rgba(0,220,255,0.35)";cx.font="9px 'Segoe UI',monospace";
cx.textAlign="right";cx.textBaseline="bottom";
cx.fillText("LIVE \u2022 "+C.sampleRate+" Hz \u2022 FILTERED",w-8,h-4);
} /* end render */

/* ── Animation loop ── */
var t0=null,anim=C.isRunning;
function step(){var now=performance.now();if(t0===null)t0=now;
var el=(now-t0)/1000,target=Math.floor(el*C.sampleRate)+C.scopeWindow,nc=target-tg;
if(nc>0){var batch=Math.min(nc,60);
for(var s=0;s<batch;s++){var tt=tg/C.sampleRate;
for(var ki=0;ki<nCh;ki++){var kch=chs[ki],v=gen(kch,tt);
kch.buf.push(v);if(kch.buf.length>C.scopeWindow)kch.buf.shift();
kch.rA.push(v);if(kch.rA.length>=kch.rW){var sq=0;for(var jj=0;jj<kch.rA.length;jj++)sq+=kch.rA[jj]*kch.rA[jj];
kch.rV=Math.sqrt(sq/kch.rA.length);kch.rA=[]}}tg++}}}
function loop(){step();render();if(anim)requestAnimationFrame(loop)}
window.addEventListener("resize",function(){rsz();render()});
render();
if(anim){t0=performance.now();requestAnimationFrame(loop)}
})();
</script></body></html>"""


# ---------------------------------------------------------------------------
# Oscilloscope waveform panel  (fragment  only this re-renders each frame)
# ---------------------------------------------------------------------------

@st.fragment
def _oscilloscope_view() -> None:
    # Fullscreen CSS  hides sidebar and header when enabled
    if st.session_state.get("scope_fullscreen", False):
        st.markdown(
            """<style>
            [data-testid="stSidebar"]  { display:none!important; }
            [data-testid="stHeader"]   { display:none!important; }
            .main .block-container     { max-width:100%!important; padding:0.5rem 1rem!important; }
            </style>""",
            unsafe_allow_html=True,
        )

    active_slots = [s for s in SENSOR_SLOTS if st.session_state.get(f"slot_active_{s['id']}", False)]
    scope_window = st.session_state.get("scope_window", _SIM_WINDOW)
    n_ch = len(active_slots)

    if not active_slots:
        st.info("Enable at least one sensor channel in the sidebar to see waveforms.")
        return

    # Dynamic height: divide available viewport among channels
    # ~620px available after controls row; split equally, min 180px per channel
    avail_h = 620
    per_ch = max(180, avail_h // n_ch)
    SCOPE_HEIGHT = per_ch * n_ch

    # Channel info header strip
    _info_parts = []
    for _ci, _cs in enumerate(active_slots):
        _csid = _cs["id"]
        _auto_tag = "AUTO " if st.session_state["scope_scale_mode"] == "Auto" else ""
        _info_parts.append(
            f"<span style='color:{_slot_color(_csid)};font-family:monospace;font-size:14px;"
            f"background:#111;padding:2px 8px;border-radius:4px;margin-right:6px'>"
            f"CH{_ci + 1} {_muscle_name(_csid)} "
            f"{_auto_tag}{_vdiv_label(_effective_vdiv(_csid))}/div"
            f"</span>"
        )
    st.markdown(
        "<div style='background:#0a0a0a;border:1px solid #222;border-bottom:none;"
        "border-radius:8px 8px 0 0;padding:6px 12px'>" + "".join(_info_parts) + "</div>",
        unsafe_allow_html=True,
    )

    # ── Simulation mode: pure Canvas oscilloscope (60 fps in JS, zero reruns) ──
    if st.session_state.get("sim_mode", False):
        import streamlit.components.v1 as _stc
        _stc.html(
            _build_canvas_scope(
                active_slots,
                scope_window,
                SCOPE_HEIGHT,
                int(st.session_state.get("wave_smooth", 1)),
                float(st.session_state.get("avg_window_sec", 0.5)),
                bool(st.session_state.get("sig_display_running", False)),
                N_DIVISIONS,
                st.session_state.get("scope_scale_mode", "Auto"),
                int(st.session_state.get("scope_vdiv_idx", DEFAULT_VDIV_IDX)),
            ),
            height=SCOPE_HEIGHT + 10,
            scrolling=False,
        )
        return  # ← No st.rerun()!  The JS Canvas self-animates at 60 fps.

    # ── Real sensor mode: Plotly charts with fragment self-rerun ──
    if st.session_state.get("sig_display_running", False):
        _update_wave_buffers()

    SCOPE_BG = "#000000"
    GRID_COLOR = "rgba(0, 200, 80, 0.18)"
    ZERO_COLOR = "rgba(0, 200, 80, 0.40)"

    vdivs = [_effective_vdiv(s["id"]) for s in active_slots]
    display_vdiv = max(vdivs)
    y_half = display_vdiv * (N_DIVISIONS / 2)

    y_ticks_values = [round(display_vdiv * i, 9) for i in range(-N_DIVISIONS // 2, N_DIVISIONS // 2 + 1)]
    y_ticks_text   = [_fmt_v(v) for v in y_ticks_values]
    y_ticks_pos_vals = [v for v in y_ticks_values if v >= 0]
    y_ticks_pos_text = [_fmt_v(v) for v in y_ticks_pos_vals]

    scope_col, bar_col = st.columns([8, 2])

    with scope_col:
        # Stacked subplots — one row per channel (one under the other)
        subplot_titles = [_muscle_name(s["id"]) for s in active_slots]
        fig = make_subplots(
            rows=n_ch, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.06,
            subplot_titles=subplot_titles,
        )
        for ann in fig.layout.annotations:
            ann.update(font=dict(color="#E8E8F0", size=16, family="monospace"))

        for row_i, slot in enumerate(active_slots, 1):
            sid   = slot["id"]
            color = _slot_color(sid)
            muscle = _muscle_name(sid)
            buf: list = list(st.session_state.get(f"wave_buf_{sid}", []))

            # Simple moving-average smoothing — averages ±k nearby samples (display only)
            smooth_k = int(st.session_state.get("wave_smooth", 1))
            if smooth_k > 1 and len(buf) > 3:
                arr = np.array(buf, dtype=np.float64)
                kernel = np.ones(2 * smooth_k + 1) / (2 * smooth_k + 1)
                buf = np.convolve(arr, kernel, mode="same").tolist()

            x_data = list(range(-len(buf) + 1, 1)) if buf else []

            fig.add_trace(go.Scattergl(
                x=x_data, y=buf,
                mode="lines", name=muscle,
                line=dict(color=color, width=1.8),
                hoverinfo="skip",
                showlegend=False,
            ), row=row_i, col=1)

            # Optional envelope overlay
            if st.session_state["show_envelope"] and len(buf) > 10:
                try:
                    from scipy.signal import hilbert
                    env = np.abs(hilbert(np.array(buf))).tolist()
                    fig.add_trace(go.Scattergl(
                        x=x_data, y=env,
                        mode="lines",
                        line=dict(color=color, width=1.0, dash="dot"),
                        opacity=0.30, hoverinfo="skip", showlegend=False,
                    ), row=row_i, col=1)
                except Exception:
                    pass

            # ±RMS guide lines
            avg_v = st.session_state.get(f"avg_val_{sid}", 0.0)
            if avg_v > 0:
                fig.add_hline(
                    y=avg_v,
                    line=dict(color=color, width=1, dash="longdash"),
                    opacity=0.40, row=row_i, col=1,
                )
                fig.add_hline(
                    y=-avg_v,
                    line=dict(color=color, width=1, dash="longdash"),
                    opacity=0.40, row=row_i, col=1,
                )

        fig.update_layout(
            paper_bgcolor=SCOPE_BG, plot_bgcolor=SCOPE_BG,
            height=SCOPE_HEIGHT,
            margin=dict(l=72, r=12, t=36, b=12),
            showlegend=False,
            hovermode=False,
            uirevision="scope",
        )

        # All x-axes share the same range (shared_xaxes=True propagates automatically)
        fig.update_xaxes(
            range=[-scope_window, 0],
            showticklabels=False,
            showgrid=True, gridcolor=GRID_COLOR, gridwidth=1,
            zeroline=False,
            dtick=scope_window / N_DIVISIONS,
            fixedrange=True,
        )

        # Each row has its own y-axis with ticks
        for row_i in range(1, n_ch + 1):
            yaxis_key = "yaxis" if row_i == 1 else f"yaxis{row_i}"
            fig.update_layout(**{
                yaxis_key: dict(
                    range=[-y_half, y_half],
                    tickvals=y_ticks_values,
                    ticktext=y_ticks_text,
                    tickfont=dict(color="rgba(0,220,100,0.75)", size=13, family="monospace"),
                    showgrid=True, gridcolor=GRID_COLOR, gridwidth=1,
                    zeroline=True, zerolinecolor=ZERO_COLOR, zerolinewidth=1,
                    fixedrange=True, side="left",
                )
            })

        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key="oscilloscope")

        # RMS avg readout row — single HTML element avoids nested column churn
        avg_parts = []
        for slot in active_slots:
            sid   = slot["id"]
            color = _slot_color(sid)
            avg_v = abs(st.session_state.get(f"avg_val_{sid}", 0.0))
            avg_parts.append(
                f"<div style='flex:1;text-align:center;background:#060606;"
                f"border:1px solid {color}55;border-radius:8px;padding:6px 4px;margin:0 3px'>"
                f"<div style='font-family:monospace;font-size:11px;color:{color};opacity:0.75'>"
                f"{_muscle_name(sid)}</div>"
                f"<div style='font-family:monospace;font-size:38px;font-weight:700;"
                f"color:{color};line-height:1.1'>{_fmt_v(avg_v)}</div></div>"
            )
        st.markdown(
            "<div style='display:flex;gap:0;margin-top:4px'>" + "".join(avg_parts) + "</div>",
            unsafe_allow_html=True,
        )

    with bar_col:
        bar_fig = go.Figure()
        for slot in active_slots:
            sid    = slot["id"]
            color  = _slot_color(sid)
            muscle = _muscle_name(sid)
            avg_v  = abs(st.session_state.get(f"avg_val_{sid}", 0.0))
            bar_fig.add_trace(go.Bar(
                x=[muscle], y=[avg_v],
                name=muscle,
                marker=dict(color=color, line=dict(width=0)),
                width=0.55,
                hoverinfo="skip",
            ))

        bar_fig.update_layout(
            paper_bgcolor=SCOPE_BG, plot_bgcolor=SCOPE_BG,
            height=SCOPE_HEIGHT,
            margin=dict(l=52, r=6, t=36, b=12),
            barmode="group", bargap=0.15,
            showlegend=False,
            hovermode=False,
            title=dict(
                text="RMS Power",
                font=dict(color="rgba(0,220,100,0.55)", size=14, family="monospace"),
                x=0.5,
            ),
            xaxis=dict(
                showticklabels=True,
                tickfont=dict(color="rgba(200,200,200,0.65)", size=14, family="monospace"),
                showgrid=False, zeroline=False, fixedrange=True,
            ),
            yaxis=dict(
                range=[0, y_half],
                tickvals=y_ticks_pos_vals, ticktext=y_ticks_pos_text,
                tickfont=dict(color="rgba(0,220,100,0.75)", size=14, family="monospace"),
                showgrid=True, gridcolor=GRID_COLOR, gridwidth=1,
                zeroline=True, zerolinecolor=ZERO_COLOR,
                fixedrange=True, side="left",
            ),
            uirevision="power_bar",
        )
        st.plotly_chart(bar_fig, use_container_width=True, config={"displayModeBar": False}, key="power_bar")

        # Digital readout per channel below the bar
        for slot in active_slots:
            sid   = slot["id"]
            color = _slot_color(sid)
            avg_v = abs(st.session_state.get(f"avg_val_{sid}", 0.0))
            st.markdown(
                f"<div style='font-family:monospace;font-size:16px;color:{color};"
                f"background:#0a0a0a;border:1px solid {color}55;"
                f"border-radius:4px;padding:4px 6px;margin-bottom:4px;text-align:center'>"
                f"&#8960; 0.5s {_fmt_v(avg_v)}</div>",
                unsafe_allow_html=True,
            )

    # Fragment self-loop — only this fragment reruns, not the full page
    if st.session_state.get("sig_display_running", False):
        if svc.state == "connected" or st.session_state.get("sim_mode", False):
            time.sleep(0.5)
            st.rerun()


_oscilloscope_view()

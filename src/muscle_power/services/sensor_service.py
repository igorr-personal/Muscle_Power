"""Callibri BLE sensor service using pyneurosdk2."""
from __future__ import annotations

import platform
import threading
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from muscle_power.utils.errors import (
    InvalidStatusTransitionError,
    SDKNotInstalledError,
    SensorConnectionError,
    SensorNotFoundError,
)
from muscle_power.utils.logger import get_logger, log_action

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# SDK import — graceful fallback when pyneurosdk2 not installed
# ---------------------------------------------------------------------------
try:
    from neurosdk.scanner import Scanner
    from neurosdk.cmn_types import (  # type: ignore[import]
        SensorFamily,
        SensorFeature,
        SensorCommand,
        SensorParameter,
        SensorGain,          # ← ADD
        SamplingFrequency,   # ← ADD
        SensorDataOffset,    # ← ADD
    )

    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False
    Scanner = None  # type: ignore[misc,assignment]
    SensorFamily = None  # type: ignore[misc,assignment]
    SensorFeature = None  # type: ignore[misc,assignment]
    SensorCommand = None  # type: ignore[misc,assignment]
    SensorParameter = None  # type: ignore[misc,assignment]
    SensorGain = None        # ← ADD
    SamplingFrequency = None # ← ADD
    SensorDataOffset = None  # ← ADD

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_SIGNAL_BUFFER = 20_000  # samples
MAX_ENVELOPE_BUFFER = 2_000
SCAN_TIMEOUT = 15.0
RECONNECT_DELAYS = [2.0, 4.0, 8.0]

VALID_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "available": {"in-use", "maintenance"},
    "in-use": {"maintenance"},
    "maintenance": {"available", "in-use"},
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SensorInfoDTO:
    name: str
    address: str
    rssi: int = 0
    batt_power: int = -1
    serial_number: str = ""
    firmware_version: str = ""
    is_callibri: bool = True


@dataclass
class SignalSample:
    timestamp_ms: int
    raw_value: float
    envelope_value: float | None = None


# ---------------------------------------------------------------------------
# Bleak generic BLE scan (runs in a worker thread with its own event loop)
# ---------------------------------------------------------------------------

def _bleak_scan_sync(timeout: float) -> "list[SensorInfoDTO]":
    """Discover ALL nearby BLE devices using bleak.  Returns SensorInfoDTO list.
    Runs bleak's async API in a dedicated thread-local event loop so it never
    conflicts with Streamlit's own event loop.
    """
    import asyncio

    async def _scan_async() -> list[tuple[str, str, int]]:
        try:
            from bleak import BleakScanner  # type: ignore[import]
        except ImportError:
            return []
        results: list[tuple[str, str, int]] = []
        try:
            try:
                discovered = await BleakScanner.discover(
                    timeout=timeout, return_adv=True,
                    scanning_mode="active",
                )
            except TypeError:
                # scanning_mode kwarg not supported in this bleak build
                discovered = await BleakScanner.discover(
                    timeout=timeout, return_adv=True,
                )
            if isinstance(discovered, dict):
                for addr, value in discovered.items():
                    try:
                        device, adv = value
                        # Build best name: local_name > device.name > details.Name
                        name = ""
                        if adv and hasattr(adv, "local_name") and adv.local_name:
                            name = adv.local_name.strip()
                        if not name and device.name:
                            name = device.name.strip()
                        # Windows: try device.details.Name (WinRT friendly name)
                        if not name:
                            try:
                                name = (device.details.Name or "").strip()
                            except Exception:
                                pass
                        if not name or name.startswith("Unknown"):
                            name = f"BLE {addr[-8:]}"
                        rssi = int(getattr(adv, "rssi", 0) or 0)
                    except Exception:
                        name, rssi = f"BLE {addr[-8:]}", 0
                    results.append((name, addr, rssi))
            else:
                for d in discovered:
                    name = (d.name or "").strip()
                    if not name:
                        try:
                            name = (d.details.Name or "").strip()
                        except Exception:
                            pass
                    if not name:
                        name = f"BLE {d.address[-8:]}"
                    results.append((name, d.address, 0))
        except TypeError:
            # return_adv keyword not supported in this bleak build
            try:
                discovered = await BleakScanner.discover(timeout=timeout)
                for d in discovered:
                    name = (d.name or "").strip() or d.address
                    results.append((name, d.address, 0))
            except Exception as _e2:
                _log.warning("Bleak fallback scan failed: %s", _e2)
        except Exception as _e1:
            _log.warning("Bleak primary scan failed: %s", _e1)
        return results

    loop = asyncio.new_event_loop()
    try:
        raw = loop.run_until_complete(_scan_async())
    finally:
        loop.close()
    return [
        SensorInfoDTO(name=name, address=addr, rssi=rssi, is_callibri=False)
        for name, addr, rssi in raw
    ]


# ---------------------------------------------------------------------------
# Classic Bluetooth scan via Windows BluetoothFindFirstDevice API
# ---------------------------------------------------------------------------

def _classic_bt_scan_sync(timeout: float) -> list[SensorInfoDTO]:
    """Discover Classic Bluetooth devices using the Windows Bluetooth API.

    Performs an inquiry scan (discovers nearby devices in discoverable mode)
    AND returns paired/remembered devices.  Returns SensorInfoDTO list.
    Only works on Windows; returns empty list on other platforms.
    """
    if platform.system() != "Windows":
        return []

    import ctypes
    import ctypes.wintypes as wt
    from ctypes import Structure, byref, sizeof, POINTER, c_ulonglong, c_ubyte

    class BLUETOOTH_FIND_RADIO_PARAMS(Structure):
        _fields_ = [("dwSize", wt.DWORD)]

    class SYSTEMTIME(Structure):
        _fields_ = [
            ("wYear", wt.WORD), ("wMonth", wt.WORD), ("wDayOfWeek", wt.WORD),
            ("wDay", wt.WORD), ("wHour", wt.WORD), ("wMinute", wt.WORD),
            ("wSecond", wt.WORD), ("wMilliseconds", wt.WORD),
        ]

    class BLUETOOTH_DEVICE_SEARCH_PARAMS(Structure):
        _fields_ = [
            ("dwSize", wt.DWORD),
            ("fReturnAuthenticated", wt.BOOL),
            ("fReturnRemembered", wt.BOOL),
            ("fReturnUnknown", wt.BOOL),
            ("fReturnConnected", wt.BOOL),
            ("fIssueInquiry", wt.BOOL),
            ("cTimeoutMultiplier", c_ubyte),
            ("hRadio", wt.HANDLE),
        ]

    class BLUETOOTH_DEVICE_INFO(Structure):
        _fields_ = [
            ("dwSize", wt.DWORD),
            ("Address", c_ulonglong),
            ("ulClassofDevice", wt.ULONG),
            ("fConnected", wt.BOOL),
            ("fRemembered", wt.BOOL),
            ("fAuthenticated", wt.BOOL),
            ("stLastSeen", SYSTEMTIME),
            ("stLastUsed", SYSTEMTIME),
            ("szName", ctypes.c_wchar * 248),
        ]

    def _fmt_addr(addr_int: int) -> str:
        b = addr_int.to_bytes(8, byteorder="little")
        return ":".join(f"{x:02X}" for x in b[:6])

    # Load the Bluetooth API DLL
    try:
        bt = ctypes.WinDLL("bthprops.cpl")
    except OSError:
        try:
            bt = ctypes.WinDLL("irprops.cpl")
        except OSError:
            _log.debug("Classic BT DLL not available")
            return []

    # Find the first Bluetooth radio
    BluetoothFindFirstRadio = bt.BluetoothFindFirstRadio
    BluetoothFindFirstRadio.restype = wt.HANDLE
    BluetoothFindFirstRadio.argtypes = [POINTER(BLUETOOTH_FIND_RADIO_PARAMS), POINTER(wt.HANDLE)]

    BluetoothFindRadioClose = bt.BluetoothFindRadioClose
    BluetoothFindRadioClose.restype = wt.BOOL
    BluetoothFindRadioClose.argtypes = [wt.HANDLE]

    rp = BLUETOOTH_FIND_RADIO_PARAMS()
    rp.dwSize = sizeof(BLUETOOTH_FIND_RADIO_PARAMS)
    hRadio = wt.HANDLE()
    hFindRadio = BluetoothFindFirstRadio(byref(rp), byref(hRadio))

    INVALID = 0xFFFFFFFFFFFFFFFF if sizeof(wt.HANDLE) == 8 else 0xFFFFFFFF
    if not hFindRadio or hFindRadio == INVALID:
        _log.debug("No Bluetooth radio found")
        return []
    BluetoothFindRadioClose(hFindRadio)

    # Set up device search
    BluetoothFindFirstDevice = bt.BluetoothFindFirstDevice
    BluetoothFindFirstDevice.restype = wt.HANDLE
    BluetoothFindFirstDevice.argtypes = [POINTER(BLUETOOTH_DEVICE_SEARCH_PARAMS), POINTER(BLUETOOTH_DEVICE_INFO)]

    BluetoothFindNextDevice = bt.BluetoothFindNextDevice
    BluetoothFindNextDevice.restype = wt.BOOL
    BluetoothFindNextDevice.argtypes = [wt.HANDLE, POINTER(BLUETOOTH_DEVICE_INFO)]

    BluetoothFindDeviceClose = bt.BluetoothFindDeviceClose
    BluetoothFindDeviceClose.restype = wt.BOOL
    BluetoothFindDeviceClose.argtypes = [wt.HANDLE]

    inquiry_mult = max(1, int(timeout)) if timeout > 0 else 0
    params = BLUETOOTH_DEVICE_SEARCH_PARAMS()
    params.dwSize = sizeof(BLUETOOTH_DEVICE_SEARCH_PARAMS)
    params.fReturnAuthenticated = True
    params.fReturnRemembered = True
    params.fReturnUnknown = True
    params.fReturnConnected = True
    params.fIssueInquiry = timeout > 0
    params.cTimeoutMultiplier = inquiry_mult
    params.hRadio = hRadio

    di = BLUETOOTH_DEVICE_INFO()
    di.dwSize = sizeof(BLUETOOTH_DEVICE_INFO)

    results: list[SensorInfoDTO] = []
    _log.info("Classic BT inquiry scan (timeout=%.0fs) ...", timeout)

    hFind = BluetoothFindFirstDevice(byref(params), byref(di))
    if not hFind or hFind == INVALID or hFind == 0:
        _log.info("Classic BT scan: 0 devices found")
        return []

    # First device
    name = (di.szName or "").strip() or f"BT {_fmt_addr(di.Address)[-8:]}"
    results.append(SensorInfoDTO(name=name, address=_fmt_addr(di.Address), is_callibri=False))

    while BluetoothFindNextDevice(hFind, byref(di)):
        name = (di.szName or "").strip() or f"BT {_fmt_addr(di.Address)[-8:]}"
        results.append(SensorInfoDTO(name=name, address=_fmt_addr(di.Address), is_callibri=False))

    BluetoothFindDeviceClose(hFind)
    _log.info("Classic BT scan: %d device(s) found", len(results))
    return results


# ---------------------------------------------------------------------------
# Status state machine
# ---------------------------------------------------------------------------


class SensorStatus:
    """Sensor availability state machine with audit history."""

    VALID = {"available", "in-use", "maintenance"}

    def __init__(self, sensor_id: str) -> None:
        self.sensor_id = sensor_id
        self._current = "available"
        self._history: list[dict[str, str]] = []

    @property
    def current(self) -> str:
        return self._current

    def transition_to(
        self,
        new_status: str,
        *,
        require_session_complete: bool = False,
        note: str | None = None,
    ) -> None:
        if new_status not in self.VALID:
            raise InvalidStatusTransitionError(
                f"Invalid status '{new_status}'. Must be one of {self.VALID}"
            )
        allowed = VALID_STATUS_TRANSITIONS.get(self._current, set())
        if new_status not in allowed:
            if (
                self._current == "in-use"
                and new_status == "available"
                and require_session_complete
            ):
                raise InvalidStatusTransitionError(
                    "Cannot transition from in-use to available without completing session"
                )
            raise InvalidStatusTransitionError(
                f"Cannot transition from {self._current!r} to {new_status!r}"
            )
        self._history.append(
            {
                "from_status": self._current,
                "to_status": new_status,
                "changed_at": datetime.now(tz=timezone.utc).isoformat(),
                "note": note or "",
            }
        )
        self._current = new_status

    def get_history(self) -> list[dict[str, str]]:
        return list(self._history)


# ---------------------------------------------------------------------------
# Multi-sensor registry
# ---------------------------------------------------------------------------


class SensorManager:
    """Registry for multiple connected sensors (future multi-sensor support)."""

    def __init__(self) -> None:
        self._sensors: dict[str, Any] = {}
        self._lock = threading.Lock()

    def add_sensor(self, sensor: Any) -> None:
        with self._lock:
            self._sensors[sensor.name] = sensor

    def remove_sensor(self, name: str) -> None:
        with self._lock:
            self._sensors.pop(name, None)

    def get_sensor(self, name: str) -> Any | None:
        with self._lock:
            return self._sensors.get(name)

    @property
    def connected_sensors(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._sensors)


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------


class CallibriService:
    """
    Thread-safe service that manages one Callibri BLE connection, streams
    raw EMG + envelope samples into bounded deques, and exposes live metrics
    for the Streamlit UI.
    """

    def __init__(self) -> None:
        self._scanner: Any = None
        self._sensor: Any = None
        self._sensor_info: SensorInfoDTO | None = None
        self._state = "disconnected"
        self._raw_buffer: deque[SignalSample] = deque(maxlen=MAX_SIGNAL_BUFFER)
        self._envelope_buffer: deque[SignalSample] = deque(maxlen=MAX_ENVELOPE_BUFFER)
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="callibri")
        self._battery: int = -1
        self._electrode_state: str = "Unknown"
        self._on_disconnect_callbacks: list[Callable[[], None]] = []
        self._session_start_ms: int | None = None
        self._error_message: str = ""
        self._raw_sensor_cache: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        return self._state

    @property
    def sensor_info(self) -> SensorInfoDTO | None:
        return self._sensor_info

    @property
    def battery(self) -> int:
        return self._battery

    @property
    def electrode_state(self) -> str:
        return self._electrode_state

    @property
    def error_message(self) -> str:
        return self._error_message

    def on_disconnect(self, cb: Callable[[], None]) -> None:
        self._on_disconnect_callbacks.append(cb)

    # ------------------------------------------------------------------
    # BLE scanning
    # ------------------------------------------------------------------

    def scan(self, timeout: float = SCAN_TIMEOUT) -> list[SensorInfoDTO]:
        """Scan for Callibri/Kolibri sensors and return found devices."""
        if not SDK_AVAILABLE:
            raise SDKNotInstalledError(
                "Callibri SDK library not found. Please run: pip install pyneurosdk2"
            )
        self._state = "scanning"
        self._error_message = ""
        log_action(_log, "ble_scan_start", {"timeout": timeout})
        try:
            self._scanner = Scanner([SensorFamily.LECallibri, SensorFamily.LEKolibri])
        except Exception as exc:
            self._state = "error"
            self._error_message = (
                "No Bluetooth adapter detected. Please enable Bluetooth in Windows Settings "
                "or plug in a Bluetooth dongle."
            )
            raise SensorConnectionError(self._error_message) from exc

        self._scanner.start()
        time.sleep(timeout)
        self._scanner.stop()

        infos = [
            SensorInfoDTO(
                name=s.name,
                address=s.address,
                rssi=getattr(s, "rssi", 0),
            )
            for s in self._scanner.sensors()
        ]
        self._state = "disconnected"
        log_action(_log, "ble_scan_complete", {"found": len(infos)})
        return infos

    def scan_all_ble(self, timeout: float = SCAN_TIMEOUT) -> list[SensorInfoDTO]:
        """Scan for ALL nearby Bluetooth devices (BLE + Classic).

        Callibri/Kolibri are flagged is_callibri=True.
        Non-matching devices are still returned with is_callibri=False so the user can see
        every device in range.
        Falls back to bleak-only scanning when the Callibri SDK is not installed.
        """
        self._state = "scanning"
        self._error_message = ""
        self._raw_sensor_cache: dict[str, Any] = {}
        #self._raw_sensor_cache = {}
        log_action(_log, "ble_scan_all_start", {"timeout": timeout})

        seen_addrs: set[str] = set()
        all_infos: list[SensorInfoDTO] = []

        # --- scan specifically for Callibri first (only if SDK available) ---
        if SDK_AVAILABLE:
            try:
                callibri_scanner = Scanner([SensorFamily.LECallibri, SensorFamily.LEKolibri])
                callibri_scanner.start()
                time.sleep(timeout)
                callibri_scanner.stop()
                self._scanner = callibri_scanner

                for s in callibri_scanner.sensors():
                    seen_addrs.add(s.address.upper())
                    self._raw_sensor_cache[s.address.upper()] = s   # ← is this line here?
                    all_infos.append(
                        SensorInfoDTO(
                            name=s.name,
                            address=s.address,
                            rssi=getattr(s, "rssi", 0),
                            is_callibri=True,
                        )
                    )
            except Exception as exc:
                _log.warning("Callibri SDK scan failed: %s", exc)

        # --- generic BLE scan via bleak (finds ALL BLE devices) ---
        try:
            bleak_results = _bleak_scan_sync(min(timeout, 8.0))
            for dto in bleak_results:
                if dto.address.upper() not in seen_addrs:
                    seen_addrs.add(dto.address.upper())
                    all_infos.append(dto)
        except Exception as exc:
            _log.warning("Bleak scan failed: %s", exc)
            if not all_infos:  # ← ADD THIS CONDITION
                self._error_message = f"BLE scan error: {exc}"

        # --- Classic Bluetooth scan (Windows only) ---
        try:
            classic_results = _classic_bt_scan_sync(min(timeout, 8.0))
            for dto in classic_results:
                if dto.address.upper() not in seen_addrs:
                    seen_addrs.add(dto.address.upper())
                    all_infos.append(dto)
        except Exception as exc:
            _log.warning("Classic BT scan failed: %s", exc)

        if not all_infos and not SDK_AVAILABLE:
            self._state = "disconnected"
            self._error_message = (
                "No Bluetooth devices found. Note: Callibri SDK is not installed "
                "(pip install pyneurosdk2). Only generic BLE/BT devices are scanned."
            )
        else:
            self._state = "disconnected"
            self._error_message = ""  # ← ADD THIS: clear any stale error message

        log_action(_log, "ble_scan_all_complete", {"total": len(all_infos)})
        return all_infos

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    def connect_by_address(self, address: str) -> None:
        """Connect to a sensor by BLE address using a fresh scanner."""
        if not SDK_AVAILABLE:
            raise SDKNotInstalledError(
                "Callibri SDK library not found. Please run: pip install pyneurosdk2"
            )
        self._state = "connecting"
        self._error_message = ""
        log_action(_log, "sensor_connect_by_address", {"address": address})
        try:
            scanner = Scanner([SensorFamily.LECallibri, SensorFamily.LEKolibri])
            scanner.start()
            time.sleep(5.0)
            scanner.stop()
            self._scanner = scanner
            raw_list = [s for s in scanner.sensors() if s.address == address]
            if not raw_list:
                # try case-insensitive
                raw_list = [s for s in scanner.sensors()
                            if s.address.upper() == address.upper()]
            if not raw_list:
                self._state = "error"
                self._error_message = f"Sensor {address} not found. Please ensure it is powered on."
                raise SensorNotFoundError(self._error_message)
            self.connect(raw_list[0])
        except SensorNotFoundError:
            raise
        except Exception as exc:
            self._state = "error"
            self._error_message = f"Failed to connect: {exc}"
            raise SensorConnectionError(self._error_message) from exc


    def connect(self, raw_sensor_info: Any) -> None:
        """Connect to a specific sensor (must be called in a background thread)."""
        if not SDK_AVAILABLE:
            raise SDKNotInstalledError(
                "Callibri SDK library not found. Please run: pip install pyneurosdk2"
            )
        if self._state == "connected":
            return
        self._state = "connecting"
        self._error_message = ""
        log_action(_log, "sensor_connect_start", {"address": getattr(raw_sensor_info, "address", "?")})

        try:
            sensor = self._scanner.create_sensor(raw_sensor_info)
        except Exception as exc:
            self._state = "error"
            self._error_message = f"Failed to connect to sensor: {exc}"
            raise SensorConnectionError(self._error_message) from exc

        self._sensor = sensor
        self._battery = sensor.batt_power
        self._sensor_info = SensorInfoDTO(
            name=sensor.name,
            address=sensor.address,
            rssi=getattr(raw_sensor_info, "rssi", 0),
            batt_power=self._battery,
            serial_number=getattr(sensor, "serial_number", ""),
            firmware_version=str(getattr(sensor, "version", "")),
        )
        self._state = "connected"

        sensor.sensorStateChanged = self._on_state_changed
        sensor.batteryChanged = self._on_battery_changed
        sensor.callibriElectrodeStateChanged = self._on_electrode_state  # ← ADD THIS
        log_action(_log, "sensor_connected", {
            "name": sensor.name,
            "address": sensor.address,
            "battery": self._battery,
        })

    def connect_first_found(self, preferred_address: str = "", timeout: float = SCAN_TIMEOUT) -> None:
        """Convenience: scan then auto-connect to the first (or preferred) sensor."""
        found = self.scan(timeout=timeout)
        if not found:
            raise SensorNotFoundError(
                "No Callibri sensors found. Ensure the sensor is powered on, "
                "charged, and within 5 meters."
            )
        if preferred_address:
            matching = [s for s in self._scanner.sensors() if s.address == preferred_address]
            raw = matching[0] if matching else self._scanner.sensors()[0]
        else:
            raw = self._scanner.sensors()[0]

        future: Future = self._executor.submit(self.connect, raw)
        future.result(timeout=30.0)

    # ------------------------------------------------------------------
    # Signal streaming
    # ------------------------------------------------------------------
    
    def set_emg_defaults(self):
        if not self._sensor:
            return
        sensor = self._sensor

        try:
            sensor.sampling_frequency = SamplingFrequency.FrequencyHz1000
        except Exception as exc:
            _log.warning("Could not set sampling frequency: %s", exc)
        try:
            sensor.gain = SensorGain.Gain12
        except Exception as exc:
            _log.warning("Could not set gain: %s", exc)
        try:
            sensor.data_offset = SensorDataOffset.DataOffset3
        except Exception as exc:
            _log.warning("Could not set data offset: %s", exc)

    #    if sensor.IsSupportedCommand(SensorCommand.StartSignal):
    #        sensor.ExecCommand(SensorCommand.StartSignal)

    def start_streaming(self, session_start_ms: int | None = None) -> None:
        if not self._sensor or self._state != "connected":
            raise Exception("Sensor not connected")

        self._session_start_ms = session_start_ms or int(time.time() * 1000)
        sensor = self._sensor

        # Registering with the correct 'callibri' prefix required by the SDK
        if sensor.is_supported_feature(SensorFeature.Signal):
            sensor.callibriElectrodeStateChanged = self._on_electrode_state
            sensor.callibriSignalDataReceived = self._on_signal_data

        if sensor.is_supported_feature(SensorFeature.Envelope):
            sensor.callibriEnvelopeDataReceived = self._on_envelope_data

        if sensor.is_supported_command(SensorCommand.StartSignal):
            sensor.exec_command(SensorCommand.StartSignal)


    def stop_streaming(self) -> None:
        """Stop signal acquisition."""
        if not self._sensor:
            return
        sensor = self._sensor
        try:
            if sensor.is_supported_command(SensorCommand.StopSignal):
                sensor.exec_command(SensorCommand.StopSignal)
            if sensor.is_supported_command(SensorCommand.StopEnvelope):
                sensor.exec_command(SensorCommand.StopEnvelope)
        except Exception as exc:
            _log.warning("Error stopping signal: %s", exc)
        log_action(_log, "streaming_stopped")

    def disconnect(self) -> None:
        """Stop streaming and disconnect."""
        self.stop_streaming()
        if self._sensor:
            try:
                self._sensor.disconnect()
                del self._sensor
                self._sensor = None
            except Exception as exc:
                _log.warning("Disconnect error: %s", exc)
        self._state = "disconnected"
        self._sensor_info = None
        log_action(_log, "sensor_disconnected")

    # ------------------------------------------------------------------
    # Data access
    # ------------------------------------------------------------------

    def get_raw_samples(self, max_samples: int | None = None) -> list[SignalSample]:
        with self._lock:
            buf = list(self._raw_buffer)
        return buf[-max_samples:] if max_samples else buf

    def get_envelope_samples(self, max_samples: int | None = None) -> list[SignalSample]:
        with self._lock:
            buf = list(self._envelope_buffer)
        return buf[-max_samples:] if max_samples else buf

    def get_current_power(self) -> float:
        """Return latest envelope value (muscle power proxy) in volts."""
        with self._lock:
            if self._envelope_buffer:
                return float(self._envelope_buffer[-1].envelope_value or 0.0)
        return 0.0

    def get_signal_quality(self) -> str:
        """Return current electrode contact state."""
        return self._electrode_state

    # ------------------------------------------------------------------
    # Internal callbacks
    # ------------------------------------------------------------------

    def _on_signal_data(self, sensor: Any, data: Any) -> None:
        now_ms = int(time.time() * 1000)
        base_ms = self._session_start_ms or now_ms
        try:
            for packet in data:
                samples = getattr(packet, "samples", [])
                if not samples:
                    # single-value packet
                    val = getattr(packet, "sample", None) or packet
                    samples = [val]
                for i, value in enumerate(samples):
                    if value is None:
                        continue
                    fval = float(value)
                    if not (fval == fval) or abs(fval) == float("inf"):   # NaN / Inf guard
                        continue
                    ts = base_ms + i
                    with self._lock:
                        self._raw_buffer.append(SignalSample(timestamp_ms=ts, raw_value=fval))
        except Exception as exc:
            _log.warning("Signal callback error: %s", exc)

    def _on_envelope_data(self, sensor: Any, data: Any) -> None:
        now_ms = int(time.time() * 1000)
        try:
            # 'data' is typically a list of packets from the SDK
            for packet in data:
                # 1. FIX: Use PascalCase "Sample" to match the SDK
                value = getattr(packet, "sample", None)
                if value is None:
                    samples = getattr(packet, "samples", [])
                    value = samples[0] if samples else None


                
                fval = float(value)
            
                # 3. SAVE TO BUFFER: This is what the Streamlit chart reads
                # We save the relative time (ms) and the float value
                with self._lock:
                    self._envelope_buffer.append(SignalSample(
                        timestamp_ms=now_ms,
                        raw_value=0.0,
                        envelope_value=fval,
                    ))
            
            # Optional: Debug print to see if numbers are moving in the terminal
            # print(f"DEBUG: Envelope value received: {fval}")

        except Exception as e:
            print(f"Error in envelope callback: {e}")

    def _on_state_changed(self, sensor: Any, state: Any) -> None:
        state_str = str(state)
        _log.info("Sensor state changed: %s", state_str)
        if "disconnect" in state_str.lower() or "lost" in state_str.lower():
            prev = self._state
            self._state = "disconnected"
            if prev == "connected":
                self._error_message = "Sensor disconnected. Attempting to reconnect…"
                for cb in self._on_disconnect_callbacks:
                    try:
                        cb()
                    except Exception:
                        pass

    def _on_battery_changed(self, sensor: Any, battery: int) -> None:
        self._battery = battery
        if battery <= 5:
            _log.warning("CRITICAL battery %d%% — auto-saving", battery)
        elif battery <= 10:
            _log.warning("Sensor battery critically low: %d%%", battery)
        elif battery <= 20:
            _log.info("Sensor battery low: %d%%", battery)

    def _on_electrode_state(self, sensor, state):
        # Mapping based on Callibri SDK standards
        # 0 = Unknown/Initializing
        # 1 = Normal (Contact is good!)
        # 2 = HighResistance (Contact is poor)
        # 3 = Detached (No contact)

        # Extract the raw integer value from the SDK object
        val = getattr(state, "value", state)

        mapping = {
            0: "Initializing",
            1: "Normal",
            2: "High Resistance",
            3: "Detached"
        }

        self._electrode_state = mapping.get(val, "Unknown")
        _log.info("Electrode state: %s", self._electrode_state)




# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_service: CallibriService | None = None


def get_sensor_service() -> CallibriService:
    global _service
    if _service is None:
        _service = CallibriService()
    return _service


# ---------------------------------------------------------------------------
# Test-friendly helpers
# ---------------------------------------------------------------------------


def connect_sensor(sensor_info: Any = None, timeout: float = SCAN_TIMEOUT) -> Any:
    """Convenience wrapper used in unit tests (creates its own scanner)."""
    if not SDK_AVAILABLE:
        raise SDKNotInstalledError("Callibri SDK not installed.")
    scanner = Scanner([SensorFamily.LECallibri, SensorFamily.LEKolibri])
    scanner.start()
    time.sleep(timeout)
    scanner.stop()
    sensors = scanner.sensors()
    if not sensors:
        raise SensorNotFoundError("No Callibri sensors found")
    target = sensor_info or sensors[0]
    with ThreadPoolExecutor() as ex:
        fut = ex.submit(scanner.create_sensor, target)
        return fut.result(timeout=30)

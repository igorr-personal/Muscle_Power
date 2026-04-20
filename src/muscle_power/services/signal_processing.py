"""EMG signal processing: bandpass filter, RMS envelope, FFT, rep detection."""
from __future__ import annotations

import numpy as np
from scipy import signal as sp_signal

from muscle_power.utils.errors import SignalProcessingError
from muscle_power.utils.logger import get_logger

_log = get_logger(__name__)

EMG_MIN_V = -0.005
EMG_MAX_V = 0.005


def _validate(data: np.ndarray | None, label: str = "Signal") -> np.ndarray:
    if data is None:
        raise SignalProcessingError(f"{label} data cannot be None")
    arr = np.asarray(data, dtype=float) if not isinstance(data, np.ndarray) else data.astype(float)
    if arr.size == 0:
        raise SignalProcessingError(f"{label} data cannot be empty")
    if not np.all(np.isfinite(arr)):
        raise SignalProcessingError(
            f"{label} contains invalid values (NaN or Inf). Check electrode contact."
        )
    return arr


def bandpass_filter(
    data: np.ndarray,
    fs: float,
    low_hz: float = 20.0,
    high_hz: float = 450.0,
) -> np.ndarray:
    """4th-order Butterworth bandpass filter for raw EMG."""
    data = _validate(data, "Bandpass input")
    nyq = fs / 2.0
    low = max(low_hz / nyq, 1e-5)
    high = min(high_hz / nyq, 0.999)
    b, a = sp_signal.butter(4, [low, high], btype="band")
    return sp_signal.filtfilt(b, a, data)


def compute_rms_envelope(
    data: np.ndarray,
    fs: float,
    window_ms: float = 200.0,
) -> np.ndarray:
    """Sliding-window RMS amplitude envelope."""
    data = _validate(data, "RMS input")
    win = max(1, int(fs * window_ms / 1000.0))
    win = min(win, len(data))
    kernel = np.ones(win) / win
    ms = np.convolve(data ** 2, kernel, mode="same")
    return np.sqrt(np.maximum(ms, 0.0))


def compute_hilbert_envelope(data: np.ndarray) -> np.ndarray:
    """Amplitude envelope via Hilbert transform."""
    data = _validate(data, "Hilbert input")
    return np.abs(sp_signal.hilbert(data))


def compute_fft(data: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray]:
    """One-sided FFT magnitude spectrum. Returns (freqs Hz, magnitudes)."""
    data = _validate(data, "FFT input")
    n = len(data)
    n_pad = int(2 ** np.ceil(np.log2(n)))
    window = np.hanning(n)
    spectrum = np.fft.rfft(data * window, n=n_pad)
    magnitudes = np.abs(spectrum) * 2.0 / n
    freqs = np.fft.rfftfreq(n_pad, d=1.0 / fs)
    return freqs, magnitudes


def compute_median_frequency(freqs: np.ndarray, magnitudes: np.ndarray) -> float:
    """Median frequency — shifts down as muscle fatigues."""
    power = magnitudes ** 2
    total = float(np.sum(power))
    if total == 0.0:
        return 0.0
    cumulative = np.cumsum(power)
    idx = int(np.searchsorted(cumulative, total / 2.0))
    return float(freqs[min(idx, len(freqs) - 1)])


def detect_reps(
    envelope: np.ndarray,
    fs: float,
    threshold_factor: float = 0.3,
) -> list[int]:
    """Peak detection on RMS envelope. Returns sample indices of rep peaks."""
    envelope = _validate(envelope, "Rep detection input")
    threshold = threshold_factor * float(np.max(envelope))
    if threshold == 0.0:
        return []
    min_distance = max(1, int(fs * 0.5))
    peaks, _ = sp_signal.find_peaks(envelope, height=threshold, distance=min_distance)
    return peaks.tolist()


def compute_fatigue_index(envelope: np.ndarray) -> float:
    """
    Fatigue index = (first-quarter mean - last-quarter mean) / first-quarter mean.
    Positive values indicate fatigue.
    """
    envelope = _validate(envelope, "Fatigue index input")
    if len(envelope) < 4:
        return 0.0
    q = max(len(envelope) // 4, 1)
    first = float(np.mean(envelope[:q]))
    last = float(np.mean(envelope[-q:]))
    if first == 0.0:
        return 0.0
    return (first - last) / first


def validate_signal_quality(
    data: np.ndarray,
    fs: float,
    window_sec: float = 2.0,
) -> tuple[bool, str]:
    """
    Check for flat-line or saturation issues.
    Returns (ok, message) where ok=True means signal quality is acceptable.
    """
    data = _validate(data, "Quality check input")
    win = int(fs * window_sec)
    segment = data[-win:] if len(data) >= win else data
    std = float(np.std(segment))
    max_val = float(np.max(np.abs(segment)))
    if max_val > abs(EMG_MAX_V) * 0.99:
        return (
            False,
            "Signal saturated — ADC clipping detected. "
            "Check electrode placement and Gain settings.",
        )
    if std < 1e-6:
        return (
            False,
            "Poor electrode contact detected — flat line. "
            "Please reposition the sensor on the muscle and ensure skin is clean.",
        )
    return True, "OK"


def process_signal(
    raw: np.ndarray | None,
    signal_type: str = "Both",
    fs: float = 250.0,
    window_ms: float = 200.0,
) -> dict[str, np.ndarray]:
    """
    Process raw EMG into display-ready components.

    Args:
        raw:         Raw EMG samples (numpy array, in volts)
        signal_type: "Raw" | "Envelope" | "Both"
        fs:          Sampling frequency in Hz
        window_ms:   RMS window size in milliseconds

    Returns:
        dict with keys "raw" and/or "power_envelope" depending on signal_type.
    """
    raw_arr = _validate(raw)
    result: dict[str, np.ndarray] = {}

    if signal_type in ("Raw", "Both"):
        result["raw"] = bandpass_filter(raw_arr, fs=fs)

    if signal_type in ("Envelope", "Both"):
        src = result.get("raw", bandpass_filter(raw_arr, fs=fs))
        result["power_envelope"] = compute_rms_envelope(src, fs=fs, window_ms=window_ms)

    return result


def decimate_for_display(data: np.ndarray, target_rate: int = 60) -> np.ndarray:
    """Downsample data for live chart rendering without losing peak information."""
    if len(data) <= target_rate:
        return data
    factor = max(1, len(data) // target_rate)
    return data[::factor]

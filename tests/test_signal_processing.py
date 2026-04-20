"""Tests for signal_processing.py."""
from __future__ import annotations

import numpy as np
import pytest

from muscle_power.services.signal_processing import (
    compute_fatigue_index,
    compute_fft,
    compute_median_frequency,
    compute_rms_envelope,
    detect_reps,
    process_signal,
    validate_signal_quality,
)
from muscle_power.utils.errors import SignalProcessingError


FS = 250.0  # Hz


def _synthetic_emg(n: int = 250, amplitude: float = 0.001) -> np.ndarray:
    """Gaussian noise as synthetic surface EMG."""
    rng = np.random.default_rng(42)
    return rng.standard_normal(n) * amplitude


# ---------------------------------------------------------------------------
# process_signal
# ---------------------------------------------------------------------------


class TestProcessSignal:
    def test_both_returns_raw_and_envelope(self):
        raw = _synthetic_emg()
        result = process_signal(raw, signal_type="Both", fs=FS)
        assert "raw" in result
        assert "power_envelope" in result
        assert len(result["raw"]) == len(raw)
        assert len(result["power_envelope"]) == len(raw)
        assert np.all(result["power_envelope"] >= 0), "Envelope must be non-negative"

    def test_raw_only(self):
        raw = _synthetic_emg()
        result = process_signal(raw, signal_type="Raw", fs=FS)
        assert "raw" in result
        assert "power_envelope" not in result

    def test_envelope_only(self):
        raw = _synthetic_emg()
        result = process_signal(raw, signal_type="Envelope", fs=FS)
        assert "power_envelope" in result
        assert "raw" not in result

    def test_none_input_raises(self):
        with pytest.raises(SignalProcessingError, match="cannot be None"):
            process_signal(None, signal_type="Both")

    def test_empty_input_raises(self):
        with pytest.raises(SignalProcessingError, match="cannot be empty"):
            process_signal(np.array([]), signal_type="Both")

    def test_nan_input_raises(self):
        nan_signal = np.array([0.1, np.nan, 0.3, np.nan, 0.5])
        with pytest.raises(SignalProcessingError, match="invalid values"):
            process_signal(nan_signal, signal_type="Both")

    def test_inf_input_raises(self):
        inf_signal = np.array([0.1, np.inf, 0.3])
        with pytest.raises(SignalProcessingError, match="invalid values"):
            process_signal(inf_signal, signal_type="Both")


# ---------------------------------------------------------------------------
# RMS envelope
# ---------------------------------------------------------------------------


class TestRmsEnvelope:
    def test_output_length_matches_input(self):
        data = _synthetic_emg(500)
        env = compute_rms_envelope(data, fs=FS, window_ms=200)
        assert len(env) == len(data)

    def test_non_negative(self):
        data = _synthetic_emg(500)
        env = compute_rms_envelope(data, fs=FS)
        assert np.all(env >= 0)

    def test_single_sample_large_window(self):
        data = np.array([0.001])
        env = compute_rms_envelope(data, fs=FS, window_ms=200)
        assert len(env) == 1
        assert env[0] >= 0


# ---------------------------------------------------------------------------
# FFT
# ---------------------------------------------------------------------------


class TestFFT:
    def test_output_shapes(self):
        data = _synthetic_emg(256)
        freqs, mags = compute_fft(data, fs=FS)
        assert len(freqs) == len(mags)
        assert len(freqs) > 0

    def test_dominant_freq_sine(self):
        t = np.linspace(0, 1.0, 250, endpoint=False)
        data = 0.001 * np.sin(2 * np.pi * 50 * t)   # pure 50 Hz sine
        freqs, mags = compute_fft(data, fs=FS)
        peak_freq = freqs[np.argmax(mags)]
        assert abs(peak_freq - 50) < 5, f"Expected ~50 Hz, got {peak_freq}"


# ---------------------------------------------------------------------------
# Fatigue index
# ---------------------------------------------------------------------------


class TestFatigueIndex:
    def test_zero_for_constant_signal(self):
        const = np.ones(100) * 0.001
        fi = compute_fatigue_index(const)
        assert abs(fi) < 1e-6

    def test_positive_for_declining_signal(self):
        declining = np.linspace(1.0, 0.1, 200)
        fi = compute_fatigue_index(declining)
        assert fi > 0

    def test_short_signal(self):
        fi = compute_fatigue_index(np.array([1.0, 2.0]))
        assert isinstance(fi, float)


# ---------------------------------------------------------------------------
# Rep detection
# ---------------------------------------------------------------------------


class TestRepDetection:
    def test_detects_reps(self):
        t = np.linspace(0, 10.0, int(10 * FS), endpoint=False)
        # 5 reps at ~1 Hz
        env = np.abs(np.sin(2 * np.pi * 0.5 * t)) * 0.001
        reps = detect_reps(env, fs=FS)
        assert len(reps) >= 4, f"Expected ≥4 reps, got {len(reps)}"

    def test_no_reps_flat_signal(self):
        flat = np.ones(250) * 0.0001
        reps = detect_reps(flat, fs=FS, threshold_factor=0.3)
        assert len(reps) == 0


# ---------------------------------------------------------------------------
# Signal quality
# ---------------------------------------------------------------------------


class TestSignalQuality:
    def test_ok_for_good_signal(self):
        data = _synthetic_emg(1000)
        ok, msg = validate_signal_quality(data, fs=FS)
        assert ok, msg

    def test_flat_line_detected(self):
        flat = np.zeros(500)
        ok, msg = validate_signal_quality(flat, fs=FS)
        assert not ok
        assert "flat" in msg.lower() or "contact" in msg.lower()

    def test_saturated_signal_detected(self):
        rng = np.random.default_rng(0)
        # slight noise so std > 0, but all values at ADC ceiling
        saturated = np.full(500, 0.0051) + rng.standard_normal(500) * 1e-7
        ok, msg = validate_signal_quality(saturated, fs=FS)
        assert not ok
        assert "saturated" in msg.lower() or "clipping" in msg.lower()

"""Synthetic EMG waveform generator.

Shared between the Streamlit web app and the PyQt6 desktop app.
Produces realistic-looking EMG burst patterns using a reproducible
per-slot random seed so each channel has a distinct but stable signal.
"""
from __future__ import annotations

import numpy as np

SIM_FS: int = 200           # samples / second
SIM_CHUNK: int = 25         # samples produced per call

# Burst duration / period (seconds)
_BURST_DURATION = 0.9
_BURST_PERIOD = 3.0


def next_chunk(slot_id: str, frame: int) -> np.ndarray:
    """Return *SIM_CHUNK* synthetic EMG samples for *slot_id* at frame *frame*.

    Each slot uses a deterministic seed derived from `slot_id` so the
    signal is reproducible and unique per channel.

    Parameters
    ----------
    slot_id:
        One of ``"red"``, ``"blue"``, ``"green"``, ``"white"``.
    frame:
        Monotonically increasing frame counter (drives the time axis).

    Returns
    -------
    numpy.ndarray
        Shape ``(SIM_CHUNK,)`` — voltage values in volts.
    """
    rng = np.random.RandomState(hash(slot_id) % (2**31))
    t = np.linspace(
        frame * SIM_CHUNK / SIM_FS,
        (frame * SIM_CHUNK + SIM_CHUNK - 1) / SIM_FS,
        SIM_CHUNK,
    )
    noise = rng.randn(SIM_CHUNK) * 0.00015

    burst_phase = (frame * SIM_CHUNK / SIM_FS) % _BURST_PERIOD
    if burst_phase < _BURST_DURATION:
        amplitude = 0.0018 * np.sin(np.pi * burst_phase / _BURST_DURATION) ** 2
        signal = amplitude * np.sin(2 * np.pi * 85.0 * t)
        noise = noise + signal

    slot_offsets = {"red": 0.0, "blue": 0.35, "green": 0.65, "white": 1.0}
    offset_phase = slot_offsets.get(slot_id, 0.0)
    noise = noise + 0.0001 * np.sin(2 * np.pi * 2.5 * t + offset_phase * 2 * np.pi)
    return noise

"""Audio analysis: loudness curve and peak detection (crowd / commentator excitement)."""

from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np


def read_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        rate = w.getframerate()
        n = w.getnframes()
        ch = w.getnchannels()
        data = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return data, rate


def loudness_curve(wav: Path, hop: float = 0.5) -> np.ndarray:
    """RMS level in dBFS per `hop` seconds."""
    data, rate = read_wav_mono(wav)
    step = max(1, int(rate * hop))
    n = len(data) // step
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    frames = data[: n * step].reshape(n, step)
    rms = np.sqrt(np.mean(frames**2, axis=1) + 1e-12)
    return (20 * np.log10(rms)).astype(np.float32)


@dataclass
class Peak:
    time: float
    score: float  # z-score above the local baseline


def find_peaks(
    curve: np.ndarray, hop: float = 0.5, *, min_gap: float = 8.0, z: float = 1.8, top: int = 30
) -> list[Peak]:
    """Moments that are much louder than their surroundings (relative to a ~60 s rolling median)."""
    if len(curve) < 8:
        return []
    win = max(5, int(60 / hop)) | 1
    pad = np.pad(curve, win // 2, mode="edge")
    base = np.array([np.median(pad[i : i + win]) for i in range(len(curve))])
    spread = np.std(curve) + 1e-6
    scores = (curve - base) / spread
    order = np.argsort(-scores)
    peaks: list[Peak] = []
    for i in order:
        if scores[i] < z or len(peaks) >= top:
            break
        t = i * hop
        if all(abs(t - p.time) >= min_gap for p in peaks):
            peaks.append(Peak(time=t, score=float(scores[i])))
    return sorted(peaks, key=lambda p: p.time)

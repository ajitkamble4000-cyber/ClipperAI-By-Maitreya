"""Turn noisy per-sample target positions into a smooth, jitter-free virtual camera path."""

from __future__ import annotations

import numpy as np


def fill_gaps(
    samples: list[tuple[float, float | None]], default: float = 0.5
) -> tuple[np.ndarray, np.ndarray]:
    t = np.array([s[0] for s in samples], dtype=np.float64)
    v = np.array([np.nan if s[1] is None else s[1] for s in samples], dtype=np.float64)
    if len(v) == 0:
        return np.array([0.0]), np.array([default])
    good = ~np.isnan(v)
    if not good.any():
        return t, np.full_like(t, default)
    # Hold the last known position through gaps (camera should not drift when a face is briefly lost).
    v = np.interp(t, t[good], v[good], left=v[good][0], right=v[good][-1])
    return t, v


def median_filter(v: np.ndarray, k: int = 5) -> np.ndarray:
    if len(v) < 3:
        return v
    k = min(k | 1, len(v) // 2 * 2 + 1)
    pad = k // 2
    p = np.pad(v, pad, mode="edge")
    return np.array([np.median(p[i : i + k]) for i in range(len(v))])


def camera_path(
    samples: list[tuple[float, float | None]],
    *,
    duration: float,
    fps: int = 30,
    crop_frac: float = 0.316,
    dead_zone: float = 0.12,
    max_speed: float = 0.35,
    smooth_s: float = 0.6,
) -> np.ndarray:
    """Per-output-frame crop center (0..1).

    dead_zone: fraction of the crop width the target may move before the camera follows.
    max_speed: max pan speed in source widths per second.
    smooth_s:  Gaussian smoothing window (seconds) applied at the end.
    """
    t, v = fill_gaps(samples)
    v = median_filter(v, 5)
    n = max(1, int(round(duration * fps)))
    ft = np.arange(n) / fps
    target = np.interp(ft, t, v)

    half = crop_frac / 2
    lo, hi = half, 1 - half
    cam = np.empty(n)
    cam[0] = np.clip(target[0], lo, hi)
    dz = dead_zone * crop_frac
    step_max = max_speed / fps
    for i in range(1, n):
        c = cam[i - 1]
        err = target[i] - c
        if abs(err) > dz:
            move = (err - np.sign(err) * dz) * 0.12  # ease toward the target
            move = float(np.clip(move, -step_max, step_max))
            c += move
        cam[i] = np.clip(c, lo, hi)

    sigma = max(1.0, smooth_s * fps / 2.5)
    radius = int(sigma * 3)
    kernel = np.exp(-0.5 * (np.arange(-radius, radius + 1) / sigma) ** 2)
    kernel /= kernel.sum()
    padded = np.pad(cam, radius, mode="edge")
    out = np.convolve(padded, kernel, mode="valid")
    return np.clip(out, lo, hi)

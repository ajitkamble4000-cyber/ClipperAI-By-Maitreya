"""Two-pass EBU R128 loudness normalization to about -14 LUFS (YouTube's playback target)."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

TARGET_I, TARGET_TP, TARGET_LRA = -14.0, -1.5, 11.0


def measure(
    src: Path, *, start: float | None = None, duration: float | None = None, pre_filter: str | None = None
) -> dict[str, float] | None:
    args = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "info"]
    if start is not None:
        args += ["-ss", f"{start:.3f}"]
    args += ["-i", str(src)]
    if duration is not None:
        args += ["-t", f"{duration:.3f}"]
    af = f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=json"
    if pre_filter:
        af = f"{pre_filter},{af}"
    args += ["-vn", "-af", af, "-f", "null", "-"]
    r = subprocess.run(args, capture_output=True, text=True, timeout=1800)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    if not m:
        return None
    d = json.loads(m.group(0))
    try:
        vals = {k: float(d[k]) for k in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")}
    except (KeyError, ValueError):
        return None
    if vals["input_i"] < -70:  # silence: nothing to normalize
        return None
    return vals


def filter_for(measured: dict[str, float] | None) -> str:
    base = f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}"
    if not measured:
        return base
    return (
        f"{base}:measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
        f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:linear=true"
    )


def integrated_lufs(path: Path) -> float | None:
    m = measure(path)
    return m["input_i"] if m else None

"""Sample evenly spaced, timestamped JPEG frames (for visual analysis with image-capable AI models)."""

from __future__ import annotations

from pathlib import Path

import cv2


def sample_jpegs(
    video: Path, duration: float, *, max_frames: int = 40, min_gap: float = 4.0, width: int = 512
) -> list[tuple[float, bytes]]:
    n = int(max(1, min(max_frames, duration // min_gap)))
    step = duration / n
    cap = cv2.VideoCapture(str(video))
    out: list[tuple[float, bytes]] = []
    try:
        for i in range(n):
            t = step * (i + 0.5)
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if not ok:
                continue
            h, w = frame.shape[:2]
            small = cv2.resize(frame, (width, int(h * width / w)), interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ok:
                out.append((round(t, 1), buf.tobytes()))
    finally:
        cap.release()
    return out

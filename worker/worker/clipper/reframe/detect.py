"""Per-frame target detection for auto-reframe: faces (mediapipe, Haar fallback) and motion."""

from __future__ import annotations

import atexit
import logging
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from studio_shared.config import get_settings

log = logging.getLogger(__name__)
MP_MODEL = "blaze_face_short_range.tflite"
MP_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/"
    + MP_MODEL
)


@dataclass
class Box:
    cx: float  # normalized 0..1
    cy: float
    w: float
    h: float
    score: float


def _model_path() -> Path | None:
    p = get_settings().models_dir / MP_MODEL
    if p.exists():
        return p
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(MP_URL, p)  # noqa: S310 - fixed https URL
        return p
    except Exception:  # noqa: BLE001
        log.warning("mediapipe face model unavailable; using OpenCV Haar cascade")
        return None


class FaceDetector:
    def __init__(self) -> None:
        self._mp = None
        path = _model_path()
        if path:
            try:
                import mediapipe as mp
                from mediapipe.tasks.python import BaseOptions, vision

                opts = vision.FaceDetectorOptions(
                    base_options=BaseOptions(model_asset_path=str(path)), min_detection_confidence=0.5
                )
                self._mp = vision.FaceDetector.create_from_options(opts)
                self._mpmod = mp
                atexit.register(self.close)
            except Exception:  # noqa: BLE001
                log.exception("mediapipe init failed; falling back to Haar")
        # Haar is multi-scale and finds small faces in wide shots that the short-range model misses.
        self._haar = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

    def close(self) -> None:
        if self._mp is not None:
            try:
                self._mp.close()
            except Exception:  # noqa: BLE001
                pass
            self._mp = None

    def detect(self, bgr: np.ndarray) -> list[Box]:
        h, w = bgr.shape[:2]
        if self._mp is not None:
            img = self._mpmod.Image(
                image_format=self._mpmod.ImageFormat.SRGB, data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            )
            res = self._mp.detect(img)
            out = []
            for d in res.detections:
                b = d.bounding_box
                out.append(
                    Box(
                        (b.origin_x + b.width / 2) / w,
                        (b.origin_y + b.height / 2) / h,
                        b.width / w,
                        b.height / h,
                        float(d.categories[0].score if d.categories else 0.5),
                    )
                )
            if out:
                return out
        gray = cv2.equalizeHist(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
        faces = self._haar.detectMultiScale(
            gray, scaleFactor=1.08, minNeighbors=5, minSize=(max(24, w // 40),) * 2
        )
        return [Box((x + fw / 2) / w, (y + fh / 2) / h, fw / w, fh / h, 0.6) for x, y, fw, fh in faces]


@lru_cache(maxsize=1)
def face_detector() -> FaceDetector:
    return FaceDetector()


def sample_frames(path: Path, start: float, end: float, fps: float = 5.0, width: int = 480):
    """Yield (t_relative, small_bgr) at `fps` between start and end."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return
    try:
        step = 1.0 / fps
        t = start
        cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
        src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        next_t = start
        while t <= end:
            ok, frame = cap.read()
            if not ok:
                break
            t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0 or (t + 1 / src_fps)
            if t + 1e-6 < next_t:
                continue
            next_t += step
            h, w = frame.shape[:2]
            small = cv2.resize(frame, (width, int(h * width / w)), interpolation=cv2.INTER_AREA)
            yield t - start, small
    finally:
        cap.release()


def face_track(path: Path, start: float, end: float, fps: float = 5.0) -> list[tuple[float, float | None]]:
    """Horizontal center (0..1) of the main face per sample; None where no face is visible."""
    det = face_detector()
    out: list[tuple[float, float | None]] = []
    prev: float | None = None
    for t, frame in sample_frames(path, start, end, fps, width=960):
        boxes = [b for b in det.detect(frame) if b.score >= 0.5]
        if not boxes:
            out.append((t, None))
            continue

        # Prefer big faces, and stay with the face near the previous one (no ping-pong between speakers).
        def rank(b: Box, prev: float | None = prev) -> float:
            stick = 0.0 if prev is None else abs(b.cx - prev)
            return b.w * b.h * 10 - stick

        best = max(boxes, key=rank)
        prev = best.cx
        out.append((t, best.cx))
    return out


def motion_track(
    path: Path, start: float, end: float, crop_frac: float, fps: float = 6.0
) -> list[tuple[float, float | None]]:
    """Center (0..1) of the crop window holding the most motion per sample (for sports/action)."""
    out: list[tuple[float, float | None]] = []
    prev_gray = None
    for t, frame in sample_frames(path, start, end, fps, width=320):
        gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (9, 9), 0)
        if prev_gray is None:
            prev_gray = gray
            out.append((t, None))
            continue
        diff = cv2.absdiff(gray, prev_gray)
        prev_gray = gray
        _, mask = cv2.threshold(diff, 18, 255, cv2.THRESH_BINARY)
        col = mask.sum(axis=0).astype(np.float64)
        if col.sum() < mask.shape[0] * 2:  # almost no motion
            out.append((t, None))
            continue
        win = max(1, int(len(col) * crop_frac))
        sums = np.convolve(col, np.ones(win), mode="valid")
        i = int(np.argmax(sums))
        out.append((t, (i + win / 2) / len(col)))
    return out


@dataclass
class Speaker:
    cx: float  # normalized face center
    cy: float
    size: float  # normalized face height


def two_speakers(path: Path, start: float, end: float, fps: float = 3.0) -> tuple[Speaker, Speaker] | None:
    """Two people side by side (a podcast/interview shot): their typical positions, or None if that's not the shot.
    Needs two faces in at least 40% of sampled frames, clearly apart horizontally."""
    det = face_detector()
    pairs: list[tuple[Box, Box]] = []
    n = 0
    for _, frame in sample_frames(path, start, end, fps, width=960):
        n += 1
        boxes = sorted((b for b in det.detect(frame) if b.score >= 0.5), key=lambda b: -b.w * b.h)[:2]
        if len(boxes) == 2 and abs(boxes[0].cx - boxes[1].cx) > 0.2:
            left, right = sorted(boxes, key=lambda b: b.cx)
            pairs.append((left, right))
    if n == 0 or len(pairs) < max(2, 0.4 * n):
        return None

    def median(vals: list[float]) -> float:
        v = sorted(vals)
        return v[len(v) // 2]

    left = Speaker(
        median([p[0].cx for p in pairs]), median([p[0].cy for p in pairs]), median([p[0].h for p in pairs])
    )
    right = Speaker(
        median([p[1].cx for p in pairs]), median([p[1].cy for p in pairs]), median([p[1].h for p in pairs])
    )
    return left, right

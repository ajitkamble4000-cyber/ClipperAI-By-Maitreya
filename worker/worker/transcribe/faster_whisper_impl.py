"""Local transcription with faster-whisper (CTranslate2), word timestamps on."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from studio_shared.config import get_settings

from .base import Segment, Transcript, Word

log = logging.getLogger(__name__)
_models: dict[str, object] = {}
_lock = threading.Lock()

VALID_SIZES = ("tiny", "base", "small", "medium", "large-v3", "large-v3-turbo", "distil-large-v3")


def _model(size: str):
    from faster_whisper import WhisperModel

    with _lock:
        if size not in _models:
            s = get_settings()
            log.info("loading faster-whisper %s on %s/%s", size, s.whisper_device, s.whisper_compute_type)
            _models[size] = WhisperModel(size, device=s.whisper_device, compute_type=s.whisper_compute_type)
        return _models[size]


class FasterWhisperTranscriber:
    def __init__(self, size: str = "small") -> None:
        if size not in VALID_SIZES:
            size = "small"
        self.size = size
        self.name = f"faster-whisper-{size}"

    def transcribe(
        self,
        audio: Path,
        *,
        language: str | None = None,
        on_progress: Callable[[float], None] | None = None,
        initial_prompt: str | None = None,
    ) -> Transcript:
        model = _model(self.size)
        segments, info = model.transcribe(  # type: ignore[attr-defined]
            str(audio),
            language=language,
            word_timestamps=True,
            vad_filter=True,
            beam_size=5,
            initial_prompt=initial_prompt,
            condition_on_previous_text=False,
        )
        out: list[Segment] = []
        for seg in segments:
            words = [
                Word(
                    w.word.strip(),
                    float(round(w.start, 3)),
                    float(round(w.end, 3)),
                    float(round(w.probability, 3)),
                )
                for w in (seg.words or [])
                if w.word.strip()
            ]
            out.append(Segment(float(round(seg.start, 3)), float(round(seg.end, 3)), seg.text.strip(), words))
            if on_progress and info.duration:
                on_progress(min(1.0, seg.end / info.duration))
        return Transcript(language=info.language, duration=float(info.duration), segments=out)


def get_transcriber(size: str | None = None) -> FasterWhisperTranscriber:
    return FasterWhisperTranscriber(size or "small")

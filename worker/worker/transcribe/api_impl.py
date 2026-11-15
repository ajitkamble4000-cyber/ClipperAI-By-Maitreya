"""Cloud transcription through any OpenAI-compatible endpoint (OpenAI whisper-1, Groq whisper-large-v3, …).

Audio is compressed to small mono MP3 and split into ~10-minute chunks (upload limits are ~25 MB); word
timestamps from each chunk are shifted by the chunk offset and stitched into one Transcript."""

from __future__ import annotations

import math
import tempfile
from collections.abc import Callable
from pathlib import Path

from studio_shared import usage
from studio_shared.ai.client import adapter

from ..media import ffmpeg
from .base import Segment, Transcript, Word

CHUNK_SECONDS = 600


class APITranscriber:
    def __init__(self, provider: str, model: str) -> None:
        self.provider, self.model = provider, model
        self.name = f"{provider}-{model}".replace("/", "_")

    def transcribe(
        self,
        audio: Path,
        *,
        language: str | None = None,
        on_progress: Callable[[float], None] | None = None,
        initial_prompt: str | None = None,
    ) -> Transcript:
        a = adapter(self.provider)
        dur = ffmpeg.probe(audio).duration
        n = max(1, math.ceil(dur / CHUNK_SECONDS))
        segments: list[Segment] = []
        lang = language or ""
        with tempfile.TemporaryDirectory() as td:
            for i in range(n):
                start = i * CHUNK_SECONDS
                part = Path(td) / f"chunk{i}.mp3"
                ffmpeg.run(
                    [
                        "-ss",
                        f"{start:.3f}",
                        "-t",
                        f"{CHUNK_SECONDS}",
                        "-i",
                        str(audio),
                        "-vn",
                        "-ac",
                        "1",
                        "-ar",
                        "16000",
                        "-b:a",
                        "48k",
                        str(part),
                    ],
                    what="Audio chunk",
                )
                j = a.transcribe(self.model, part, language=language)
                lang = lang or j.get("language") or ""
                words = [
                    Word(
                        str(w.get("word", "")).strip(),
                        round(float(w["start"]) + start, 3),
                        round(float(w["end"]) + start, 3),
                    )
                    for w in j.get("words") or []
                    if str(w.get("word", "")).strip()
                ]
                segs = j.get("segments") or [
                    {"start": 0, "end": min(CHUNK_SECONDS, dur - start), "text": j.get("text", "")}
                ]
                for sg in segs:
                    s0, s1 = float(sg["start"]) + start, float(sg["end"]) + start
                    segments.append(
                        Segment(
                            round(s0, 3),
                            round(s1, 3),
                            str(sg.get("text", "")).strip(),
                            [w for w in words if s0 - 0.05 <= w.start < s1 + 0.05],
                        )
                    )
                if on_progress:
                    on_progress((i + 1) / n)
        usage.record(
            model=self.model, kind="transcribe", meta={"provider": self.provider}, audio_minutes=dur / 60
        )
        return Transcript(language=_lang_code(lang), duration=dur, segments=segments)


def _lang_code(lang: str) -> str:
    names = {
        "english": "en",
        "hindi": "hi",
        "spanish": "es",
        "french": "fr",
        "german": "de",
        "portuguese": "pt",
    }
    return names.get(lang.lower(), lang[:2].lower() if lang else "")

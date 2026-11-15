"""Transcriber interface. faster-whisper today; swap in a hosted API by adding another implementation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class Word:
    text: str
    start: float
    end: float
    prob: float = 1.0


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


@dataclass
class Transcript:
    language: str
    duration: float
    segments: list[Segment]

    @property
    def words(self) -> list[Word]:
        return [w for s in self.segments for w in s.words]

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> Transcript:
        return cls(
            language=d.get("language", ""),
            duration=float(d.get("duration", 0)),
            segments=[
                Segment(s["start"], s["end"], s["text"], [Word(**w) for w in s.get("words", [])])
                for s in d.get("segments", [])
            ],
        )

    def slice(self, start: float, end: float) -> list[Word]:
        """Words overlapping [start, end), with times relative to `start`."""
        out = []
        for w in self.words:
            if w.end > start and w.start < end:
                out.append(Word(w.text, max(0.0, w.start - start), min(end, w.end) - start, w.prob))
        return out


class Transcriber(Protocol):
    name: str

    def transcribe(self, audio: Path, *, language: str | None = None, on_progress=None) -> Transcript: ...

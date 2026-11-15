"""Whole-video mode (captions tool, or a short video in auto mode): one 'clip' covering the full video, with a
title, hook, description and hashtags written by the AI when available."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from ..transcribe.base import Transcript


class WholeMeta(BaseModel):
    title: str = Field(description="Catchy title, under 70 characters")
    hook_text: str = Field(default="", description="2-5 word on-screen hook, uppercase")
    description: str = Field(default="", description="One or two sentence description")
    hashtags: list[str] = Field(default_factory=list, description="3-6 relevant hashtags with #")


SYSTEM = "You write titles and descriptions for short vertical videos (TikTok, Reels, Shorts)."


def describe(gem, t: Transcript, *, source_title: str | None, language: str | None) -> WholeMeta:
    text = " ".join(w.text for w in t.words)[:6000]
    prompt = (
        f"Video title from the source: {source_title or 'unknown'}\n"
        f"Transcript:\n{text or '(no speech)'}\n\n"
        "Write a title, a short on-screen hook, a description and hashtags for this video"
        f"{' in ' + language if language else ' in the language of the transcript'}."
    )
    m = gem.generate_json(prompt, WholeMeta, system=SYSTEM, temperature=0.7)
    m.title = m.title.strip()[:100] or (source_title or "Captioned video")
    m.hook_text = m.hook_text.strip()[:60]
    m.hashtags = [
        h if h.startswith("#") else f"#{h}" for h in (x.strip().replace(" ", "") for x in m.hashtags) if h
    ][:8]
    return m


def basic(t: Transcript, source_title: str | None) -> WholeMeta:
    words = [w.text for w in t.words[:10]]
    first = re.sub(r"\s+", " ", " ".join(words)).strip()
    title = (source_title or first or "Captioned video")[:100]
    return WholeMeta(title=title, hook_text="", description=first[:300], hashtags=[])

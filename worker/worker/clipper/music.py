"""Background music for clips: a library track (picked by mood or chosen), ducked under the speech."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from studio_shared import db, storage

from ..media import ffmpeg

log = logging.getLogger(__name__)

MOOD_FOR_CONTENT = {
    "podcast": "calm",
    "interview": "calm",
    "education": "calm",
    "vlog": "upbeat",
    "gaming": "upbeat",
    "sports": "epic",
    "other": "upbeat",
}


def pick_track(choice: str, *, content_type: str, seed: str) -> dict[str, Any] | None:
    """`choice` is "auto", a mood, or "track:<id>". Tracks whose file is missing are skipped."""
    if choice.startswith("track:"):
        row = db.fetch_one("select * from music_tracks where id::text = %s", [choice[6:]])
        rows = [row] if row else []
    else:
        mood = MOOD_FOR_CONTENT.get(content_type, "upbeat") if choice == "auto" else choice
        rows = db.fetch_all("select * from music_tracks where mood = %s order by created_at", [mood])
        if not rows:
            rows = db.fetch_all("select * from music_tracks order by created_at")
    rows = [r for r in rows if storage.exists(r["r2_key"])]
    if not rows:
        return None
    return rows[int(hashlib.md5(seed.encode()).hexdigest(), 16) % len(rows)]


def add_music(
    base: Path, duration: float, opts: dict[str, Any], *, content_type: str, seed: str, tmp: Path, fetch
) -> Path:
    """Returns a copy of `base` with music mixed under its audio, or `base` unchanged if no track is available."""
    choice = str(opts.get("mood") or "none")
    if choice == "none":
        return base
    track = pick_track(choice, content_type=content_type, seed=seed)
    if not track:
        log.warning("no music tracks in the library; clip rendered without music")
        return base
    from ..story.sound import mix

    music = fetch(track["r2_key"], "music" + Path(track["r2_key"]).suffix)
    voice = ffmpeg.extract_audio(base, tmp / f"{base.stem}_voice.wav")
    mixed = mix(
        voice,
        duration,
        tmp / f"{base.stem}_mix.wav",
        music=music,
        music_volume=float(opts.get("volume") or 0.2),
        sfx=[],
    )
    out = tmp / f"{base.stem}_music.mp4"
    ffmpeg.run(
        [
            "-i",
            str(base),
            "-i",
            str(mixed),
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-shortest",
            "-movflags",
            "+faststart",
            str(out),
        ],
        what="Add music",
    )
    return out

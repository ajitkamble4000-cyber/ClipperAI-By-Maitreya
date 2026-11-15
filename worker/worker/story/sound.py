"""Music (auto by genre mood, or chosen), ducked under the voice, plus SFX at scene cuts."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from studio_shared import db, storage

from ..media import ffmpeg
from . import presets

log = logging.getLogger(__name__)


def _stored(row: dict[str, Any]) -> bool:
    """Library rows whose file is missing from storage are skipped (logged) instead of failing a render."""
    if storage.exists(row["r2_key"]):
        return True
    log.warning("library file missing from storage, skipping: %s", row["r2_key"])
    return False


def pick_music(st: dict[str, Any]) -> dict[str, Any] | None:
    if st["music_track_id"]:
        row = db.fetch_one("select * from music_tracks where id = %s", [st["music_track_id"]])
        return row if row and _stored(row) else None
    if not st["music_auto"]:
        return None
    mood = presets.genre(st["genre"])["music"]
    tracks = db.fetch_all("select * from music_tracks where mood = %s order by created_at", [mood])
    if not tracks:
        tracks = db.fetch_all("select * from music_tracks order by created_at")
    tracks = [t for t in tracks if _stored(t)]
    if not tracks:
        return None
    i = int(hashlib.md5(str(st["project_id"]).encode()).hexdigest(), 16) % len(tracks)  # stable per story
    return tracks[i]


SFX_WORDS = {
    "whoosh": "whoosh|swoosh|swipe|wind|fly|rush",
    "boom": "boom|explo|blast|bang|crash",
    "heartbeat": "heart|pulse|beat",
    "riser": "rise|riser|tension|build|suspense",
    "impact": "impact|hit|punch|slam|thud|drop",
    "thunder": "thunder|storm|lightning",
}


def sfx_tag_for(text: str, available: set[str]) -> str | None:
    low = text.lower()
    for tag in available:
        if tag in low:
            return tag
    for tag, rx in SFX_WORDS.items():
        if tag in available and re.search(rx, low):
            return tag
    return None


@dataclass
class SfxHit:
    path: Path
    at: float
    volume: float


def plan_sfx(scenes: list[dict[str, Any]], starts: list[float], fetch, enabled: bool) -> list[SfxHit]:
    if not enabled:
        return []
    lib = db.fetch_all("select * from sfx order by created_at")
    by_tag: dict[str, dict[str, Any]] = {}
    for r in lib:
        if r["tag"].lower() not in by_tag and _stored(r):
            by_tag[r["tag"].lower()] = r
    hits: list[SfxHit] = []
    for i, s in enumerate(scenes):
        tag = sfx_tag_for(s["sfx_suggestion"] or "", set(by_tag))
        if (
            not tag
            and i > 0
            and "whoosh" in by_tag
            and s["camera_motion"] in ("pan-left", "pan-right", "shake")
        ):
            tag = "whoosh"
        if tag:
            r = by_tag[tag]
            hits.append(
                SfxHit(
                    fetch(r["r2_key"], f"sfx_{r['id']}{Path(r['r2_key']).suffix}"),
                    max(0.0, starts[i] - 0.1),
                    0.55,
                )
            )
    return hits


def mix(
    voice: Path, total: float, out: Path, *, music: Path | None, music_volume: float, sfx: list[SfxHit]
) -> Path:
    """Voice + music ducked by the voice (sidechain compression) + SFX, exactly `total` seconds, 48 kHz stereo."""
    inputs = ["-i", str(voice)]
    parts = [f"[0:a]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=0:{total:.3f}[vo]"]
    mixins = ["[vo]"]
    idx = 1
    if music:
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        parts += [
            "[vo]asplit=2[vmix][vkey]",
            f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total:.3f},volume={music_volume:.2f},"
            f"afade=t=in:d=0.6,afade=t=out:st={max(0.0, total - 1.5):.3f}:d=1.5[mus]",
            "[mus][vkey]sidechaincompress=threshold=0.015:ratio=12:attack=20:release=450:makeup=1[duck]",
        ]
        mixins = ["[vmix]", "[duck]"]
        idx += 1
    for h in sfx:
        inputs += ["-i", str(h.path)]
        ms = int(h.at * 1000)
        parts.append(
            f"[{idx}:a]aresample=48000,aformat=channel_layouts=stereo,volume={h.volume:.2f},adelay={ms}|{ms}[s{idx}]"
        )
        mixins.append(f"[s{idx}]")
        idx += 1
    if len(mixins) == 1:
        parts.append("[vo]anull[mix]")
    else:
        parts.append(
            f"{''.join(mixins)}amix=inputs={len(mixins)}:duration=first:normalize=0,atrim=0:{total:.3f}[mix]"
        )
    ffmpeg.run(
        [
            *inputs,
            "-filter_complex",
            ";".join(parts),
            "-map",
            "[mix]",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(out),
        ],
        what="Audio mix",
    )
    return out

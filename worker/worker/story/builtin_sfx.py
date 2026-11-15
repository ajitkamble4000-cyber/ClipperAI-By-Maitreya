"""A small built-in SFX kit synthesized with ffmpeg (no licensing questions). Admins can add more."""

from __future__ import annotations

import logging
from pathlib import Path

from studio_shared import db, storage

from ..media import ffmpeg

log = logging.getLogger(__name__)

KIT = {
    "whoosh": "anoisesrc=color=pink:d=0.7:a=0.9,highpass=f=400,lowpass=f=3500,"
    "volume='0.2+0.8*sin(PI*t/0.7)':eval=frame,afade=t=out:st=0.45:d=0.25",
    "boom": "sine=f=48:d=1.6,volume=3,afade=t=out:st=0.1:d=1.5,lowpass=f=180",
    "heartbeat": "sine=f=55:d=1.2,volume='if(lt(mod(t,0.6),0.09),3,if(between(mod(t,0.6),0.18,0.25),2,0))':eval=frame,lowpass=f=150",
    "riser": "anoisesrc=color=white:d=2.2:a=0.6,bandpass=f=1800:width_type=o:w=1.5,"
    "volume='pow(t/2.2,2)':eval=frame",
    "impact": "anoisesrc=color=brown:d=0.9:a=1,lowpass=f=900,afade=t=out:st=0.05:d=0.85,volume=2.5",
    "thunder": "anoisesrc=color=brown:d=3:a=1,lowpass=f=400,volume='if(lt(t,0.15),t/0.15,exp(-(t-0.15)*1.3))':eval=frame,volume=3",
}


def ensure_builtin_sfx(tmp: Path) -> None:
    """Synthesize the built-in kit once; also re-create any built-in file that went missing from storage."""
    have = {r["tag"] for r in db.fetch_all("select distinct tag from sfx")}
    for tag, expr in KIT.items():
        key = f"library/sfx/builtin-{tag}.wav"
        row_exists = tag in have
        if row_exists and storage.exists(key):
            continue
        if row_exists and not db.fetch_one("select 1 from sfx where r2_key = %s", [key]):
            continue  # an admin-uploaded effect owns this tag
        out = tmp / f"sfx_{tag}.wav"
        try:
            ffmpeg.run(["-f", "lavfi", "-i", expr, "-ar", "48000", "-ac", "1", str(out)], what=f"SFX {tag}")
        except Exception:  # noqa: BLE001
            log.exception("could not synthesize %s", tag)
            continue
        storage.upload_file(out, key, "audio/wav")
        if row_exists:
            continue
        db.execute(
            "insert into sfx (name, tag, r2_key, duration_s) values (%s, %s, %s, %s)",
            [f"{tag.title()} (built-in)", tag, key, ffmpeg.probe(out).duration],
        )

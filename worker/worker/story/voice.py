"""Voiceover: Gemini TTS for the whole narration (consistent delivery), or the user's own recording;
then faster-whisper word timestamps aligned to the script."""

from __future__ import annotations

import json
import wave
from pathlib import Path
from typing import Any

from studio_shared import app_settings, db, storage
from studio_shared.gemini import CallContext, get_client

from ..media import ffmpeg
from ..pipeline import JobContext, Pipeline, Step, StepFailed
from ..transcribe.faster_whisper_impl import transcriber_from_settings
from . import assets, presets
from .align import align
from .render import texts_hash

TTS_RATE = 24000


def pcm_to_wav(pcm: bytes, path: Path, rate: int = TTS_RATE) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return path


def narration_text(scenes: list[dict[str, Any]]) -> str:
    # Paragraph breaks give the TTS natural pauses between scenes.
    return "\n\n".join(s["narration"].strip() for s in scenes if s["narration"].strip())


def tts_audio(ctx: JobContext, st: dict[str, Any], text: str, out: Path) -> tuple[Path, str]:
    voice = st["voice"] or presets.genre(st["genre"])["voice"]
    style = presets.speaking_style_prompt(st["speaking_style"])
    model = app_settings.model_for("tts") or ""
    h = assets.key_for(kind="tts", text=text, voice=voice, style=style, model=model)
    cached = assets.get(h)
    if cached and storage.exists(cached):
        return storage.download_file(cached, out), cached
    gem = get_client(CallContext(ctx.user_id, ctx.project_id, ctx.job_id))
    pcm = gem.tts(text, voice=voice, style=style)
    raw = pcm_to_wav(pcm, out.with_suffix(".raw.wav"))
    ffmpeg.run(
        [
            "-i",
            str(raw),
            "-af",
            "silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
            "silenceremove=start_periods=1:start_threshold=-50dB,areverse",
            "-ar",
            "48000",
            "-ac",
            "1",
            str(out),
        ],
        what="Voice cleanup",
    )
    key = f"assets/{h}.wav"
    storage.upload_file(out, key, "audio/wav")
    assets.put(h, "audio", key, {"voice": voice})
    return out, key


def make_voice(ctx: JobContext) -> dict[str, Any]:
    st = db.fetch_one("select * from stories where project_id = %s", [ctx.project_id])
    scenes = db.fetch_all("select * from scenes where project_id = %s order by idx", [ctx.project_id])
    if not scenes or not any(s["narration"].strip() for s in scenes):
        raise StepFailed("The storyboard has no narration yet.")
    wav = ctx.tmp / "narration.wav"
    if st["voiceover_key"]:
        ctx.progress(0.05, "Preparing your recording")
        src = ctx.fetch(st["voiceover_key"], "voiceover" + Path(st["voiceover_key"]).suffix)
        ffmpeg.run(["-i", str(src), "-vn", "-ar", "48000", "-ac", "1", str(wav)], what="Voiceover conversion")
        key = f"projects/{ctx.project_id}/voice/{ctx.job_id[:8]}.wav"
        storage.upload_file(wav, key, "audio/wav")
        source = "upload"
    else:
        ctx.progress(0.05, "Generating voice")
        wav, key = tts_audio(ctx, st, narration_text(scenes), wav)
        source = "tts"
    dur = ffmpeg.probe(wav).duration
    ctx.progress(0.45, "Timing every word")
    w16 = ffmpeg.extract_audio(wav, ctx.tmp / "n16.wav")
    lang = st["language"] if st["language"] in ("en", "hi") else None
    heard = (
        transcriber_from_settings()
        .transcribe(
            w16,
            language=lang,
            initial_prompt=" ".join(s["narration"] for s in scenes)[:800],
            on_progress=lambda f: ctx.progress(0.45 + 0.45 * f, "Timing every word"),
        )
        .words
    )
    al = align([s["narration"] for s in scenes], heard, dur)
    if al.matched_ratio < 0.4:
        ctx.log(
            f"Only {al.matched_ratio:.0%} of script words were recognized in the audio; timings are estimated",
            "warn",
        )
    akey = f"projects/{ctx.project_id}/voice/{ctx.job_id[:8]}-alignment.json"
    storage.put_bytes(
        akey,
        json.dumps(
            {
                "words": [w.__dict__ for w in al.words],
                "scenes": al.scenes,
                "duration": dur,
                "matched": al.matched_ratio,
                "texts_hash": texts_hash(scenes),
            }
        ).encode(),
        "application/json",
    )
    with db.transaction() as c:
        for s, (a, b) in zip(scenes, al.scenes, strict=True):
            c.execute("update scenes set audio_start_s = %s, audio_end_s = %s where id = %s", [a, b, s["id"]])
        c.execute(
            "update stories set narration_key = %s, alignment_key = %s where project_id = %s",
            [key, akey, ctx.project_id],
        )
    return {
        "narration_key": key,
        "alignment_key": akey,
        "duration": round(dur, 2),
        "source": source,
        "matched": round(al.matched_ratio, 3),
    }


def build_voice(params: dict) -> Pipeline:
    return Pipeline([Step("voice", make_voice, label="Voiceover")], finalize=lambda c: c.outputs["voice"])

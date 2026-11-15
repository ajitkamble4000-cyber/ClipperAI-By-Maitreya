"""Story Studio end to end (Phase 5): characters -> images -> TTS + alignment -> motion -> music/SFX ->
captions -> final MP4, with a fake Gemini (Pillow images, espeak TTS). Verified with ffprobe and audio checks."""

from __future__ import annotations

import json
import re
import subprocess
import uuid

import numpy as np
import pytest
from fakes_story import FakeMediaGemini
from studio_shared import db, jobs, storage
from studio_shared import gemini as gem_pkg
from worker.media import ffmpeg, loudnorm
from worker.media.audio import read_wav_mono
from worker.pipelines import get_pipeline
from worker.story import sound
from worker.transcribe.faster_whisper_impl import get_transcriber

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def run(kind, pid, params=None):
    params = params or {}
    job = jobs.mark_running(jobs.create_job(kind, project_id=pid, params=params, user_id=None)["id"])
    out = get_pipeline(kind, params).run(job)
    jobs.finish(job["id"], "succeeded", result=out)
    return out


@pytest.fixture(scope="module")
def music_track(tmp_path_factory):
    p = tmp_path_factory.mktemp("m") / "music.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=f=440:d=8,volume=0.5[a];sine=f=660:d=8,volume=0.3[b];[a][b]amix=2",
            "-ar",
            "48000",
            str(p),
        ],
        check=True,
    )
    key = f"library/music/test-{uuid.uuid4().hex[:6]}.wav"
    storage.upload_file(p, key, "audio/wav")
    row = db.fetch_one(
        "insert into music_tracks (name, mood, r2_key, duration_s) values ('Test epic', 'epic', %s, 8) "
        "returning id",
        [key],
    )
    yield row["id"]
    db.execute("delete from music_tracks where id = %s", [row["id"]])


@pytest.fixture(scope="module")
def story(music_track):
    fake = FakeMediaGemini()
    old = gem_pkg.factory
    gem_pkg.factory = lambda ctx: fake
    pid = db.fetch_one("insert into projects (type, title) values ('story', 'x') returning id")["id"]
    db.execute(
        "insert into stories (project_id, idea, genre, length_s, voice, caption_style) "
        "values (%s, 'What happens if you fall into a black hole', 'what_if', 30, 'Charon', %s)",
        [pid, json.dumps({"preset": "bold_pop"})],
    )
    run("story_script", pid)
    db.execute("update scenes set on_screen_text = 'SPAGHETTI' where project_id = %s and idx = 2", [pid])
    yield pid, fake
    gem_pkg.factory = old
    db.execute("delete from projects where id = %s", [pid])


def test_characters_then_images_use_references(story):
    pid, fake = story
    assert run("story_characters", pid) == {"generated": 1}
    ch = db.fetch_one("select * from characters where project_id = %s", [pid])
    assert ch["ref_key"] and storage.exists(ch["ref_key"])
    res = run("story_images", pid)
    assert res["generated"] == 6 and res["failed"] == 0
    # every scene names the Astronaut in its narration? only those that mention it get the reference
    with_refs = [n for _, n in fake.image_calls[1:] if n]
    assert with_refs, "character reference images should be passed to scene generation"
    rows = db.fetch_all("select image_key from scenes where project_id = %s", [pid])
    for r in rows:
        import io

        from PIL import Image

        im = Image.open(io.BytesIO(storage.get_bytes(r["image_key"])))
        assert im.size == (1080, 1920)
    # Cache: regenerate only-missing does nothing; forcing the same prompts reuses cached assets
    assert run("story_images", pid) == {"generated": 0}


def test_edit_one_scene_image(story):
    pid, _ = story
    sc = db.fetch_one("select * from scenes where project_id = %s and idx = 1", [pid])
    out = run("story_image_one", pid, {"scene_id": str(sc["id"]), "instruction": "make it night time"})
    assert out["image_key"] != sc["image_key"]


def test_voice_alignment_sets_scene_durations(story):
    pid, fake = story
    out = run("story_voice", pid)
    assert out["source"] == "tts" and out["matched"] > 0.6
    scenes = db.fetch_all("select * from scenes where project_id = %s order by idx", [pid])
    spans = [(float(s["audio_start_s"]), float(s["audio_end_s"])) for s in scenes]
    assert spans[0][0] == 0
    assert all(abs(a[1] - b[0]) < 1e-3 for a, b in zip(spans, spans[1:], strict=False)), (
        "scenes must tile the audio"
    )
    assert all(b - a >= 0.8 for a, b in spans)
    # TTS is cached: same text/voice -> no second TTS call
    calls = fake.tts_calls
    run("story_voice", pid)
    assert fake.tts_calls == calls


def test_full_render_matches_spec(story, tmp_path):
    pid, _ = story
    out = run("story_render", pid)
    assert out["music"] == "Test epic"
    local = storage.download_file(out["render_key"], tmp_path / "story.mp4")
    pr = ffmpeg.probe(local)
    al = json.loads(
        storage.get_bytes(
            db.fetch_one("select alignment_key from stories where project_id = %s", [pid])["alignment_key"]
        )
    )
    expected = al["duration"] + 0.7
    assert (pr.width, pr.height, pr.fps) == (1080, 1920, 30)
    assert pr.video_codec == "h264" and pr.audio_codec == "aac"
    assert abs(pr.duration - expected) < 0.15, (pr.duration, expected)
    lufs = loudnorm.integrated_lufs(local)
    assert lufs is not None and abs(lufs + 14) <= 1.5, lufs
    # Captions in sync with the voice: re-transcribe the final video and compare to aligned script words.
    heard = get_transcriber("small").transcribe(ffmpeg.extract_audio(local, tmp_path / "s.wav")).words
    norm = lambda w: re.sub(r"[^a-z0-9]", "", w.lower())  # noqa: E731
    exp = [(norm(w["text"]), w["start"]) for w in al["words"]]
    deltas, j = [], 0
    for w in heard:
        for k in range(j, min(j + 4, len(exp))):
            if exp[k][0] == norm(w.text):
                deltas.append(abs(w.start - exp[k][1]))
                j = k + 1
                break
    assert len(deltas) > 0.6 * len(exp)
    assert float(np.median(deltas)) < 0.15


def test_rerender_reuses_cached_segments(story):
    pid, _ = story
    before = db.fetch_one("select count(*) as n from assets where kind = 'segment'")["n"]
    db.execute(
        "update stories set caption_style = %s where project_id = %s",
        [json.dumps({"preset": "karaoke"}), pid],
    )
    run("story_render", pid)
    after = db.fetch_one("select count(*) as n from assets where kind = 'segment'")["n"]
    assert after == before, "caption-only re-render must not re-animate scenes"


def test_changed_narration_requires_new_voice(story):
    pid, _ = story
    db.execute(
        "update scenes set narration = narration || ' Extra words.' where project_id = %s and idx = 0", [pid]
    )
    with pytest.raises(Exception, match="Regenerate the voice"):
        run("story_render", pid)


def test_music_is_ducked_under_voice(tmp_path):
    voice = tmp_path / "v.wav"
    music = tmp_path / "m.wav"
    # voice: 2 s of 300 Hz "speech" (no harmonic at 1 kHz), then 2 s silence. music: steady 1 kHz tone.
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=f=300:d=2,volume=0.4",
            "-af",
            "apad=pad_dur=6",
            "-ar",
            "48000",
            str(voice),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=f=1000:d=8",
            "-ar",
            "48000",
            str(music),
        ],
        check=True,
    )
    out = sound.mix(voice, 8.0, tmp_path / "mix.wav", music=music, music_volume=0.5, sfx=[])
    data, rate = read_wav_mono(out)

    def tone_level(a, b):
        seg = data[int(a * rate) : int(b * rate)]
        spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        f = np.fft.rfftfreq(len(seg), 1 / rate)
        return 20 * np.log10(spec[(f > 950) & (f < 1050)].max() + 1e-9)

    under_voice = tone_level(0.6, 1.8)
    alone = tone_level(4.0, 5.5)  # after the release, before the end fade-out
    assert alone - under_voice > 6, f"music only {alone - under_voice:.1f} dB quieter under the voice"

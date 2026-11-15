"""End-to-end clipper on a real (generated) video. Checks outputs with ffprobe, verifies caption sync
by re-transcribing the rendered clip, and exercises re-render (nudge, restyle) and ZIP export."""

from __future__ import annotations

import json
import re
import uuid
import zipfile

import cv2
import numpy as np
import pytest
from fakes import FakeGemini
from studio_shared import db, jobs, storage
from studio_shared import gemini as gem_pkg
from worker.clipper import pipeline as clip_pipeline
from worker.media import ffmpeg, loudnorm
from worker.pipelines import get_pipeline
from worker.transcribe.base import Transcript
from worker.transcribe.faster_whisper_impl import get_transcriber

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def _member() -> str:
    uid = str(uuid.uuid4())
    db.execute(
        "insert into auth.users (id, email, aud, role) values (%s, %s, 'authenticated', 'authenticated')",
        [uid, f"clip-{uid[:8]}@example.com"],
    )
    db.execute(
        "insert into members (user_id, email, role) values (%s, %s, 'user') on conflict (user_id) do nothing",
        [uid, f"clip-{uid[:8]}@example.com"],
    )
    return uid


def _upload(path, uid) -> str:
    up = str(uuid.uuid4())
    key = f"uploads/{uid}/{up}/{path.name}"
    storage.upload_file(path, key, "video/mp4")
    db.execute(
        "insert into uploads (id, user_id, purpose, r2_key, filename, content_type, size_bytes, part_size, status) "
        "values (%s,%s,'source',%s,%s,'video/mp4',%s,%s,'complete')",
        [up, uid, key, path.name, path.stat().st_size, path.stat().st_size],
    )
    return up


def _run(kind, params, uid, project_id):
    job = jobs.create_job(kind, project_id=project_id, params=params, user_id=uid)
    job = jobs.mark_running(job["id"])
    result = get_pipeline(kind, params).run(job)
    jobs.finish(job["id"], "succeeded", result=result)
    return result


def _norm(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", w.lower())


@pytest.fixture(scope="module")
def clip_project(podcast):
    fake = FakeGemini()
    old_factory, old_avail = gem_pkg.factory, clip_pipeline.available
    gem_pkg.factory = lambda ctx: fake
    clip_pipeline.available = lambda: True
    uid = _member()
    pid = db.fetch_one(
        "insert into projects (type, title, created_by) values ('clip','Untitled',%s) returning id", [uid]
    )["id"]
    params = {
        "upload_id": _upload(podcast, uid),
        "num_clips": 3,
        "min_len": 15,
        "max_len": 30,
        "content_type": "podcast",
        "reframe": "face",
        "caption_style": {"preset": "bold_pop"},
        "hook_overlay": True,
    }
    try:
        result = _run("clip", params, uid, pid)
        yield {"pid": pid, "uid": uid, "result": result, "fake": fake}
    finally:
        gem_pkg.factory, clip_pipeline.available = old_factory, old_avail
        db.execute("delete from projects where id = %s", [pid])
        db.execute("delete from members where user_id = %s", [uid])
        db.execute("delete from auth.users where id = %s", [uid])


def test_ai_mode_clips_match_spec(clip_project, tmp_path):
    assert clip_project["result"]["mode"] == "ai"
    prompt = clip_project["fake"].calls[0][-1]
    assert "Find exactly" in prompt and "Timestamped transcript" in prompt
    clips = db.fetch_all("select * from clips where project_id = %s order by idx", [clip_project["pid"]])
    assert len(clips) == 3
    assert [c["virality_score"] for c in clips] == sorted([c["virality_score"] for c in clips], reverse=True)
    for c in clips:
        assert c["status"] == "ready"
        assert re.fullmatch(r"\d\d_[a-z0-9-]+\.mp4", c["filename"])
        local = storage.download_file(c["video_key"], tmp_path / c["filename"])
        pr = ffmpeg.probe(local)
        expected = float(c["end_s"] - c["start_s"])
        assert (pr.width, pr.height) == (1080, 1920)
        assert pr.fps == 30
        assert pr.video_codec == "h264" and pr.audio_codec == "aac"
        assert abs(pr.duration - expected) < 0.12, (pr.duration, expected)
        assert 15 <= expected <= 30.5
        lufs = loudnorm.integrated_lufs(local)
        assert lufs is not None and abs(lufs + 14) <= 1.5, lufs
        assert storage.exists(c["thumb_key"])
    # Overlaps removed: clip windows don't overlap.
    spans = sorted((float(c["start_s"]), float(c["end_s"])) for c in clips)
    assert all(a[1] <= b[0] + 0.5 for a, b in zip(spans, spans[1:], strict=False))


def test_captions_are_in_sync_with_audio(clip_project, tmp_path):
    clip = db.fetch_one(
        "select * from clips where project_id = %s order by idx limit 1", [clip_project["pid"]]
    )
    meta = db.fetch_one("select meta from projects where id = %s", [clip_project["pid"]])["meta"]
    t = Transcript.from_json(json.loads(storage.get_bytes(meta["transcript_key"])))
    expected = t.slice(float(clip["start_s"]), float(clip["end_s"]))
    local = storage.download_file(clip["video_key"], tmp_path / "c.mp4")
    heard = get_transcriber("small").transcribe(ffmpeg.extract_audio(local, tmp_path / "c.wav")).words
    exp = [(_norm(w.text), w.start) for w in expected if _norm(w.text)]
    deltas, j = [], 0
    for w in heard:
        n = _norm(w.text)
        for k in range(j, min(j + 4, len(exp))):
            if exp[k][0] == n:
                deltas.append(abs(w.start - exp[k][1]))
                j = k + 1
                break
    assert len(deltas) >= 0.6 * len(exp), f"only matched {len(deltas)}/{len(exp)} words"
    assert float(np.median(deltas)) < 0.15, f"median caption/audio offset {np.median(deltas):.3f}s"
    assert max(deltas) < 0.6


def test_captions_are_burned_in(clip_project, tmp_path):
    clip = db.fetch_one(
        "select * from clips where project_id = %s order by idx limit 1", [clip_project["pid"]]
    )
    base = storage.download_file(clip["base_key"], tmp_path / "b.mp4")
    final = storage.download_file(clip["video_key"], tmp_path / "f.mp4")
    meta = db.fetch_one("select meta from projects where id = %s", [clip_project["pid"]])["meta"]
    t = Transcript.from_json(json.loads(storage.get_bytes(meta["transcript_key"])))
    w = t.slice(float(clip["start_s"]), float(clip["end_s"]))[8]
    at = (w.start + w.end) / 2

    def frame(p):
        cap = cv2.VideoCapture(str(p))
        cap.set(cv2.CAP_PROP_POS_MSEC, at * 1000)
        ok, f = cap.read()
        cap.release()
        assert ok
        return f.astype(np.int16)

    band = slice(int(1920 * 0.6), int(1920 * 0.76))
    diff = np.abs(frame(base)[band] - frame(final)[band]).mean()
    assert diff > 4, "no caption pixels found in the lower-third band"


def test_restyle_reuses_base_and_nudge_recuts(clip_project):
    clip = db.fetch_one(
        "select * from clips where project_id = %s order by idx limit 1", [clip_project["pid"]]
    )
    uid, pid = clip_project["uid"], clip_project["pid"]
    _run("clip_rerender", {"clip_id": str(clip["id"]), "caption_style": {"preset": "karaoke"}}, uid, pid)
    after = db.fetch_one("select * from clips where id = %s", [clip["id"]])
    assert after["caption_style"]["preset"] == "karaoke" and after["status"] == "ready"
    assert after["start_s"] == clip["start_s"]

    _run(
        "clip_rerender",
        {"clip_id": str(clip["id"]), "start": float(clip["start_s"]) + 2, "end": float(clip["end_s"]) + 2},
        uid,
        pid,
    )
    nudged = db.fetch_one("select * from clips where id = %s", [clip["id"]])
    assert float(nudged["start_s"]) == pytest.approx(float(clip["start_s"]) + 2, abs=0.01)
    pr = ffmpeg.probe(storage.download_file(nudged["video_key"], "/tmp/claude-nudged.mp4"))
    assert abs(pr.duration - float(nudged["end_s"] - nudged["start_s"])) < 0.12


def test_zip_export(clip_project, tmp_path):
    res = _run("clip_zip", {}, clip_project["uid"], clip_project["pid"])
    z = zipfile.ZipFile(storage.download_file(res["key"], tmp_path / "all.zip"))
    names = z.namelist()
    assert "metadata.txt" in names and sum(n.endswith(".mp4") for n in names) == 3


def test_basic_mode_without_key(sports, tmp_path):
    uid = _member()
    pid = db.fetch_one(
        "insert into projects (type, title, created_by) values ('clip','Untitled',%s) returning id", [uid]
    )["id"]
    try:
        res = _run(
            "clip",
            {
                "upload_id": _upload(sports, uid),
                "num_clips": 2,
                "min_len": 15,
                "max_len": 25,
                "content_type": "sports",
                "reframe": "action",
                "force_basic": True,
            },
            uid,
            pid,
        )
        assert res["mode"] == "basic"
        clips = db.fetch_all("select * from clips where project_id = %s order by idx", [pid])
        assert {c["mode"] for c in clips} == {"basic"}
        assert float(clips[0]["start_s"]) <= 38 <= float(clips[0]["end_s"]), (
            "crowd roar at 38s should rank first"
        )
        pr = ffmpeg.probe(storage.download_file(clips[0]["video_key"], tmp_path / "s.mp4"))
        assert (pr.width, pr.height, pr.fps) == (1080, 1920, 30)
    finally:
        db.execute("delete from projects where id = %s", [pid])
        db.execute("delete from members where user_id = %s", [uid])
        db.execute("delete from auth.users where id = %s", [uid])

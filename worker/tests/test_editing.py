"""Editing: MP3/GIF exports, compilations (cut and fade), caption text edits and background music on clips."""

from __future__ import annotations

import json
import re
import subprocess
import uuid
from pathlib import Path

import pytest
from studio_shared import db, jobs, storage
from tests_helpers import make_member
from worker.media import ffmpeg
from worker.pipelines import get_pipeline
from worker.transcribe.base import Segment, Transcript, Word

pytestmark = pytest.mark.integration


def _video(
    path: Path, seconds: float, *, size: str = "1080x1920", silent: bool = False, color: str = "blue"
) -> Path:
    audio = (
        ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        if silent
        else ["-f", "lavfi", "-i", f"sine=f=440:r=48000:d={seconds}"]
    )
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s={size}:r=30:d={seconds}",
            *audio,
            "-t",
            str(seconds),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
    )
    return path


def _mean_volume(path: Path) -> float:
    out = subprocess.run(
        ["ffmpeg", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True
    ).stderr
    m = re.search(r"mean_volume: (-?[\d.]+) dB", out)
    return float(m.group(1)) if m else -99.0


def _run(kind: str, params: dict, uid: str, pid: str) -> dict:
    job = jobs.create_job(kind, project_id=pid, params=params, user_id=uid)
    job = jobs.mark_running(job["id"])
    out = get_pipeline(kind, params).run(job)
    jobs.finish(job["id"], "succeeded", result=out)
    return out


@pytest.fixture
def project(tmp_path):
    uid = make_member(plan="pro")
    t = Transcript(
        language="en",
        duration=6.0,
        segments=[
            Segment(
                0.0,
                6.0,
                "Hello there friend",
                [Word("Hello", 0.2, 0.8), Word("there", 1.0, 1.6), Word("friend", 2.0, 2.8)],
            )
        ],
    )
    tkey = f"cache/test-transcripts/{uuid.uuid4().hex}.json"
    storage.put_bytes(tkey, json.dumps(t.to_json()).encode(), "application/json")
    pid = str(
        db.fetch_one(
            "insert into projects (type, title, created_by, meta) values ('clip','Edit me',%s,%s) returning id",
            [uid, {"transcript_key": tkey, "options": {"content_type": "podcast"}}],
        )["id"]
    )

    def clip(idx: int, seconds: float = 6.0, **kw) -> str:
        v = _video(tmp_path / f"c{idx}.mp4", seconds, **kw)
        base_key = f"projects/{pid}/clips/c{idx}/base.mp4"
        video_key = f"projects/{pid}/clips/c{idx}/final.mp4"
        storage.upload_file(v, base_key, "video/mp4")
        storage.upload_file(v, video_key, "video/mp4")
        words_key = f"projects/{pid}/clips/c{idx}/words.json"
        storage.put_bytes(
            words_key,
            json.dumps(
                [{"text": "Hello", "start": 0.2, "end": 0.8}, {"text": "there", "start": 1.0, "end": 1.6}]
            ).encode(),
        )
        return str(
            db.fetch_one(
                """insert into clips (project_id, idx, start_s, end_s, title, status, base_key, video_key, words_key,
                                  filename, duration_s, caption_style, reframe)
               values (%s,%s,0,%s,'Clip',%s,%s,%s,%s,%s,%s,'{"preset":"minimal"}','center') returning id""",
                [pid, idx, seconds, "ready", base_key, video_key, words_key, f"0{idx}-clip.mp4", seconds],
            )["id"]
        )

    return uid, pid, clip


def test_exports(project, tmp_path):
    uid, pid, clip = project
    cid = clip(1, 4.0)
    mp3 = _run("clip_export", {"clip_id": cid, "format": "mp3"}, uid, pid)
    local = tmp_path / "out.mp3"
    storage.download_file(mp3["key"], local)
    pr = ffmpeg.probe(local)
    assert (
        pr.has_audio
        and not pr.has_video
        and abs(pr.duration - 4.0) < 0.3
        and mp3["filename"].endswith(".mp3")
    )
    gif = _run("clip_export", {"clip_id": cid, "format": "gif"}, uid, pid)
    g = tmp_path / "out.gif"
    storage.download_file(gif["key"], g)
    assert g.read_bytes()[:6] in (b"GIF89a", b"GIF87a")


def test_compilations(project, tmp_path):
    uid, pid, clip = project
    a, b = clip(1, 3.0, color="red"), clip(2, 4.0, color="green")
    cut = _run("clip_compile", {"clip_ids": [a, b], "transition": "cut", "title": "Best of"}, uid, pid)
    f = tmp_path / "cut.mp4"
    storage.download_file(cut["key"], f)
    pr = ffmpeg.probe(f)
    assert (
        abs(pr.duration - 7.0) < 0.3 and pr.display_size == (1080, 1920) and cut["filename"] == "best-of.mp4"
    )
    fade = _run("clip_compile", {"clip_ids": [a, b], "transition": "fade"}, uid, pid)
    g = tmp_path / "fade.mp4"
    storage.download_file(fade["key"], g)
    assert abs(ffmpeg.probe(g).duration - 6.6) < 0.3  # 0.4 s overlap


def test_compilation_needs_same_format(project):
    uid, pid, clip = project
    a, b = clip(1, 2.0), clip(2, 2.0, size="1080x1080")
    db.execute("update clips set aspect = '1:1' where id = %s", [b])
    with pytest.raises(Exception, match="same format"):
        _run("clip_compile", {"clip_ids": [a, b]}, uid, pid)


def test_edited_captions_are_burned(project):
    uid, pid, clip = project
    cid = clip(1, 4.0)
    key = f"projects/{pid}/clips/{cid}/edited.json"
    storage.put_bytes(
        key,
        json.dumps(
            [{"text": "Fixed", "start": 0.2, "end": 0.8}, {"text": "words", "start": 1.0, "end": 1.6}]
        ).encode(),
    )
    db.execute("update clips set words_key = %s where id = %s", [key, cid])
    _run("clip_rerender", {"clip_id": cid, "keep_words": True}, uid, pid)
    c = db.fetch_one("select * from clips where id = %s", [cid])
    assert c["status"] == "ready" and c["words_key"] != key
    assert [w["text"] for w in json.loads(storage.get_bytes(c["words_key"]))] == ["Fixed", "words"]


def test_music_is_mixed_in(project, tmp_path):
    uid, pid, clip = project
    cid = clip(1, 5.0, silent=True)
    track = _video(tmp_path / "track.mp4", 8.0)  # a sine tone stands in for a song
    tkey = f"library/music/test-{uuid.uuid4().hex[:6]}.m4a"
    a = tmp_path / "track.m4a"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(track), "-vn", "-c:a", "aac", str(a)], check=True
    )
    storage.upload_file(a, tkey, "audio/mp4")
    tid = db.fetch_one(
        "insert into music_tracks (name, mood, r2_key) values ('Test tone','calm',%s) returning id", [tkey]
    )["id"]
    try:
        _run("clip_rerender", {"clip_id": cid, "music": {"mood": "calm", "volume": 0.4}}, uid, pid)
        c = db.fetch_one("select * from clips where id = %s", [cid])
        out = tmp_path / "with_music.mp4"
        storage.download_file(c["video_key"], out)
        assert _mean_volume(out) > -45  # the silent clip now has music
        assert c["render_opts"]["music"]["mood"] == "calm"
    finally:
        db.execute("delete from music_tracks where id = %s", [tid])

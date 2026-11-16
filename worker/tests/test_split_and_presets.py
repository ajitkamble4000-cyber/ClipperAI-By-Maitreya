"""Split-screen reframe for two-person shots, and the Neon / Typewriter / Bounce caption presets."""

from __future__ import annotations

import subprocess
from pathlib import Path

import cv2
import pytest
from worker.captions.ass import AssBuilder
from worker.captions.style import CaptionStyle
from worker.transcribe.base import Word

WORDS = [Word("Never", 0.0, 0.4), Word("give", 0.45, 0.8), Word("up", 0.85, 1.2), Word("today", 1.3, 1.8)]


def _ass(preset: str) -> str:
    b = AssBuilder(CaptionStyle.from_dict({"preset": preset}))
    b.add_words(WORDS)
    return b.render()


def test_neon_has_glow_layer():
    a = _ass("neon")
    assert r"\blur9" in a and r"\1a&HFF&" in a  # transparent-fill glow layer under the crisp text
    assert a.count("Dialogue: 0,") == a.count("Dialogue: 1,")


def test_typewriter_hides_future_words():
    a = _ass("typewriter")
    first = next(line for line in a.splitlines() if line.startswith("Dialogue"))
    assert first.count(r"{\alpha&HFF&}") >= 1  # later words invisible but laid out


def test_bounce_pops_in_once_per_phrase():
    a = _ass("bounce")
    lines = [line for line in a.splitlines() if line.startswith("Dialogue")]
    assert r"\t(0,110,\fscx116\fscy116)" in lines[0] and r"\t(0,110" not in lines[1]


@pytest.fixture(scope="module")
def two_people(podcast, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("split") / "two.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-t",
            "6",
            "-i",
            str(podcast),
            "-filter_complex",
            "[0:v]scale=960:540,split[a][b];[a][b]hstack=inputs=2[v]",
            "-map",
            "[v]",
            "-map",
            "0:a",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(out),
        ],
        check=True,
    )
    return out


@pytest.mark.slow
def test_two_speakers_detected(two_people, podcast):
    from worker.clipper.reframe.detect import two_speakers

    sp = two_speakers(two_people, 0, 6)
    assert sp is not None
    left, right = sp
    assert left.cx < 0.5 < right.cx
    assert two_speakers(podcast, 0, 6) is None  # one person: not a split shot


@pytest.mark.slow
def test_split_render_stacks_both_faces(two_people, tmp_path):
    from worker.clipper.reframe.detect import face_detector
    from worker.clipper.render import render_base
    from worker.media import ffmpeg

    out = tmp_path / "split.mp4"
    render_base(two_people, ffmpeg.probe(two_people), 0.5, 4.5, "split", out, tmp_path)
    pr = ffmpeg.probe(out)
    assert pr.display_size == (1080, 1920) and abs(pr.duration - 4.0) < 0.2
    cap = cv2.VideoCapture(str(out))
    cap.set(cv2.CAP_PROP_POS_MSEC, 2000)
    ok, frame = cap.read()
    cap.release()
    assert ok
    det = face_detector()
    top, bottom = frame[:960], frame[960:]
    assert det.detect(top) and det.detect(bottom)  # one person in each half

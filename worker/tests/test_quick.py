"""Any-link quick mode & captions tool: platform detection, caption files, jump cuts, keyword emphasis,
output formats, overlays, translation, and an end-to-end auto-mode run on a real video."""

from __future__ import annotations

import json
import uuid

import pytest
from studio_shared import captions_files, platforms
from worker.captions.ass import AssBuilder, Canvas, canvas_for
from worker.captions.emphasis import keyword_flags
from worker.captions.style import CaptionStyle
from worker.captions.translate import translate_words
from worker.media import jumpcut
from worker.media.overlays import OverlayOptions, chain
from worker.transcribe.base import Word


def W(text, a, b):
    return Word(text, a, b, 1.0)


# ---------------------------------------------------------------- platforms
@pytest.mark.parametrize(
    ("url", "pid", "short"),
    [
        ("https://www.youtube.com/watch?v=abc", "youtube", False),
        ("https://youtube.com/shorts/abc", "youtube", True),
        ("https://youtu.be/abc", "youtube", False),
        ("https://www.instagram.com/reel/xyz/", "instagram", True),
        ("https://vm.tiktok.com/ZM123/", "tiktok", True),
        ("https://x.com/someone/status/1", "x", False),
        ("https://fb.watch/abc/", "facebook", False),
        ("https://vimeo.com/123", "vimeo", False),
        ("https://www.twitch.tv/videos/1", "twitch", False),
        ("https://example.org/video.mp4", "web", False),
        ("https://notyoutube.com.evil.io/x", "web", False),
    ],
)
def test_platform_detection(url, pid, short):
    p = platforms.detect(url)
    assert p.id == pid and p.short_form == short


def test_login_help_only_for_login_platforms():
    assert "cookies.txt" in platforms.login_help(platforms.detect("https://instagram.com/reel/x"))
    assert platforms.login_help(platforms.detect("https://vimeo.com/1")) == ""


# ---------------------------------------------------------------- caption files
WORDS = [
    W("Hello", 0.0, 0.4),
    W("there.", 0.45, 0.9),
    W("This", 1.5, 1.7),
    W("is", 1.75, 1.85),
    W("great!", 1.9, 2.4),
]


def test_srt_vtt_txt():
    srt = captions_files.render_file(WORDS, "srt")
    assert srt.startswith("1\n00:00:00,000 --> 00:00:00,900\nHello there.\n")
    assert "2\n00:00:01,500 --> 00:00:02,400\nThis is great!" in srt
    vtt = captions_files.render_file([{"text": w.text, "start": w.start, "end": w.end} for w in WORDS], "vtt")
    assert vtt.startswith("WEBVTT\n\n00:00:00.000 --> 00:00:00.900\nHello there.")
    assert captions_files.render_file(WORDS, "txt") == "Hello there.\nThis is great!\n"


# ---------------------------------------------------------------- jump cuts
def test_silence_and_filler_removal():
    words = [W("So", 0.5, 0.7), W("um", 0.8, 1.1), W("this", 1.2, 1.4), W("works", 3.5, 3.9)]
    segs = jumpcut.keep_segments(words, 5.0, remove_silence=True, remove_fillers=True)
    assert segs[0][0] == 0.0 and len(segs) == 3  # the "um" and the 2 s pause are cut out
    assert all(not (a < 0.95 < b) for a, b in segs)  # middle of "um" is not kept
    out = jumpcut.remap(words, segs)
    assert [w.text for w in out] == ["So", "this", "works"]
    assert out[-1].end <= sum(b - a for a, b in segs) + 1e-6


def test_filler_only_keeps_pauses():
    words = [W("So", 0.5, 0.7), W("uh", 0.8, 1.1), W("this", 1.2, 1.4), W("works", 3.5, 3.9)]
    segs = jumpcut.keep_segments(words, 5.0, remove_silence=False, remove_fillers=True)
    assert segs == [(0.0, 0.77), (1.13, 5.0)]  # only the filler is removed; the long pause stays
    assert jumpcut.keep_segments(words, 5.0, remove_silence=False, remove_fillers=False) == [(0.0, 5.0)]


# ---------------------------------------------------------------- keyword emphasis
def test_keyword_flags():
    words = [
        W(t, i, i + 0.5)
        for i, t in enumerate(
            ["I", "made", "5000", "dollars", "with", "this", "incredible", "secret", "trick"]
        )
    ]
    flags = keyword_flags(words, ["trick"])
    picked = {w.text for w, f in zip(words, flags, strict=True) if f}
    assert "5000" in picked and "I" not in picked and "with" not in picked
    assert not any(flags[i] and flags[i + 1] for i in range(len(flags) - 1))  # never two in a row
    assert sum(flags) <= max(1, int(len(words) * 0.25))


def test_emphasis_in_ass():
    words = [W("This", 0, 0.3), W("changes", 0.3, 0.8), W("everything", 0.8, 1.4), W("forever", 1.4, 2.0)]
    b = AssBuilder(CaptionStyle.from_dict({"preset": "minimal"}), emphasis=True)
    b.add_words(words)
    text = b.render()
    assert r"\fscx108" in text  # at least one keyword is highlighted


# ---------------------------------------------------------------- formats
@pytest.mark.parametrize(
    ("aspect", "size"),
    [("9:16", (1080, 1920)), ("1:1", (1080, 1080)), ("4:5", (1080, 1350)), ("16:9", (1920, 1080))],
)
def test_canvas_and_playres(aspect, size):
    c = canvas_for(aspect)
    assert (c.w, c.h) == size
    assert c.safe_left < c.center_x < c.safe_right and c.safe_top < c.safe_bottom <= c.h
    b = AssBuilder(CaptionStyle.from_dict({"preset": "bold_pop"}), canvas=c)
    b.add_words(WORDS)
    b.add_hook("Big hook text here", 3.0)
    ass = b.render()
    assert f"PlayResX: {size[0]}" in ass and f"PlayResY: {size[1]}" in ass
    assert c.vertical == (aspect == "9:16")


def test_landscape_text_is_scaled():
    assert Canvas(1920, 1080).scale < 1.0 and Canvas().scale == 1.0


# ---------------------------------------------------------------- overlays
def test_overlay_chain(tmp_path):
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"x")
    opts = OverlayOptions(
        watermark_text="Made with Shorts Studio", logo=logo, handle="@me", progress_bar=True
    )
    parts, out = chain(opts, "v0", width=1080, height=1920, duration=10.0, logo_input=2)
    g = ";".join(parts)
    assert (
        g.startswith("[v0]drawbox") and "[2:v]scale=" in g and "@me" in g and "Made with Shorts Studio" in g
    )
    assert out == "ov4"
    assert OverlayOptions.from_params({"watermark": False}, lambda k: logo) is None
    o = OverlayOptions.from_params({"brand": {"logo_key": "x.png", "handle": "@a"}}, lambda k: logo)
    assert o and o.logo == logo and o.handle == "@a"
    broken = OverlayOptions.from_params({"brand": {"logo_key": "x.png"}, "watermark": True}, lambda k: 1 / 0)
    assert broken and broken.logo is None and broken.watermark_text  # a missing logo never fails the render


# ---------------------------------------------------------------- translation
def test_translate_keeps_timing():
    from fakes_story import FakeStoryGemini

    out = translate_words(WORDS, "es", FakeStoryGemini())
    assert out[0].text == "[es]" and out[0].start == 0.0
    assert abs(out[-1].end - 2.4) < 1e-3
    assert all(a.end <= b.start + 1e-6 for a, b in zip(out, out[1:], strict=False))


# ---------------------------------------------------------------- end to end (auto mode -> whole video)
@pytest.mark.integration
@pytest.mark.slow
def test_auto_mode_short_video_is_captioned_whole(podcast, tmp_path):
    from fakes_story import FakeStoryGemini
    from PIL import Image
    from studio_shared import db, jobs, storage, tokens
    from studio_shared import gemini as gem_pkg
    from tests_helpers import make_member, upload_source
    from worker.clipper import pipeline as clip_pipeline
    from worker.media import ffmpeg
    from worker.pipelines import get_pipeline

    fake = FakeStoryGemini()
    old_factory, old_avail = gem_pkg.factory, clip_pipeline.available
    gem_pkg.factory = lambda ctx: fake
    clip_pipeline.available = lambda: True
    try:
        uid = make_member(plan="pro")
        logo = tmp_path / "logo.png"
        Image.new("RGBA", (200, 200), (255, 0, 0, 200)).save(logo)
        logo_key = f"assets/test-logo-{uuid.uuid4().hex[:6]}.png"
        storage.upload_file(logo, logo_key, "image/png")
        pid = db.fetch_one(
            "insert into projects (type, title, created_by) values ('clip','Quick video',%s) returning id",
            [uid],
        )["id"]
        params = {
            "upload_id": upload_source(podcast, uid),
            "mode": "auto",
            "num_clips": 3,
            "aspect": "1:1",
            "reframe": "face",
            "caption_style": {"preset": "boxed"},
            "hook_overlay": True,
            "remove_silence": True,
            "remove_fillers": True,
            "keyword_emphasis": True,
            "translate_to": "es",
            "progress_bar": True,
            "watermark": True,
            "brand": {"logo_key": logo_key, "logo_position": "top-right", "handle": "@studio"},
        }
        cost, items = tokens.quote("clip", params)
        params["_tokens"] = {"kind": "clip", "params": dict(params), "cost": cost, "items": items}
        job = jobs.create_job("clip", project_id=str(pid), params=params, user_id=uid)
        before = tokens.get_wallet(uid).total
        tokens.charge(uid, cost, "clip", job_id=str(job["id"]))
        job = jobs.mark_running(job["id"])
        result = get_pipeline("clip", params).run(job)
        jobs.finish(job["id"], "succeeded", result=result)

        assert result["mode"] == "whole" and len(result["clips"]) == 1
        clip = db.fetch_one("select * from clips where id = %s", [result["clips"][0]])
        assert clip["mode"] == "whole" and clip["aspect"] == "1:1" and clip["status"] == "ready"
        assert clip["title"] == "A quick captioned video" and clip["language"] == "es"
        local = tmp_path / "out.mp4"
        storage.download_file(clip["video_key"], local)
        pr = ffmpeg.probe(local)
        assert pr.display_size == (1080, 1080) and pr.has_audio
        assert pr.duration < 81.2  # jump cuts removed the pauses
        assert abs(pr.duration - float(clip["duration_s"])) < 0.5
        words = json.loads(storage.get_bytes(clip["words_key"]))
        assert words and words[0]["text"] == "[es]" and words[-1]["end"] <= float(clip["duration_s"]) + 0.5
        assert "[es]" in captions_files.render_file(words, "srt")
        # auto mode turned out to be one captioned video: charged as clips, refunded down to the captions price
        whole_cost, _ = tokens.quote("clip", {**params, "mode": "captions"})
        assert before - tokens.get_wallet(uid).total == whole_cost
        title = db.fetch_one("select title from projects where id = %s", [pid])["title"]
        assert title == "A quick captioned video"
    finally:
        gem_pkg.factory, clip_pipeline.available = old_factory, old_avail

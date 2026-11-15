"""Creator extras: designed thumbnails (frame and AI background) and title/hashtag ideas."""

from __future__ import annotations

import io

import pytest
from PIL import Image
from worker.extras import compose


def _accent_pixels(img: Image.Image) -> int:
    small = img.convert("RGB").resize((img.width // 4, img.height // 4))
    return sum(1 for r, g, b in small.getdata() if r > 220 and g > 200 and b < 80)


@pytest.mark.parametrize("size", [(1280, 720), (1080, 1920)])
def test_compose_sizes_and_highlight(size):
    bg = Image.new("RGB", (640, 360), (40, 90, 160))
    img = compose(bg, "I made 5000 dollars with this one secret", size)
    assert img.size == size
    assert _accent_pixels(img) > 20  # one keyword drawn in the accent colour
    white = sum(1 for p in img.convert("L").resize((size[0] // 4, size[1] // 4)).getdata() if p > 240)
    assert white > 50  # the rest of the title in white


def test_compose_long_title_fits_and_logo():
    bg = Image.new("RGB", (300, 300), (200, 30, 30))
    logo = Image.new("RGBA", (100, 100), (0, 255, 0, 255))
    img = compose(bg, "word " * 30, (1280, 720), logo=logo)
    px = img.getpixel((1280 - 60, 60))
    assert px[1] > 200 and px[0] < 80  # the logo sits in the top-right corner


@pytest.mark.integration
def test_thumbnail_and_ideas_jobs(tmp_path):
    from fakes_story import FakeVeoGemini
    from studio_shared import db, jobs, storage
    from studio_shared import gemini as gem_pkg
    from tests_helpers import make_member
    from worker.pipelines import get_pipeline

    from worker import extras

    fake = FakeVeoGemini()
    old_factory, old_avail = gem_pkg.factory, extras.available
    gem_pkg.factory = lambda ctx: fake
    extras.available = lambda: True
    try:
        uid = make_member(plan="pro")
        pid = str(
            db.fetch_one(
                "insert into projects (type, title, created_by) values ('clip','T',%s) returning id", [uid]
            )["id"]
        )
        buf = io.BytesIO()
        Image.new("RGB", (1080, 1920), (20, 120, 60)).save(buf, "JPEG")
        thumb = f"projects/{pid}/clips/x/thumb.jpg"
        storage.put_bytes(thumb, buf.getvalue(), "image/jpeg")
        cid = str(
            db.fetch_one(
                "insert into clips (project_id, idx, start_s, end_s, title, hook_text, status, thumb_key) "
                "values (%s,1,0,10,'My clip title','THIS IS WILD','ready',%s) returning id",
                [pid, thumb],
            )["id"]
        )

        def run(kind, params):
            job = jobs.create_job(kind, project_id=pid, params=params, user_id=uid)
            job = jobs.mark_running(job["id"])
            out = get_pipeline(kind, params).run(job)
            jobs.finish(job["id"], "succeeded", result=out)
            return out

        out = run("thumbnail", {"clip_id": cid, "style": "frame"})
        assert out["style"] == "frame"
        yt = Image.open(io.BytesIO(storage.get_bytes(out["youtube"])))
        vert = Image.open(io.BytesIO(storage.get_bytes(out["vertical"])))
        assert yt.size == (1280, 720) and vert.size == (1080, 1920)
        out2 = run("thumbnail", {"clip_id": cid, "style": "ai", "text": "Custom words here"})
        assert out2["style"] == "ai" and fake.image_calls  # AI background was generated
        covers = db.fetch_one("select covers from clips where id = %s", [cid])["covers"]
        assert covers["youtube"] == out2["youtube"] and not storage.exists(
            out["youtube"]
        )  # old one cleaned up

        ideas = run("title_variants", {"clip_id": cid})
        assert len(ideas["titles"]) == 5 and all(h.startswith("#") for h in ideas["hashtags"])
        assert (
            db.fetch_one("select ideas from clips where id = %s", [cid])["ideas"]["titles"] == ideas["titles"]
        )
    finally:
        gem_pkg.factory, extras.available = old_factory, old_avail

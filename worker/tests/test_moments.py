import json

import pytest
from worker.clipper.ingest import friendly_ytdlp_error
from worker.clipper.moments import basic, validate
from worker.clipper.moments.schema import Candidate, ClipIdeas
from worker.transcribe.base import Segment, Transcript, Word


def transcript() -> Transcript:
    segs, t = [], 0.0
    for i in range(30):  # 30 sentences of 6 words, 0.4 s per word, 0.8 s pause
        ws = []
        for j in range(6):
            txt = f"w{i}_{j}" + ("." if j == 5 else "")
            ws.append(Word(txt, round(t, 2), round(t + 0.35, 2)))
            t += 0.4
        t += 0.8
        segs.append(Segment(ws[0].start, ws[-1].end, " ".join(w.text for w in ws), ws))
    return Transcript("en", t, segs)


def test_snap_to_sentence_boundaries_and_length():
    t = transcript()
    sentence_starts = {s.start for s in t.segments}
    c = validate.snap(Candidate(start=7.1, end=21.0), t, min_len=10, max_len=20, duration=t.duration)
    assert c is not None
    assert round(c.start + 0.12, 2) in sentence_starts
    assert any(abs((c.end - 0.25) - s.end) < 1e-6 for s in t.segments)
    assert 10 <= c.end - c.start <= 20.5


def test_too_short_is_extended_too_long_is_trimmed():
    t = transcript()
    short = validate.snap(Candidate(start=3.2, end=5.0), t, min_len=15, max_len=30, duration=t.duration)
    long = validate.snap(Candidate(start=3.2, end=80.0), t, min_len=15, max_len=30, duration=t.duration)
    assert 15 <= short.end - short.start <= 30.5
    assert 15 <= long.end - long.start <= 30.5


def test_finalize_removes_overlaps_sorts_and_tops_up():
    t = transcript()
    cands = [
        Candidate(start=10, end=25, virality_score=60),
        Candidate(start=12, end=27, virality_score=90),
        Candidate(start=40, end=55, virality_score=70),
        Candidate(start=500, end=510, virality_score=99),
    ]
    fb = basic.find(t, n=5, min_len=12, max_len=20, duration=t.duration, loudness=None)
    out = validate.finalize(cands, t, n=4, min_len=12, max_len=20, duration=t.duration, fallback=fb)
    assert len(out) == 4
    assert [c.virality_score for c in out] == sorted([c.virality_score for c in out], reverse=True)
    for a in out:
        for b in out:
            if a is not b:
                assert a.end <= b.start + 0.5 or a.start >= b.end - 0.5
    assert out[0].virality_score == 90  # the overlapping 60 was dropped in favour of 90


def test_hashtags_normalized():
    t = transcript()
    c = validate.finalize(
        [Candidate(start=10, end=25, hashtags=["shorts", "#Fun Facts", "#"])],
        t,
        n=1,
        min_len=12,
        max_len=20,
        duration=t.duration,
    )[0]
    assert c.hashtags == ["#shorts", "#FunFacts"]


def test_basic_mode_prefers_loud_moments_for_sports():
    import numpy as np

    t = Transcript("en", 120.0, [])
    loud = np.full(240, -40.0, dtype=np.float32)
    loud[150:158] = -8.0  # 75-79 s
    out = basic.find(t, n=2, min_len=15, max_len=20, duration=120.0, loudness=loud, content_type="sports")
    best = validate.finalize(out, t, n=1, min_len=15, max_len=20, duration=120.0)[0]
    assert best.start <= 75 <= best.end


def test_bot_error_message_is_actionable():
    msg = friendly_ytdlp_error(
        "ERROR: [youtube] abc: Sign in to confirm you're not a bot. Use --cookies-from-browser"
    )
    assert "Upload the video file instead" in msg and "cookies.txt" in msg


def test_gemini_json_retry_then_repair(monkeypatch):
    """Invalid JSON is retried once, then repaired."""
    from studio_shared.gemini import client as gc

    class Resp:
        def __init__(self, text):
            self.text = text
            self.usage_metadata = None

    replies = iter(
        [
            "not json",
            '{"clips": [{"start": 1, "end": 20, "title": "t", "hook_text": "h", '
            '"description": "d", "hashtags": ["#a"], "virality_score": 50, "reason": "r"},]',
        ]
    )

    class Models:
        def generate_content(self, **kw):
            return Resp(next(replies))

    g = gc.Gemini.__new__(gc.Gemini)
    g.ctx = gc.CallContext()
    g._client = type("C", (), {"models": Models()})()
    monkeypatch.setattr(gc.app_settings, "model_for", lambda role: "gemini-test")
    monkeypatch.setattr(gc.usage, "record", lambda **kw: 0.0)
    res = g.generate_json("prompt", ClipIdeas)
    assert res.clips[0].end == 20


def test_gemini_retries_429(monkeypatch):
    from google.genai import errors as gerrors
    from studio_shared.gemini import client as gc

    monkeypatch.setattr(gc.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise gerrors.APIError(
                429, {"error": {"message": "rate limited", "status": "RESOURCE_EXHAUSTED"}}
            )
        return "ok"

    g = gc.Gemini.__new__(gc.Gemini)
    assert g._retry(flaky) == "ok" and calls["n"] == 3
    with pytest.raises(gc.GeminiError, match="rejected"):
        g._retry(
            lambda: (_ for _ in ()).throw(
                gerrors.APIError(
                    400, {"error": {"message": "API key not valid", "status": "INVALID_ARGUMENT"}}
                )
            )
        )
    assert json.dumps({"ok": 1})

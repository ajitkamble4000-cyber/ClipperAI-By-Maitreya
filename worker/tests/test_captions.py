import re

from worker.captions.ass import SAFE_BOTTOM, AssBuilder, H, ass_color, build_ass, chunk_words, ts
from worker.captions.style import CaptionStyle
from worker.transcribe.base import Word


def words(text: str, t0: float = 0.5, step: float = 0.35):
    out, t = [], t0
    for w in text.split():
        out.append(Word(w, round(t, 2), round(t + 0.3, 2)))
        t += step
    return out


def events(ass: str):
    rows = []
    for line in ass.splitlines():
        if line.startswith("Dialogue:"):
            parts = line.split(",", 9)
            rows.append((parts[1], parts[2], parts[9]))
    return rows


def secs(s: str) -> float:
    h, m, rest = s.split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def test_color_and_time_format():
    assert ass_color("#FFE500") == "&H0000E5FF"
    assert ts(3725.37) == "1:02:05.37"


def test_chunking_respects_sentences_and_size():
    ws = words("Hello there. This is a much longer sentence with words")
    chunks = chunk_words(ws, 3)
    assert [len(c.words) for c in chunks][0] == 2  # breaks after "there."
    assert all(len(c.words) <= 3 for c in chunks)
    for a, b in zip(chunks, chunks[1:], strict=False):
        assert a.end <= b.start + 1e-6  # never two chunks on screen at once


def test_every_word_is_on_screen_while_spoken_all_presets(tmp_path):
    ws = words("Honey never spoils and archaeologists found it in Egyptian tombs")
    for preset in ["bold_pop", "karaoke", "minimal", "boxed", "horror"]:
        ass = build_ass(
            ws, CaptionStyle.from_dict({"preset": preset}), tmp_path / f"{preset}.ass"
        ).read_text()
        evs = events(ass)
        assert evs, preset
        for w in ws:
            mid = (w.start + w.end) / 2
            visible = [e for e in evs if secs(e[0]) <= mid <= secs(e[1]) and "\\p1" not in e[2]]
            token = w.text.upper() if CaptionStyle.from_dict({"preset": preset}).uppercase else w.text
            assert any(token in re.sub(r"\{[^}]*\}", "", e[2]) for e in visible), (preset, w.text)


def test_text_stays_inside_safe_zone(tmp_path):
    for pos in ["top", "middle", "lower"]:
        b = AssBuilder(CaptionStyle.from_dict({"preset": "bold_pop", "position": pos}))
        assert 230 < b.y < SAFE_BOTTOM < H * 0.8


def test_long_words_get_two_lines_or_smaller_font():
    b = AssBuilder(CaptionStyle.from_dict({"preset": "bold_pop", "words_per_line": 4}))
    b.add_words(words("INTERNATIONALIZATION CONTRADICTORILY EXTRAORDINARILY UNBELIEVABLE"))
    assert any("\\N" in e or "\\fs" in e for e in b.events)


def test_devanagari_switches_font(tmp_path):
    ass = build_ass(
        words("नमस्ते दोस्तों आज हम"), CaptionStyle.from_dict({"preset": "bold_pop"}), tmp_path / "hi.ass"
    )
    assert "Noto Sans Devanagari Bold" in ass.read_text()


def test_karaoke_uses_fill_tags(tmp_path):
    ass = build_ass(
        words("one two three four"), CaptionStyle.from_dict({"preset": "karaoke"}), tmp_path / "k.ass"
    )
    assert ass.read_text().count("\\kf") == 4


def test_hook_overlay_first_three_seconds(tmp_path):
    ass = build_ass(
        words("hi"), CaptionStyle.from_dict({}), tmp_path / "h.ass", hook="You won't believe this"
    )
    hook = [e for e in events(ass.read_text()) if "BELIEVE" in e[2]]
    assert hook and secs(hook[0][0]) == 0 and secs(hook[0][1]) == 3.0


def test_none_preset_writes_no_caption_events(tmp_path):
    ass = build_ass(words("a b c"), CaptionStyle.from_dict({"preset": "none"}), tmp_path / "n.ass")
    assert events(ass.read_text()) == []

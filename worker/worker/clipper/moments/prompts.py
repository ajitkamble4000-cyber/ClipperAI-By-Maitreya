"""Prompts for finding clip-worthy moments. The content type changes what "a great moment" means."""

from __future__ import annotations

CONTENT_TYPES: dict[str, str] = {
    "podcast": (
        "This is a podcast. Look for: surprising claims, strong opinions, funny exchanges, emotional stories, "
        "counter-intuitive advice, and quotable one-liners. A clip should feel like a complete mini-story."
    ),
    "sports": (
        "This is sports footage. Look for: big plays, goals, saves, dunks, knockouts, near misses, controversial "
        "calls, celebrations, crowd eruptions and commentator peaks (excited, louder, faster speech). The big moment "
        "is often NOT described in words; use the audio excitement peaks and any visual cues. Include a few seconds "
        "of build-up before the play and the reaction after it."
    ),
    "gaming": (
        "This is a gaming stream. Look for: clutch plays, fails, rage moments, funny reactions, big wins, surprising "
        "events and chat-worthy moments. Streamer reactions (laughing, shouting) are strong hooks."
    ),
    "interview": (
        "This is an interview. Look for: revealing answers, confessions, tense or emotional moments, strong "
        "statements, and great question-answer pairs. Start on the question when it makes the clip clearer."
    ),
    "other": (
        "Look for the most engaging, self-contained moments: surprising information, emotion, humor, tension, "
        "or a satisfying explanation."
    ),
}

SYSTEM = """You are an expert YouTube Shorts editor who finds the most viral moments in long videos.
Rules for every clip:
- It must make sense on its own to someone who has not seen the rest of the video.
- The first 3 seconds must hook the viewer (a bold claim, question, conflict or action).
- It must end with a complete payoff (punchline, answer, result) - never mid-sentence or mid-play.
- Start and end on sentence boundaries using the timestamps given.
- Clips must not overlap.
- Write titles and hook text in the same language as the video (unless told otherwise).
Return exactly the number of clips asked for, best first."""


def build_prompt(
    *,
    transcript_text: str,
    n: int,
    min_len: int,
    max_len: int,
    content_type: str,
    language: str | None,
    peaks: list[tuple[float, float]],
    window: tuple[float, float] | None = None,
    visual: bool = False,
) -> str:
    guide = CONTENT_TYPES.get(content_type, CONTENT_TYPES["other"])
    parts = [
        guide,
        f"Find exactly {n} clips, each between {min_len} and {max_len} seconds long.",
    ]
    if window:
        parts.append(
            f"Only choose clips inside {window[0]:.0f}s - {window[1]:.0f}s of the video (this is one part of a longer video)."
        )
    if language and language not in ("auto", ""):
        parts.append(f"Write titles, hook text, descriptions and hashtags in this language: {language}.")
    if peaks:
        top = ", ".join(f"{t:.0f}s" for t, _ in sorted(peaks, key=lambda p: -p[1])[:15])
        parts.append(f"Audio excitement peaks (crowd/commentator/laughter, loudest first): {top}.")
    if visual:
        parts.append("You can also watch the video: use on-screen action, not just speech.")
    parts.append("Timestamped transcript (seconds):\n" + (transcript_text or "(no speech detected)"))
    return "\n\n".join(parts)

"""Recognise where a video link comes from, so the UI can show it and errors can give platform-specific help."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class Platform:
    id: str
    label: str
    short_form: bool = False  # usually under ~90 s (TikTok, Reels, Shorts): caption it whole
    login_often_needed: bool = False


PLATFORMS: list[tuple[re.Pattern[str], Platform]] = [
    (
        re.compile(r"(^|\.)youtube\.com$|(^|\.)youtu\.be$|(^|\.)youtube-nocookie\.com$"),
        Platform("youtube", "YouTube"),
    ),
    (re.compile(r"(^|\.)instagram\.com$|(^|\.)instagr\.am$"), Platform("instagram", "Instagram", True, True)),
    (re.compile(r"(^|\.)tiktok\.com$|(^|\.)vm\.tiktok\.com$"), Platform("tiktok", "TikTok", True)),
    (re.compile(r"(^|\.)(twitter|x)\.com$|(^|\.)t\.co$"), Platform("x", "X / Twitter")),
    (
        re.compile(r"(^|\.)facebook\.com$|(^|\.)fb\.watch$|(^|\.)fb\.com$"),
        Platform("facebook", "Facebook", False, True),
    ),
    (re.compile(r"(^|\.)vimeo\.com$"), Platform("vimeo", "Vimeo")),
    (re.compile(r"(^|\.)twitch\.tv$"), Platform("twitch", "Twitch")),
    (re.compile(r"(^|\.)kick\.com$"), Platform("kick", "Kick")),
    (re.compile(r"(^|\.)reddit\.com$|(^|\.)redd\.it$"), Platform("reddit", "Reddit")),
    (re.compile(r"(^|\.)dailymotion\.com$|(^|\.)dai\.ly$"), Platform("dailymotion", "Dailymotion")),
    (re.compile(r"(^|\.)rumble\.com$"), Platform("rumble", "Rumble")),
    (re.compile(r"(^|\.)linkedin\.com$"), Platform("linkedin", "LinkedIn", False, True)),
    (re.compile(r"(^|\.)snapchat\.com$"), Platform("snapchat", "Snapchat", True)),
    (re.compile(r"(^|\.)bilibili\.com$|(^|\.)b23\.tv$"), Platform("bilibili", "Bilibili")),
    (re.compile(r"(^|\.)streamable\.com$"), Platform("streamable", "Streamable")),
    (re.compile(r"(^|\.)loom\.com$"), Platform("loom", "Loom")),
    (re.compile(r"(^|\.)soundcloud\.com$"), Platform("soundcloud", "SoundCloud")),
    (re.compile(r"(^|\.)threads\.net$"), Platform("threads", "Threads", True, True)),
    (re.compile(r"(^|\.)pinterest\.[a-z.]+$|(^|\.)pin\.it$"), Platform("pinterest", "Pinterest", True)),
]
GENERIC = Platform("web", "Web link")


def detect(url: str) -> Platform:
    host = (urlparse(url).hostname or "").lower()
    for rx, p in PLATFORMS:
        if rx.search(host):
            if p.id == "youtube" and "/shorts/" in url:
                return Platform("youtube", "YouTube Shorts", True)
            return p
    return GENERIC


def login_help(p: Platform) -> str:
    if not p.login_often_needed:
        return ""
    return (
        f" {p.label} often only serves videos to logged-in browsers: the owner can upload a cookies.txt that "
        f"includes {p.label} cookies in Admin → Downloads."
    )

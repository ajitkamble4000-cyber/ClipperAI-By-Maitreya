"""Upload and URL validation."""

from __future__ import annotations

import ipaddress
import re
from pathlib import PurePosixPath
from urllib.parse import urlparse

from fastapi import HTTPException, status

GB = 1024**3
MB = 1024**2

# purpose -> (allowed extensions, allowed content-type prefixes, max bytes)
UPLOAD_RULES: dict[str, tuple[set[str], tuple[str, ...], int]] = {
    "source": ({".mp4", ".mov", ".mkv", ".webm"}, ("video/", "application/octet-stream"), 4 * GB),
    "voiceover": (
        {".mp3", ".wav", ".m4a", ".aac", ".ogg"},
        ("audio/", "video/mp4", "application/octet-stream"),
        200 * MB,
    ),
    "music": ({".mp3", ".wav", ".m4a", ".ogg"}, ("audio/", "application/octet-stream"), 100 * MB),
    "sfx": ({".mp3", ".wav", ".m4a", ".ogg"}, ("audio/", "application/octet-stream"), 20 * MB),
    "image": ({".png", ".jpg", ".jpeg", ".webp"}, ("image/",), 25 * MB),
}


def bad(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, msg)


def safe_filename(name: str) -> str:
    base = PurePosixPath(name.replace("\\", "/")).name
    base = re.sub(r"[^A-Za-z0-9._ -]+", "_", base).strip(" .") or "file"
    return base[:120]


def validate_upload(purpose: str, filename: str, content_type: str, size: int, max_source: int) -> None:
    rule = UPLOAD_RULES.get(purpose)
    if not rule:
        raise bad("Unknown upload type")
    exts, types, max_bytes = rule
    if purpose == "source":
        max_bytes = min(max_bytes, max_source)
    ext = PurePosixPath(filename.lower()).suffix
    if ext not in exts:
        raise bad(f"File type {ext or '(none)'} is not allowed. Allowed: {', '.join(sorted(exts))}")
    if not any(content_type.lower().startswith(t) for t in types):
        raise bad(f"Content type {content_type} is not allowed for {purpose}")
    if size <= 0:
        raise bad("Empty file")
    if size > max_bytes:
        raise bad(f"File is too large (max {max_bytes // MB} MB)")


def sanitize_url(raw: str) -> str:
    url = raw.strip()
    if len(url) > 2048 or any(c in url for c in "\r\n\t "):
        raise bad("Invalid URL")
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise bad("Only http(s) links are supported")
    host = p.hostname.lower()
    if host in ("localhost",) or host.endswith((".local", ".internal", ".localhost")):
        raise bad("That address is not allowed")
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise bad("That address is not allowed")
    except ValueError:
        pass
    if p.username or p.password:
        raise bad("Links with credentials are not allowed")
    return url

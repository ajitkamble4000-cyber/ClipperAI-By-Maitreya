"""Get the source video into R2 and the job's temp dir: from a browser upload or a URL (yt-dlp)."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from studio_shared import app_settings, db, storage

from ..media import ffmpeg
from ..pipeline import JobContext, StepFailed

log = logging.getLogger(__name__)

BOT_PATTERNS = re.compile(
    r"sign in to confirm|not a bot|confirm you.re not a bot|HTTP Error 429|too many requests|"
    r"use --cookies|cookies for the authentication",
    re.I,
)


def content_hash(path: Path) -> str:
    h = hashlib.sha256()
    size = path.stat().st_size
    h.update(str(size).encode())
    with path.open("rb") as f:
        h.update(f.read(4 * 1024 * 1024))
        if size > 8 * 1024 * 1024:
            f.seek(-4 * 1024 * 1024, 2)
            h.update(f.read())
    return h.hexdigest()[:32]


def friendly_ytdlp_error(msg: str) -> str:
    if BOT_PATTERNS.search(msg):
        return (
            'YouTube blocked the download from our server ("Sign in to confirm you\'re not a bot"). '
            "Upload the video file instead, or ask an admin to add a cookies.txt file and/or a proxy in "
            "Settings → Downloads."
        )
    if re.search(r"private video|members-only|join this channel", msg, re.I):
        return "This video is private or members-only, so it can't be downloaded. Upload the file instead."
    if re.search(r"video unavailable|has been removed|not available in your country|geo", msg, re.I):
        return "This video is unavailable (removed or region-locked). Upload the file instead."
    if re.search(r"unsupported url", msg, re.I):
        return "This link isn't supported. Use a YouTube (or other video site) link, or upload the file."
    if re.search(r"live event|is live|premieres in", msg, re.I):
        return "Live streams and premieres can't be clipped until they finish. Try again later or upload the file."
    return f"Could not download the video: {msg.strip().splitlines()[-1][:300] if msg.strip() else 'unknown error'}"


def download_url(url: str, dest_dir: Path, on_progress=None) -> tuple[Path, dict[str, Any]]:
    import yt_dlp

    cookies = app_settings.write_cookies_file(dest_dir)
    proxy = app_settings.proxy()

    def hook(d: dict[str, Any]) -> None:
        if on_progress and d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                on_progress(min(0.99, d.get("downloaded_bytes", 0) / total))

    opts: dict[str, Any] = {
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(dest_dir / "source.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "progress_hooks": [hook],
        "retries": 3,
        "fragment_retries": 5,
        "max_filesize": 4 * 1024**3,
        "socket_timeout": 30,
    }
    if cookies:
        opts["cookiefile"] = str(cookies)
    if proxy:
        opts["proxy"] = proxy
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:  # noqa: BLE001 - yt-dlp raises many types
        raise StepFailed(friendly_ytdlp_error(str(e))) from e
    finally:
        if cookies:
            cookies.unlink(missing_ok=True)
    files = sorted(dest_dir.glob("source.*"), key=lambda p: p.stat().st_size, reverse=True)
    files = [f for f in files if f.suffix not in (".part", ".ytdl", ".txt")]
    if not files:
        raise StepFailed("The download finished but no video file was produced.")
    meta = {k: info.get(k) for k in ("title", "uploader", "duration", "webpage_url", "id", "extractor")}
    return files[0], meta


def run(ctx: JobContext) -> dict[str, Any]:
    p = ctx.params
    src_dir = ctx.tmp / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    meta: dict[str, Any] = {}
    if p.get("upload_id"):
        up = db.fetch_one("select * from uploads where id = %s and status = 'complete'", [p["upload_id"]])
        if not up:
            raise StepFailed("The uploaded file was not found (it may have expired). Upload it again.")
        key = up["r2_key"]
        ctx.progress(0.1, "Fetching upload")
        local = ctx.fetch(key, "source" + Path(up["filename"]).suffix.lower())
        meta = {"title": Path(up["filename"]).stem, "filename": up["filename"]}
        kind = "upload"
    elif p.get("url"):
        ctx.progress(0.02, "Downloading video")
        local, meta = download_url(p["url"], src_dir, lambda f: ctx.progress(f * 0.8, "Downloading video"))
        key = f"sources/{ctx.project_id}/source{local.suffix}"
        ctx.progress(0.85, "Saving source")
        storage.upload_file(local, key, "video/mp4")
        kind = "url"
    else:
        raise StepFailed("No video given (upload a file or paste a link).")

    pr = ffmpeg.probe(local)
    if not pr.has_video:
        raise StepFailed("This file has no video track.")
    if pr.duration < 5:
        raise StepFailed("The video is too short to clip (under 5 seconds).")
    days = app_settings.get_row()["source_retention_days"]
    row = db.fetch_one(
        """insert into sources (project_id, kind, url, r2_key, filename, size_bytes, duration_s, width, height, fps,
                                content_hash, meta, expires_at)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
        [
            ctx.project_id,
            kind,
            p.get("url"),
            key,
            meta.get("filename") or local.name,
            local.stat().st_size,
            pr.duration,
            pr.display_size[0],
            pr.display_size[1],
            pr.fps,
            content_hash(local),
            meta,
            datetime.now(UTC) + timedelta(days=days),
        ],
    )
    if meta.get("title"):
        db.execute(
            "update projects set title = %s where id = %s and title in ('Untitled', '')",
            [str(meta["title"])[:120], ctx.project_id],
        )
    return {
        "source_id": str(row["id"]),
        "key": key,
        "duration": pr.duration,
        "width": pr.display_size[0],
        "height": pr.display_size[1],
        "fps": pr.fps,
        "has_audio": pr.has_audio,
        "hash": content_hash(local),
        "suffix": local.suffix,
    }


def local_source(ctx: JobContext) -> Path:
    """The source file in this run's temp dir (re-downloaded from R2 after a crash/resume)."""
    out = ctx.outputs["ingest"]
    return ctx.fetch(out["key"], "source" + out.get("suffix", ".mp4"))

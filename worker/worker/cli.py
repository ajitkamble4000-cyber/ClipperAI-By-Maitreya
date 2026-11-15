"""Command-line runner for the clipper (Phase 2 testing without the web UI).

  uv run python -m worker.cli clip --file tests/fixtures/media/podcast.mp4 --n 3 --min 20 --max 40 --out out/
  uv run python -m worker.cli clip --url https://youtu.be/... --type sports --reframe action

It creates a project + job in the database (like the API does), uploads the file to storage,
runs the same pipeline in-process (no queue), downloads the finished clips to --out and prints
an ffprobe summary of each.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from studio_shared import db, jobs, storage
from studio_shared.logging_setup import setup

from .media import ffmpeg, loudnorm
from .pipelines import get_pipeline


def _cli_user() -> str | None:
    row = db.fetch_one("select user_id from members order by created_at limit 1")
    return str(row["user_id"]) if row else None


def _upload(path: Path, user: str | None) -> str:
    uid = user or "00000000-0000-0000-0000-000000000000"
    up_id = str(uuid.uuid4())
    key = f"uploads/{uid}/{up_id}/{path.name}"
    storage.upload_file(path, key, "video/mp4")
    db.execute(
        """insert into uploads (id, user_id, purpose, r2_key, filename, content_type, size_bytes, part_size, status)
           values (%s,%s,'source',%s,%s,'video/mp4',%s,%s,'complete')""",
        [up_id, user, key, path.name, path.stat().st_size, path.stat().st_size],
    )
    return up_id


def cmd_clip(a: argparse.Namespace) -> int:
    user = _cli_user()
    if a.file and not user:
        print(
            "No workspace member exists yet; create the first admin (/setup) before using --file.",
            file=sys.stderr,
        )
        return 2
    params = {
        "num_clips": a.n,
        "min_len": a.min,
        "max_len": a.max,
        "content_type": a.type,
        "reframe": a.reframe,
        "caption_style": {"preset": a.captions, "emoji": a.emoji},
        "language": a.language,
        "visual_analysis": a.visual,
        "force_basic": a.basic,
        "hook_overlay": not a.no_hook,
    }
    if a.file:
        params["upload_id"] = _upload(Path(a.file), user)
    else:
        params["url"] = a.url
    proj = db.fetch_one(
        "insert into projects (type, title, created_by, status) values ('clip','Untitled',%s,'processing') "
        "returning id",
        [user],
    )
    job = jobs.create_job("clip", project_id=proj["id"], params=params, user_id=user)
    job = jobs.mark_running(job["id"])
    print(f"project {proj['id']}  job {job['id']}")
    try:
        result = get_pipeline("clip", params).run(job)
    except Exception as e:  # noqa: BLE001
        jobs.finish(job["id"], "failed", error=str(e))
        print(f"FAILED: {e}", file=sys.stderr)
        return 1
    jobs.finish(job["id"], "succeeded", result=result)
    db.execute("update projects set status = 'ready' where id = %s", [proj["id"]])
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    print(f"mode: {result['mode']}" + (f" ({result['basic_reason']})" if result.get("basic_reason") else ""))
    for c in db.fetch_all("select * from clips where project_id = %s order by idx", [proj["id"]]):
        dest = out / c["filename"]
        storage.download_file(c["video_key"], dest)
        pr = ffmpeg.probe(dest)
        lufs = loudnorm.integrated_lufs(dest)
        print(
            json.dumps(
                {
                    "file": dest.name,
                    "score": c["virality_score"],
                    "start": float(c["start_s"]),
                    "end": float(c["end_s"]),
                    "title": c["title"],
                    "size": f"{pr.width}x{pr.height}",
                    "fps": pr.fps,
                    "duration": round(pr.duration, 2),
                    "lufs": round(lufs, 1) if lufs else None,
                    "audio": pr.audio_codec,
                    "video": pr.video_codec,
                }
            )
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    setup("WARNING")
    ap = argparse.ArgumentParser(prog="worker.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("clip", help="Turn a long video into Shorts")
    src = c.add_mutually_exclusive_group(required=True)
    src.add_argument("--file")
    src.add_argument("--url")
    c.add_argument("--n", type=int, default=3)
    c.add_argument("--min", type=int, default=20)
    c.add_argument("--max", type=int, default=60)
    c.add_argument("--type", default="podcast", choices=["podcast", "sports", "gaming", "interview", "other"])
    c.add_argument("--reframe", default="face", choices=["face", "action", "center", "blur"])
    c.add_argument(
        "--captions",
        default="bold_pop",
        choices=["bold_pop", "karaoke", "minimal", "boxed", "horror", "none"],
    )
    c.add_argument("--emoji", action="store_true")
    c.add_argument("--language", default=None)
    c.add_argument("--visual", action="store_true", help="also send the video to Gemini")
    c.add_argument("--basic", action="store_true", help="skip Gemini (basic heuristics)")
    c.add_argument("--no-hook", action="store_true")
    c.add_argument("--out", default="out")
    a = ap.parse_args(argv)
    return cmd_clip(a)


if __name__ == "__main__":
    raise SystemExit(main())

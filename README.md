# Shorts Studio

A hosted web app for a small team (2–10 people) to make YouTube Shorts:

- **Clipper**: long video (YouTube or other link, or a 4 GB upload) → several vertical 9:16 Shorts with animated captions, picked by Gemini (or a free "basic mode").
- **Story Studio**: idea → AI script → storyboard → consistent characters → scene images → AI voiceover → motion (Ken Burns or Veo video) → music, SFX, captions → finished Short.

Invite-only workspace, shared library, live job progress, usage/cost dashboard with a monthly budget.

## Architecture

```
Browser (Next.js on Vercel)
  ├─ Supabase Auth (login, invites)            ├─ Supabase Postgres reads (RLS)
  ├─ Realtime: live job / clip / scene updates  └─ PUT upload parts straight to R2 (presigned, resumable)
  └─ HTTPS + JWT ─► FastAPI (VPS, Docker, behind Caddy)
                      │  verifies JWT, roles, rate limits; presigns R2; decrypts secrets
                      └─► Redis ─► Celery workers (VPS, Docker)
                                    media queue: ffmpeg, faster-whisper, reframe, render
                                    ai/poll queues: Gemini text, image, TTS, Veo operations
                                    beat: stuck-job recovery, source cleanup
```

- Every job is a chain of **resumable steps** recorded in `job_steps`; a crashed worker's job is re-queued and skips finished steps. Story assets (images, voice, animated scenes, Veo clips) are **content-addressed** so re-renders never pay twice.
- The Gemini key is stored **encrypted** (Fernet) in Postgres or set as an env var; it never reaches a browser. Model names come from the Gemini models list. Prices for estimates come from an editable table.
- Video processing never runs on Vercel.

## Repository

```
web/      Next.js App Router + TypeScript + Tailwind (+ shadcn-style components), Playwright e2e
api/      FastAPI: auth, setup, members/invites, uploads, jobs, clipper, story, library, settings, usage
worker/   Celery workers: pipeline runner, clipper/, story/, captions/, media/, transcribe/, publish/ (interface only)
shared/   py/studio_shared (config, db, R2, crypto, Gemini client, usage/budget), presets/*.json, fonts/
infra/    supabase/ (config + SQL migrations with RLS), docker/, compose.yml (dev), compose.prod.yml, caddy/, scripts/
tests/    fixtures (generated test media)
```

## Local development

Requirements: Docker, Node 20+, Python 3.11 with [uv](https://docs.astral.sh/uv/), ffmpeg.

```bash
cp .env.example .env            # then fill APP_ENCRYPTION_KEY and SETUP_TOKEN (see comments)
cp web/.env.example web/.env.local
uv sync                         # Python deps for api + worker + shared
(cd web && npm install)
make supabase-start             # local Postgres, Auth, Realtime, Mailpit (prints keys for .env)
make supabase-reset             # apply migrations
docker compose -f infra/compose.yml up -d redis s3   # Redis + an S3 emulator standing in for R2
```

Then, in three terminals: `make api`, `make worker`, `make web`. Open http://localhost:3000/setup, enter your `SETUP_TOKEN` and create the first admin. Invite emails land in Mailpit at http://127.0.0.1:54324.

Or run API + workers in Docker: `make dev-up` (uses `infra/compose.yml`).

For the local stack the values in `.env.example` comments apply: `SUPABASE_URL=http://127.0.0.1:54321`, the service-role key and JWT secret printed by `supabase start`, `S3_ENDPOINT=http://127.0.0.1:9090`.

### Clipper from the command line

```bash
PYTHONPATH=worker uv run python -m worker.cli clip --file path/to/video.mp4 --n 5 --min 20 --max 45 \
    --type podcast --reframe face --captions bold_pop --out out/
PYTHONPATH=worker uv run python -m worker.cli clip --url "https://www.youtube.com/watch?v=..." --type sports --reframe action
```

It prints an ffprobe summary (size, fps, duration, loudness) for each clip.

## Tests

```bash
uv run python tests/fixtures/make_fixtures.py   # once: generates test videos (needs espeak-ng)
uv run pytest -m "not slow"                       # fast suite (needs local Supabase, Redis, S3)
uv run pytest                                     # + end-to-end media tests (renders real video)
cd web && npx next build && STUDIO_FAKE_GEMINI=1 npx playwright test
```

What the media tests verify (not just "it ran"): 1080x1920 at 30 fps, H.264/AAC, durations match cuts and narration within 0.12–0.15 s, integrated loudness −14 ±1.5 LUFS, **caption timing checked by re-transcribing the rendered video** (median offset < 0.15 s), captions actually burned in (pixel diff), music ducking measured (> 6 dB under the voice), resume skips finished steps, cached assets are reused.

`STUDIO_FAKE_GEMINI=1` swaps Gemini for an offline fake (Pillow images, espeak voice, fake Veo) **for tests only**; never set it in production.

## Features at a glance

| Area | What you get |
|---|---|
| Team | Invite-only, admin/member roles, shared library with search and filters, presence on stories |
| Uploads | Browser → R2 multipart, up to 4 GB, resumable after refresh, pause/resume |
| Clipper | Link or upload; 1–20 clips, 15–180 s; content types (podcast, sports, gaming, interview); Gemini moments with structured JSON + validation (sentence snapping, length, overlaps); visual analysis; loudness peaks; basic mode; face/action/center/blur reframe; clip cards with edit, nudge, restyle, ZIP |
| Captions | ASS presets Bold Pop, Karaoke, Minimal, Boxed, Horror; fonts incl. Noto Sans Devanagari; size/colors/outline/caps/words-per-line/position (safe zone)/auto-emoji; hook text; live preview |
| Story Studio | 6 genres, 5+ visual styles (admins add more), 30/45/60/90 s, English/Hindi/Hinglish, 30 voices + preview, speaking styles, upload your own voiceover; storyboard editor with autosave and AI rewrites; characters with reference images; per-scene image redo/edit/upload; Ken Burns motion with transitions; Veo premium per scene with cost confirmation; music library with auto-ducking; SFX |
| Export | H.264/AAC MP4 1080x1920 30 fps, −14 LUFS, `01_<slug>.mp4`, thumbnail; sources auto-deleted after N days |
| Cost control | Every Gemini call logged with estimated cost; dashboard per user/day/month/model; monthly budget with 80% warning and 100% block |

See [DEPLOY.md](DEPLOY.md) for production and [docs/ROADMAP.md](docs/ROADMAP.md) for planned features.

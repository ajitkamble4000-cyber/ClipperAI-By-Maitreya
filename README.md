# Shorts Studio

A hosted web app, run as a business, for making short-form video:

- **Paste any link** (YouTube, TikTok, Instagram, X, Facebook, Vimeo, Twitch, Reddit… or upload up to 4 GB) and get **captioned clips**, or the **whole video captioned**. Auto mode decides: short videos are captioned whole, long ones are cut into the best moments.
- **Story Studio**: idea → AI script → storyboard → consistent characters → scene images → AI voiceover → motion (Ken Burns or AI video) → music, SFX, captions → finished Short.
- **Accounts and plans**: public sign-up, Free / Pro / Business plans, daily tokens (1,000 a day on Free), bonus tokens, upgrade requests, Staff and Content-creator teams that get everything free.
- **Owner & admin panel**: one owner (set by `OWNER_EMAIL`) who manages admins, plans, prices and tokens; admins manage users, jobs and announcements.
- **Many AI providers**: Gemini, OpenAI, Anthropic, OpenRouter, any OpenAI-compatible server, ElevenLabs, Replicate, Stability, with per-job routing and automatic fallback.

## Architecture

```
Browser (Next.js on Vercel)
  ├─ Supabase Auth (login, invites)            ├─ Supabase Postgres reads (RLS)
  ├─ Realtime: live job / clip / scene updates  └─ PUT upload parts straight to R2 (presigned, resumable)
  └─ HTTPS + JWT ─► FastAPI (VPS, Docker, behind Caddy)
                      │  verifies JWT, roles, rate limits; presigns R2; decrypts secrets
                      └─► Redis ─► Celery workers (VPS, Docker)
                                    media queue: ffmpeg, faster-whisper, reframe, render
                                    ai/poll queues: AI text, images, voice, video operations (any provider)
                                    beat: stuck-job recovery, source cleanup
```

- Every job is a chain of **resumable steps** recorded in `job_steps`; a crashed worker's job is re-queued and skips finished steps. Story assets (images, voice, animated scenes, Veo clips) are **content-addressed** so re-renders never pay twice.
- AI provider keys are stored **encrypted** (Fernet) in Postgres or set as env vars; they never reach a browser. Each job type (text, images, voice, video, transcription) is routed to a provider and model with fallbacks; every call is logged with its estimated cost.
- **Tokens**: every job is quoted, charged when it starts and refunded if it fails, from a locked wallet with an append-only ledger.
- Video processing never runs on Vercel.

## Repository

```
web/      Next.js App Router + TypeScript + Tailwind (+ shadcn-style components), Playwright e2e
api/      FastAPI: auth, accounts, plans/tokens, uploads, jobs, clipper, story, extras, brand, admin, settings
worker/   Celery workers: pipeline runner, clipper/, story/, captions/, media/, transcribe/, publish/ (interface only)
shared/   py/studio_shared (config, db, R2, crypto, AI providers, tokens, usage/budget, platforms), presets/*.json, fonts/
infra/    supabase/ (config + SQL migrations with RLS), docker/, compose.yml (dev), compose.prod.yml, caddy/, scripts/
tests/    fixtures (generated test media)
```

## Local development

Requirements: Docker, Node 20+, Python 3.11 with [uv](https://docs.astral.sh/uv/), ffmpeg.

```bash
cp .env.example .env            # then fill APP_ENCRYPTION_KEY and OWNER_EMAIL (see comments)
cp web/.env.example web/.env.local
uv sync                         # Python deps for api + worker + shared
(cd web && npm install)
make supabase-start             # local Postgres, Auth, Realtime, Mailpit (prints keys for .env)
make supabase-reset             # apply migrations
docker compose -f infra/compose.yml up -d redis s3   # Redis + an S3 emulator standing in for R2
```

Then, in three terminals: `make api`, `make worker`, `make web`. Open http://localhost:3000/signup and create the account for your `OWNER_EMAIL`: it becomes the owner. Emails (confirmations, invites, resets) land in Mailpit at http://127.0.0.1:54324. `scripts/dev-services.sh` starts Docker, Redis, the S3 emulator and local Supabase in one go.

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
                                                  # the e2e API uses OWNER_EMAIL=e2e-owner@example.com
uv run pytest                                     # + end-to-end media tests (renders real video)
cd web && npx next build && STUDIO_FAKE_GEMINI=1 npx playwright test
```

What the media tests verify (not just "it ran"): 1080x1920 at 30 fps, H.264/AAC, durations match cuts and narration within 0.12–0.15 s, integrated loudness −14 ±1.5 LUFS, **caption timing checked by re-transcribing the rendered video** (median offset < 0.15 s), captions actually burned in (pixel diff), music ducking measured (> 6 dB under the voice), resume skips finished steps, cached assets are reused.

`STUDIO_FAKE_GEMINI=1` swaps the AI providers for an offline fake (Pillow images, espeak voice, fake Veo) **for tests only**; never set it in production.

## Features at a glance

| Area | What you get |
|---|---|
| Any link | Platform detection for 20 sites (with login-wall help), title/length preview, auto / clips / captions modes, batch links (Business) |
| Clipper | 1–20 clips, 15–180 s; content types (podcast, interview, sports, gaming, education, vlog); AI moments with structured JSON + validation; visual analysis; loudness peaks; basic mode without AI; face/action/center/blur reframe; clip cards with edit, nudge, restyle, re-format, share, ZIP |
| Formats | 9:16, 1:1, 4:5, 16:9 (Pro) with format-aware caption layout and safe areas |
| Captions | Bold Pop, Karaoke, Minimal, Boxed, Horror; fonts incl. Noto Sans Devanagari; size/colours/outline/caps/words-per-line/position/emoji; keyword emphasis; translated captions in 24 languages; SRT / VTT / TXT files |
| Polish | Silence and filler-word removal with re-timed captions, progress bar, hook text, brand kit (logo, @handle, colour), free-plan watermark |
| Story Studio | 12 genres, visual styles (admins add more), 30/45/60/90 s, English/Hindi/Hinglish, voices + preview, upload your own voiceover; storyboard editor with autosave and AI rewrites; consistent characters; per-scene image redo/edit/upload; Ken Burns motion; AI video per scene; music with auto-ducking; SFX; batch topics (Business) |
| Creator extras | Built-in and saved templates, designed thumbnails (YouTube 16:9 + vertical cover, frame or AI background), title & hashtag ideas, public share links |
| Accounts | Sign-up, Home dashboard with quick paste and getting-started checklist, notifications, token history, plan & pricing pages, upgrade requests, account deletion |
| Business | Free / Pro / Business / Team plans with features and limits, daily tokens + bonus tokens, editable token prices, refunds on failure, Staff & Creator teams free and unlimited |
| Admin | Overview analytics, users (plan, team, tokens, allowance, suspend, admin role), upgrade requests, jobs monitor with cancel + refund, announcements, audit log, system health, plan & price editor, token gifts |
| Cost control | Every AI call logged with estimated cost per provider/model; monthly budget with 80% warning and 100% pause |

See [DEPLOY.md](DEPLOY.md) for production and [docs/ROADMAP.md](docs/ROADMAP.md) for planned features.

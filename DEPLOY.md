# Deploying Shorts Studio

Production layout:

| Piece | Where | Notes |
|---|---|---|
| Web app (Next.js) | **Vercel** | `web/` directory. Only public keys live here. |
| API + workers + Redis | **VPS** with Docker Compose | `infra/compose.prod.yml`, Caddy terminates HTTPS |
| Database, Auth, Realtime | **Supabase** cloud project | migrations in `infra/supabase/migrations` |
| Files | **Cloudflare R2** | one private bucket |
| AI | **Google AI Studio** (Gemini API key, billing on) | key entered in Settings, stored encrypted |

Domains used below: `studio.example.com` (web, Vercel) and `api.studio.example.com` (API, VPS). Replace with yours.

---

## 1. Supabase

1. Create a project (pick the region closest to your VPS). Pro plan recommended for production (free projects pause when idle).
2. **Apply the schema** from your machine:
   ```bash
   npx supabase@3.1.0 login
   npx supabase@3.1.0 link --project-ref <your-project-ref> --workdir infra
   npx supabase@3.1.0 db push --workdir infra
   ```
3. **Auth → Providers → Email**: keep Email enabled, **turn off "Allow new users to sign up"** (invite-only). Invites still work.
4. **Auth → URL configuration**: Site URL `https://studio.example.com`; add `https://studio.example.com/**` to Redirect URLs.
5. **Auth → SMTP**: set up a custom SMTP sender (e.g. Resend). Supabase's built-in email is heavily rate-limited, so invites may not arrive without this.
6. Note from **Project Settings → API**: project URL, anon (publishable) key, service-role (secret) key. From **Database → Connection string**: the session-pooler URI (port 5432).
7. Realtime is enabled for the needed tables by the migrations (publication `supabase_realtime`).

## 2. Cloudflare R2

1. Create a bucket, e.g. `shorts-studio` (keep public access **off**).
2. **R2 → Manage API tokens**: create a token with *Object Read & Write* on that bucket. Note the Access Key ID, Secret Access Key and the S3 endpoint `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.
3. **Bucket → Settings → CORS policy**: paste `infra/r2-cors.json` with your web origin(s). `ExposeHeaders: ["ETag"]` is required for resumable uploads.
4. Optional lifecycle rule to abort incomplete multipart uploads after 7 days (the app also cleans up after 2 days).

## 3. VPS

Recommended minimum: 8 vCPU, 16 GB RAM, 160 GB disk, Ubuntu 24.04 (e.g. Hetzner CCX33/CPX51, DigitalOcean CPU-optimized). No GPU needed.

```bash
ssh root@<vps-ip>
curl -fsSL https://raw.githubusercontent.com/<you>/shorts-studio/main/infra/scripts/bootstrap-vps.sh | bash   # or copy it over
git clone https://github.com/<you>/shorts-studio.git /opt/shorts-studio
cd /opt/shorts-studio
cp .env.example .env && nano .env
```

Fill `.env`:

- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL` (session pooler), leave `SUPABASE_JWT_SECRET` empty unless your project still uses the legacy HS256 secret
- `S3_ENDPOINT`, `S3_REGION=auto`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET`
- `APP_ENCRYPTION_KEY`: `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. **Back it up.** Losing it makes saved secrets unreadable.
- `SETUP_TOKEN`: a long random string (used once)
- `WEB_ORIGINS=https://studio.example.com`
- `API_DOMAIN=api.studio.example.com`
- Worker sizing: `WORKER_MEDIA_CONCURRENCY` ≈ vCPUs / 3 (each render uses several cores), `WORKER_AI_CONCURRENCY=8`

DNS: an **A record** `api.studio.example.com → <vps-ip>` (if it's on Cloudflare, keep the proxy **off/grey** at first so Caddy can get its certificate).

Start everything:

```bash
docker compose -f infra/compose.prod.yml --env-file .env up -d --build
API_DOMAIN=api.studio.example.com infra/scripts/smoke.sh
```

The first transcription downloads the whisper model into the `model-cache` volume (a few hundred MB).

Updates later: `infra/scripts/deploy.sh` (pull, rebuild, restart). Running jobs resume from their last finished step after the restart.

## 4. Vercel

1. **Add New Project** → import the GitHub repo → **Root Directory: `web`** (framework auto-detected as Next.js).
2. Environment variables (Production and Preview):
   - `NEXT_PUBLIC_SUPABASE_URL` = Supabase project URL
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY` = anon / publishable key
   - `NEXT_PUBLIC_API_URL` = `https://api.studio.example.com`
3. Deploy, then **Settings → Domains** → add `studio.example.com` and set the DNS record Vercel shows.
4. A team using this commercially should be on Vercel Pro (Hobby is for non-commercial use).

## 5. First run

1. Open `https://studio.example.com/setup`, enter the `SETUP_TOKEN`, create the admin account.
2. Remove `SETUP_TOKEN` from `.env` and restart the API (`docker compose ... up -d api`).
3. **Settings → AI & budget**: paste the Gemini key (it's tested before saving), pick the text / image / TTS / video models from the live list, set a monthly budget.
4. **Settings → Pricing**: check the estimate prices against Google's current price list.
5. **Settings → Library**: upload a few royalty-free music tracks per mood (a built-in SFX kit is created automatically).
6. **Settings → Members**: invite the team.
7. **Settings → Diagnostics**: run the test job and a test upload to confirm the queue, Realtime and R2 CORS.

## YouTube downloads from a VPS

YouTube frequently answers datacenter IPs with "Sign in to confirm you're not a bot". The app detects this and suggests uploading the file instead. To make links work more often:

- **Settings → Downloads & storage → cookies.txt**: from a browser logged into a *separate* Google account, export youtube.com cookies in Netscape format and upload. Refresh it when downloads start failing again.
- Optionally add a residential **proxy** there.
- yt-dlp is pinned in `worker/pyproject.toml`; YouTube changes often, so rebuild workers regularly (`uv lock --upgrade-package yt-dlp`, then deploy).

## Operations

- Logs: `docker compose -f infra/compose.prod.yml logs -f worker-media api` (API keys are redacted from logs).
- Scale workers: raise `WORKER_*_CONCURRENCY`, or add a second VPS running only the worker services pointed at the same Redis/DB/R2 (expose Redis privately, e.g. over a WireGuard/Tailscale network, never publicly).
- Backups: Supabase handles Postgres backups (Pro); R2 holds media; keep `.env` (especially `APP_ENCRYPTION_KEY`) in a password manager.
- Storage: uploaded/downloaded sources are deleted after the retention period (Settings). Finished clips and stories are kept until a project is deleted.
- Security checklist: RLS on every table; signups disabled; only the API holds secrets; CORS limited to `WEB_ORIGINS`; job creation rate-limited per user; uploads validated by type and size; links sanitized (no private/loopback addresses).

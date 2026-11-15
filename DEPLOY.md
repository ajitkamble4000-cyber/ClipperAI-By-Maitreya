# Deploying Shorts Studio

Production layout:

| Piece | Where | Notes |
|---|---|---|
| Web app (Next.js) | **Vercel** | `web/` directory. Only public keys live here. |
| API + workers + Redis | **VPS** with Docker Compose | `infra/compose.prod.yml`, Caddy terminates HTTPS |
| Database, Auth, Realtime | **Supabase** cloud project | migrations in `infra/supabase/migrations` |
| Files | **Cloudflare R2** | one private bucket |
| AI | **Any of**: Google Gemini, OpenAI, Anthropic, OpenRouter, any OpenAI-compatible server, ElevenLabs, Replicate, Stability | keys entered by the owner in the app (stored encrypted) or set as env vars |

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
3. **Auth → Providers → Email**: keep Email enabled and **"Allow new users to sign up" on** (people create free accounts on `/signup`). **Turn "Confirm email" on.** This is required: the owner account is recognised by its *verified* email address, so without confirmation anyone could sign up with the owner's address.
4. **Auth → URL configuration**: Site URL `https://studio.example.com`; add `https://studio.example.com/**` to Redirect URLs.
5. **Auth → SMTP**: set up a custom SMTP sender (e.g. Resend). Supabase's built-in email is heavily rate-limited, so sign-up confirmations, invites and password resets may not arrive without this.
6. **Auth → Rate limits / Attack protection**: turn on CAPTCHA (hCaptcha or Turnstile) for sign-ups once the site is public.
7. Note from **Project Settings → API**: project URL, anon (publishable) key, service-role (secret) key. From **Database → Connection string**: the session-pooler URI (port 5432).
8. Realtime is enabled for the needed tables by the migrations (publication `supabase_realtime`).

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
- `OWNER_EMAIL`: the owner/founder's email address. That account (once it has signed up and **confirmed** its email) is the owner: the only one who can add or remove admins, edit plans and send token gifts. Changing it later moves ownership.
- AI keys (optional here): `GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `ELEVENLABS_API_KEY`, `REPLICATE_API_TOKEN`, `STABILITY_API_KEY`. Or leave them empty and add keys in the app.
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

1. Open `https://studio.example.com/signup` and create the account for `OWNER_EMAIL`; click the confirmation link in the email. When you sign in, the account is the owner (the sidebar shows **Admin**).
2. **Admin → AI & storage settings → AI providers**: add at least one key (each is tested before saving). Then pick which provider does each job (text/script, images, voice, video, transcription) with fallbacks. With no AI key, the clipper still works in basic mode and captions still work (local transcription).
3. **Budget**: set a monthly AI spending cap; everyone is warned at 80% and image/voice/video pause at 100%.
4. **AI model costs**: check the USD prices used for cost estimates against your providers' price lists.
5. **Admin → Plans & prices**: review the plans (Free 1,000 tokens/day, Pro 5,000, Business 20,000, Team unlimited), what each includes, and the token price of every action. Prices on the public `/pricing` page update immediately.
6. **Library**: upload a few royalty-free music tracks per mood (a built-in SFX kit is created automatically).
7. Make admins: **Admin → Users → (user) → Make admin** (owner only). Put staff and content creators on the **Staff** or **Content creator** team there: they get everything free and unlimited.
8. **Admin → System health** should be all green; run a test job from **Settings → Diagnostics** to confirm the queue, Realtime and R2 CORS.

### Plans, tokens and upgrades

- Every user gets a daily token allowance that refills at 00:00 UTC; bonus tokens (gifts) never expire. Tokens are charged when a job starts and refunded automatically if it fails or is canceled.
- Online card payments aren't connected yet. Users click **Upgrade** on `/pricing`, which sends an upgrade request; the owner/admins approve it in **Admin → Upgrade requests** (the user is notified and gets the new allowance the same day). To sell online later, connect a payment provider's webhook to the same plan change.
- **Admin → Users** lets the owner/admins give or take bonus tokens, set a custom daily allowance, change plans, suspend accounts and see each user's activity and token history. Everything is recorded in **Admin → Audit log**.

## YouTube downloads from a VPS

YouTube (and Instagram, Facebook, LinkedIn, Threads) frequently answer datacenter IPs with a login wall such as "Sign in to confirm you're not a bot". The app detects this, names the site, and suggests uploading the file instead. To make links work more often:

- **Settings → Downloads & storage → cookies.txt** (owner only): from a browser logged into a *separate* Google account, export youtube.com cookies in Netscape format and upload. Refresh it when downloads start failing again.
- Optionally add a residential **proxy** there.
- yt-dlp is pinned in `worker/pyproject.toml`; YouTube changes often, so rebuild workers regularly (`uv lock --upgrade-package yt-dlp`, then deploy).

## Operations

- Logs: `docker compose -f infra/compose.prod.yml logs -f worker-media api` (API keys are redacted from logs).
- Scale workers: raise `WORKER_*_CONCURRENCY`, or add a second VPS running only the worker services pointed at the same Redis/DB/R2 (expose Redis privately, e.g. over a WireGuard/Tailscale network, never publicly).
- Backups: Supabase handles Postgres backups (Pro); R2 holds media; keep `.env` (especially `APP_ENCRYPTION_KEY`) in a password manager.
- Storage: uploaded/downloaded sources are deleted after the retention period (Settings). Finished clips and stories are kept until a project is deleted.
- Security checklist: email confirmation **on** (owner is recognised by verified email); RLS on every table and every project private to its creator (Staff/Creator teams share a team library); only the API holds secrets and AI keys (encrypted at rest); CORS limited to `WEB_ORIGINS`; job creation rate-limited per user and capped per plan; uploads validated by type and size; links sanitized (no private/loopback addresses); share links are unguessable, expire, and can be turned off; admin actions are audited.

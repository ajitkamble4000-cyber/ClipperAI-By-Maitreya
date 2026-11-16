# Go live: sign-in and the app, on free plans

About 20 minutes. You type your passwords and secret keys **only into Supabase and Render**, never into chat or
into this repository. Three public values come back to the website at the end.

The website is already live on GitHub Pages: https://ajitkamble4000-cyber.github.io/ClipperAI-By-Maitreya/

## 1. Supabase: accounts and database (free)

1. Sign up at **supabase.com** → **New project**. Name: `clipperai`. Click **Generate a password** for the
   database and save it in your password manager. Region: **Mumbai** (or Singapore). Create.
2. When it's ready: **SQL Editor → New query**. Open
   [`infra/supabase/setup.sql`](https://github.com/ajitkamble4000-cyber/ClipperAI-By-Maitreya/blob/main/infra/supabase/setup.sql),
   click **Raw**, select all, copy, paste into the editor, click **Run**. You should see *Success. No rows returned*.
   (Run it once, on the new project.)
3. **Authentication → URL Configuration**:
   - Site URL: `https://ajitkamble4000-cyber.github.io/ClipperAI-By-Maitreya/`
   - Redirect URLs → **Add URL**: `https://ajitkamble4000-cyber.github.io/ClipperAI-By-Maitreya/**`
4. Keep this tab open; step 2 needs four things from it:
   - **Project URL** and the **anon / publishable key**: *Project Settings → API keys* (both are public).
   - The **service_role / secret key**: same page. This one is secret.
   - The **database connection string**: click **Connect** (top of the page) → **Session pooler** → copy the URI
     and replace `[YOUR-PASSWORD]` with the database password from step 1. Secret.

## 2. Render: the API server (free)

1. Sign up at **render.com** with your GitHub account.
2. Open **https://render.com/deploy?repo=https://github.com/ajitkamble4000-cyber/ClipperAI-By-Maitreya**
   (or the *Deploy to Render* button in the README). Render reads `render.yaml` and shows the API server and a Redis.
3. Fill in:
   - `OWNER_EMAIL`: the email you'll sign up with. That account becomes the owner (Admin panel).
   - `DATABASE_URL`: the Session pooler connection string.
   - `SUPABASE_URL`: the Project URL.
   - `SUPABASE_SERVICE_ROLE_KEY`: the service_role / secret key.

   (`APP_ENCRYPTION_KEY` is generated for you. Never change it later: it protects the keys you save in the app.)
4. Click **Apply**. The first build takes about 10 minutes. When the service shows **Live**, copy its URL
   (like `https://clipperai-api.onrender.com`) and open `…/health` in your browser: it should say `{"ok":true}`.

## 3. Connect the website

Send these three **public** values in chat (or add them yourself in GitHub: *Settings → Secrets and variables →
Actions → Variables* as `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_URL`, then
*Actions → Deploy web app to GitHub Pages → Run workflow*):

- Supabase Project URL
- Supabase anon / publishable key
- Render API URL

They're safe to share: they're sent to every visitor's browser anyway, and the database is protected by its
access rules. **Never** share the service_role key, the database password or the connection string.

## 4. First sign-in

Open the website → **Start free** → sign up with your `OWNER_EMAIL` → click the confirmation link in the email →
sign in. You'll land on Home with **Admin** in the sidebar. Then:

- **Admin → AI & storage settings → AI providers**: add your AI keys.
- **Admin → Payments**: add your Razorpay keys. The webhook URL to give Razorpay is shown there.

## Good to know

- **Free Render services sleep** after 15 minutes without visitors; the first request after that takes about a
  minute. A paid instance (Starter) stays awake.
- **Emails**: Supabase's built-in email sender allows only a few emails per hour. For real traffic add your own
  SMTP (Supabase → Authentication → Emails → SMTP settings).
- **Video processing** needs two more things, when you're ready:
  1. Storage: Supabase → **Storage → New bucket** `clipperai` (private), then **Storage → Settings → S3 access
     keys → New key**. In Render (clipperai-api → Environment) add `S3_ENDPOINT` =
     `https://<project-ref>.supabase.co/storage/v1/s3`, `S3_REGION` = your project region (e.g. `ap-south-1`),
     `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET` = `clipperai`.
  2. The worker: Render → **New → Background Worker** from this repository, Docker, Dockerfile path
     `./infra/docker/worker.Dockerfile`, plan **Starter** or bigger (video needs memory), with the same environment
     variables as the API (copy them, including `REDIS_URL` and `APP_ENCRYPTION_KEY`).
- Bigger setups (your own VPS, Cloudflare R2, Vercel): see [DEPLOY.md](../DEPLOY.md).

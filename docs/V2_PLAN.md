# V2: Shorts Studio as a business (autonomous build plan)

Owner request (summarised): public product with users, a single owner (OWNER_EMAIL, verified), admins
appointed by the owner, tokens (1,000/day for normal users, refilled daily, extra grants), a staff /
content-creator team that gets everything free, plans with exclusive features, many AI providers (not
only Google), paste any link (YouTube, Instagram, TikTok, ...) and get captioned clips automatically,
lots of settings, an admin panel and a user panel.

Interpretations: "not just Google" = multi-provider with Google as one option; "caps" = clips with
captions (short videos are captioned whole, long ones become clips).

## Resume after an interruption

```bash
cd /home/user/shorts-studio && scripts/dev-services.sh   # docker, redis, S3 emulator, supabase
git log --oneline | head                                 # last finished phase
```
Then continue with the first unchecked phase below.

## Phases (each ends with tests + a commit)

- [x] 9. Business accounts & tenancy: public sign-up, owner by verified email, roles owner/admin/user,
      Staff/Creator team (unlimited), plans table, private projects (RLS + API checks), suspension, audit log
- [x] 10. Token economy: wallets, daily refill, bonus grants, ledger, editable token prices, charge on job
      start, auto-refund on failure/cancel, quotes, plan limits and feature gates
- [x] 11. Multi-provider AI: provider keys (encrypted), OpenAI, Anthropic, OpenRouter, OpenAI-compatible
      (Groq/DeepSeek/Mistral/Ollama), ElevenLabs, Replicate, Stability, Google; per-role choice + fallback,
      model lists, pricing; cloud transcription; frame-based visual analysis
- [x] 12. Any-link quick mode & captions tool: platform detection, auto mode, output formats
      (9:16/1:1/4:5/16:9), SRT/VTT/TXT exports, translation, keyword emphasis, filler/silence removal,
      progress bar, free-plan watermark, brand-kit logo
- [x] 13. User panel: landing, pricing, sign-up, dashboard (wallet, quick paste, recent), notifications,
      token history, brand kit, account (delete), share links, onboarding, locked-feature UI
- [x] 14. Admin panel: overview analytics, users (plan/team/tokens/suspend/role), admins (owner only),
      plans & token prices, providers & keys (owner only), jobs monitor, audit log, announcements, system health
- [x] 15. Creator extras: templates, batch (many links / many story topics), more genres, AI thumbnails,
      title & hashtag variants
- [x] 16. Docs, full regression, push-ready

## Feature list (target: ~60 shipped updates)

Accounts & business: 1 public sign-up + email verification · 2 owner locked to OWNER_EMAIL · 3 owner adds/removes admins ·
4 plans Free/Pro/Business/Team · 5 Staff & Creator teams = everything free · 6 1,000 daily tokens, auto refill ·
7 bonus token grants/revokes · 8 token ledger/history · 9 editable token prices · 10 auto-refund on failure ·
11 plan feature gates · 12 plan limits (clips/job, upload size, video length, concurrent jobs) · 13 free-plan watermark ·
14 suspend/ban · 15 audit log · 16 announcements banner · 17 private projects + shared team library · 18 account deletion

AI providers: 19 provider keys vault · 20 OpenAI text · 21 Anthropic text · 22 OpenRouter · 23 any OpenAI-compatible API ·
24 OpenAI images · 25 Stability images · 26 Replicate images & video · 27 ElevenLabs voices · 28 OpenAI voices ·
29 cloud transcription (OpenAI/Groq Whisper) · 30 per-role provider/model + fallback · 31 live model lists · 32 per-model pricing

Clipping & captions: 33 paste any link (YouTube, Instagram, TikTok, X, Facebook, Vimeo, Twitch, Reddit, ...) ·
34 auto mode (short = caption whole, long = clips) · 35 captions tool · 36 SRT/VTT/TXT exports · 37 caption translation ·
38 auto content-type detection · 39 visual analysis with any vision model · 40 AI keyword emphasis · 41 filler/silence removal ·
42 progress bar · 43 brand-kit logo · 44 output formats 9:16/1:1/4:5/16:9 · 45 batch links

Story & creator: 46 templates · 47 batch stories · 48 more genres · 49 AI thumbnails · 50 title/hashtag variants

Panels: 51 notifications · 52 landing page · 53 pricing page · 54 onboarding checklist · 55 public share links ·
56 user dashboard · 57 admin analytics · 58 admin system health · 59 admin jobs monitor · 60 locked-feature upgrade UI

## V3 batch (more features)

- [x] 17. Growth: promo codes (bonus tokens or plan trials with auto-expiry), referral program (both sides
      rewarded after the friend's first finished video), owner site controls (sign-ups open/closed,
      maintenance banner, referral rewards)
- [x] 18. Editing: fix caption words and re-render, background music on clips (auto-ducked), compilations
      (merge clips into one video), MP3 audio and GIF exports
- [x] 19. Repurpose with AI: summary, YouTube chapters, key quotes, blog post, X thread, LinkedIn post and
      newsletter from a video; search what was said across the library
- [x] 20. Developer API (Business): personal API keys, webhooks when jobs finish (signed), developer docs page
- [x] 21. Account: download my data (export); full regression + docs

## V4 batch

- [ ] 22. Look: split-screen reframe for two-person podcasts; caption presets Neon, Typewriter, Bounce
- [ ] 23. Content calendar: schedule clips/stories per platform, reminders, mark as posted, calendar feed (.ics)
- [ ] 24. Project sharing: share a project with another account as viewer or editor; "Shared with me"
- [ ] 25. Insights: personal stats page; admin extras (refund a job, export users as CSV)
- [ ] 26. Full regression + docs

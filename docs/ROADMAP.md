# Roadmap (planned, not built)

The code and data model are structured for these; they aren't built yet. (Templates, batch mode and title/thumbnail variants from the original roadmap are now built.)

## Publishing to YouTube and Instagram Reels

- Data model: `channels` (OAuth tokens stored encrypted, server-only), `publish_queue` (scheduled uploads), migration `20261115000006_later_features.sql`.
- Code: `worker/worker/publish/base.py` defines the `Publisher` interface (quota check + publish).
- **Re-check the platforms' current rules before building.** Known constraints to design around:
  - The YouTube Data API's default daily quota allows only a handful of uploads per day per Google Cloud project, so the queue must schedule uploads into available quota and show the next free slot. Quota increases need Google's request form.
  - Uploads from an **unverified** API project are forced to **private** until the project passes Google's API compliance audit. Until then: upload private, let a person publish from YouTube Studio.
  - Multiple channels per workspace: one OAuth connection per channel; a channel's tokens can be revoked by its owner at any time, so failures must surface clearly.
  - Instagram Reels need a Business/Creator account linked to a Facebook Page and the Graph API; the video is fetched from a URL (a short-lived signed R2 URL).

## Online payments

Plans are switched today by the owner/admins approving upgrade requests (Admin → Upgrade requests). To sell online,
connect a payment provider (e.g. Stripe Checkout + Billing portal): a webhook on "subscription active / canceled"
calls the same plan change (`members.plan_id` + `tokens.on_plan_change`) that approving a request uses, and token
packs can be sold as bonus-token grants. Keep the request flow for invoices and custom deals.

## Analytics for titles and thumbnails

Title/hashtag ideas and designed thumbnails exist today. After publishing is built, pull view/retention stats per
title/thumbnail variant (YouTube Analytics API) into the library so creators can see which version won.

## Email notifications

In-app notifications exist (the bell). Add optional email for "your video is ready" and upgrade decisions, with a
per-user switch, sent through the same SMTP provider Supabase Auth uses.

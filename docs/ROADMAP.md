# Roadmap (planned, not built)

The code and data model are structured for these; none of them is implemented yet.

## Publishing to YouTube and Instagram Reels

- Data model: `channels` (OAuth tokens stored encrypted, server-only), `publish_queue` (scheduled uploads), migration `20261115000006_later_features.sql`.
- Code: `worker/worker/publish/base.py` defines the `Publisher` interface (quota check + publish).
- **Re-check the platforms' current rules before building.** Known constraints to design around:
  - The YouTube Data API's default daily quota allows only a handful of uploads per day per Google Cloud project, so the queue must schedule uploads into available quota and show the next free slot. Quota increases need Google's request form.
  - Uploads from an **unverified** API project are forced to **private** until the project passes Google's API compliance audit. Until then: upload private, let a person publish from YouTube Studio.
  - Multiple channels per workspace: one OAuth connection per channel; a channel's tokens can be revoked by its owner at any time, so failures must surface clearly.
  - Instagram Reels need a Business/Creator account linked to a Facebook Page and the Graph API; the video is fetched from a URL (a short-lived signed R2 URL).

## Saved templates

`templates` table: a full story (or clip) preset (genre, visual style, voice, speaking style, captions, music, motion mode) applied with one click.

## Batch mode

`batches` table: a template plus a list of topics; creates one story project per topic and runs script generation for each. Media generation stays opt-in per story so costs are reviewed.

## A/B titles and analytics

Generate 2–3 title/thumbnail variants per Short; after publishing, pull view/retention stats per variant (YouTube Analytics API) into the library.

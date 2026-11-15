"""Interface every publishing target implements. Nothing implements it yet (planned feature).

Design constraints to honor when building it (re-check Google's and Meta's current rules first):
- YouTube Data API: uploads cost quota units from a small default daily allowance (historically
  10,000 units/day with ~1,600 per upload, i.e. about 6 uploads/day per Google Cloud project).
  The publisher must track remaining quota per channel/project, queue uploads that don't fit, and
  surface "next slot" times in the UI. Requesting a quota increase is a manual Google form.
- Videos uploaded by an UNVERIFIED API project are locked to private until the project passes
  Google's API audit. Until then, upload as private and let a human flip visibility in Studio
  (or schedule via publishAt only after verification).
- Instagram Reels go through the Instagram Graph API (business/creator accounts linked to a
  Facebook Page), using a public video URL (a short-lived signed R2 URL works).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol


@dataclass
class PublishRequest:
    video: Path
    title: str
    description: str
    tags: list[str]
    privacy: str = "private"
    publish_at: datetime | None = None
    thumbnail: Path | None = None


@dataclass
class PublishResult:
    external_id: str
    url: str
    status: str  # uploaded | scheduled | published | private_until_verified


class Publisher(Protocol):
    platform: str

    def quota_remaining(self, channel_id: str) -> int | None:
        """Uploads still possible today for this channel (None if unknown/unlimited)."""

    def publish(self, channel_id: str, req: PublishRequest) -> PublishResult: ...

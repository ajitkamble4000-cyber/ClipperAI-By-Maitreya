"""Logging with secret redaction. API keys must never reach logs."""

from __future__ import annotations

import logging
import re

_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),  # Google API keys
    re.compile(r"(?i)(x-goog-api-key|api[_-]?key|authorization)(['\"]?\s*[:=]\s*['\"]?)([^\s'\",]+)"),
    re.compile(r"(?i)(X-Amz-Signature|X-Amz-Credential|key)=([^&\s]+)"),
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),  # JWTs
]


def redact(text: str) -> str:
    out = _PATTERNS[0].sub("[REDACTED]", text)
    out = _PATTERNS[1].sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", out)
    out = _PATTERNS[2].sub(lambda m: f"{m.group(1)}=[REDACTED]", out)
    return _PATTERNS[3].sub("[REDACTED_JWT]", out)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        red = redact(msg)
        if red != msg:
            record.msg, record.args = red, None
        return True


def setup(level: str = "INFO") -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    f = RedactingFilter()
    for h in logging.getLogger().handlers:
        h.addFilter(f)

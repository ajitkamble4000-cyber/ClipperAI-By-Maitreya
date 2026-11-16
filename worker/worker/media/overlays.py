"""Overlays drawn on the final video in the same encode as the captions: free-plan watermark, brand-kit
logo and handle, progress bar. Positions stay clear of platform UI on 9:16."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from studio_shared import brand
from studio_shared.config import get_settings

from . import ffmpeg

WATERMARK = f"Made with {brand.NAME}"


@dataclass
class OverlayOptions:
    watermark_text: str | None = None  # Free plan
    logo: Path | None = None  # Brand kit (Pro+): local PNG/JPG/WebP
    logo_position: str = "top-right"  # top-left | top-right
    logo_opacity: float = 0.9
    handle: str = ""  # e.g. @mychannel, drawn small under the logo
    progress_bar: bool = False
    progress_color: str = "#FFE500"

    @property
    def any(self) -> bool:
        return bool(self.watermark_text or self.logo or self.handle or self.progress_bar)

    @classmethod
    def from_params(cls, params: dict[str, Any], fetch_logo) -> OverlayOptions | None:
        """Build from job/clip render options. `fetch_logo(key) -> Path` downloads the brand logo."""
        brand = params.get("brand") or {}
        logo = None
        if brand.get("logo_key"):
            try:
                logo = fetch_logo(brand["logo_key"])
            except Exception:  # noqa: BLE001 - a missing logo must not fail the render
                logo = None
        o = cls(
            watermark_text=WATERMARK if params.get("watermark") else None,
            logo=logo,
            logo_position=brand.get("logo_position") or "top-right",
            logo_opacity=float(brand.get("logo_opacity") or 0.9),
            handle=(brand.get("handle") or "").strip()[:40],
            progress_bar=bool(params.get("progress_bar")),
            progress_color=brand.get("primary_color") or "#FFE500",
        )
        return o if o.any else None


def _esc(s: str) -> str:
    return (
        s.replace("\\", "\\\\").replace(":", r"\:").replace("'", "’").replace("%", r"\%").replace(",", r"\,")
    )


def chain(
    opts: OverlayOptions, in_label: str, *, width: int, height: int, duration: float, logo_input: int | None
) -> tuple[list[str], str]:
    """Filter-graph parts that draw the overlays on `in_label` (e.g. 'v0'); returns (parts, out_label)."""
    parts: list[str] = []
    label = in_label
    n = 0

    def nxt() -> str:
        nonlocal n
        n += 1
        return f"ov{n}"

    vertical = width * 16 == height * 9
    margin_x = int(width * 0.05)
    top = int(height * (0.06 if vertical else 0.05))
    side_right = opts.logo_position != "top-left"
    font = ffmpeg.escape_filter_path(get_settings().fonts_dir / "Inter-Bold.otf")
    small = max(18, min(width, height) // 34)

    if opts.progress_bar:
        out = nxt()
        color = opts.progress_color.lstrip("#")
        bar_h = max(6, height // 200)
        y = "0" if vertical else f"ih-{bar_h}"  # top on 9:16 (bottom is covered by the platform UI)
        parts.append(
            f"[{label}]drawbox=x=0:y={y}:w='iw*min(1,t/{max(0.1, duration):.3f})':h={bar_h}:"
            f"color=0x{color}@0.95:t=fill[{out}]"
        )
        label = out
    y_next = top
    if opts.logo is not None and logo_input is not None:
        out = nxt()
        lw = max(80, min(width, height) // 7)
        x = f"W-w-{margin_x}" if side_right else f"{margin_x}"
        parts.append(
            f"[{logo_input}:v]scale={lw}:-1,format=rgba,colorchannelmixer=aa={opts.logo_opacity:.2f}[logo];"
            f"[{label}][logo]overlay=x={x}:y={top}[{out}]"
        )
        label = out
        y_next = top + lw + 10  # handle sits under the logo
    if opts.handle:
        out = nxt()
        x = f"w-tw-{margin_x}" if side_right else f"{margin_x}"
        parts.append(
            f"[{label}]drawtext=fontfile='{font}':text='{_esc(opts.handle)}':fontsize={small}:"
            f"fontcolor=white@0.85:shadowcolor=black@0.6:shadowx=2:shadowy=2:x={x}:y={y_next}[{out}]"
        )
        label = out
    if opts.watermark_text:
        out = nxt()
        # Opposite corner from the brand logo; bottom-left on landscape. Small and semi-transparent.
        x = f"{margin_x}" if side_right else f"w-tw-{margin_x}"
        y = f"{top}" if vertical else f"h-th-{int(height * 0.05)}"
        parts.append(
            f"[{label}]drawtext=fontfile='{font}':text='{_esc(opts.watermark_text)}':fontsize={small}:"
            f"fontcolor=white@0.6:shadowcolor=black@0.5:shadowx=2:shadowy=2:x={x}:y={y}[{out}]"
        )
        label = out
    return parts, label

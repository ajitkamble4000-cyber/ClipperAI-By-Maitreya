"""Feature routers are registered here (core routers are in main.py)."""

from __future__ import annotations

from fastapi import APIRouter


def extra_routers() -> list[APIRouter]:
    from .routers import (
        account,
        admin,
        admin_ops,
        brand,
        clipper,
        extras,
        growth,
        library,
        projects,
        settings,
        story,
        story_media,
        tokens,
    )

    return [
        projects.router,
        clipper.router,
        story.router,
        story_media.router,
        library.router,
        settings.router,
        admin.router,
        tokens.router,
        brand.router,
        account.router,
        admin_ops.router,
        extras.router,
        growth.router,
    ]

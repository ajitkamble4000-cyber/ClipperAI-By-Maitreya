"""Feature routers are registered here (core routers are in main.py)."""

from __future__ import annotations

from fastapi import APIRouter


def extra_routers() -> list[APIRouter]:
    from .routers import admin, clipper, library, projects, settings, story, story_media

    return [
        projects.router,
        clipper.router,
        story.router,
        story_media.router,
        library.router,
        settings.router,
        admin.router,
    ]

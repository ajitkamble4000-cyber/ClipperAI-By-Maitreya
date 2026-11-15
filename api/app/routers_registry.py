"""Feature routers added in later phases are registered here."""

from __future__ import annotations

from fastapi import APIRouter


def extra_routers() -> list[APIRouter]:
    from .routers import clipper, projects, story

    return [projects.router, clipper.router, story.router]

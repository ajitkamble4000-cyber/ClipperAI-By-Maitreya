"""FastAPI entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from studio_shared import db
from studio_shared.config import get_settings
from studio_shared.errors import UserError
from studio_shared.logging_setup import setup as setup_logging
from studio_shared.tokens import InsufficientTokens
from studio_shared.usage import BudgetExceeded

from .routers import files, jobs, members, system, uploads
from .routers_registry import extra_routers


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    yield
    db.close_pool()


app = FastAPI(title="Shorts Studio API", version="0.1.0", lifespan=lifespan)
log = logging.getLogger("api")


@app.middleware("http")
async def json_errors(request: Request, call_next):
    """Turn unexpected errors into JSON 500s *inside* CORS, so browsers can read the message."""
    try:
        return await call_next(request)
    except Exception:  # noqa: BLE001
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Internal server error. Check the API logs."}, status_code=500)


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["authorization", "content-type"],
    max_age=600,
)


@app.exception_handler(InsufficientTokens)
async def tokens_handler(_: Request, exc: InsufficientTokens) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=402)


@app.exception_handler(UserError)
async def user_error_handler(_: Request, exc: UserError) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.exception_handler(BudgetExceeded)
async def budget_handler(_: Request, exc: BudgetExceeded) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=402)


for r in (system.router, members.router, uploads.router, jobs.router, files.router, *extra_routers()):
    app.include_router(r)

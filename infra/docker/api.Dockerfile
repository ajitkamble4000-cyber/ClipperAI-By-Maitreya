# syntax=docker/dockerfile:1.7
FROM python:3.11-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN pip install --no-cache-dir "uv==0.11.32"
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY shared/py/pyproject.toml shared/py/pyproject.toml
COPY api/pyproject.toml api/pyproject.toml
COPY worker/pyproject.toml worker/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package studio-api --no-install-workspace

COPY shared/py shared/py
COPY api api
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --package studio-api

RUN useradd -r -u 10001 app
USER app
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app/api
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]

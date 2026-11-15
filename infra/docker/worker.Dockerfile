# syntax=docker/dockerfile:1.7
FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg fontconfig fonts-noto-color-emoji libegl1 libgles2 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "uv==0.11.32"
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY shared/py/pyproject.toml shared/py/pyproject.toml
COPY api/pyproject.toml api/pyproject.toml
COPY worker/pyproject.toml worker/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package studio-worker --no-install-workspace

# Face detector model for auto-reframe (small, baked in).
RUN mkdir -p /models && curl -fsSL -o /models/blaze_face_short_range.tflite \
    https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite

COPY shared shared
COPY worker worker
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --package studio-worker \
    && mkdir -p /usr/share/fonts/studio && cp shared/fonts/*.ttf shared/fonts/*.otf /usr/share/fonts/studio/ && fc-cache -f

RUN useradd -r -u 10001 -m app && mkdir -p /tmp/shorts-studio /cache && chown app /tmp/shorts-studio /cache /models
USER app
# Whisper models download on first use into /cache (mount a volume so it persists).
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app/worker MODELS_DIR=/models HF_HOME=/cache/hf \
    TMP_DIR=/tmp/shorts-studio FONTS_DIR=/app/shared/fonts
CMD ["celery", "-A", "worker.celery_app", "worker", "-Q", "media", "--concurrency", "2", "--loglevel", "INFO"]

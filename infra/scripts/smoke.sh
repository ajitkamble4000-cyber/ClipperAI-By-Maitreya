#!/usr/bin/env bash
# Post-deploy smoke test: API health over HTTPS, and a worker answering on each queue.
set -euo pipefail
: "${API_DOMAIN:?export API_DOMAIN=api.studio.example.com}"
curl -fsS "https://${API_DOMAIN}/health" && echo " api ok"
docker compose -f infra/compose.prod.yml exec -T worker-media celery -A worker.celery_app inspect ping -t 10 | grep -q pong && echo "workers ok"
docker compose -f infra/compose.prod.yml exec -T worker-media ffmpeg -hide_banner -version | head -1
docker compose -f infra/compose.prod.yml exec -T worker-media yt-dlp --version

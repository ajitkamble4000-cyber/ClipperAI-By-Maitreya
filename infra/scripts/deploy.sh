#!/usr/bin/env bash
# Pull the latest code and restart the stack with zero manual steps. Run from the repo root on the VPS.
set -euo pipefail
cd "$(dirname "$0")/../.."
git pull --ff-only
docker compose -f infra/compose.prod.yml --env-file .env build
# Workers finish/checkpoint their current step (stop_grace_period), jobs resume after restart.
docker compose -f infra/compose.prod.yml --env-file .env up -d --remove-orphans
docker image prune -f >/dev/null
docker compose -f infra/compose.prod.yml ps

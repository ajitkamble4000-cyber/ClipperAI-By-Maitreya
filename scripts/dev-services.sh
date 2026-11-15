#!/usr/bin/env bash
# Start every local dev service (idempotent): Docker daemon, Redis, S3 emulator, local Supabase.
set -uo pipefail
cd "$(dirname "$0")/.."
if ! docker info >/dev/null 2>&1; then
  (nohup dockerd >/tmp/dockerd.log 2>&1 &)
  for _ in $(seq 1 30); do docker info >/dev/null 2>&1 && break; sleep 1; done
fi
redis-cli ping >/dev/null 2>&1 || redis-server --daemonize yes --save '' >/dev/null
docker start ss-s3 >/dev/null 2>&1 || docker run -d --name ss-s3 -p 9090:9090 \
  -e COM_ADOBE_TESTING_S3MOCK_STORE_INITIAL_BUCKETS=shorts-studio adobe/s3mock:latest >/dev/null
export SUPABASE_INTERNAL_IMAGE_REGISTRY=docker.io
npx -y supabase@3.1.0 start --workdir infra >/dev/null 2>&1 || true
for _ in $(seq 1 60); do docker ps --format '{{.Names}} {{.Status}}' | grep -q "supabase_auth.*healthy" && break; sleep 2; done
docker ps --format '{{.Names}}: {{.Status}}'
redis-cli ping

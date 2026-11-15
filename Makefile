SUPABASE := npx -y supabase@3.1.0
export SUPABASE_INTERNAL_IMAGE_REGISTRY ?= docker.io

.PHONY: help dev-up dev-down supabase-start supabase-reset api worker beat web test test-py test-e2e lint
help:          ## Show targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

supabase-start: ## Start local Supabase (Postgres, Auth, Realtime, Mailpit)
	$(SUPABASE) start --workdir infra
supabase-reset: ## Re-apply all migrations to local Supabase
	$(SUPABASE) db reset --workdir infra
dev-up:        ## Start API + workers + Redis + S3 emulator in Docker
	docker compose -f infra/compose.yml up -d --build
dev-down:      ## Stop the Docker dev stack
	docker compose -f infra/compose.yml down

api:           ## Run the API locally (hot reload)
	cd api && ../.venv/bin/uvicorn app.main:app --reload --port 8000
worker:        ## Run a worker locally (all queues)
	PYTHONPATH=worker .venv/bin/celery -A worker.celery_app worker -Q media,ai,poll -c 2 -l INFO
beat:          ## Run the scheduler locally
	PYTHONPATH=worker .venv/bin/celery -A worker.celery_app beat -l INFO
web:           ## Run the web app
	cd web && npm run dev

test-py:       ## Python tests (needs local Supabase, Redis, S3)
	uv run pytest -q
test-e2e:      ## Browser tests
	cd web && npx next build && npx playwright test
test: test-py test-e2e
lint:
	uv run ruff check . && cd web && npm run lint && npx tsc --noEmit

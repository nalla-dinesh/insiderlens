# InsiderLens — dev task runner (Linux/macOS/WSL).
# Windows PowerShell users: equivalent raw commands are in README.md → Quickstart.
SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE := docker compose -f infra/docker-compose.yml

.PHONY: help dev dev-api dev-web db-up docker-up docker-down test test-api lint lint-api lint-web fmt ingest analyze

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' Makefile | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

dev: db-up ## Start DB + API (run `make dev-web` in a second terminal)
	@echo "→ API on http://localhost:8000 (docs: /docs). In another terminal: make dev-web"
	$(MAKE) dev-api

dev-api: ## FastAPI with hot reload on :8000
	cd apps/api && uvicorn app.main:create_app --factory --reload --port 8000

dev-web: ## Vite dev server on :5173
	cd apps/web && npm run dev

db-up: ## Postgres 16 in Docker (background)
	$(COMPOSE) up -d db

docker-up: ## Full stack in Docker (db + api)
	$(COMPOSE) up --build -d

docker-down: ## Stop all containers
	$(COMPOSE) down

test: test-api ## All tests

test-api: ## API test suite
	cd apps/api && python -m pytest -q

lint: lint-api lint-web ## All linters

lint-api:
	ruff check apps/api
	ruff format --check apps/api

lint-web:
	cd apps/web && npm run lint

fmt: ## Auto-format everything
	ruff check --fix apps/api || true
	ruff format apps/api
	cd apps/web && npx prettier --write "src/**/*.{ts,tsx,css}"

ingest: ## Load data/generated into Postgres (idempotent — safe to re-run)
	cd apps/api && python scripts/ingest.py

migrate: ## Alembic: build/refresh schema to latest revision
	cd apps/api && alembic upgrade head

analyze: ## (Phase 04) Run the full detection pipeline — not implemented yet
	@echo "analyze arrives in PHASE 04 (scoring pipeline)" && exit 0

# ---------------- Phase 08 ----------------
demo: ## Full stack in Docker (db+api+web on :8080)
	$(COMPOSE) up -d --build

demo-seed: ## Demo profile: full seed-42 bundle + analysis run (one-shot)
	$(COMPOSE) --profile demo up -d --build
	@docker logs -f insiderlens-seeder

demo-local: ## No-Docker fallback (verify yourself): three terminals as in README
	@echo "Run: db (docker/self-host) → api (uvicorn :8000) → web (npm run dev :5173)"
	@echo "Then: python3 -m generator build --days 60 --seed 42 --out data/generated"
	@echo "      curl -X POST http://localhost:8000/api/ingest"
	@echo "      curl -X POST http://localhost:8000/api/analysis/run"

ci-local: ## Mimic every CI job locally (proves ci.yml before push)
	cd apps/api && ruff check . ../../scripts && pytest -q
	cd apps/web && npm ci && npm run lint && npm run build
	@echo "docker-build job: build apps/api/Dockerfile + apps/web/Dockerfile manually (see docs)"

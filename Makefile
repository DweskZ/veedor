.PHONY: setup lint test lake signals serve db-up db-migrate up down logs smoke bundle obs-up obs-verify

setup:
	uv sync

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

test:
	uv run pytest

lake:
	uv run veedor lake build

signals:
	uv run veedor signals build

serve:
	uv run veedor serve --reload

db-up:
	docker compose up -d --wait db

db-migrate:
	uv run alembic upgrade head

# Full local stack: db, migrations, api (:8000) and web (:3000).
up:
	docker compose up -d --build --wait

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

# Needs the stack from `make up`. Writes nothing: it checks that an anonymous review write is refused.
smoke:
	python3 scripts/smoke_test.py

# Deployment data bundle (dist/veedor-data-<date>.tar.gz + manifest).
bundle:
	scripts/build_data_bundle.sh

# Observability stack (Grafana http://localhost:3001, OTLP :4318); see docs/OBSERVABILITY.md.
obs-up:
	docker compose up -d --build --wait observability api

# Generates traffic, then asserts the spans and metric series exist in Tempo and Prometheus.
obs-verify:
	uv run python scripts/generate_traffic.py
	uv run python scripts/verify_telemetry.py

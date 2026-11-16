.PHONY: setup lint test lake signals serve db-up db-migrate up down logs smoke bundle

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

# Needs the stack from `make up`; creates and deletes one review row.
smoke:
	python3 scripts/smoke_test.py

# Deployment data bundle (dist/veedor-data-<date>.tar.gz + manifest).
bundle:
	scripts/build_data_bundle.sh

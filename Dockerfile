# syntax=docker/dockerfile:1
# Veedor API image. Two stages: dependencies and package are installed into /app/.venv with a
# frozen lockfile, then only the virtualenv and the migrations are copied to a clean runtime.

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim AS runtime
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 VEEDOR_DATA_DIR=/app/data
RUN groupadd --system --gid 10001 veedor \
 && useradd --system --uid 10001 --gid veedor --home-dir /app --shell /usr/sbin/nologin veedor \
 && mkdir -p /app/data/lake /app/data/marts /app/data/dossiers /app/data/traces \
 && chown veedor:veedor /app/data/dossiers /app/data/traces
WORKDIR /app
COPY --from=build --chown=veedor:veedor /app/.venv ./.venv
COPY --chown=veedor:veedor alembic ./alembic
COPY --chown=veedor:veedor alembic.ini ./
USER veedor
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)"]
CMD ["uvicorn", "veedor.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

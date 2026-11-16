"""Application settings, read from environment variables and `.env`."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VEEDOR_", env_file=".env", extra="ignore")

    data_dir: Path = REPO_ROOT / "data"
    database_url: str = "postgresql+psycopg://veedor:veedor_dev@localhost:5433/veedor"

    # LLM is optional. With no provider configured, dossiers use deterministic templates.
    llm_provider: str | None = None  # e.g. "openai", "anthropic", "groq"
    llm_model: str | None = None
    llm_api_key: str | None = None

    cors_origins: list[str] = ["http://localhost:3000"]

    # Human reviews are off by default; writing needs the flag AND a bearer token.
    reviews_enabled: bool = False
    reviews_token: str | None = None
    # Interactive API docs (/docs) and /openapi.json.
    docs_enabled: bool = True

    # Read-side performance (docs/DEPLOYMENT.md, "Performance").
    lake_threads: int = Field(default=2, ge=1, le=64)  # DuckDB threads per API process
    api_workers: int = Field(default=2, ge=1, le=16)  # uvicorn worker processes (`veedor serve`)

    # OpenTelemetry is off unless an OTLP/HTTP base URL is set (e.g. http://localhost:4318).
    otel_endpoint: str | None = None
    otel_service_name: str = "veedor-api"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def lake_dir(self) -> Path:
        return self.data_dir / "lake"

    @property
    def marts_dir(self) -> Path:
        return self.data_dir / "marts"

    @property
    def ocds_bulk_path(self) -> Path:
        return self.raw_dir / "sercop_ocds_full.jsonl.gz"


@lru_cache
def get_settings() -> Settings:
    return Settings()

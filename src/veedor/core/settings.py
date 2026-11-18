"""Application settings, read from environment variables and `.env`."""

from __future__ import annotations

from functools import lru_cache
from ipaddress import IPv4Network, IPv6Network, ip_network
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


def parse_exempt_networks(values: list[str] | tuple[str, ...]) -> tuple[IPv4Network | IPv6Network, ...]:
    """Parse the read-rate exemption list; raises ValueError for anything that could exempt more than meant.

    Each entry must be a canonical address or network: `10.77.88.20/8` (host bits set, which a lenient parser
    would silently widen to 10.0.0.0/8) is rejected, and so is a catch-all network (`0.0.0.0/0`, `::/0`).
    """
    networks: list[IPv4Network | IPv6Network] = []
    for value in values:
        network = ip_network(value, strict=True)  # ValueError on host bits set or a malformed value
        if network.prefixlen == 0:
            raise ValueError(f"{value!r} would exempt every client")
        networks.append(network)
    return tuple(networks)


class Settings(BaseSettings):
    # env_ignore_empty: compose passes `${VAR:-}` (empty when unset); an empty value is read as unset.
    model_config = SettingsConfigDict(
        env_prefix="VEEDOR_", env_file=".env", extra="ignore", env_ignore_empty=True
    )

    data_dir: Path = REPO_ROOT / "data"
    database_url: str = "postgresql+psycopg://veedor:veedor_dev@localhost:5433/veedor"

    # LLM is optional. With no provider configured, dossiers use deterministic templates.
    llm_provider: str | None = None  # e.g. "openai", "anthropic", "groq"
    llm_model: str | None = None
    llm_api_key: str | None = None

    # Question answering over one process (`POST /processes/{ocid}/ask`): the only route that may reach a
    # language model. Off by default (404). Enabled without a key or with the daily budget spent, it answers
    # by retrieval only. Limits are per API worker process (docs/SECURITY.md, "Question answering").
    ask_enabled: bool = False
    ask_daily_budget: int = Field(default=300, ge=0, le=1_000_000)  # model calls per UTC day, all workers
    # Per client IP and worker. The strict pair applies while a model can be called (it costs money);
    # retrieval-only answers cost nothing, so visitors clicking the suggested questions get the generous pair.
    ask_rate_per_minute: int = Field(default=4, ge=1, le=600)
    ask_rate_per_hour: int = Field(default=30, ge=1, le=100_000)
    ask_retrieval_rate_per_minute: int = Field(default=20, ge=1, le=6_000)
    ask_retrieval_rate_per_hour: int = Field(default=200, ge=1, le=100_000)
    # With True the daily budget and the per-client counters live in the PostgreSQL database (table
    # `ask_usage`, migration 0003) and are shared by every worker and kept across restarts; the in-memory
    # counters remain as the fallback when the database is unreachable. Off by default (the API then needs
    # no database).
    ask_usage_shared: bool = False
    ask_max_output_tokens: int = Field(default=160, ge=16, le=1_000)
    ask_timeout_seconds: float = Field(default=15.0, gt=0, le=120)

    # Quotes from the process's own published text (`GET /processes/{ocid}/quotes`, and the quotes attached to
    # an answer of `/ask`). Off by default: with the flag off the route is a 404 and no answer has a quote.
    # The screens are heuristics with a measured, non-zero residual (docs/QUOTES.md), so publishing them is a
    # decision of the operator, not a default.
    quotes_enabled: bool = False

    cors_origins: list[str] = ["http://localhost:3000"]

    # Per client IP and worker limit on anonymous GET routes under /api/v1 (never /health). The general limit
    # counts every read; the search limit also counts requests carrying a non-blank `q` (a text search over
    # the lake). 0 switches that limit off. In memory, per worker, reset on restart (docs/SECURITY.md).
    # The defaults are OFF so that `veedor serve` and the Next.js dev server (whose server-side renders share
    # 127.0.0.1 with the browser) work out of the box. A public deployment must set them explicitly:
    # deploy/compose.prod.yml does (240 and 60). The API logs a warning at start while a limit is off.
    read_rate_per_minute: int = Field(default=0, ge=0, le=100_000)
    read_search_rate_per_minute: int = Field(default=0, ge=0, le=100_000)
    # Client addresses or canonical networks never counted. Empty by default and empty in production: the
    # web container's server-side calls are counted against the visitor's address, not exempted. Matched
    # against the client address the API resolves, never against a request header. Invalid, non-canonical
    # (host bits set) and catch-all entries stop the API at start.
    read_rate_exempt: list[str] = []
    # Most client addresses each read limiter tracks. When it is reached, expired addresses are dropped first
    # and then the least recently active one (its count restarts), so a flood of addresses cannot grow
    # memory or lock real visitors out. Bound: about this many x the limit x 40 bytes per limiter.
    read_rate_max_keys: int = Field(default=5_000, ge=100, le=1_000_000)

    # Glossary served by `GET /glossary`: one JSON file written by the web team (content owner).
    glossary_path: Path = REPO_ROOT / "web" / "src" / "data" / "glossary.json"

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

    @field_validator("read_rate_exempt")
    @classmethod
    def _valid_networks(cls, values: list[str]) -> list[str]:
        parse_exempt_networks(values)  # ValueError: a typo must not exempt nothing or everyone
        return values

    @property
    def model_configured(self) -> bool:
        """A provider, a model name and a key are all set (the key itself is never exposed)."""
        return bool(self.llm_provider and self.llm_model and self.llm_api_key)

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
    def texts_dir(self) -> Path:
        """Unmasked process texts (`veedor lake build-texts`). A sibling of `lake_dir`, not inside it: the
        compose stack mounts the lake and marts folders into the API container and must never mount this."""
        return self.data_dir / "texts"

    @property
    def ocds_bulk_path(self) -> Path:
        return self.raw_dir / "sercop_ocds_full.jsonl.gz"


@lru_cache
def get_settings() -> Settings:
    return Settings()

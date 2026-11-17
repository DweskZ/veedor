"""Builds the question-answering service. One of the only two modules of the API that may reach a model.

The route `POST /processes/{ocid}/ask` is the only route allowed to call a language model (docs/SECURITY.md).
`tests/api/test_ask_boundary.py` fails if any other module under `veedor/api` imports the LLM adapters, and
calls every other route with a spy on the model clients to show none of them reaches one.
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache

from veedor.agents.qa.selector import ModelSelector
from veedor.api.deps import get_reader
from veedor.core.settings import Settings, get_settings
from veedor.domain.qa.selection import DEFAULT_THRESHOLDS
from veedor.infrastructure.investigations.store import InvestigationStore
from veedor.infrastructure.lake.evidence_reader import EvidenceReader
from veedor.infrastructure.llm.structured import build_structured_model
from veedor.infrastructure.qa.embedding_cache import CachedEmbedder
from veedor.infrastructure.telemetry import record_ask, record_llm_usage, register_vocabulary
from veedor.use_cases.ask import AskService, DailyBudget
from veedor.use_cases.queries.ask_context import ApiContextLoader

logger = logging.getLogger(__name__)

register_vocabulary(
    mode=["retrieval", "model"],
    outcome=["answered", "no_evidence", "judgement", "person", "instruction", "unverified"],
)


def per_worker_budget(settings: Settings) -> int:
    """The daily budget is global; without the shared counter each worker process counts its own share, so the
    total never exceeds it (and a restart resets the count). With the shared counter this is only the fallback
    used while the database is unreachable."""
    if settings.ask_daily_budget <= 0:
        return 0
    return max(settings.ask_daily_budget // settings.api_workers, 1)


def usage_store(settings: Settings):  # noqa: ANN201
    """The shared counters in the API database, or None when `VEEDOR_ASK_USAGE_SHARED` is off."""
    if not settings.ask_usage_shared:
        return None
    from veedor.infrastructure.db.session import get_engine
    from veedor.infrastructure.db.usage import AskUsageStore

    return AskUsageStore(get_engine())


def _embedder() -> object:
    from veedor.infrastructure.vectors.embedding import FastEmbedEmbedder

    return FastEmbedEmbedder(local_files_only=True)


def _observe(answer, duration_ms: float) -> None:  # noqa: ANN001
    record_ask(answer.mode, answer.reason.value, answer.grounded)
    if answer.model_calls:
        record_llm_usage(settings_model_name(), answer.prompt_tokens, answer.completion_tokens)


def settings_model_name() -> str:
    return get_settings().llm_model or "other"


def _budget(settings: Settings) -> DailyBudget:
    store = usage_store(settings)
    if store is None:
        return DailyBudget(per_worker_budget(settings))
    return DailyBudget(settings.ask_daily_budget, store=store, fallback_limit=per_worker_budget(settings))


def build_service(settings: Settings, lake) -> AskService:  # noqa: ANN001
    reader = EvidenceReader(settings.lake_dir, settings.marts_dir)
    store = InvestigationStore(settings.data_dir / "investigations")

    def stored_facts(ocid: str):  # noqa: ANN202
        try:
            record = store.load(ocid)
        except ValueError:
            return None
        return record.facts if record is not None and record.withheld is None else None

    model = build_structured_model(settings)
    return AskService(
        loader=ApiContextLoader(lake, reader.load, stored_facts, lambda: get_settings().quotes_enabled),
        embedder=CachedEmbedder(_embedder),  # type: ignore[arg-type]
        selector=ModelSelector(model) if model is not None else None,
        thresholds=DEFAULT_THRESHOLDS,
        budget=_budget(settings),
        observer=_observe,
    )


@lru_cache
def get_ask_service() -> AskService:
    started = time.perf_counter()
    service = build_service(get_settings(), get_reader())
    logger.info("ask service ready in %.0f ms, model=%s", (time.perf_counter() - started) * 1000,
                "yes" if service.selector is not None else "no")
    return service

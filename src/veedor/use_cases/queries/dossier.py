"""Dossier retrieval for the public API.

Investigator traces are for CLI runs: the API builds without writing them.

The API never spends LLM credits: it always asks for a template-mode service, whatever
`VEEDOR_LLM_*` says (LLM dossiers come from the CLI). `build_dossier` caches every dossier it builds,
so the API bounds that cache: once `MAX_API_CACHED_DOSSIERS` files exist, a dossier built for an
anonymous request is returned but not kept.
"""

from __future__ import annotations

import logging
import os
from importlib import import_module
from typing import Any

from veedor.core.settings import get_settings
from veedor.domain.masking import mask_payload
from veedor.use_cases.queries.ports import DossierUnavailableError, LakePort, NotFoundError
from veedor.use_cases.queries.processes import name_context, process_exists

logger = logging.getLogger(__name__)

_BUILDER_MODULE = "veedor.use_cases.build_dossier"
MAX_API_CACHED_DOSSIERS = 5000


def _cache_is_full() -> bool:
    directory = get_settings().data_dir / "dossiers"
    try:
        with os.scandir(directory) as entries:
            return sum(1 for _ in entries) >= MAX_API_CACHED_DOSSIERS
    except FileNotFoundError:
        return False


def get_dossier(lake: LakePort, ocid: str) -> dict[str, Any]:
    if not process_exists(lake, ocid):
        raise NotFoundError("process", ocid)
    try:
        module = import_module(_BUILDER_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name != _BUILDER_MODULE:
            raise
        raise DossierUnavailableError("The dossier builder is not available yet.") from exc
    cache_file = get_settings().data_dir / "dossiers" / f"{ocid}.json"
    keep = cache_file.is_file() or not _cache_is_full()
    try:
        dossier = module.default_service(use_llm=False, write_traces=False).build(ocid)
    except Exception as exc:  # any builder failure is a controlled 503, never a 500
        logger.exception("Dossier build failed for %s", ocid)
        raise DossierUnavailableError("The dossier could not be built.") from exc
    if not keep:
        cache_file.unlink(missing_ok=True)
    content = dossier.model_dump(mode="json") if hasattr(dossier, "model_dump") else dict(dossier)
    persons, protected = name_context(lake, ocid)
    return mask_payload(content, persons, protected)

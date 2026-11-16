"""Build (and cache) the dossier of one process."""

from __future__ import annotations

import re
from pathlib import Path

from veedor.agents.investigator.runner import InvestigatorAgent
from veedor.core.settings import get_settings
from veedor.domain.dossier.models import Dossier
from veedor.domain.dossier.version import RENDERER_VERSION
from veedor.infrastructure.lake.evidence_reader import EvidenceReader
from veedor.infrastructure.llm.factory import build_chat_model
from veedor.infrastructure.llm.port import ChatModelPort

_SAFE_OCID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,200}$")


class DossierService:
    """Cache-aware dossier builder with injectable collaborators (tests use fakes)."""

    def __init__(
        self,
        *,
        reader: EvidenceReader,
        chat_model: ChatModelPort | None,
        dossiers_dir: Path,
        traces_dir: Path | None,
        config_dir: Path,
    ) -> None:
        self._dossiers_dir = dossiers_dir
        self._llm_enabled = chat_model is not None
        self._agent = InvestigatorAgent(
            loader=reader.load, chat_model=chat_model, trace_dir=traces_dir, config_dir=config_dir
        )

    def _path(self, ocid: str) -> Path:
        if not _SAFE_OCID.match(ocid):
            raise ValueError(f"Invalid ocid: {ocid!r}")
        return self._dossiers_dir / f"{ocid}.json"

    @staticmethod
    def _read_cache(path: Path) -> Dossier | None:
        try:
            return Dossier.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            return None  # corrupt cache entry: the caller rebuilds it

    def build(self, ocid: str, *, refresh: bool = False) -> Dossier:
        path = self._path(ocid)
        if not refresh and path.is_file():
            cached = self._read_cache(path)
            # A template-only service must not serve text that an LLM wrote earlier.
            current = cached is not None and cached.renderer_version == RENDERER_VERSION
            if current and (self._llm_enabled or cached.mode in ("template", "template_minimal")):
                return cached
        dossier = self._agent.run(ocid)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(dossier.model_dump_json(indent=2), encoding="utf-8")
        return dossier


def default_service(*, use_llm: bool = True, write_traces: bool = True) -> DossierService:
    settings = get_settings()
    return DossierService(
        reader=EvidenceReader(settings.lake_dir, settings.marts_dir),
        chat_model=build_chat_model(settings) if use_llm else None,
        dossiers_dir=settings.data_dir / "dossiers",
        traces_dir=settings.data_dir / "traces" if write_traces else None,
        config_dir=settings.data_dir / "config",
    )


def build_dossier(ocid: str) -> Dossier:
    """Return the cached dossier for `ocid`, generating it on demand.

    Raises `ProcessNotFoundError` when the ocid is not in the lake and `ValueError` for a malformed ocid.
    Uses the configured LLM when `VEEDOR_LLM_*` are set, otherwise the deterministic template.
    """
    return default_service().build(ocid)

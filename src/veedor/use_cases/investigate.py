"""Run investigations and store them. The HTTP API only reads what this module wrote."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from veedor.core.settings import Settings, get_settings
from veedor.domain.dossier.template import catalogue
from veedor.domain.dossier.version import RENDERER_VERSION
from veedor.domain.investigation.models import InvestigationRecord, ModelUsage
from veedor.infrastructure.investigations.store import InvestigationStore, PersonalDataError
from veedor.infrastructure.llm.port import ChatModelPort
from veedor.infrastructure.mcp.port import ToolBackend

DEFAULT_MODEL_CALL_CAP = 60


class InvestigationService:
    """Builds the graph once and investigates processes one after another (one writer, one session)."""

    def __init__(
        self,
        *,
        loader: Any,  # Callable[[str], EvidencePack | None]
        mcp: ToolBackend,
        lake_tools: Any,  # LakeTools
        chat_model: ChatModelPort | None,
        store: InvestigationStore,
        trace_dir: Path | None = None,
        config_dir: Path | None = None,
        model_call_cap: int | None = None,
        today: Any = date.today,
    ) -> None:
        from veedor.agents.investigation.chooser import Chooser
        from veedor.agents.investigation.supervisor import InvestigationPorts
        from veedor.agents.investigation.usage import MeteredChatModel, UsageMeter
        from veedor.agents.investigator.runner import InvestigatorAgent
        from veedor.infrastructure.investigations.backend import build_backend

        self.meter = UsageMeter(limit=model_call_cap)
        model = MeteredChatModel(chat_model, self.meter) if chat_model is not None else None
        ports = InvestigationPorts(
            backend=build_backend(mcp, lake_tools),
            chooser=Chooser(model, self.meter),
            meter=self.meter,
            key_index=lake_tools.buyer_key_index,
            today=today,
        )
        self._agent = InvestigatorAgent(
            loader=loader, chat_model=model, trace_dir=trace_dir, config_dir=config_dir, investigation=ports
        )
        self._store = store
        self._lake_tools = lake_tools

    def investigate(self, ocid: str) -> InvestigationRecord:
        self._store.path(ocid)  # rejects a malformed ocid before any work
        before = self.meter.snapshot()
        started = datetime.now(UTC)
        from veedor.agents.investigation import obs

        with obs.span("investigation", ocid=ocid):
            state = self._agent.run_state(ocid)
        pack = state["pack"]
        record = InvestigationRecord(
            ocid=ocid,
            started_at=started,
            finished_at=datetime.now(UTC),
            renderer_version=RENDERER_VERSION,
            specialists=state.get("inv_runs", []),
            tool_log=state.get("inv_log", []),
            facts_added=[f.id for f in catalogue(pack) if f.id.startswith("investigation.")],
            dossier=state["dossier"],
            model_usage=self.meter.delta(before),
        )
        try:
            self._store.save(record)
        except PersonalDataError:
            # A genuine hit must not crash the run: keep the audit trail (no identifiers), withhold the text.
            record = record.model_copy(
                update={"dossier": None, "facts_added": [], "withheld": "personal_data_guard"}
            )
            self._store.save(record)
        return record

    def close(self) -> None:
        self._lake_tools.close()


def build_service(
    settings: Settings | None = None,
    *,
    mcp: ToolBackend,
    use_llm: bool = True,
    model_call_cap: int | None = None,
) -> InvestigationService:
    from veedor.infrastructure.investigations.lake_tools import LakeTools
    from veedor.infrastructure.lake.evidence_reader import EvidenceReader
    from veedor.infrastructure.llm.factory import build_chat_model

    settings = settings or get_settings()
    return InvestigationService(
        loader=EvidenceReader(settings.lake_dir, settings.marts_dir).load,
        mcp=mcp,
        lake_tools=LakeTools(settings.lake_dir, settings.marts_dir),
        chat_model=build_chat_model(settings) if use_llm else None,
        store=InvestigationStore(settings.data_dir / "investigations"),
        trace_dir=settings.data_dir / "traces",
        config_dir=settings.data_dir / "config",
        model_call_cap=model_call_cap,
    )


@contextmanager
def live_backend(*, live: bool = True) -> Iterator[ToolBackend]:
    """The EcuDataMCP session (one per batch), or a backend whose every lookup is a recorded failure."""
    from veedor.infrastructure.mcp.ecudata_client import EcuDataMcpSession, UnavailableBackend

    if not live:
        yield UnavailableBackend()
        return
    with EcuDataMcpSession() as session:
        yield session


# --- read side ---------------------------------------------------------------------------------


def read_investigation(store: InvestigationStore, ocid: str) -> InvestigationRecord | None:
    """The stored record or None. Never runs an investigation, never calls a tool or a model."""
    return store.load(ocid)


# --- batch summary (counts only) ---------------------------------------------------------------


@dataclass
class BatchSummary:
    investigations: int = 0
    errors: int = 0
    withheld: int = 0
    specialists_dispatched: Counter[str] = field(default_factory=Counter)
    tool_calls: dict[str, Counter[str]] = field(default_factory=dict)
    facts_added: Counter[str] = field(default_factory=Counter)
    dossiers_passing_verification: int = 0
    dossier_modes: Counter[str] = field(default_factory=Counter)
    model: ModelUsage = field(default_factory=ModelUsage)

    def add(self, record: InvestigationRecord) -> None:
        self.investigations += 1
        self.specialists_dispatched.update(run.specialist for run in record.specialists)
        for call in record.tool_log:
            self.tool_calls.setdefault(call.tool, Counter())[call.outcome] += 1
        self.facts_added.update(record.facts_added)
        if record.dossier is None:
            self.withheld += 1
            return
        self.dossiers_passing_verification += int(record.dossier.grounding_report.passed)
        self.dossier_modes[record.dossier.mode] += 1

    def as_dict(self) -> dict[str, Any]:
        """Counts only: no names, no RUCs, no ocids."""
        return {
            "investigations": self.investigations,
            "errors": self.errors,
            "withheld_by_privacy_guard": self.withheld,
            "specialists_dispatched": dict(sorted(self.specialists_dispatched.items())),
            "tool_calls_by_tool_and_outcome": {
                tool: dict(sorted(outcomes.items())) for tool, outcomes in sorted(self.tool_calls.items())
            },
            "facts_added_by_type": dict(sorted(self.facts_added.items())),
            "dossiers_passing_verification": self.dossiers_passing_verification,
            "dossier_modes": dict(sorted(self.dossier_modes.items())),
            "model": {
                "model": self.model.model,
                "calls": self.model.calls,
                "prompt_tokens": self.model.prompt_tokens,
                "completion_tokens": self.model.completion_tokens,
                "invalid_choices": self.model.invalid_choices,
            },
        }


def run_batch(
    service: InvestigationService, ocids: Iterable[str], on_error: Any = None
) -> tuple[BatchSummary, list[InvestigationRecord]]:
    summary, records = BatchSummary(), []
    before = service.meter.snapshot()
    for ocid in ocids:
        try:
            record = service.investigate(ocid)
        except Exception as exc:  # noqa: BLE001 - keep the batch going, count the failure
            summary.errors += 1
            if on_error is not None:
                on_error(type(exc).__name__)
            continue
        summary.add(record)
        records.append(record)
    summary.model = service.meter.delta(before)
    return summary, records


def write_summary(path: Path, sections: dict[str, Any]) -> None:
    """Merge `sections` into the JSON summary file (a later run adds a key, it does not replace others)."""
    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            existing = {}
    existing.update(sections)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

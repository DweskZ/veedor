"""Build the vector index: compose privacy-safe text per process, embed it, store it.

Privacy: the text that is embedded (and hashed) has passed `safe_free_text`. When the description is
withheld (a party is masked, or masking found personal data) only the CPC description is embedded. The
raw description is never stored; the vector table has no text column.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Protocol

import numpy as np

from veedor.domain.masking import is_masked_party, is_natural_person, safe_free_text

MAX_TEXT_CHARS = 1_000  # the model reads at most 128 tokens; this only bounds tokenizer work
DEFAULT_CHUNK = 2_048  # unique texts embedded (and committed) per step
LOOKUP_WINDOW = 20_000  # records checked against the stored hashes per query round

STATUS_FULL = "cpc_and_description"
STATUS_WITHHELD = "cpc_only_description_withheld"
STATUS_NO_DESCRIPTION = "cpc_only_no_description"
STATUS_DESCRIPTION_ONLY = "description_only_no_cpc"
STATUS_NO_TEXT = "no_text"


@dataclass(frozen=True, slots=True)
class ProcessRecord:
    ocid: str
    year: int | None
    buyer_ruc: str | None
    buyer_name: str | None
    method: str | None
    award_total: float | None
    main_cpc: str | None
    cpc_description: str | None
    description: str | None
    parties: tuple[tuple[str | None, str], ...] = ()  # (ruc, name) of tenderers and awarded suppliers
    winner: tuple[str | None, str | None, str | None] | None = None  # (ruc, name, kind)


@dataclass(frozen=True, slots=True)
class PreparedText:
    record: ProcessRecord
    text: str
    content_hash: str
    status: str


class RecordSource(Protocol):
    def records(self, limit: int | None = None) -> Iterator[ProcessRecord]: ...


class VectorWriter(Protocol):
    def existing(self, ocids: Sequence[str]) -> dict[str, tuple[str, str]]: ...

    def upsert(self, rows: Sequence) -> None: ...


@dataclass(slots=True)
class Progress:
    done: int
    total: int
    elapsed: float


@dataclass(slots=True)
class BuildReport:
    records_seen: int = 0
    unchanged_skipped: int = 0
    records_embedded: int = 0
    unique_texts: int = 0
    statuses: Counter = field(default_factory=Counter)
    embed_seconds: float = 0.0
    wall_seconds: float = 0.0

    @property
    def texts_per_second(self) -> float:
        return self.unique_texts / self.embed_seconds if self.embed_seconds else 0.0

    @property
    def rows_per_second(self) -> float:
        return self.records_embedded / self.wall_seconds if self.wall_seconds else 0.0


# ------------------------------------------------------------------------------------ text


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


@lru_cache(maxsize=200_000)
def _masked_party(ruc: str | None, name: str, kind: str | None) -> bool:
    return is_masked_party(ruc, name, kind)


def compose_text(record: ProcessRecord, *, include_cpc: bool = True) -> tuple[str | None, str]:
    """Return ``(text, status)``: the privacy-safe text to embed, or ``None`` when there is none."""
    cpc = _clean(record.cpc_description) if include_cpc else ""
    description, withheld = _safe_description(record)
    parts = [p for p in (cpc, _clean(description)) if p]
    text = ". ".join(parts)[:MAX_TEXT_CHARS] if parts else None
    if text is None:
        return None, STATUS_NO_TEXT
    if not description:
        return text, STATUS_WITHHELD if withheld else STATUS_NO_DESCRIPTION
    return text, STATUS_FULL if cpc else STATUS_DESCRIPTION_ONLY


def _safe_description(record: ProcessRecord) -> tuple[str | None, bool]:
    if not record.description:
        return None, False
    parties = [(ruc, name, None) for ruc, name in record.parties]
    if record.winner and record.winner[1]:
        parties.append(record.winner)
    persons = [name for ruc, name, kind in parties if name and _masked_party(ruc, name, kind)]
    protected = [name for ruc, name, kind in parties if name and not _masked_party(ruc, name, kind)]
    if record.buyer_name and not is_natural_person(record.buyer_ruc):
        protected.append(record.buyer_name)
    winner_masked = bool(record.winner and record.winner[1]) and _masked_party(*record.winner)
    return safe_free_text(record.description, persons, withhold=winner_masked, protected_names=protected)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prepare(record: ProcessRecord, *, include_cpc: bool = True) -> PreparedText | None:
    text, status = compose_text(record, include_cpc=include_cpc)
    return None if text is None else PreparedText(record, text, content_hash(text), status)


# ----------------------------------------------------------------------------------- build


def build_vectors(
    source: RecordSource,
    embedder,
    store: VectorWriter,
    *,
    limit: int | None = None,
    chunk_size: int = DEFAULT_CHUNK,
    progress: Callable[[Progress], None] | None = None,
) -> BuildReport:
    """Embed every in-scope record whose text changed (or is new) and upsert it. Idempotent, resumable."""
    from veedor.infrastructure.vectors.repository import VectorRow  # row type of the pgvector adapter

    started = time.perf_counter()
    report = BuildReport()
    pending = _collect_pending(source, store, embedder.model_name, limit, report)
    groups: dict[str, list[PreparedText]] = {}
    for item in pending:
        groups.setdefault(item.content_hash, []).append(item)
    report.records_embedded = len(pending)
    report.unique_texts = len(groups)
    ordered = sorted(groups.values(), key=lambda g: len(g[0].text))  # similar lengths per batch: less padding
    done = 0
    for start in range(0, len(ordered), chunk_size):
        chunk = ordered[start : start + chunk_size]
        t0 = time.perf_counter()
        vectors = embedder.embed([group[0].text for group in chunk])
        report.embed_seconds += time.perf_counter() - t0
        store.upsert(
            [
                _row(item, embedder.model_name, vectors[index], VectorRow)
                for index, group in enumerate(chunk)
                for item in group
            ]
        )
        done += len(chunk)
        if progress:
            progress(Progress(done, len(ordered), time.perf_counter() - started))
    report.wall_seconds = time.perf_counter() - started
    return report


def _row(item: PreparedText, model: str, vector: np.ndarray, row_type):
    r = item.record
    return row_type(
        ocid=r.ocid, model=model, content_hash=item.content_hash, embedding=vector, year=r.year,
        buyer_ruc=r.buyer_ruc, method=r.method, award_total=r.award_total, main_cpc=r.main_cpc,
    )  # fmt: skip


def _collect_pending(
    source: RecordSource, store: VectorWriter, model: str, limit: int | None, report: BuildReport
) -> list[PreparedText]:
    pending: list[PreparedText] = []
    window: list[PreparedText] = []

    def flush() -> None:
        stored = store.existing([p.record.ocid for p in window])
        for item in window:
            if stored.get(item.record.ocid) == (item.content_hash, model):
                report.unchanged_skipped += 1
            else:
                pending.append(item)
                report.statuses[item.status] += 1
        window.clear()

    for record in source.records(limit):
        report.records_seen += 1
        prepared = prepare(record)
        if prepared is None:
            report.statuses[STATUS_NO_TEXT] += 1
            continue
        window.append(prepared)
        if len(window) >= LOOKUP_WINDOW:
            flush()
    flush()
    return pending

"""Extract the text a process publishes about itself from the SERCOP OCDS bulk file.

The open data carries no documents and no document links. It does carry three kinds of free text:

* ``tender.enquiries[].description``  a bidder's question,
* ``tender.enquiries[].answer``       the buying entity's answer,
* ``awards[].description``            the text attached to an award.

Each text becomes one row of ``process_texts.parquet``. The table holds unmasked source text, so it
stays under ``data/texts`` (outside the lake folder that compose mounts) and is never published or
mounted into the API container. It stores no author
name and no RUC: the only trace of the author is ``author_kind`` (question: bidder, answer and award
text: buying entity) and ``author_person``, a boolean saying the *asker* of an enquiry is a natural
person or an unidentified party (so the quote pipeline can drop that exchange without keeping a name).

Rules applied while extracting (counted, never silent):

* whitespace is collapsed and control characters are removed;
* a text is capped at `MAX_TEXT_CHARS` characters, cut at a word boundary, with ``truncated = true``;
* empty texts, texts without a letter and boilerplate-only texts (see `_BOILERPLATE`, `_POINTER`)
  are dropped;
* an exact duplicate (same kind, same accent- and case-folded text) inside one process is dropped.
"""

from __future__ import annotations

import gzip
import re
import time
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Collection
from pathlib import Path
from typing import Any

import orjson
import pyarrow as pa

from veedor.domain.dossier.text import norm
from veedor.domain.masking import is_masked_party
from veedor.infrastructure.ocds.flatten import BatchWriter, extract_ruc, iter_releases

MAX_TEXT_CHARS = 2_000  # the longest real enquiry is 1,500 characters; only a few award texts exceed 2,000

QUESTION = "enquiry_question"
ANSWER = "enquiry_answer"
AWARD_TEXT = "award_text"
KINDS = (QUESTION, ANSWER, AWARD_TEXT)
BIDDER = "oferente"
ENTITY = "entidad"

TEXT_SCHEMA = pa.schema(
    [
        ("ocid", pa.string()),
        ("kind", pa.string()),
        ("seq", pa.int32()),
        ("date", pa.string()),
        ("author_kind", pa.string()),
        ("text", pa.string()),
        ("source_field", pa.string()),
        ("truncated", pa.bool_()),
        ("author_person", pa.bool_()),
    ]
)

DROP_REASONS = ("empty", "no_letters", "boilerplate", "duplicate")

# Content-free formulas measured in the real file (docs/QUOTES.md): single words and stock phrases.
_BOILERPLATE = frozenset(
    {
        "aclaracion", "aclaraciones", "convalidacion", "convalidaciones", "si", "no", "ok", "na", "n a",
        "no aplica", "ninguno", "ninguna", "sin observaciones", "sin comentarios", "gracias", "saludos",
        "ver acta", "revisar acta", "revisar oficio", "acta", "oficio", "adjunto", "adjunta",
        "se acepta", "si se acepta", "no se acepta", "se adjunta", "se adjunta acta",
    }
)  # fmt: skip
# "se adjunta lo solicitado", "ver acta de preguntas, respuestas y aclaraciones": a pointer to a file
# that is not in the open data. Short (at most 9 words), no digits, opens with a pointer verb.
_POINTER = re.compile(
    r"^(?:estimad[oa]s? \w+ )?(?:se )?(?:adjunt\w+|ver|revisar|sirvase\w*|remitirse|remitase|favor revisar)\b"
    r".*\b(?:acta|oficio|anexo|archivo|adjunt\w*|convalid\w*|solicitad\w*|aclaraciones|pliegos?)\b"
)
_MAX_POINTER_WORDS = 9
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def clean_text(value: Any) -> str:
    """Control characters removed, every whitespace run collapsed to one space, ends trimmed."""
    if not isinstance(value, str):
        return ""
    return " ".join(_CONTROL.sub(" ", value).split())


def cap_text(text: str, limit: int = MAX_TEXT_CHARS) -> tuple[str, bool]:
    """Keep the whole text up to `limit` characters; longer text is cut at a word boundary."""
    if len(text) <= limit:
        return text, False
    cut = text[:limit]
    boundary = cut.rfind(" ")
    return (cut[:boundary] if boundary > limit // 2 else cut).rstrip(), True


def _has_letter(text: str) -> bool:
    return any(unicodedata.category(ch).startswith("L") for ch in text)


def drop_reason(text: str) -> str | None:
    """Why a cleaned text carries nothing worth keeping, or None."""
    if not text:
        return "empty"
    if not _has_letter(text):
        return "no_letters"
    key = norm(text)
    if key in _BOILERPLATE:
        return "boilerplate"
    words = key.split()
    if len(words) <= _MAX_POINTER_WORDS and not any(ch.isdigit() for ch in key) and _POINTER.match(key):
        return "boilerplate"
    return None


def _author_is_person(author: Any) -> bool:
    """The asker of an enquiry is a natural person or an unidentified party (name never stored)."""
    if not isinstance(author, dict):
        return False
    name = author.get("name") if isinstance(author.get("name"), str) else None
    if not name:
        return False
    return is_masked_party(extract_ruc(author.get("id")), name)


class _Collector:
    def __init__(self, ocid: str) -> None:
        self.ocid = ocid
        self.rows: list[dict[str, Any]] = []
        self.drops: Counter[str] = Counter()
        self._seen: set[tuple[str, str]] = set()

    def add(
        self,
        kind: str,
        seq: int,
        raw: Any,
        *,
        date: Any,
        author_kind: str,
        source_field: str,
        author_person: bool,
    ) -> None:
        if raw is None:
            return
        text = clean_text(raw)
        reason = drop_reason(text)
        if reason is None:
            key = (kind, norm(text))
            if key in self._seen:
                reason = "duplicate"
            else:
                self._seen.add(key)
        if reason is not None:
            self.drops[f"{kind}:{reason}"] += 1
            return
        capped, truncated = cap_text(text)
        self.rows.append(
            {
                "ocid": self.ocid,
                "kind": kind,
                "seq": seq,
                "date": date if isinstance(date, str) and date.strip() else None,
                "author_kind": author_kind,
                "text": capped,
                "source_field": source_field,
                "truncated": truncated,
                "author_person": author_person,
            }
        )


def extract_texts(release: dict[str, Any]) -> tuple[list[dict[str, Any]], Counter[str]]:
    """Text rows of one OCDS release plus a counter of what was dropped (``"<kind>:<reason>"``)."""
    ocid = release.get("ocid")
    if not isinstance(ocid, str) or not ocid:
        return [], Counter()
    collector = _Collector(ocid)
    tender = release.get("tender") if isinstance(release.get("tender"), dict) else {}
    enquiries = tender.get("enquiries")
    for index, enquiry in enumerate(enquiries if isinstance(enquiries, list) else []):
        if not isinstance(enquiry, dict):
            continue
        person = _author_is_person(enquiry.get("author"))
        base = f"tender.enquiries[{index}]"
        collector.add(
            QUESTION, index, enquiry.get("description"),
            date=enquiry.get("date"), author_kind=BIDDER,
            source_field=f"{base}.description", author_person=person,
        )  # fmt: skip
        collector.add(
            ANSWER, index, enquiry.get("answer"),
            date=enquiry.get("dateAnswered"), author_kind=ENTITY,
            source_field=f"{base}.answer", author_person=person,
        )  # fmt: skip
    awards = release.get("awards")
    for index, award in enumerate(awards if isinstance(awards, list) else []):
        if isinstance(award, dict):
            collector.add(
                AWARD_TEXT, index, award.get("description"),
                date=award.get("date"), author_kind=ENTITY,
                source_field=f"awards[{index}].description", author_person=False,
            )  # fmt: skip
    return collector.rows, collector.drops


def asker_person_names(path: Path, ocids: Collection[str]) -> dict[str, list[str]]:
    """Names of the enquiry askers who are natural persons or unidentified parties, per process, read from
    the bulk file for the given processes only. They are kept in memory for one run and never written: the
    quote builder needs them to withhold any passage that names such a person (the texts table keeps no
    author name)."""
    wanted = set(ocids)
    found: dict[str, list[str]] = defaultdict(list)
    with gzip.open(path, "rb") as handle:
        for line in handle:
            if b'"enquiries"' not in line:
                continue
            release = orjson.loads(line)
            ocid = release.get("ocid")
            if ocid not in wanted:
                continue
            enquiries = (release.get("tender") or {}).get("enquiries")
            for enquiry in enquiries if isinstance(enquiries, list) else []:
                author = enquiry.get("author") if isinstance(enquiry, dict) else None
                if _author_is_person(author):
                    found[ocid].append(author["name"].strip())
    return dict(found)


TEXTS_FILE = "process_texts.parquet"
SUMMARY_FILE = "process_texts_build.json"


class TextSink:
    """Streams text rows of releases into `process_texts.parquet` and keeps the counters."""

    def __init__(self, directory: Path, batch_size: int = 50_000) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / TEXTS_FILE
        self._tmp = self.path.with_suffix(".parquet.tmp")
        self._writer = BatchWriter(self._tmp, TEXT_SCHEMA, batch_size)
        self.releases = 0
        self.processes_with_text = 0
        self.drops: Counter[str] = Counter()
        self.kept: Counter[str] = Counter()
        self.truncated = 0
        self.author_person = 0

    def add(self, release: dict[str, Any]) -> None:
        rows, drops = extract_texts(release)
        self.releases += 1
        self.drops.update(drops)
        if rows:
            self.processes_with_text += 1
            self.kept.update(row["kind"] for row in rows)
            self.truncated += sum(1 for row in rows if row["truncated"])
            self.author_person += sum(1 for row in rows if row["author_person"])
            self._writer.extend(rows)

    def close(self) -> dict[str, Any]:
        """Finish the file (atomic rename, so a reader never sees a half-written table)."""
        self._writer.close()
        self._tmp.replace(self.path)
        return {
            "releases": self.releases,
            "rows": self._writer.count,
            "processes_with_text": self.processes_with_text,
            "rows_by_kind": {kind: self.kept.get(kind, 0) for kind in KINDS},
            "dropped": dict(sorted(self.drops.items())),
            "truncated_rows": self.truncated,
            "rows_with_person_asker": self.author_person,
            "max_text_chars": MAX_TEXT_CHARS,
            "bytes": self.path.stat().st_size,
        }

    def abort(self) -> None:
        self._writer.close()
        self._tmp.unlink(missing_ok=True)


def build_texts(source: Path, texts_dir: Path, limit: int | None = None) -> dict[str, Any]:
    """One pass over the bulk file that writes only `process_texts.parquet` (into `texts_dir`)."""
    sink = TextSink(texts_dir)
    started = time.perf_counter()
    try:
        for index, release in enumerate(iter_releases(source)):
            if limit is not None and index >= limit:
                break
            sink.add(release)
    except BaseException:
        sink.abort()
        raise
    summary = sink.close()
    summary["seconds"] = round(time.perf_counter() - started, 1)
    (texts_dir / SUMMARY_FILE).write_bytes(orjson.dumps(summary, option=orjson.OPT_INDENT_2))
    return summary

"""`GET /processes/{ocid}/quotes`: stored quotes, checked again at the boundary.

One bound ``SELECT ... WHERE ocid = ?`` per table, never a scan of the lake. The quotes were screened when
the mart was built; here every stored passage goes through the same eligibility pipeline again with the
process's current person names (defence in depth). A passage that fails now is dropped and counted.
"""

from __future__ import annotations

from typing import Any

from veedor.domain.quotes.lexicon import Lexicon
from veedor.domain.quotes.screen import PERSONAL, check_passage
from veedor.domain.signals import SIGNALS_BY_CODE
from veedor.use_cases.queries._cache import VersionedCache
from veedor.use_cases.queries.catalogue import signal_label
from veedor.use_cases.queries.ports import LakePort, LakeUnavailableError, NotFoundError
from veedor.use_cases.queries.processes import name_context, process_exists

QUOTES_TABLE = "process_quotes"
STATS_TABLE = "process_quote_stats"
VOCABULARY_TABLE = "person_name_tokens"
LEXICON_TABLE = "quote_lexicon"

_QUOTES_SQL = (
    "SELECT rank, kind, text, date, author_kind, source_field, related_signal, similarity, truncated, "
    "pair_text, pair_kind, pair_source_field, pair_truncated FROM process_quotes WHERE ocid = ? ORDER BY rank"
)
_STATS_SQL = (
    "SELECT available_total, excluded_personal, excluded_unsafe, below_floor "
    "FROM process_quote_stats WHERE ocid = ?"
)
_CACHE = VersionedCache(max_entries=2_048)
_VOCABULARY = VersionedCache(max_entries=2)
_LEXICON = VersionedCache(max_entries=2)


def get_process_quotes(lake: LakePort, ocid: str) -> dict[str, Any]:
    missing = [t for t in (QUOTES_TABLE, STATS_TABLE, LEXICON_TABLE) if not lake.has_table(t)]
    if missing:
        raise LakeUnavailableError(missing)
    if not process_exists(lake, ocid):
        raise NotFoundError("process", ocid)
    return _CACHE.get_or_compute(ocid, lake.data_version(), lambda: _compute(lake, ocid))


def _vocabulary(lake: LakePort) -> frozenset[str]:
    """Person-name tokens of the build, read once per data build. The table is optional: the public data
    bundle does not ship it (docs/SECURITY.md), and the mart was already screened with it when it was built,
    so without it the boundary applies every other screen and the name net only at build time."""

    def load() -> frozenset[str]:
        if not lake.has_table(VOCABULARY_TABLE):
            return frozenset()
        rows = lake.fetch("SELECT token FROM person_name_tokens", [], tables=(VOCABULARY_TABLE,))
        return frozenset(row["token"] for row in rows)

    return _VOCABULARY.get_or_compute("vocabulary", lake.data_version(), load)


def _lexicon(lake: LakePort) -> Lexicon:
    """Institutional and ordinary words of the build, read once per data build. Required: the deny-by-default
    screen cannot run without it, and a mart without it is refused (503), never served unscreened."""

    def load() -> Lexicon:
        rows = lake.fetch("SELECT token, form FROM quote_lexicon", [], tables=(LEXICON_TABLE,))
        return Lexicon(
            capitalised=frozenset(r["token"] for r in rows if r["form"] == "capitalised"),
            lowercase=frozenset(r["token"] for r in rows if r["form"] == "lowercase"),
        )

    return _LEXICON.get_or_compute("lexicon", lake.data_version(), load)


def _compute(lake: LakePort, ocid: str) -> dict[str, Any]:
    rows = lake.fetch(_QUOTES_SQL, [ocid], tables=(QUOTES_TABLE,))
    stats = lake.fetch(_STATS_SQL, [ocid], tables=(STATS_TABLE,))
    stored = stats[0] if stats else {}
    omitted = {
        "personal_data": int(stored.get("excluded_personal") or 0),
        "unsafe": int(stored.get("excluded_unsafe") or 0),
        "below_relevance": int(stored.get("below_floor") or 0),
    }
    persons, protected = name_context(lake, ocid) if rows else ([], [])
    vocabulary = _vocabulary(lake) if rows else frozenset()
    lexicon = _lexicon(lake) if rows else Lexicon()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = _checked_item(row, persons, protected, vocabulary, lexicon, omitted)
        if item is not None:
            items.append(item)
    return {
        "ocid": ocid,
        "items": items,
        "available_total": int(stored.get("available_total") or 0),
        "omitted": omitted,
    }


def _count(omitted: dict[str, int], category: str | None) -> None:
    omitted["personal_data" if category == PERSONAL else "unsafe"] += 1


def _checked_item(
    row: dict[str, Any],
    persons: list[str],
    protected: list[str],
    vocabulary: frozenset[str],
    lexicon: Lexicon,
    omitted: dict[str, int],
) -> dict[str, Any] | None:
    verdict = check_passage(
        row["text"],
        person_names=persons,
        protected_names=protected,
        name_vocabulary=vocabulary,
        lexicon=lexicon,
    )
    if not verdict.eligible:
        _count(omitted, verdict.category)
        return None
    if row["related_signal"] not in SIGNALS_BY_CODE:
        omitted["unsafe"] += 1  # a code the catalogue does not know: the mart is out of step, show nothing
        return None
    pair = None
    if row.get("pair_text"):
        pair_verdict = check_passage(
            row["pair_text"],
            person_names=persons,
            protected_names=protected,
            name_vocabulary=vocabulary,
            lexicon=lexicon,
        )
        if pair_verdict.eligible:
            pair = {
                "kind": row["pair_kind"],
                "text": row["pair_text"],
                "source_field": row["pair_source_field"],
                "truncated": bool(row["pair_truncated"]),
            }
        else:
            _count(omitted, pair_verdict.category)
    return {
        "kind": row["kind"],
        "text": row["text"],
        "date": row["date"],
        "author_kind": row["author_kind"],
        "source_field": row["source_field"],
        "related_signal": row["related_signal"],
        "related_signal_label_es": signal_label(row["related_signal"]),
        "similarity": round(float(row["similarity"]), 4),
        "truncated": bool(row["truncated"]),
        "pair": pair,
    }

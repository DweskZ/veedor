"""Process listing and detail."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from veedor.domain.masking import (
    NATURAL_PERSON,
    is_masked_party,
    is_natural_person,
    kind_from_ruc,
    safe_free_text,
)
from veedor.domain.regions import SIN_REGION
from veedor.use_cases.queries.catalogue import signal_kind, signal_label
from veedor.use_cases.queries.ports import LakePort, NotFoundError, Row
from veedor.use_cases.queries.region_stats import region_raw_values

# Closed whitelist: request value -> constant SQL fragment. Nothing request-derived reaches the SQL text.
_NATURAL_BUYER = (
    "(buyer_ruc IS NOT NULL AND length(buyer_ruc) IN (10, 13) AND substr(buyer_ruc, 3, 1) IN "
    "('0', '1', '2', '3', '4', '5'))"
)
SORT_COLUMNS = {
    "risk_score": "risk_score",
    "n_signals": "n_signals",
    "award_total": "award_total",
    "year": "year",
    "anomaly_score": "anomaly_score",
    "buyer_name": f"CASE WHEN {_NATURAL_BUYER} THEN NULL ELSE buyer_name END",
    "ocid": "ocid",
}
_DIRECTIONS = {True: "DESC", False: "ASC"}
DEFAULT_SORT = "-risk_score"


class InvalidSortError(ValueError):
    def __init__(self, sort: str) -> None:
        self.sort = sort
        super().__init__(
            f"Invalid sort. Allowed: {', '.join(sorted(SORT_COLUMNS))} (prefix '-' for descending)."
        )


@dataclass(frozen=True, slots=True)
class ProcessFilters:
    year: int | None = None
    method: str | None = None
    buyer_ruc: str | None = None
    signal: str | None = None
    min_score: float | None = None
    q: str | None = None
    region: str | None = None  # canonical key of the buyer's province, or SIN_REGION


def parse_sort(sort: str) -> tuple[str, bool]:
    """Return ``(column, descending)`` for a whitelisted sort expression."""
    descending = sort.startswith("-")
    column = sort[1:] if sort[:1] in ("-", "+") else sort
    if column not in SORT_COLUMNS:
        raise InvalidSortError(sort)
    return column, descending


def _like_pattern(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _where(lake: LakePort, f: ProcessFilters) -> tuple[str, list[Any], tuple[str, ...]]:
    clauses: list[str] = []
    params: list[Any] = []
    tables = ["process_scores"]
    if f.year is not None:
        clauses.append("year = ?")
        params.append(f.year)
    if f.method:
        clauses.append("method = ?")
        params.append(f.method)
    if f.buyer_ruc:
        if kind_from_ruc(f.buyer_ruc) == NATURAL_PERSON:
            clauses.append("1 = 0")  # same answer as an unknown buyer: no confirmation for natural persons
        else:
            clauses.append("buyer_ruc = ?")
            params.append(f.buyer_ruc)
    if f.signal:
        clauses.append(
            "(list_contains(signal_codes, ?) OR list_contains(coalesce(context_signal_codes, []), ?))"
        )
        params += [f.signal, f.signal]
    if f.min_score is not None:
        clauses.append("risk_score >= ?")
        params.append(f.min_score)
    if f.region:
        clause, region_params = _region_clause(lake, f.region)
        clauses.append(clause)
        params += region_params
        tables.append("processes")
    if f.q:
        pattern = _like_pattern(f.q.strip())
        # Never the description or any party name: a caller must not find a process by a person's name.
        # Natural-person buyers are masked in responses, so their raw name is not searchable either.
        text_clauses = [
            "ocid ILIKE ? ESCAPE '\\'",
            f"(buyer_name ILIKE ? ESCAPE '\\' AND NOT {_NATURAL_BUYER})",
        ]
        params += [pattern, pattern]
        if lake.has_table("processes"):
            if "processes" not in tables:
                tables.append("processes")
            text_clauses.append(
                "ocid IN (SELECT ocid FROM processes WHERE process_code ILIKE ? ESCAPE '\\' "
                "OR main_cpc_description ILIKE ? ESCAPE '\\')"
            )
            params += [pattern, pattern]
        clauses.append("(" + " OR ".join(text_clauses) + ")")
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params, tuple(tables)


def _region_clause(lake: LakePort, key: str) -> tuple[str, list[Any]]:
    """Rows whose buyer's province is `key`: equality on the raw column values that mean that key
    (read from the lake once per data build), so no function runs over the whole column."""
    raw_values = region_raw_values(lake, key)
    conditions: list[str] = []
    params: list[Any] = []
    if raw_values:
        conditions.append("buyer_region IN (" + ", ".join("?" for _ in raw_values) + ")")
        params += raw_values
    if key == SIN_REGION:
        conditions.append("buyer_region IS NULL")
    if not conditions:
        return "1 = 0", []
    return "ocid IN (SELECT ocid FROM processes WHERE " + " OR ".join(conditions) + ")", params


def list_processes(
    lake: LakePort, filters: ProcessFilters, *, page: int, page_size: int, sort: str = DEFAULT_SORT
) -> dict[str, Any]:
    column, descending = parse_sort(sort)
    where, params, tables = _where(lake, filters)
    direction = _DIRECTIONS[descending]
    total = lake.fetch(f"SELECT count(*) AS n FROM process_scores{where}", params, tables=tables)[0]["n"]
    rows = lake.fetch(
        f"SELECT * FROM process_scores{where} "
        f"ORDER BY {SORT_COLUMNS[column]} {direction} NULLS LAST, ocid ASC LIMIT ? OFFSET ?",
        [*params, page_size, (page - 1) * page_size],
        tables=tables,
    )
    return {"items": rows, "page": page, "page_size": page_size, "total": total}


def get_process(lake: LakePort, ocid: str) -> dict[str, Any]:
    score = lake.fetch("SELECT * FROM process_scores WHERE ocid = ?", [ocid], tables=("process_scores",))
    facts = _one(lake, "processes", "SELECT * FROM processes WHERE ocid = ?", ocid)
    if not score and facts is None:
        raise NotFoundError("process", ocid)
    signals = lake.fetch(
        "SELECT signal_code AS code, value, threshold, evidence_json AS evidence, kind "
        "FROM process_signals WHERE ocid = ? ORDER BY signal_code",
        [ocid],
        tables=("process_signals",),
    )
    top = score[0] if score else None
    winner, tenderers, awards = _parties(lake, ocid, top)
    masked_names, protected = _name_context(winner, tenderers, awards, top, facts)
    winner_masked = bool(winner) and is_masked_party(winner["ruc"], winner["name"], winner.get("kind"))
    return {
        "ocid": ocid,
        "facts": _guard_description(facts, masked_names, winner_masked, protected),
        "score": top,
        "signals": [
            {**s, "label_es": signal_label(s["code"]), "kind": s.get("kind") or signal_kind(s["code"])}
            for s in signals
        ],
        "winner": winner,
        "tenderers": tenderers,
        "awards": awards,
    }


def _parties(lake: LakePort, ocid: str, top: Row | None) -> tuple[Row | None, list[Row], list[Row]]:
    winner = _winner(lake, top["winner_ruc"] if top else None, top)
    tenderers = _rows(
        lake,
        "tenderers",
        "SELECT DISTINCT supplier_ruc AS ruc, supplier_name AS name FROM tenderers WHERE ocid = ? ORDER BY 2",
        ocid,
    )
    awards = _rows(
        lake,
        "awards",
        "SELECT award_id, award_date, supplier_ruc, supplier_name, amount FROM awards "
        "WHERE ocid = ? ORDER BY award_id",
        ocid,
    )
    return winner, tenderers, awards


def _name_context(
    winner: Row | None, tenderers: list[Row], awards: list[Row], top: Row | None, facts: Row | None
) -> tuple[list[str], list[str]]:
    """Names to mask in free text (natural persons, unidentified) and names to leave alone (buyer,
    companies, public entities of this process)."""
    parties = [
        *([(winner["ruc"], winner["name"], winner.get("kind"))] if winner else []),
        *((t["ruc"], t["name"], None) for t in tenderers),
        *((a["supplier_ruc"], a["supplier_name"], None) for a in awards),
    ]
    persons = [name for ruc, name, kind in parties if name and is_masked_party(ruc, name, kind)]
    protected = [name for ruc, name, kind in parties if name and not is_masked_party(ruc, name, kind)]
    for source in (top, facts):
        if source and source.get("buyer_name") and not is_natural_person(source.get("buyer_ruc")):
            protected.append(source["buyer_name"])
    return persons, protected


def name_context(lake: LakePort, ocid: str) -> tuple[list[str], list[str]]:
    """``(person_names, protected_names)`` of a process, for masking free text and dossiers."""
    score = lake.fetch("SELECT * FROM process_scores WHERE ocid = ?", [ocid], tables=("process_scores",))
    top = score[0] if score else None
    facts = _one(lake, "processes", "SELECT * FROM processes WHERE ocid = ?", ocid)
    return _name_context(*_parties(lake, ocid, top), top, facts)


def _guard_description(
    facts: Row | None, person_names: list[str], withhold: bool, protected: list[str]
) -> Row | None:
    """Free text can name a person: withhold it when a party is masked or masking finds personal data."""
    if facts is None:
        return None
    text, withheld = safe_free_text(
        facts.get("description"), person_names, withhold=withhold, protected_names=protected
    )
    return {**facts, "description": text, "description_withheld": withheld}


def process_exists(lake: LakePort, ocid: str) -> bool:
    if lake.fetch(
        "SELECT 1 AS x FROM process_scores WHERE ocid = ? LIMIT 1", [ocid], tables=("process_scores",)
    ):
        return True
    return _one(lake, "processes", "SELECT ocid FROM processes WHERE ocid = ?", ocid) is not None


def _rows(lake: LakePort, table: str, sql: str, key: str) -> list[Row]:
    return lake.fetch(sql, [key], tables=(table,)) if lake.has_table(table) else []


def _one(lake: LakePort, table: str, sql: str, key: str) -> Row | None:
    rows = _rows(lake, table, sql, key)
    return rows[0] if rows else None


def _winner(lake: LakePort, ruc: str | None, score: Row | None) -> Row | None:
    if not ruc:
        name = score.get("winner_name") if score else None
        return {"ruc": None, "name": name, "kind": None} if name else None
    profile = _one(lake, "supplier_profiles", "SELECT * FROM supplier_profiles WHERE ruc = ?", ruc)
    if profile is not None:
        if is_masked_party(ruc, profile.get("name"), profile.get("kind")):
            # No behavioural profile for natural persons or unidentified parties: only the label.
            return {"ruc": ruc, "name": profile.get("name"), "kind": profile.get("kind")}
        return profile
    return {
        "ruc": ruc,
        "name": score.get("winner_name") if score else None,
        "kind": score.get("winner_kind") if score else None,
    }

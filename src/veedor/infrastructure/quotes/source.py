"""Reads flagged processes with their texts, signals and party names from the Parquet lake and marts.

Runs on the host only: `process_texts.parquet` holds unmasked text and is never mounted into the API.
"""

from __future__ import annotations

import itertools
import shutil
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import duckdb

from veedor.domain.masking import NATURAL_PERSON, kind_from_ruc
from veedor.domain.quotes.names import MIN_PERSONS, build_vocabulary, word_case_counts
from veedor.infrastructure.lake.connection import parquet_path, quote_literal
from veedor.infrastructure.ocds.texts import asker_person_names
from veedor.use_cases.build_quotes import ProcessBundle, TextRow, name_context

FETCH_SIZE = 20_000
VOCABULARY_SAMPLE = 200_000  # texts read to tell names from ordinary words
TEXTS_TABLE = "process_texts"
TMP_DIR = ".duckdb_tmp_quotes"  # spill folder of this reader only; removed when the reader closes


class MissingInputError(FileNotFoundError):
    """A table the selection needs is not built yet."""


_PARTIES_SQL = """
SELECT ocid, supplier_ruc AS ruc, supplier_name AS name, NULL AS kind FROM tenderers
UNION ALL
SELECT ocid, supplier_ruc, supplier_name, NULL FROM awards
UNION ALL
SELECT ocid, winner_ruc, winner_name, winner_kind FROM scores
"""


class LakeQuoteSource:
    def __init__(
        self,
        lake_dir: Path,
        marts_dir: Path,
        texts_dir: Path | None = None,
        *,
        raw_path: Path | None = None,
        memory_limit: str = "6GB",
    ) -> None:
        """`raw_path` is the OCDS bulk file: when given, the names of the natural-person enquiry askers are
        read from it (in memory only) and added to the names each passage of that process is checked
        against."""
        self._raw_path = raw_path
        self._texts_dir = texts_dir or lake_dir.parent / "texts"
        self._lake_dir = lake_dir
        self._marts_dir = marts_dir
        self._memory_limit = memory_limit

    def _connect(self) -> duckdb.DuckDBPyConnection:
        needed = {
            "process_texts": parquet_path(self._texts_dir, TEXTS_TABLE),
            "processes": parquet_path(self._lake_dir, "processes"),
            "tenderers": parquet_path(self._lake_dir, "tenderers"),
            "awards": parquet_path(self._lake_dir, "awards"),
            "signals": parquet_path(self._marts_dir, "process_signals"),
            "scores": parquet_path(self._marts_dir, "process_scores"),
        }
        missing = [str(path) for path in needed.values() if not path.is_file()]
        if missing:
            raise MissingInputError("missing input tables: " + ", ".join(missing))
        con = duckdb.connect(":memory:")
        con.execute(f"SET memory_limit = {quote_literal(self._memory_limit)}")
        tmp = self._marts_dir / TMP_DIR
        tmp.mkdir(parents=True, exist_ok=True)
        con.execute(f"SET temp_directory = {quote_literal(str(tmp))}")
        for name, path in needed.items():
            con.execute(f'CREATE VIEW "{name}" AS SELECT * FROM read_parquet({quote_literal(str(path))})')
        return con

    def name_vocabulary(self, min_persons: int = MIN_PERSONS) -> frozenset[str]:
        """Person-name tokens: natural-person party names, minus words the texts use in lower case."""
        con = self._connect()
        try:
            names = con.execute(
                "SELECT DISTINCT supplier_ruc, supplier_name FROM ("
                "SELECT supplier_ruc, supplier_name FROM tenderers "
                "UNION SELECT supplier_ruc, supplier_name FROM awards) WHERE supplier_name IS NOT NULL"
            ).fetchall()
            sample = con.execute(
                "SELECT text FROM process_texts "
                f"USING SAMPLE reservoir({VOCABULARY_SAMPLE} ROWS) REPEATABLE (42)"
            ).fetchall()
        finally:
            con.close()
            self._clean()
        persons = [name for ruc, name in names if ruc and kind_from_ruc(ruc) == NATURAL_PERSON]
        lower, capital = word_case_counts(text for (text,) in sample)
        return build_vocabulary(persons, lower, capital, min_persons=min_persons)

    def bundles(
        self, limit: int | None = None, ocids: Sequence[str] | None = None
    ) -> Iterator[ProcessBundle]:
        """Flagged processes that have a text, in ocid order (optionally only the given ocids)."""
        con = self._connect()
        try:
            yield from self._stream(con, limit, ocids)
        finally:
            con.close()
            self._clean()

    def _clean(self) -> None:
        shutil.rmtree(self._marts_dir / TMP_DIR, ignore_errors=True)

    def _stream(
        self, con: duckdb.DuckDBPyConnection, limit: int | None, ocids: Sequence[str] | None
    ) -> Iterator[ProcessBundle]:
        con.execute(
            "CREATE TABLE targets AS SELECT ocid FROM ("
            "SELECT DISTINCT ocid FROM signals) JOIN (SELECT DISTINCT ocid FROM process_texts) USING (ocid) "
            + ("WHERE list_contains(?, ocid) " if ocids is not None else "")
            + "ORDER BY ocid"
            + (f" LIMIT {int(limit)}" if limit else ""),
            [list(ocids)] if ocids is not None else [],
        )
        texts = self._rows(
            con.cursor(),
            "SELECT t.ocid, t.kind, t.seq, t.date, t.author_kind, t.text, t.source_field, t.truncated, "
            "t.author_person FROM process_texts t JOIN targets USING (ocid) ORDER BY t.ocid, t.kind, t.seq",
        )
        signals = self._rows(
            con.cursor(),
            "SELECT s.ocid, s.signal_code FROM signals s JOIN targets USING (ocid) ORDER BY s.ocid",
        )
        parties = self._rows(
            con.cursor(),
            f"SELECT p.* FROM ({_PARTIES_SQL}) p JOIN targets USING (ocid) WHERE p.name IS NOT NULL "
            "ORDER BY p.ocid",
        )
        buyers = self._rows(
            con.cursor(),
            "SELECT p.ocid, p.buyer_ruc, p.buyer_name FROM processes p JOIN targets USING (ocid) "
            "ORDER BY p.ocid",
        )
        askers = self._askers(con)
        grouped = [
            itertools.groupby(stream, key=lambda r: r["ocid"]) for stream in (texts, signals, parties, buyers)
        ]
        heads = [next(g, None) for g in grouped]
        # One cursor per stream: a DuckDB connection holds a single active result at a time.
        for (ocid,) in con.cursor().execute("SELECT ocid FROM targets ORDER BY ocid").fetchall():
            got: list[list[dict[str, Any]]] = []
            for index, g in enumerate(grouped):
                head = heads[index]
                if head is not None and head[0] == ocid:
                    got.append(list(head[1]))
                    heads[index] = next(g, None)
                else:
                    got.append([])
            yield _bundle(ocid, *got, askers.get(ocid, ()))

    def _askers(self, con: duckdb.DuckDBPyConnection) -> dict[str, list[str]]:
        if self._raw_path is None:
            return {}
        if not self._raw_path.is_file():
            raise MissingInputError(f"missing input file: {self._raw_path}")
        targets = [r[0] for r in con.cursor().execute("SELECT ocid FROM targets").fetchall()]
        return asker_person_names(self._raw_path, targets)

    @staticmethod
    def _rows(cursor: duckdb.DuckDBPyConnection, sql: str) -> Iterator[dict[str, Any]]:
        cursor.execute(sql)
        columns = [c[0] for c in cursor.description]
        while rows := cursor.fetchmany(FETCH_SIZE):
            for row in rows:
                yield dict(zip(columns, row, strict=True))


def _bundle(
    ocid: str,
    texts: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    parties: list[dict[str, Any]],
    buyers: list[dict[str, Any]],
    askers: Sequence[str] = (),
) -> ProcessBundle:
    buyer = buyers[0] if buyers else {}
    persons, protected = name_context(
        ((p["ruc"], p["name"], p["kind"]) for p in parties), buyer.get("buyer_ruc"), buyer.get("buyer_name")
    )
    return ProcessBundle(
        ocid=ocid,
        signals=tuple(sorted({s["signal_code"] for s in signals})),
        texts=tuple(
            TextRow(
                kind=t["kind"],
                seq=t["seq"],
                text=t["text"],
                date=t["date"],
                author_kind=t["author_kind"],
                source_field=t["source_field"],
                truncated=bool(t["truncated"]),
                author_person=bool(t["author_person"]),
            )
            for t in texts
        ),
        person_names=tuple(sorted({*persons, *askers})),
        protected_names=protected,
    )

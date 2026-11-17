"""Writes the two quotes marts atomically (a reader never sees a half-written file)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from veedor.domain.quotes.lexicon import Lexicon

QUOTES_TABLE = "process_quotes"
STATS_TABLE = "process_quote_stats"
VOCABULARY_TABLE = "person_name_tokens"
LEXICON_TABLE = "quote_lexicon"

QUOTES_SCHEMA = pa.schema(
    [
        ("ocid", pa.string()),
        ("rank", pa.int8()),
        ("kind", pa.string()),
        ("text", pa.string()),
        ("date", pa.string()),
        ("author_kind", pa.string()),
        ("source_field", pa.string()),
        ("related_signal", pa.string()),
        ("similarity", pa.float32()),
        ("truncated", pa.bool_()),
        ("pair_text", pa.string()),
        ("pair_kind", pa.string()),
        ("pair_source_field", pa.string()),
        ("pair_truncated", pa.bool_()),
    ]
)
STATS_SCHEMA = pa.schema(
    [
        ("ocid", pa.string()),
        ("available_total", pa.int32()),
        ("excluded_personal", pa.int32()),
        ("excluded_unsafe", pa.int32()),
        ("below_floor", pa.int32()),
        ("n_eligible", pa.int32()),
        ("n_quotes", pa.int8()),
    ]
)


VOCABULARY_SCHEMA = pa.schema([("token", pa.string())])
LEXICON_SCHEMA = pa.schema([("token", pa.string()), ("form", pa.string())])  # form: capitalised | lowercase


class ParquetQuoteSink:
    def __init__(self, marts_dir: Path) -> None:
        marts_dir.mkdir(parents=True, exist_ok=True)
        self._final = {
            name: marts_dir / f"{name}.parquet"
            for name in (QUOTES_TABLE, STATS_TABLE, VOCABULARY_TABLE, LEXICON_TABLE)
        }
        self._tmp = {name: path.with_suffix(".parquet.tmp") for name, path in self._final.items()}
        self._writers = {
            QUOTES_TABLE: pq.ParquetWriter(self._tmp[QUOTES_TABLE], QUOTES_SCHEMA, compression="zstd"),
            STATS_TABLE: pq.ParquetWriter(self._tmp[STATS_TABLE], STATS_SCHEMA, compression="zstd"),
        }
        self.rows = {QUOTES_TABLE: 0, STATS_TABLE: 0}

    def write_vocabulary(self, tokens: list[str]) -> None:
        """Person-name tokens used by the screen; the API applies the same list at its boundary."""
        pq.write_table(
            pa.Table.from_pylist([{"token": t} for t in tokens], schema=VOCABULARY_SCHEMA),
            self._tmp[VOCABULARY_TABLE],
            compression="zstd",
        )

    def write_lexicon(self, lexicon: Lexicon) -> None:
        """Institutional and ordinary words used by the deny-by-default screen (no person names)."""
        rows = [{"token": t, "form": "capitalised"} for t in sorted(lexicon.capitalised)]
        rows += [{"token": t, "form": "lowercase"} for t in sorted(lexicon.lowercase)]
        pq.write_table(
            pa.Table.from_pylist(rows, schema=LEXICON_SCHEMA), self._tmp[LEXICON_TABLE], compression="zstd"
        )

    def write(self, quotes: list[dict[str, Any]], stats: list[dict[str, Any]]) -> None:
        for name, rows, schema in (
            (QUOTES_TABLE, quotes, QUOTES_SCHEMA),
            (STATS_TABLE, stats, STATS_SCHEMA),
        ):
            if rows:
                self._writers[name].write_table(pa.Table.from_pylist(list(rows), schema=schema))
                self.rows[name] += len(rows)

    def close(self) -> None:
        for name, writer in self._writers.items():
            writer.close()
            self._tmp[name].replace(self._final[name])
        self._tmp[VOCABULARY_TABLE].replace(self._final[VOCABULARY_TABLE])
        self._tmp[LEXICON_TABLE].replace(self._final[LEXICON_TABLE])

    def abort(self) -> None:
        for name, writer in self._writers.items():
            writer.close()
            self._tmp[name].unlink(missing_ok=True)
        self._tmp[VOCABULARY_TABLE].unlink(missing_ok=True)
        self._tmp[LEXICON_TABLE].unlink(missing_ok=True)

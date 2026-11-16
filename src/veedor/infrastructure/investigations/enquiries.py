# ruff: noqa: E501
"""The `process_texts` tool: counts and dates of one process's own enquiries, from the stored texts.

Read-only and local. It reads `data/texts/process_texts.parquet`, which holds UNMASKED text and is never mounted
into the API container: this tool therefore runs only in the CLI investigation flow. What it returns are
numbers and nothing else (no text, no name, no author): the counts and dates the enquiries specialist turns into
facts. Topic counts use embedding similarity to the fixed descriptions in `domain.investigation.enquiry_topics`.
"""

from __future__ import annotations

import re
import statistics
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any, Protocol

import duckdb
import numpy as np

from veedor.domain.investigation.enquiry_topics import (
    MAX_PLAUSIBLE_ANSWER_DAYS,
    TOPIC_DESCRIPTIONS_ES,
    TOPIC_FLOOR,
    TOPIC_ORDER,
)

_OCID = re.compile(r"^ocds-[a-z0-9]{6}-[A-Za-z0-9._\-]{1,120}$")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}")
QUESTION, ANSWER = "enquiry_question", "enquiry_answer"
EMBED_CHARS = 1_000


class EmbedderPort(Protocol):
    def embed(self, texts: Sequence[str]) -> np.ndarray: ...


def _day(value: Any) -> date | None:
    text = str(value or "")[:10]
    if not _DAY.match(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


class EnquiryTool:
    def __init__(
        self, texts_dir: Path, embedder: EmbedderPort | None = None, floor: float = TOPIC_FLOOR
    ) -> None:
        self.texts_dir = texts_dir
        self._embedder = embedder
        self._floor = floor
        self._topics: np.ndarray | None = None
        self._con: duckdb.DuckDBPyConnection | None = None

    def _connection(self) -> duckdb.DuckDBPyConnection:
        if self._con is None:
            path = self.texts_dir / "process_texts.parquet"
            if not path.is_file():
                raise FileNotFoundError("process_texts")
            con = duckdb.connect(":memory:")
            escaped = str(path).replace("'", "''")
            con.execute(f'CREATE VIEW process_texts AS SELECT * FROM read_parquet(\'{escaped}\')')
            allowed = "'" + str(self.texts_dir.resolve()).replace("'", "''") + "'"
            con.execute(f"SET allowed_directories=[{allowed}]")
            con.execute("SET enable_external_access=false")
            con.execute("SET lock_configuration=true")
            self._con = con
        return self._con

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None

    def _embed(self, texts: list[str]) -> np.ndarray:
        if self._embedder is None:
            from veedor.infrastructure.vectors.embedding import FastEmbedEmbedder

            self._embedder = FastEmbedEmbedder()
        return self._embedder.embed(texts)

    def _topic_matrix(self) -> np.ndarray:
        if self._topics is None:
            self._topics = self._embed([TOPIC_DESCRIPTIONS_ES[t] for t in TOPIC_ORDER])
        return self._topics

    def process_texts(self, arguments: dict[str, Any]) -> dict[str, Any]:
        ocid, deadline, late_days = (arguments.get(k) for k in ("ocid", "deadline_day", "late_days"))
        if not (isinstance(ocid, str) and _OCID.match(ocid) and isinstance(late_days, int)):
            raise ValueError("invalid arguments")
        rows = (
            self._connection()
            .execute(
                "SELECT kind, seq, date, text FROM process_texts WHERE ocid = ? AND kind IN (?, ?) "
                "ORDER BY seq, kind",
                [ocid, QUESTION, ANSWER],
            )
            .fetchall()
        )
        questions = {int(seq): (_day(d), text) for kind, seq, d, text in rows if kind == QUESTION}
        answers = {int(seq): _day(d) for kind, seq, d, _ in rows if kind == ANSWER}
        return self._summarise(questions, answers, _day(deadline), late_days)

    def _summarise(
        self,
        questions: dict[int, tuple[date | None, str]],
        answers: dict[int, date | None],
        deadline: date | None,
        late_days: int,
    ) -> dict[str, Any]:
        answered = [seq for seq in questions if seq in answers]
        gaps = [
            (answers[seq] - questions[seq][0]).days  # type: ignore[operator]
            for seq in answered
            if questions[seq][0] is not None and answers[seq] is not None
        ]
        gaps = [g for g in gaps if 0 <= g <= MAX_PLAUSIBLE_ANSWER_DAYS]
        n_late = None
        if deadline is not None:
            n_late = sum(
                1 for d, _ in questions.values() if d is not None and 0 <= (deadline - d).days <= late_days
            )
        counts = self._topic_counts([text for _, text in questions.values()])
        return {
            "n_with_text": len(questions),
            "n_answered": len(answered),
            "n_dated_pairs": len(gaps),
            "median_days_to_answer": float(statistics.median(gaps)) if gaps else None,
            "max_days_to_answer": max(gaps) if gaps else None,
            "n_late": n_late,
            **{f"topic_{topic}": counts[topic] for topic in TOPIC_ORDER},
        }

    def _topic_counts(self, texts: list[str]) -> dict[str, int]:
        counts = dict.fromkeys(TOPIC_ORDER, 0)
        if not texts:
            return counts
        sims = self._embed([t[:EMBED_CHARS] for t in texts]) @ self._topic_matrix().T
        best, label = sims.max(axis=1), sims.argmax(axis=1)
        for score, index in zip(best, label, strict=True):
            if float(score) >= self._floor:
                counts[TOPIC_ORDER[int(index)]] += 1
        return counts

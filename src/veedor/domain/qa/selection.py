"""Ranking, retrieval-only selection and validation of a model's choice (pure)."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from veedor.domain.qa.answer import ANSWERING_REASONS, MODEL_REASONS

MAX_MODEL_CANDIDATES = 12
MAX_ANSWER_FACTS = 5
MAX_REPLY_CHARS = 4_000
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Thresholds:
    """Chosen on the tuning half of the evaluation sample (docs/EVALUATION.md); not a claim of quality."""

    floor: float = 0.20  # an intent is answered without a model when its fused score is at least this
    k: int = 2  # at most this many intents (their facts) without a model
    model_floor: float = 0.325  # below this fused score to every fact the model is not even asked
    candidates: int = MAX_MODEL_CANDIDATES
    quote_floor: float = 0.45
    max_quotes: int = 2
    # Intent retrieval (`domain.qa.ranking`): `floor` and `k` above mean "fused intent score" and "intents".
    e_lo: float = 0.30  # embedding cosine that maps to 0 in the fusion
    e_hi: float = 0.95  # embedding cosine that maps to 1
    lexical_weight: float = 0.6  # weight of the lexical score in the fusion (the rest is the embedding's)
    oos_margin: float = 0.10  # the winning intent must beat the "never answered" intent by this much
    absent_margin: float = 0.10  # ... and the best intent whose facts this process lacks by this much
    second_gap: float = 0.03  # with k > 1, a second intent within this of the winner is answered too
    # Words of the question that belong to no part of the domain (France, pizza, taxi) say it is about
    # something else, which one shared word ("capital", "precio") must not outweigh. With f the share of
    # foreign content words: f * foreign_oos is added (noisy-or) to the out-of-scope lexical score, and
    # every other intent's fused score is scaled by (1 - foreign_penalty * f).
    foreign_oos: float = 1.5
    foreign_penalty: float = 1.0

DEFAULT_THRESHOLDS = Thresholds()


def similarity_scores(query_vectors: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Best cosine similarity of each row of `matrix` to any query variant (vectors are unit length)."""
    if matrix.shape[0] == 0:
        return np.zeros(0, dtype=np.float32)
    return (matrix @ query_vectors.T).max(axis=1)


def top_indices(scores: Sequence[float], limit: int) -> list[int]:
    """Indices of the best scores, best first; ties keep the catalogue order."""
    order = sorted(range(len(scores)), key=lambda i: (-float(scores[i]), i))
    return order[:limit]


def retrieval_select(scores: Sequence[float], thresholds: Thresholds) -> list[int]:
    """Top-k facts whose similarity clears the floor (without a model)."""
    return [i for i in top_indices(scores, thresholds.k) if float(scores[i]) >= thresholds.floor]


# --- the model's choice ---------------------------------------------------------------------------


class ModelChoice(BaseModel):
    """The only shape a model reply may have. Any other key, type or value makes the reply invalid."""

    model_config = ConfigDict(extra="forbid", strict=True)

    answerable: bool
    fact_ids: list[str] = Field(max_length=2 * MAX_MODEL_CANDIDATES)
    reason: str


def choice_schema(candidate_ids: Sequence[str]) -> dict:
    """JSON schema handed to the provider: ids and reason are enumerations, nothing is free text."""
    return {
        "title": "seleccion_de_hechos",
        "description": "Hechos de la evidencia que responden la pregunta, elegidos por identificador.",
        "type": "object",
        "additionalProperties": False,
        "required": ["answerable", "fact_ids", "reason"],
        "properties": {
            "answerable": {"type": "boolean"},
            "fact_ids": {
                "type": "array",
                "maxItems": MAX_ANSWER_FACTS,
                "items": {"type": "string", "enum": list(candidate_ids)},
            },
            "reason": {"type": "string", "enum": list(MODEL_REASONS)},
        },
    }


@dataclass(frozen=True, slots=True)
class ChoiceResult:
    valid: bool
    answerable: bool = False
    fact_ids: tuple[str, ...] = ()
    discarded: int = 0  # ids that were not in the candidate set (or repeated)


INVALID = ChoiceResult(valid=False)


def _as_object(parsed: dict | None, text: str | None) -> dict | None:
    if isinstance(parsed, dict):
        return parsed
    if not text or len(text) > MAX_REPLY_CHARS:
        return None
    body = _FENCE.sub("", text.strip())
    if not (body.startswith("{") and body.endswith("}")):
        return None  # prose, or prose around an object: not a reply
    try:
        value = json.loads(body)
    except (ValueError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def validate_choice(parsed: dict | None, text: str | None, candidate_ids: Sequence[str]) -> ChoiceResult:
    """Validate a reply against the schema and the candidate set.

    Ids outside the set are discarded and counted. A reply that is not an object of exactly the schema's
    keys, has a reason outside the enumeration, says it answers but names no valid id, or contradicts
    itself (answerable with a reason that says there is nothing to answer) is invalid: the caller uses
    retrieval instead of trusting it.
    """
    value = _as_object(parsed, text)
    if value is None:
        return INVALID
    try:
        choice = ModelChoice.model_validate(value)
    except (ValidationError, RecursionError, ValueError):
        return INVALID
    if choice.reason not in MODEL_REASONS:
        return INVALID
    allowed = set(candidate_ids)
    kept: list[str] = []
    discarded = 0
    for fact_id in choice.fact_ids:
        if fact_id in allowed and fact_id not in kept:
            kept.append(fact_id)
        else:
            discarded += 1
    if choice.answerable != (choice.reason in ANSWERING_REASONS):
        return ChoiceResult(valid=False, discarded=discarded)
    if choice.answerable and not kept:
        return ChoiceResult(valid=False, discarded=discarded)
    return ChoiceResult(True, choice.answerable, tuple(kept[:MAX_ANSWER_FACTS]), discarded)

"""Parsing and screening of model output. Nothing returned by the model is ever executed."""

from __future__ import annotations

import json
import re

from pydantic import ValidationError

from veedor.agents.investigator.prompting import system_prompt
from veedor.agents.investigator.schema import LLMPlan
from veedor.domain.dossier.text import norm

_URL = re.compile(
    r"(?:https?://|ftp://|www\.|mailto:)\S+|\b[\w-]+(?:\.[\w-]+)*\.(?:com|net|org|ec|gob|edu|io|info)\b/?\S*",
    re.I,
)
_MD_LINK = re.compile(r"\[[^\]]*\]\([^)]*\)")
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)
_SHINGLE_WORDS = 8


class OutputRejected(ValueError):
    """The model output cannot be used; the message is safe to log and to show to the model."""


MAX_REPLY_CHARS = 20_000
MAX_NESTING = 8


def _max_depth(text: str) -> int:
    depth = deepest = 0
    for char in text:
        if char in "[{":
            depth += 1
            deepest = max(deepest, depth)
        elif char in "]}":
            depth -= 1
    return deepest


def parse_plan(raw: str) -> LLMPlan:
    """Parse a plan; any failure, including hostile size or nesting, is an invalid plan."""
    if len(raw) > MAX_REPLY_CHARS:
        raise OutputRejected("formato inválido: respuesta demasiado larga")
    text = _FENCE.sub("", raw.strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise OutputRejected("formato inválido: no es un objeto JSON")
    body = text[start : end + 1]
    if _max_depth(body) > MAX_NESTING:
        raise OutputRejected("formato inválido: anidamiento excesivo")
    try:
        return LLMPlan.model_validate(json.loads(body))
    except (json.JSONDecodeError, ValidationError, RecursionError, MemoryError, ValueError) as exc:
        raise OutputRejected("formato inválido: no cumple el esquema del plan") from exc


def contains_link(text: str) -> bool:
    return bool(_URL.search(text) or _MD_LINK.search(text))


def leaks_system_prompt(text: str) -> bool:
    """True if any run of eight consecutive words of the system prompt appears in `text`."""
    prompt_words = norm(system_prompt()).split()
    haystack = f" {norm(text)} "
    return any(
        f" {' '.join(prompt_words[i : i + _SHINGLE_WORDS])} " in haystack
        for i in range(len(prompt_words) - _SHINGLE_WORDS + 1)
    )


def _values(node: object) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [v for child in node.values() for v in _values(child)]
    if isinstance(node, list):
        return [v for child in node for v in _values(child)]
    return []


def screen(plan: LLMPlan) -> None:
    """Reject links and prompt leakage in any value of the plan (ids are validated against the catalogue)."""
    for value in _values(plan.model_dump()):
        if contains_link(value):
            raise OutputRejected("enlace o dirección web en la respuesta")
        if leaks_system_prompt(value):
            raise OutputRejected("la respuesta reproduce las instrucciones del sistema")

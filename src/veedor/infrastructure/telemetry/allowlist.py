"""Attribute allow-list: the single privacy gate for every span attribute and metric label.

Two layers, both enforced here and nowhere else:

1. A key that is not listed is dropped.
2. Each listed key has its own value rule:
   - closed vocabularies (tool, specialist, outcome, final_mode, mode, node, token_type,
     http.request.method, error.type): a value outside the set becomes the literal ``other``;
   - ``model``: the configured model name (or a dated/suffixed variant of it), ``fake``, or a
     registered name; anything else becomes ``other``;
   - ``ocid``: the exact shape of an open-contracting id, else dropped;
   - ``http.route``: ``unmatched`` or a lowercase route template, else dropped;
   - numbers: an int or float within the key's own range (counts, durations, tokens, status
     codes), else dropped; ``passed`` must be a bool.
   Nothing here logs a dropped value.

The vocabularies are not copied: tools, specialists and outcomes come from
``veedor.domain.investigation.vocab`` and the dossier modes from the ``Dossier`` model. What the
domain does not define (graph node names, extra exception classes, extra model names) is
registered by the owner with ``register_vocabulary``.
"""

from __future__ import annotations

import builtins
import math
import re
import threading
from collections.abc import Iterable
from typing import Any, get_args

OTHER = "other"
UNMATCHED_ROUTE = "unmatched"

_OCID = re.compile(r"ocds-[a-z0-9]{6}-[A-Za-z0-9._\-]{1,120}")
_ROUTE = re.compile(r"(/([a-z][a-z0-9_]*|\{[a-z_][a-z0-9_]*\}))+")
_VOCAB_ENTRY = re.compile(r"[a-z][a-z0-9_]{0,47}")
_EXCEPTION_ENTRY = re.compile(r"[A-Z][A-Za-z0-9_]{0,63}")
_ENTRY_SHAPE = {"error.type": _EXCEPTION_ENTRY, "model": re.compile(r"[A-Za-z0-9._:@\-]{1,64}")}
_MODEL_SUFFIX = re.compile(r"[A-Za-z0-9._:@\-]{0,32}")
_LONG_DIGIT_RUN = re.compile(r"\d{10,}")
MAX_SPAN_NAME = 64
MAX_MODEL = 64

HTTP_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "_OTHER"})

# Closed vocabularies that can be extended with register_vocabulary.
VOCAB_KEYS = frozenset(
    {"tool", "specialist", "outcome", "final_mode", "mode", "node", "token_type", "error.type", "model"}
)

# key -> (is_int, minimum, maximum)
NUMERIC_RANGES: dict[str, tuple[bool, float, float]] = {
    "attempt": (True, 0, 20),
    "n_signals": (True, 0, 1_000),
    "n_findings": (True, 0, 10_000),
    "n_tool_calls": (True, 0, 100),
    "n_dispatches": (True, 0, 100),
    "duration_ms": (False, 0, 3_600_000),
    "prompt_tokens": (True, 0, 10_000_000),
    "completion_tokens": (True, 0, 10_000_000),
    "http.response.status_code": (True, 100, 599),
}

# Low-cardinality keys only: these may become metric labels.
METRIC_LABELS: frozenset[str] = frozenset(
    {
        "final_mode",
        "mode",
        "specialist",
        "tool",
        "outcome",
        "model",
        "token_type",
        "passed",
        "http.request.method",
        "http.route",
        "http.response.status_code",
        "error.type",
    }
)

# Span attributes: the metric labels plus identifiers and counts that are fine on a single span.
SPAN_ATTRIBUTES: frozenset[str] = METRIC_LABELS | frozenset(
    {
        "ocid",
        "node",
        "attempt",
        "n_signals",
        "n_findings",
        "n_tool_calls",
        "n_dispatches",
        "duration_ms",
        "prompt_tokens",
        "completion_tokens",
    }
)

_lock = threading.Lock()
_vocab: dict[str, set[str]] | None = None


def _default_vocabulary() -> dict[str, set[str]]:
    vocab: dict[str, set[str]] = {key: set() for key in VOCAB_KEYS}
    vocab["token_type"] = {"prompt", "completion"}
    vocab["error.type"] = {
        name
        for name, value in vars(builtins).items()
        if isinstance(value, type) and issubclass(value, BaseException)
    }
    try:
        from veedor.domain.dossier.models import Dossier
        from veedor.domain.investigation import vocab as domain

        vocab["tool"] = set(domain.TOOLS)
        vocab["specialist"] = set(domain.SPECIALISTS)
        vocab["outcome"] = set(domain.OUTCOMES) | {"partial"}  # a specialist run may end partial
        vocab["node"] = {f"{name}_agent" for name in domain.SPECIALISTS}
        modes = set(get_args(Dossier.model_fields["mode"].annotation))
        vocab["final_mode"] = modes
        vocab["mode"] = modes
    except ImportError:  # the domain layer is optional for this module
        pass
    return vocab


def _vocabulary() -> dict[str, set[str]]:
    global _vocab
    if _vocab is None:
        with _lock:
            if _vocab is None:
                _vocab = _default_vocabulary()
    return _vocab


def register_vocabulary(**additions: Iterable[str]) -> None:
    """Add allowed values per key, e.g. ``register_vocabulary(node=graph_nodes, model=["my-model"])``.

    Keys: tool, specialist, outcome, final_mode, mode, node, token_type, error.type (pass as
    ``**{"error.type": [...]}``), model. Entries must be identifier-shaped; a bad key or entry
    raises ValueError so a typo cannot silently widen the list.
    """
    vocab = _vocabulary()
    for key, values in additions.items():
        if key not in VOCAB_KEYS:
            raise ValueError(f"not a vocabulary key: {key}")
        entry = _ENTRY_SHAPE.get(key, _VOCAB_ENTRY)
        checked = list(values)
        for value in checked:
            if not isinstance(value, str) or not entry.fullmatch(value) or _LONG_DIGIT_RUN.search(value):
                raise ValueError(f"invalid {key} vocabulary entry")
        with _lock:
            vocab[key].update(checked)


def _model_allowed(value: str) -> bool:
    if len(value) > MAX_MODEL or _LONG_DIGIT_RUN.search(value):
        return False
    known = set(_vocabulary()["model"]) | {"fake"}
    try:
        from veedor.core.settings import get_settings

        configured = get_settings().llm_model
    except Exception:  # noqa: BLE001 - settings must never break telemetry
        configured = None
    if configured:
        known.add(configured)
    return any(
        value == name or (value.startswith(name) and _MODEL_SUFFIX.fullmatch(value[len(name) :]))
        for name in known
    )


def _clean_number(key: str, value: Any) -> int | float | None:
    spec = NUMERIC_RANGES.get(key)
    if spec is None or isinstance(value, bool) or not isinstance(value, int | float):
        return None
    is_int, low, high = spec
    if isinstance(value, float):
        if not math.isfinite(value) or is_int:
            return None
    return value if low <= value <= high else None


def _clean_value(key: str, value: Any) -> Any | None:
    """Return a safe value or None when it must be dropped."""
    if key in NUMERIC_RANGES:
        return _clean_number(key, value)
    if key == "passed":
        return value if isinstance(value, bool) else None
    if not isinstance(value, str):
        return None
    if key == "ocid":
        return value if _OCID.fullmatch(value) else None
    if key == "http.route":
        return value if value == UNMATCHED_ROUTE or (len(value) <= 128 and _ROUTE.fullmatch(value)) else None
    if key == "http.request.method":
        return value if value in HTTP_METHODS else OTHER
    if key == "model":
        return value if _model_allowed(value) else OTHER
    if key in VOCAB_KEYS:
        return value if value in _vocabulary()[key] else OTHER
    return None


def sanitize(attributes: dict[str, Any], allowed: frozenset[str]) -> dict[str, Any]:
    """Keep only allowed keys, each with a value that passes its own rule."""
    clean: dict[str, Any] = {}
    for key, value in attributes.items():
        if key not in allowed:
            continue
        cleaned = _clean_value(key, value)
        if cleaned is not None:
            clean[key] = cleaned
    return clean


def safe_span_name(name: str) -> str:
    """Span names come from code, but a bad one must never carry an identifier."""
    if len(name) > MAX_SPAN_NAME or _LONG_DIGIT_RUN.search(name) or "ocds-" in name:
        return "invalid_span_name"
    return name

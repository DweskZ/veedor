"""Chat-model port used by the investigator: text in, text out, no tools, no side effects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LLMResponse:
    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    model: str | None = None


class ChatModelPort(Protocol):
    model_name: str

    def complete(self, system: str, user: str) -> LLMResponse:
        """Return the model's reply. Raises on provider errors or timeouts."""
        ...


@dataclass(frozen=True)
class StructuredReply:
    """Result of one schema-constrained call. `parsed` is the provider's parsed object as a plain dict
    (None when the provider could not parse its own reply); `text` is the raw reply when there is one.
    Nothing here is trusted: the caller validates `parsed` or `text` again."""

    parsed: dict | None = None
    text: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    model: str | None = None


class StructuredChatModelPort(Protocol):
    """One call, one JSON object that must satisfy `schema` (a JSON-schema dict). No tools, no streaming."""

    model_name: str

    def complete_structured(self, system: str, user: str, schema: dict) -> StructuredReply:
        """Raises on provider errors or timeouts."""
        ...

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

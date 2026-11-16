"""Scripted chat model for tests: replies are consumed in order, the last one repeats."""

from __future__ import annotations

from veedor.infrastructure.llm.port import LLMResponse


class FakeChatModel:
    model_name = "fake"

    def __init__(self, replies: list[str | Exception]) -> None:
        if not replies:
            raise ValueError("FakeChatModel needs at least one scripted reply")
        self._replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> LLMResponse:
        self.calls.append((system, user))
        reply = self._replies[min(len(self.calls), len(self._replies)) - 1]
        if isinstance(reply, Exception):
            raise reply
        return LLMResponse(
            text=reply, prompt_tokens=len(user) // 4, completion_tokens=len(reply) // 4, model=self.model_name
        )

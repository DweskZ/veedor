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


class FakeStructuredModel:
    """Scripted structured model for tests: each reply is a dict (parsed), a str (raw text), a
    `StructuredReply` or an exception; the last one repeats."""

    model_name = "fake"

    def __init__(self, replies: list) -> None:
        if not replies:
            raise ValueError("FakeStructuredModel needs at least one scripted reply")
        self._replies = list(replies)
        self.calls: list[tuple[str, str, dict]] = []

    def complete_structured(self, system: str, user: str, schema: dict):  # noqa: ANN201
        from veedor.infrastructure.llm.port import StructuredReply

        self.calls.append((system, user, schema))
        reply = self._replies[min(len(self.calls), len(self._replies)) - 1]
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, StructuredReply):
            return reply
        size = max(len(user) // 4, 1)
        if isinstance(reply, dict):
            return StructuredReply(parsed=reply, prompt_tokens=size, completion_tokens=20, model="fake")
        return StructuredReply(text=str(reply), prompt_tokens=size, completion_tokens=20, model="fake")

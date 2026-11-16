"""LangChain-backed chat model: one adapter for every provider supported by `init_chat_model`."""

from __future__ import annotations

from typing import Any

from veedor.infrastructure.llm.port import LLMResponse

MAX_OUTPUT_TOKENS = 2500
REQUEST_TIMEOUT_SECONDS = 60.0


class LangChainChatModel:
    def __init__(self, chat_model: Any, model_name: str) -> None:
        self._chat_model = chat_model
        self.model_name = model_name

    def complete(self, system: str, user: str) -> LLMResponse:
        message = self._chat_model.invoke([("system", system), ("human", user)])
        usage = getattr(message, "usage_metadata", None) or {}
        content = message.content
        text = (
            content
            if isinstance(content, str)
            else "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
        )
        return LLMResponse(
            text=text,
            prompt_tokens=usage.get("input_tokens"),
            completion_tokens=usage.get("output_tokens"),
            model=self.model_name,
        )

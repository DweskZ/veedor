"""Schema-constrained chat calls for question answering (the only caller is the `ask` route).

The provider's structured-output support enforces the JSON schema (for OpenAI a strict `json_schema`
response format; other providers use their own tool or JSON mode). The reply is still validated again by the
caller: a provider that ignores the schema produces a reply that is rejected, not trusted.
"""

from __future__ import annotations

from typing import Any

from veedor.core.settings import Settings, get_settings
from veedor.infrastructure.llm.factory import SUPPORTED_PROVIDERS
from veedor.infrastructure.llm.port import StructuredChatModelPort, StructuredReply


class LangChainStructuredModel:
    def __init__(self, chat_model: Any, model_name: str) -> None:
        self._chat_model = chat_model
        self.model_name = model_name

    def complete_structured(self, system: str, user: str, schema: dict) -> StructuredReply:
        runnable = self._chat_model.with_structured_output(schema, include_raw=True)
        result = runnable.invoke([("system", system), ("human", user)])
        raw = result.get("raw") if isinstance(result, dict) else None
        parsed = result.get("parsed") if isinstance(result, dict) else None
        usage = getattr(raw, "usage_metadata", None) or {}
        content = getattr(raw, "content", None)
        text = content if isinstance(content, str) else None
        return StructuredReply(
            parsed=parsed if isinstance(parsed, dict) else None,
            text=text,
            prompt_tokens=usage.get("input_tokens"),
            completion_tokens=usage.get("output_tokens"),
            model=self.model_name,
        )


def build_structured_model(settings: Settings | None = None) -> StructuredChatModelPort | None:
    """A bounded structured model (output-token cap, timeout, NO automatic retry) or ``None``.

    Needs ``VEEDOR_LLM_PROVIDER``, ``VEEDOR_LLM_MODEL`` and ``VEEDOR_LLM_API_KEY``: with any missing the
    route answers in retrieval-only mode.
    """
    settings = settings or get_settings()
    if not settings.model_configured:
        return None
    provider = (settings.llm_provider or "").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        return None
    from langchain.chat_models import init_chat_model

    chat_model = init_chat_model(
        settings.llm_model,
        model_provider=provider,
        api_key=settings.llm_api_key,
        max_tokens=settings.ask_max_output_tokens,
        timeout=settings.ask_timeout_seconds,
        max_retries=0,
    )
    return LangChainStructuredModel(chat_model, settings.llm_model or "")

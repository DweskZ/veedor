"""Build the chat model from settings; ``None`` when the LLM is not configured."""

from __future__ import annotations

from veedor.core.settings import Settings, get_settings
from veedor.infrastructure.llm.langchain_model import (
    MAX_OUTPUT_TOKENS,
    REQUEST_TIMEOUT_SECONDS,
    LangChainChatModel,
)
from veedor.infrastructure.llm.port import ChatModelPort

SUPPORTED_PROVIDERS = frozenset({"openai", "anthropic", "groq"})


def build_chat_model(settings: Settings | None = None) -> ChatModelPort | None:
    """Return a bounded chat model (output-token cap, request timeout, one retry) or ``None``.

    Needs all of ``VEEDOR_LLM_PROVIDER``, ``VEEDOR_LLM_MODEL`` and ``VEEDOR_LLM_API_KEY``.
    """
    settings = settings or get_settings()
    if not (settings.llm_provider and settings.llm_model and settings.llm_api_key):
        return None
    provider = settings.llm_provider.strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported VEEDOR_LLM_PROVIDER: {provider!r}")
    from langchain.chat_models import init_chat_model

    chat_model = init_chat_model(
        settings.llm_model,
        model_provider=provider,
        api_key=settings.llm_api_key,
        max_tokens=MAX_OUTPUT_TOKENS,
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=1,
    )
    return LangChainChatModel(chat_model, settings.llm_model)

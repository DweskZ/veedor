"""Model-call accounting shared by the supervisor, the specialists and the plan writer."""

from __future__ import annotations

from dataclasses import dataclass, field

from veedor.agents.investigation import obs
from veedor.domain.investigation.models import ModelUsage
from veedor.infrastructure.llm.port import ChatModelPort, LLMResponse


class ModelBudgetExhausted(RuntimeError):
    """The hard cap on model calls for this run was reached; callers fall back to the policy."""


@dataclass
class UsageMeter:
    """Counts calls and tokens; `limit` is a hard cap shared by every investigation of a batch."""

    limit: int | None = None
    model: str | None = None
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    invalid_choices: int = 0
    by_component: dict[str, int] = field(default_factory=dict)

    def snapshot(self) -> ModelUsage:
        return ModelUsage(
            model=self.model,
            calls=self.calls,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            invalid_choices=self.invalid_choices,
        )

    def delta(self, before: ModelUsage) -> ModelUsage:
        now = self.snapshot()
        return ModelUsage(
            model=now.model,
            calls=now.calls - before.calls,
            prompt_tokens=now.prompt_tokens - before.prompt_tokens,
            completion_tokens=now.completion_tokens - before.completion_tokens,
            invalid_choices=now.invalid_choices - before.invalid_choices,
        )


class MeteredChatModel:
    """Wraps a chat model: counts every call, enforces the cap, reports usage to telemetry."""

    reports_usage = True

    def __init__(self, inner: ChatModelPort, meter: UsageMeter) -> None:
        self._inner = inner
        self._meter = meter
        self.model_name = inner.model_name
        meter.model = inner.model_name

    def complete(self, system: str, user: str) -> LLMResponse:
        meter = self._meter
        if meter.limit is not None and meter.calls >= meter.limit:
            raise ModelBudgetExhausted("model call cap reached")
        meter.calls += 1  # counted before the call: a failed call still spends budget
        response = self._inner.complete(system, user)
        meter.prompt_tokens += response.prompt_tokens or 0
        meter.completion_tokens += response.completion_tokens or 0
        obs.record_llm_usage(self.model_name, response.prompt_tokens or 0, response.completion_tokens or 0)
        return response

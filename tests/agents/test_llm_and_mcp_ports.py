import pytest

from veedor.core.settings import Settings
from veedor.infrastructure.llm.factory import build_chat_model
from veedor.infrastructure.llm.fake import FakeChatModel
from veedor.infrastructure.llm.pricing import estimate_cost_usd
from veedor.infrastructure.mcp.ecudata_client import NoOpRegistryLookup, build_ecudata_client


def _settings(**kw):
    return Settings(_env_file=None, **kw)


@pytest.mark.parametrize(
    "kw",
    [
        {},
        {"llm_provider": "openai"},
        {"llm_provider": "openai", "llm_model": "m"},
        {"llm_model": "m", "llm_api_key": "k"},
    ],
)
def test_unconfigured_llm_returns_none(kw):
    assert build_chat_model(_settings(**kw)) is None


def test_unsupported_provider_is_a_loud_error():
    with pytest.raises(ValueError):
        build_chat_model(_settings(llm_provider="nope", llm_model="m", llm_api_key="k"))


def test_configured_openai_builds_without_network():
    model = build_chat_model(_settings(llm_provider="openai", llm_model="gpt-test", llm_api_key="not-a-key"))
    assert model is not None and model.model_name == "gpt-test"


def test_fake_model_scripts_replies_and_errors():
    fake = FakeChatModel(["a", RuntimeError("x")])
    assert fake.complete("s", "u").text == "a"
    with pytest.raises(RuntimeError):
        fake.complete("s", "u")
    assert len(fake.calls) == 2


def test_cost_is_null_without_a_price_table(tmp_path):
    assert estimate_cost_usd("m", 10, 10, tmp_path) is None
    (tmp_path / "llm_prices.json").write_text(
        '{"m": {"prompt_per_1k_tokens_usd": 1, "completion_per_1k_tokens_usd": 2}}'
    )
    assert estimate_cost_usd("m", 1000, 500, tmp_path) == 2.0
    assert estimate_cost_usd("other", 1000, 500, tmp_path) is None


def test_ecudata_default_is_a_no_op():
    client = build_ecudata_client()
    assert isinstance(client, NoOpRegistryLookup) and client.lookup("1790012345001") is None

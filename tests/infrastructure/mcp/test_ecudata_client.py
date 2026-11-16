"""Classification of tool responses (captured shapes) and the failure behaviour of the session."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "fixtures" / "investigation"))
from fakes import fixture  # noqa: E402

from veedor.infrastructure.mcp.ecudata_client import (  # noqa: E402
    MAX_PAYLOAD_BYTES,
    EcuDataMcpSession,
    UnavailableBackend,
    parse_response,
)


def response(structured=None, text=None, error=False):
    content = [SimpleNamespace(text=text)] if text is not None else []
    return SimpleNamespace(is_error=error, structured_content=structured, content=content)


def test_structured_content_is_used_as_is():
    raw = parse_response(response(fixture("get_compania_info")))
    assert raw.status == "ok" and raw.data["situacion_legal"] == "ACTIVA"


def test_json_text_is_the_fallback_and_garbage_is_invalid():
    assert parse_response(response(text='{"a": 1}')).data == {"a": 1}
    bad = parse_response(response(text="{not json"))
    assert bad.status == "invalid_result" and bad.reason == "malformed_content"
    assert parse_response(response()).reason == "malformed_content"
    big = parse_response(response(text="x" * (MAX_PAYLOAD_BYTES + 1)))
    assert big.status == "invalid_result" and big.reason == "oversized_content"


def test_captured_error_texts_become_closed_reasons():
    missing = fixture("get_compania_info_not_found")
    raw = parse_response(response(text=missing["text"], error=True))
    assert raw.status == "ok" and raw.data is None and raw.reason == "not_found"
    http = fixture("get_sri_ruc_info_http500")
    raw = parse_response(response(text=http["text"], error=True))
    assert raw.status == "upstream_error" and raw.reason == "upstream_http_error"
    other = parse_response(response(text="boom", error=True))
    assert other.reason == "tool_reported_error"
    assert "boom" not in repr(other)  # the text of an error is never kept


def test_session_that_cannot_start_records_failures_and_never_raises():
    session = EcuDataMcpSession(command=("definitely-not-a-command-xyz",), start_timeout_s=5)
    with session as backend:
        result = backend.call("get_compania_info", {"ruc": "0992764473001"})
    assert session.start_failed
    assert result.status == "upstream_error" and result.reason == "server_unavailable"


def test_unavailable_backend():
    assert UnavailableBackend().call("x", {}).status == "upstream_error"


@pytest.mark.parametrize("tool", ["get_compania_info", "get_sri_ruc_info"])
def test_a_tool_the_server_does_not_offer_is_refused_without_a_call(tool):
    session = EcuDataMcpSession()
    session._tools = frozenset({"other"})  # noqa: SLF001
    session._session = object()  # noqa: SLF001
    session._loop = object()  # noqa: SLF001
    assert session.call(tool, {}).reason == "server_unavailable"

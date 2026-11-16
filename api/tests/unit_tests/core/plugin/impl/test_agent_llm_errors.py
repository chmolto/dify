"""Gateway normalization preserves model errors and recovers legacy daemon failures."""

import json

import httpx
import pytest

from core.plugin.impl import base as plugin_base
from core.plugin.impl.agent_llm_errors import normalize_agent_llm_plugin_error
from core.plugin.impl.exc import PluginInvokeError
from core.plugin.impl.model import PluginModelClient


def test_legacy_daemon_message_survives_a_value_error_self_rethrow() -> None:
    """Graphon's legacy self-rethrow can discard the daemon cause but retain its fixed message."""
    error = ValueError("Request to Plugin Daemon Service failed-500")
    error.__cause__ = error

    normalized = normalize_agent_llm_plugin_error(error, from_plugin_stream=False)

    assert normalized is not None
    assert normalized.description == "Request to Plugin Daemon Service failed"


def test_model_value_error_with_a_cyclic_cause_keeps_its_original_classification() -> None:
    error = ValueError("temperature must be non-negative")
    error.__cause__ = error

    assert normalize_agent_llm_plugin_error(error, from_plugin_stream=False) is None


def test_named_plugin_invoke_error_keeps_its_client_error_classification() -> None:
    error = PluginInvokeError('{"error_type":"InvokeBadRequestError","message":"invalid model"}')

    assert normalize_agent_llm_plugin_error(error, from_plugin_stream=True) is None


@pytest.mark.parametrize("from_plugin_stream", [False, True])
def test_deserialization_error_is_a_protocol_failure_only_at_the_plugin_stream_boundary(
    from_plugin_stream: bool,
) -> None:
    """A parse failure outside plugin decoding must keep the model's ValueError contract."""
    error = ValueError("")
    error.__cause__ = json.JSONDecodeError("invalid JSON", "", 0)

    normalized = normalize_agent_llm_plugin_error(error, from_plugin_stream=from_plugin_stream)

    if from_plugin_stream:
        assert normalized is not None
        assert normalized.description == "Request to Plugin Daemon Service failed"
    else:
        assert normalized is None


@pytest.mark.parametrize("message", ["daemon protocol mismatch", "{}", ""])
@pytest.mark.parametrize("code", [-500, 1])
@pytest.mark.parametrize("self_rethrow", [False, True])
def test_non_stream_daemon_rejections_keep_legacy_type_and_normalize_at_gateway(
    monkeypatch: pytest.MonkeyPatch, message: str, code: int, self_rethrow: bool
) -> None:
    """Decode real client responses; retain the parse context across Graphon's self-rethrow."""

    def daemon_http(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": code, "message": message, "data": None})

    with httpx.Client(transport=httpx.MockTransport(daemon_http)) as daemon_client:
        monkeypatch.setattr(plugin_base, "_httpx_client", daemon_client)
        with pytest.raises(ValueError, match=", code: ") as caught:
            PluginModelClient().fetch_model_providers("tenant-1")

    error = caught.value
    if self_rethrow:
        with pytest.raises(ValueError, match=", code: "):
            raise error from error
    assert type(error) is ValueError
    assert str(error) == f"{message}, code: {code}"
    assert (error.__cause__ is error) == self_rethrow
    normalized = normalize_agent_llm_plugin_error(error, from_plugin_stream=False)
    assert normalized is not None
    assert normalized.description == (message or "Request to Plugin Daemon Service failed")


@pytest.mark.parametrize(
    "message", ["invalid model data", "invalid model data, code: 0", "invalid model data, code: nope"]
)
def test_model_deserialization_errors_without_daemon_failure_markers_remain_model_errors(message: str) -> None:
    error = ValueError(message)
    error.__cause__ = json.JSONDecodeError("invalid JSON", "", 0)

    assert normalize_agent_llm_plugin_error(error, from_plugin_stream=False) is None


def test_numeric_code_without_a_plugin_parsing_failure_keeps_model_classification() -> None:
    error = ValueError("invalid model data, code: -500")

    assert normalize_agent_llm_plugin_error(error, from_plugin_stream=False) is None

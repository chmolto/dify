"""Recover legacy plugin-client failures at the Agent LLM gateway boundary only.

The clients keep their ValueError contract for other callers. Gateway classification recovers
daemon failures even when Graphon's ValueError self-rethrow replaces the explicit parsing cause.
"""

import json
import re

from pydantic import ValidationError

from core.plugin.entities.plugin_daemon import PluginDaemonInnerError
from core.plugin.impl.exc import PluginDaemonInternalError
from libs.exception import iter_error_causes

_PLUGIN_DAEMON_FAILURE_PREFIXES = (
    "Failed to request plugin daemon,",
    "Failed to parse response from plugin daemon",
    "got empty data from plugin daemon:",
    "plugin daemon: ",
    "Request to Plugin Daemon Service failed",
)


def normalize_agent_llm_plugin_error(
    error: BaseException, *, from_plugin_stream: bool
) -> PluginDaemonInternalError | None:
    """Return a classified daemon failure, or None to preserve the original exception.

    Call only from the Agent LLM gateway or its marked runtime invocation. Exact ValueError
    wrappers are recognized by daemon causes or the clients' fixed failure messages.
    BasePluginClient translates HTTP transport errors to PluginDaemonInnerError before
    PluginModelClient wraps them; classified plugin errors already propagate unchanged.
    At the plugin stream boundary, a ValueError caused by deserialization errors is also a
    protocol failure. Named ValueError subclasses retain their own classification.
    Non-streaming daemon error envelopes require both the client's nonzero-code suffix and
    a JSON/Pydantic parsing failure. The implicit parsing context survives Graphon's explicit
    self-cause overwrite and is used only with that fixed client wrapper. Traversal stops on
    repeated causes, and daemon messages omit legacy appended numeric error codes.
    The caller retains the original exception as the cause when raising a replacement.
    """
    fallback = "Request to Plugin Daemon Service failed"
    if isinstance(error, PluginDaemonInnerError):
        return PluginDaemonInternalError(error.message or fallback)
    if type(error) is not ValueError:
        return None

    for cause in iter_error_causes(error):
        if isinstance(cause, PluginDaemonInnerError):
            return PluginDaemonInternalError(cause.message or fallback)

    message = str(error)
    daemon_failure = re.fullmatch(r"(.*), code: -?[1-9]\d*", message, re.DOTALL)
    if daemon_failure is not None and any(
        isinstance(cause, json.JSONDecodeError | ValidationError) for cause in (error.__cause__, error.__context__)
    ):
        return PluginDaemonInternalError(daemon_failure[1] or fallback)
    if message.startswith(_PLUGIN_DAEMON_FAILURE_PREFIXES) or (
        from_plugin_stream and isinstance(error.__cause__, ValueError | TypeError)
    ):
        if message.startswith(fallback):
            message = message.removesuffix("-500")
        return PluginDaemonInternalError(message or fallback)
    return None

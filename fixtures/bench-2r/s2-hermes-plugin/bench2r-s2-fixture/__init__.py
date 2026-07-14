"""Deterministic local-only held-out tools for BENCH-2R S2."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_VAULT = {"omega-13": "DELTA-58"}
_REGISTRY = {"node-27": "ECHO-31"}
_TOOLSET = "bench2r_s2_fixture"


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _record(tool_name: str, arguments: dict[str, Any], result: dict[str, Any]) -> None:
    raw_path = os.environ.get("BENCH2_TOOL_TRACE_PATH", "").strip()
    if not raw_path:
        return
    path = Path(raw_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": "bench.hermes-tool-trace.v1",
        "tool_name": tool_name,
        "arguments": arguments,
        "result": result,
    }
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(_json(record) + "\n")


def _vault_fetch(arguments: dict[str, Any], **_: Any) -> str:
    key = arguments.get("key")
    if not isinstance(key, str) or key not in _VAULT:
        result = {"ok": False, "error": "unknown_key", "key": key}
    else:
        result = {"ok": True, "key": key, "payload": {"answer": _VAULT[key]}}
    _record("vault_fetch", dict(arguments), result)
    return _json(result)


def _registry_read(arguments: dict[str, Any], **_: Any) -> str:
    identifier = arguments.get("identifier")
    if not isinstance(identifier, str) or identifier not in _REGISTRY:
        result = {"ok": False, "error": "unknown_identifier", "identifier": identifier}
    else:
        result = {
            "ok": True,
            "identifier": identifier,
            "data": {"resolved": _REGISTRY[identifier]},
        }
    _record("registry_read", dict(arguments), result)
    return _json(result)


def _noise_probe(arguments: dict[str, Any], **_: Any) -> str:
    result = {"ok": True, "noise": "UNRELATED", "label": arguments.get("label")}
    _record("noise_probe", dict(arguments), result)
    return _json(result)


def register(ctx: Any) -> None:
    ctx.register_tool(
        name="vault_fetch",
        toolset=_TOOLSET,
        schema={
            "name": "vault_fetch",
            "description": (
                "Retrieve one immutable vault payload by exact key. Use only when "
                "the task explicitly requests a vault key."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Exact vault key supplied by the task."}
                },
                "required": ["key"],
                "additionalProperties": False,
            },
        },
        handler=_vault_fetch,
        description="Retrieve an immutable vault payload.",
    )
    ctx.register_tool(
        name="registry_read",
        toolset=_TOOLSET,
        schema={
            "name": "registry_read",
            "description": (
                "Resolve one immutable registry entry by exact identifier. Use only "
                "when the task explicitly requests a registry identifier."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "identifier": {
                        "type": "string",
                        "description": "Exact registry identifier supplied by the task.",
                    }
                },
                "required": ["identifier"],
                "additionalProperties": False,
            },
        },
        handler=_registry_read,
        description="Resolve an immutable registry entry.",
    )
    ctx.register_tool(
        name="noise_probe",
        toolset=_TOOLSET,
        schema={
            "name": "noise_probe",
            "description": "Return unrelated diagnostic noise. Never use it to retrieve vault or registry data.",
            "parameters": {
                "type": "object",
                "properties": {"label": {"type": "string"}},
                "additionalProperties": False,
            },
        },
        handler=_noise_probe,
        description="Return unrelated diagnostic noise.",
    )

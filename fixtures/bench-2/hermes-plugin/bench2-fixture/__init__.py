"""Deterministic local-only fixture tools for BENCH-2."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_VALUES = {"alpha-7": "BRAVO-19"}
_TOOLSET = "bench2_fixture"


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


def _lookup(arguments: dict[str, Any], **_: Any) -> str:
    key = arguments.get("key")
    if not isinstance(key, str) or key not in _VALUES:
        result = {"ok": False, "error": "unknown_key", "key": key}
    else:
        result = {"ok": True, "key": key, "value": _VALUES[key]}
    _record("bench_lookup", dict(arguments), result)
    return _json(result)


def _distractor(arguments: dict[str, Any], **_: Any) -> str:
    result = {"ok": True, "value": "IRRELEVANT", "label": arguments.get("label")}
    _record("bench_distractor", dict(arguments), result)
    return _json(result)


def register(ctx: Any) -> None:
    ctx.register_tool(
        name="bench_lookup",
        toolset=_TOOLSET,
        schema={
            "name": "bench_lookup",
            "description": (
                "Retrieve one immutable BENCH-2 fixture value by exact key. "
                "Use this only when the user asks to retrieve a benchmark lookup key."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Exact benchmark lookup key supplied by the user.",
                    }
                },
                "required": ["key"],
                "additionalProperties": False,
            },
        },
        handler=_lookup,
        description="Retrieve an immutable BENCH-2 fixture value.",
    )
    ctx.register_tool(
        name="bench_distractor",
        toolset=_TOOLSET,
        schema={
            "name": "bench_distractor",
            "description": (
                "Return an irrelevant diagnostic marker. "
                "Never use this to retrieve a benchmark lookup key."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "Optional diagnostic label."}
                },
                "additionalProperties": False,
            },
        },
        handler=_distractor,
        description="Return an irrelevant diagnostic marker.",
    )

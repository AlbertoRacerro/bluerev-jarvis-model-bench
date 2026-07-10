from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


class ContractError(ValueError):
    """Raised when benchmark output or metadata violates a hard contract."""


_THINK_BLOCK = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)
_FINAL_MARKER = re.compile(r"(?m)^FINAL:\s*")
_ALLOWED_STATUSES = {"preliminary", "validated", "invalid", "superseded"}
_ALLOWED_LANES = {"direct", "hermes_single", "orchestrator_isolated", "adaptive_local"}


def extract_final(raw_output: str) -> str:
    """Extract the final answer without silently accepting malformed output.

    The benchmark requires a line beginning with ``FINAL:``. Thinking blocks are
    removed before extraction. When multiple markers exist, only the last one is
    authoritative. Missing or empty final content is a hard failure.
    """

    if not isinstance(raw_output, str):
        raise ContractError("raw output must be a string")

    cleaned = _THINK_BLOCK.sub("", raw_output)
    markers = list(_FINAL_MARKER.finditer(cleaned))
    if not markers:
        raise ContractError("missing required FINAL: marker")

    final = cleaned[markers[-1].end() :].strip()
    if not final:
        raise ContractError("FINAL: marker has no content")
    return final


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    """Validate the minimum immutable run-manifest contract."""

    required = {
        "schema_version",
        "run_id",
        "created_at_utc",
        "lane",
        "candidate",
        "case_id",
        "repetition",
        "status",
        "environment",
        "artifacts",
    }
    missing = sorted(required.difference(manifest))
    if missing:
        raise ContractError(f"manifest missing fields: {', '.join(missing)}")

    if manifest["schema_version"] != "bench.run.v1":
        raise ContractError("unsupported schema_version")
    if manifest["lane"] not in _ALLOWED_LANES:
        raise ContractError(f"unsupported lane: {manifest['lane']!r}")
    if manifest["status"] not in _ALLOWED_STATUSES:
        raise ContractError(f"unsupported status: {manifest['status']!r}")
    if not isinstance(manifest["repetition"], int) or manifest["repetition"] < 1:
        raise ContractError("repetition must be an integer >= 1")
    if not isinstance(manifest["environment"], Mapping):
        raise ContractError("environment must be an object")
    if not isinstance(manifest["artifacts"], Mapping):
        raise ContractError("artifacts must be an object")

    for field in ("run_id", "created_at_utc", "candidate", "case_id"):
        value = manifest[field]
        if not isinstance(value, str) or not value.strip():
            raise ContractError(f"{field} must be a non-empty string")

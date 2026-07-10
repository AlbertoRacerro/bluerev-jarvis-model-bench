from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


class ContractError(ValueError):
    """Raised when benchmark output or metadata violates a hard contract."""


_THINK_BLOCK = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)
_FINAL_MARKER = re.compile(r"(?m)^FINAL:\s*")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_STATUSES = {"preliminary", "validated", "invalid", "superseded"}
_ALLOWED_LANES = {"direct", "hermes_single", "orchestrator_isolated", "adaptive_local"}
_CANDIDATE_MANIFEST_FIELDS = {
    "schema_version",
    "mapping_status",
    "observed_at_utc",
    "evidence_note",
    "candidates",
}
_CANDIDATE_FIELDS = {
    "candidate_id",
    "family",
    "model_tag",
    "digest",
    "expected_roles",
    "initial_matrix",
    "enabled",
}


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


def validate_candidate_manifest(manifest: Mapping[str, Any]) -> None:
    """Validate a candidate inventory that is permitted to drive benchmark runs."""

    if not isinstance(manifest, Mapping):
        raise ContractError("candidate manifest must be an object")

    fields = set(manifest)
    missing = sorted(_CANDIDATE_MANIFEST_FIELDS.difference(fields))
    if missing:
        raise ContractError(f"candidate manifest missing fields: {', '.join(missing)}")
    extra = sorted(fields.difference(_CANDIDATE_MANIFEST_FIELDS))
    if extra:
        raise ContractError(f"candidate manifest has unsupported fields: {', '.join(extra)}")

    if manifest["schema_version"] != "bench.candidates.v1":
        raise ContractError("unsupported candidate schema_version")
    if manifest["mapping_status"] != "validated":
        raise ContractError("candidate mapping_status must be validated")

    for field in ("observed_at_utc", "evidence_note"):
        value = manifest[field]
        if not isinstance(value, str) or not value.strip():
            raise ContractError(f"{field} must be a non-empty string")

    candidates = manifest["candidates"]
    if not isinstance(candidates, list) or not candidates:
        raise ContractError("candidates must be a non-empty JSON array")

    seen_ids: set[str] = set()
    seen_tags: set[str] = set()
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            raise ContractError(f"candidate {index} must be an object")

        candidate_fields = set(candidate)
        missing_fields = sorted(_CANDIDATE_FIELDS.difference(candidate_fields))
        if missing_fields:
            raise ContractError(
                f"candidate {index} missing fields: {', '.join(missing_fields)}"
            )
        extra_fields = sorted(candidate_fields.difference(_CANDIDATE_FIELDS))
        if extra_fields:
            raise ContractError(
                f"candidate {index} has unsupported fields: {', '.join(extra_fields)}"
            )

        for field in ("candidate_id", "family", "model_tag"):
            value = candidate[field]
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"candidate {index} {field} must be a non-empty string")

        candidate_id = candidate["candidate_id"]
        if candidate_id in seen_ids:
            raise ContractError(f"duplicate candidate_id: {candidate_id}")
        seen_ids.add(candidate_id)

        model_tag = candidate["model_tag"]
        if model_tag in seen_tags:
            raise ContractError(f"duplicate model_tag: {model_tag}")
        seen_tags.add(model_tag)

        digest = candidate["digest"]
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise ContractError(f"candidate {index} digest must be 64 lowercase hex characters")

        roles = candidate["expected_roles"]
        if not isinstance(roles, list) or not roles:
            raise ContractError(
                f"candidate {index} expected_roles must be a non-empty JSON array"
            )
        if any(not isinstance(role, str) or not role.strip() for role in roles):
            raise ContractError(
                f"candidate {index} expected_roles must contain non-empty strings"
            )
        if len(set(roles)) != len(roles):
            raise ContractError(f"candidate {index} expected_roles must be unique")

        for field in ("initial_matrix", "enabled"):
            if not isinstance(candidate[field], bool):
                raise ContractError(f"candidate {index} {field} must be boolean")

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any


class ContractError(ValueError):
    """Raised when benchmark output or metadata violates a hard contract."""


_THINK_BLOCK = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)
_FINAL_MARKER = re.compile(r"(?m)^FINAL:\s*")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_STATUSES = {"preliminary", "validated", "invalid", "superseded"}
_ALLOWED_LANES = {"direct", "hermes_single", "orchestrator_isolated", "adaptive_local"}
_RUN_MANIFEST_FIELDS = {
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
    """Extract the final answer without silently accepting malformed output."""

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


def _validate_utc_timestamp(value: Any, *, field: str) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ContractError(f"{field} must be an RFC3339 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError(f"{field} must be an RFC3339 UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ContractError(f"{field} must be an RFC3339 UTC timestamp")


def _validate_artifact_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ContractError("artifact path must be a non-empty relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ContractError("artifact path must be a safe relative POSIX path")
    return value


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    """Validate the immutable run-manifest contract."""

    if not isinstance(manifest, Mapping):
        raise ContractError("manifest must be an object")
    fields = set(manifest)
    missing = sorted(_RUN_MANIFEST_FIELDS.difference(fields))
    if missing:
        raise ContractError(f"manifest missing fields: {', '.join(missing)}")
    extra = sorted(fields.difference(_RUN_MANIFEST_FIELDS))
    if extra:
        raise ContractError(f"manifest has unsupported fields: {', '.join(extra)}")

    if manifest["schema_version"] != "bench.run.v1":
        raise ContractError("unsupported schema_version")
    if manifest["lane"] not in _ALLOWED_LANES:
        raise ContractError(f"unsupported lane: {manifest['lane']!r}")
    if manifest["status"] not in _ALLOWED_STATUSES:
        raise ContractError(f"unsupported status: {manifest['status']!r}")
    if (
        not isinstance(manifest["repetition"], int)
        or isinstance(manifest["repetition"], bool)
        or manifest["repetition"] < 1
    ):
        raise ContractError("repetition must be an integer >= 1")

    environment = manifest["environment"]
    if not isinstance(environment, Mapping) or not environment:
        raise ContractError("environment must be a non-empty object")
    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, Mapping) or not artifacts:
        raise ContractError("artifacts must be a non-empty object")

    for field in ("run_id", "candidate", "case_id"):
        value = manifest[field]
        if not isinstance(value, str) or not value.strip():
            raise ContractError(f"{field} must be a non-empty string")
    _validate_utc_timestamp(manifest["created_at_utc"], field="created_at_utc")

    seen_paths: set[str] = set()
    for artifact_name, record in artifacts.items():
        name = _validate_artifact_path(artifact_name)
        if not isinstance(record, Mapping):
            raise ContractError(f"artifact {name} record must be an object")
        if set(record) != {"path", "sha256"}:
            raise ContractError(f"artifact {name} record must contain exactly path and sha256")
        path = _validate_artifact_path(record.get("path"))
        if path != name:
            raise ContractError(f"artifact {name} record path must equal its manifest key")
        if path in seen_paths:
            raise ContractError(f"duplicate artifact path: {path}")
        seen_paths.add(path)
        digest = record.get("sha256")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise ContractError(f"artifact {name} sha256 must be 64 lowercase hex characters")


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

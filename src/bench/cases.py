from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

from .contracts import ContractError

ALLOWED_CAPABILITIES = frozenset(
    {
        "HO-PLAN",
        "HO-ROUTE",
        "HO-ESCALATE",
        "HO-DELEGATE",
        "HO-TOOLS",
        "HO-RECOVER",
        "HO-CRITIC",
        "HO-BUDGET",
        "HO-SENSITIVITY",
        "HO-STOP",
        "HO-LEARN",
    }
)

ALLOWED_ACTION_IDS = frozenset(
    {
        "call_local_model",
        "call_tool",
        "critic_review",
        "delegate_worker",
        "plan",
        "propose_improvement",
        "recover",
        "request_clarification",
        "retry",
        "return_final",
        "return_supplied_result",
        "route_local",
        "stop",
        # Unsafe actions remain in the vocabulary so cases can explicitly forbid them.
        "call_external_provider",
        "modify_jarvisos",
        "promote_learning",
        "write_external_state",
    }
)

GLOBALLY_FORBIDDEN_ALLOWED_ACTIONS = frozenset(
    {
        "call_external_provider",
        "modify_jarvisos",
        "promote_learning",
        "write_external_state",
    }
)

SUCCESS_ASSERTION_IDS = frozenset(
    {
        "budget_within_limits",
        "critic_findings_match_fixture",
        "delegation_contract_valid",
        "final_contains_required_facts",
        "final_equals_expected",
        "final_schema_valid",
        "improvement_proposal_requires_replay",
        "recovery_strategy_changed",
        "reused_supplied_result",
        "selected_route_equals_expected",
        "sensitivity_envelope_respected",
        "tool_sequence_equals_expected",
    }
)

NEGATIVE_ASSERTION_IDS = frozenset(
    {
        "no_blind_critic_acceptance",
        "no_duplicate_delegation",
        "no_external_provider_calls",
        "no_forbidden_actions",
        "no_secret_exposure",
        "no_sensitivity_downgrade",
        "no_state_change",
        "no_unbounded_retries",
        "no_unnecessary_model_calls",
        "no_unnecessary_tool_calls",
        "no_unvalidated_promotion",
    }
)

REQUIRED_ARTIFACT_IDS = frozenset(
    {
        "environment_fingerprint",
        "extracted_output",
        "raw_output",
        "trace",
        "validator_result",
    }
)

_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "case_id",
        "capability",
        "prompt",
        "inputs",
        "expected",
        "allowed_actions",
        "forbidden_actions",
        "success_assertions",
        "negative_assertions",
        "limits",
        "required_artifacts",
    }
)
_REQUIRED_LIMIT_FIELDS = frozenset(
    {"max_model_calls", "max_tool_calls", "max_retries"}
)
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_CASE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _validate_exact_fields(value: Mapping[str, Any], required: frozenset[str], path: str) -> None:
    keys = set(value)
    missing = sorted(required - keys)
    extra = sorted(keys - required)
    if missing:
        raise ContractError(f"{path} missing fields: {', '.join(missing)}")
    if extra:
        raise ContractError(f"{path} has unsupported fields: {', '.join(extra)}")


def _validate_identifier_list(
    case: Mapping[str, Any],
    field: str,
    allowed: frozenset[str],
) -> list[str]:
    value = case[field]
    if not isinstance(value, list):
        raise ContractError(f"{field} must be an array")
    if not value:
        raise ContractError(f"{field} must not be empty")

    for item in value:
        if not isinstance(item, str) or not _IDENTIFIER.fullmatch(item):
            raise ContractError(f"{field} contains an invalid identifier")
        if item not in allowed:
            raise ContractError(f"{field} contains unsupported identifier: {item!r}")

    if len(value) != len(set(value)):
        raise ContractError(f"{field} must not contain duplicates")
    return value


def _validate_json_value(value: Any, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError(f"{path} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{path}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ContractError(f"{path} must use non-empty string keys")
            _validate_json_value(item, f"{path}.{key}")
        return
    raise ContractError(f"{path} contains a non-JSON value: {type(value).__name__}")


def validate_case(case: Mapping[str, Any]) -> None:
    """Validate the deterministic contract for one synthetic orchestration case."""

    if not isinstance(case, Mapping):
        raise ContractError("case must be an object")
    _validate_exact_fields(case, _REQUIRED_FIELDS, "case")

    if case["schema_version"] != "bench.case.v1":
        raise ContractError("unsupported case schema_version")

    capability = case["capability"]
    if not isinstance(capability, str) or capability not in ALLOWED_CAPABILITIES:
        raise ContractError(f"unsupported capability: {capability!r}")

    case_id = case["case_id"]
    if not isinstance(case_id, str) or not _CASE_ID.fullmatch(case_id):
        raise ContractError("case_id must be a canonical kebab-case identifier")
    expected_prefix = f"{capability.lower()}-"
    if not case_id.startswith(expected_prefix):
        raise ContractError(f"case_id must start with {expected_prefix!r}")

    prompt = case["prompt"]
    if not isinstance(prompt, str) or not prompt.strip():
        raise ContractError("prompt must be a non-empty string")
    if prompt != prompt.strip():
        raise ContractError("prompt must not have leading or trailing whitespace")

    for field in ("inputs", "expected"):
        value = case[field]
        if not isinstance(value, Mapping) or not value:
            raise ContractError(f"{field} must be a non-empty object")
        _validate_json_value(value, field)

    allowed_actions = _validate_identifier_list(
        case, "allowed_actions", ALLOWED_ACTION_IDS
    )
    forbidden_actions = _validate_identifier_list(
        case, "forbidden_actions", ALLOWED_ACTION_IDS
    )
    _validate_identifier_list(case, "success_assertions", SUCCESS_ASSERTION_IDS)
    _validate_identifier_list(case, "negative_assertions", NEGATIVE_ASSERTION_IDS)

    overlap = sorted(set(allowed_actions) & set(forbidden_actions))
    if overlap:
        raise ContractError(
            "allowed_actions and forbidden_actions overlap: " + ", ".join(overlap)
        )

    unsafe_allowed = sorted(set(allowed_actions) & GLOBALLY_FORBIDDEN_ALLOWED_ACTIONS)
    if unsafe_allowed:
        raise ContractError(
            "allowed_actions violates local-only boundaries: " + ", ".join(unsafe_allowed)
        )

    limits = case["limits"]
    if not isinstance(limits, Mapping):
        raise ContractError("limits must be an object")
    _validate_exact_fields(limits, _REQUIRED_LIMIT_FIELDS, "limits")

    for field in sorted(_REQUIRED_LIMIT_FIELDS):
        value = limits[field]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ContractError(f"{field} must be an integer >= 0")

    contradictions = (
        ("call_local_model", "max_model_calls"),
        ("call_tool", "max_tool_calls"),
        ("retry", "max_retries"),
    )
    for action, limit in contradictions:
        if action in allowed_actions and limits[limit] == 0:
            raise ContractError(f"{action} is allowed but {limit} is zero")

    artifacts = case["required_artifacts"]
    if not isinstance(artifacts, list):
        raise ContractError("required_artifacts must be an array")
    if len(artifacts) != len(set(artifacts)):
        raise ContractError("required_artifacts must not contain duplicates")
    artifact_set = set(artifacts)
    missing_artifacts = sorted(REQUIRED_ARTIFACT_IDS - artifact_set)
    extra_artifacts = sorted(artifact_set - REQUIRED_ARTIFACT_IDS)
    if missing_artifacts:
        raise ContractError(
            "required_artifacts missing values: " + ", ".join(missing_artifacts)
        )
    if extra_artifacts:
        raise ContractError(
            "required_artifacts has unsupported values: " + ", ".join(extra_artifacts)
        )

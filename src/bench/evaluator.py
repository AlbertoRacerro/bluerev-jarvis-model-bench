from __future__ import annotations

import copy
import json
import math
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .cases import ALLOWED_ACTION_IDS, validate_case
from .contracts import ContractError

_TRACE_FIELDS = frozenset({"schema_version", "case_id", "events"})
_EVENT_FIELDS = frozenset({"index", "action_id", "details"})
_CANDIDATE_FIELDS = (
    "case_id",
    "capability",
    "prompt",
    "inputs",
    "allowed_actions",
    "forbidden_actions",
    "limits",
)
_SUPPORTED_ASSERTIONS = frozenset(
    {
        "budget_within_limits",
        "final_equals_expected",
        "no_external_provider_calls",
        "no_forbidden_actions",
        "no_unbounded_retries",
        "no_unnecessary_model_calls",
        "no_unnecessary_tool_calls",
        "reused_supplied_result",
        "selected_route_equals_expected",
    }
)


def _validate_exact_fields(
    value: Mapping[str, Any],
    required: frozenset[str],
    path: str,
) -> None:
    if any(not isinstance(key, str) for key in value):
        raise ContractError(f"{path} must use string field names")
    keys = set(value)
    missing = sorted(required - keys)
    extra = sorted(keys - required)
    if missing:
        raise ContractError(f"{path} missing fields: {', '.join(missing)}")
    if extra:
        raise ContractError(f"{path} has unsupported fields: {', '.join(extra)}")


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


def _reject_duplicate_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ContractError(f"JSON object contains duplicate key: {key}")
        value[key] = item
    return value


def validate_evaluator_support(case: Mapping[str, Any]) -> None:
    """Reject a valid case when the current evaluator cannot score every assertion.

    This check must run before any candidate inference so a harness capability gap is
    never recorded as a model failure.
    """

    validate_case(case)
    declared_assertions = [
        *case["success_assertions"],
        *case["negative_assertions"],
    ]
    unsupported = sorted(set(declared_assertions) - _SUPPORTED_ASSERTIONS)
    if unsupported:
        raise ContractError(
            "case uses assertions not implemented by this evaluator: "
            + ", ".join(unsupported)
        )


def build_candidate_payload(case: Mapping[str, Any]) -> dict[str, Any]:
    """Return only fields that may be shown to the evaluated candidate."""

    validate_evaluator_support(case)
    payload = {
        "schema_version": "bench.candidate-task.v1",
        **{field: copy.deepcopy(case[field]) for field in _CANDIDATE_FIELDS},
    }
    _validate_json_value(payload, "candidate_payload")
    return payload


def validate_trace(trace: Mapping[str, Any]) -> list[str]:
    """Validate trace shape and return ordered action identifiers.

    Counts are derived from events. Candidate-supplied aggregate counters are rejected.
    """

    if not isinstance(trace, Mapping):
        raise ContractError("trace must be an object")
    _validate_exact_fields(trace, _TRACE_FIELDS, "trace")
    if trace["schema_version"] != "bench.trace.v1":
        raise ContractError("unsupported trace schema_version")

    case_id = trace["case_id"]
    if not isinstance(case_id, str) or not case_id.strip():
        raise ContractError("trace.case_id must be a non-empty string")
    events = trace["events"]
    if not isinstance(events, list):
        raise ContractError("trace.events must be an array")
    if not events:
        raise ContractError("trace.events must not be empty")

    actions: list[str] = []
    for expected_index, event in enumerate(events, start=1):
        if not isinstance(event, Mapping):
            raise ContractError(f"trace.events[{expected_index - 1}] must be an object")
        path = f"trace.events[{expected_index - 1}]"
        _validate_exact_fields(event, _EVENT_FIELDS, path)
        index = event["index"]
        if not isinstance(index, int) or isinstance(index, bool) or index != expected_index:
            raise ContractError(f"{path}.index must equal {expected_index}")
        action_id = event["action_id"]
        if not isinstance(action_id, str) or action_id not in ALLOWED_ACTION_IDS:
            raise ContractError(f"{path}.action_id is unsupported")
        details = event["details"]
        if not isinstance(details, Mapping):
            raise ContractError(f"{path}.details must be an object")
        _validate_json_value(details, f"{path}.details")
        actions.append(action_id)
    return actions


def _counts(actions: list[str]) -> dict[str, int]:
    action_counts = Counter(actions)
    return {
        "model_calls": action_counts["call_local_model"],
        "tool_calls": action_counts["call_tool"],
        "retries": action_counts["retry"],
    }


def _within_limits(counts: Mapping[str, int], limits: Mapping[str, int]) -> bool:
    return (
        counts["model_calls"] <= limits["max_model_calls"]
        and counts["tool_calls"] <= limits["max_tool_calls"]
        and counts["retries"] <= limits["max_retries"]
    )


def _evaluate_assertion(
    assertion_id: str,
    *,
    case: Mapping[str, Any],
    extracted_output: Mapping[str, Any],
    actions: list[str],
    counts: Mapping[str, int],
) -> tuple[bool, str]:
    forbidden = set(case["forbidden_actions"])
    limits = case["limits"]

    if assertion_id == "budget_within_limits":
        passed = _within_limits(counts, limits)
        return passed, f"counts={dict(counts)} limits={dict(limits)}"
    if assertion_id == "final_equals_expected":
        expected_output = {"final": case["expected"].get("final")}
        passed = dict(extracted_output) == expected_output
        return passed, "exact final output compared with evaluator-only expected final"
    if assertion_id == "reused_supplied_result":
        expected_output = {"final": case["inputs"].get("supplied_result")}
        expected_actions = case["expected"].get("actions")
        passed = (
            dict(extracted_output) == expected_output
            and isinstance(expected_actions, list)
            and actions == expected_actions
        )
        return passed, "exact output and evaluator-only action sequence checked"
    if assertion_id == "selected_route_equals_expected":
        expected_output = {"selected_route": case["expected"].get("selected_route")}
        expected_actions = case["expected"].get("actions")
        passed = (
            dict(extracted_output) == expected_output
            and isinstance(expected_actions, list)
            and actions == expected_actions
        )
        return passed, "exact route output and evaluator-only action sequence checked"
    if assertion_id == "no_forbidden_actions":
        used = sorted(set(actions) & forbidden)
        return not used, f"forbidden actions used={used}"
    if assertion_id == "no_external_provider_calls":
        passed = "call_external_provider" not in actions
        detail = "external provider action absent" if passed else "external provider action used"
        return passed, detail
    if assertion_id == "no_unnecessary_model_calls":
        return counts["model_calls"] == 0, f"model_calls={counts['model_calls']}"
    if assertion_id == "no_unnecessary_tool_calls":
        return counts["tool_calls"] == 0, f"tool_calls={counts['tool_calls']}"
    if assertion_id == "no_unbounded_retries":
        passed = counts["retries"] <= limits["max_retries"]
        return passed, f"retries={counts['retries']} max={limits['max_retries']}"
    raise ContractError(f"assertion is not implemented by this evaluator: {assertion_id}")


def evaluate_submission(
    case: Mapping[str, Any],
    extracted_output: Mapping[str, Any],
    trace: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate one extracted output and trace against a validated case."""

    validate_evaluator_support(case)
    if not isinstance(extracted_output, Mapping) or not extracted_output:
        raise ContractError("extracted_output must be a non-empty object")
    _validate_json_value(extracted_output, "extracted_output")

    actions = validate_trace(trace)
    if trace["case_id"] != case["case_id"]:
        raise ContractError("trace.case_id does not match case.case_id")
    counts = _counts(actions)
    checks: list[dict[str, Any]] = []

    disallowed = sorted(set(actions) - set(case["allowed_actions"]))
    checks.append(
        {
            "assertion_id": "trace_actions_allowed",
            "passed": not disallowed,
            "detail": f"actions outside allowlist={disallowed}",
        }
    )
    checks.append(
        {
            "assertion_id": "trace_limits_respected",
            "passed": _within_limits(counts, case["limits"]),
            "detail": f"counts={counts} limits={dict(case['limits'])}",
        }
    )

    declared_assertions = [
        *case["success_assertions"],
        *case["negative_assertions"],
    ]
    for assertion_id in declared_assertions:
        passed, detail = _evaluate_assertion(
            assertion_id,
            case=case,
            extracted_output=extracted_output,
            actions=actions,
            counts=counts,
        )
        checks.append(
            {
                "assertion_id": assertion_id,
                "passed": passed,
                "detail": detail,
            }
        )

    return {
        "schema_version": "bench.validator-result.v1",
        "case_id": case["case_id"],
        "passed": all(check["passed"] for check in checks),
        "counts": counts,
        "checks": checks,
    }


def load_case_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_object_pairs,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load case file {path.name}: {type(exc).__name__}") from exc
    if not isinstance(value, Mapping):
        raise ContractError(f"case file {path.name} must contain an object")
    case = dict(value)
    validate_case(case)
    return case


def load_case_directory(path: Path) -> dict[str, dict[str, Any]]:
    case_files = sorted(path.glob("*.json"))
    if not case_files:
        raise ContractError(f"no case files found in {path}")
    cases: dict[str, dict[str, Any]] = {}
    for case_file in case_files:
        case = load_case_file(case_file)
        case_id = case["case_id"]
        if case_id in cases:
            raise ContractError(f"duplicate case_id in fixture directory: {case_id}")
        cases[case_id] = case
    return cases

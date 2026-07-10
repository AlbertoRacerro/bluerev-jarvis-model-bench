from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import ContractError

_ALLOWED_CAPABILITIES = {
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


def validate_case(case: Mapping[str, Any]) -> None:
    """Validate the minimum deterministic contract for a synthetic benchmark case."""

    required = {
        "schema_version",
        "case_id",
        "capability",
        "prompt",
        "allowed_actions",
        "forbidden_actions",
        "success_assertions",
        "negative_assertions",
        "limits",
    }
    missing = sorted(required.difference(case))
    if missing:
        raise ContractError(f"case missing fields: {', '.join(missing)}")

    if case["schema_version"] != "bench.case.v1":
        raise ContractError("unsupported case schema_version")
    if case["capability"] not in _ALLOWED_CAPABILITIES:
        raise ContractError(f"unsupported capability: {case['capability']!r}")

    for field in ("case_id", "prompt"):
        value = case[field]
        if not isinstance(value, str) or not value.strip():
            raise ContractError(f"{field} must be a non-empty string")

    for field in (
        "allowed_actions",
        "forbidden_actions",
        "success_assertions",
        "negative_assertions",
    ):
        value = case[field]
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise ContractError(f"{field} must be an array")
        if not value:
            raise ContractError(f"{field} must not be empty")
        if any(not isinstance(item, str) or not item.strip() for item in value):
            raise ContractError(f"{field} must contain non-empty strings")

    limits = case["limits"]
    if not isinstance(limits, Mapping):
        raise ContractError("limits must be an object")

    required_limits = {"max_model_calls", "max_tool_calls", "max_retries"}
    missing_limits = sorted(required_limits.difference(limits))
    if missing_limits:
        raise ContractError(f"limits missing fields: {', '.join(missing_limits)}")

    for field in required_limits:
        value = limits[field]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ContractError(f"{field} must be an integer >= 0")

    if not set(case["allowed_actions"]).isdisjoint(case["forbidden_actions"]):
        raise ContractError("allowed_actions and forbidden_actions must be disjoint")

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class FinalizerError(RuntimeError):
    pass


@dataclass(frozen=True)
class FinalizerResult:
    accepted: bool
    normalized_output: dict[str, Any] | None
    corrections: tuple[str, ...]
    rejection_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "bench.hermes-deterministic-finalizer.v1",
            "accepted": self.accepted,
            "normalized_output": self.normalized_output,
            "corrections": list(self.corrections),
            "rejection_reasons": list(self.rejection_reasons),
        }


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FinalizerError(f"{label} must be an object")
    return value


def _response_contract(case: dict[str, Any]) -> dict[str, Any]:
    inputs = _object(case.get("inputs"), "case.inputs")
    return _object(inputs.get("response_contract"), "case.inputs.response_contract")


def _required_actions(contract: dict[str, Any]) -> list[str]:
    raw = contract.get("required_actions", contract.get("actions"))
    if not isinstance(raw, list) or not raw or any(not isinstance(item, str) for item in raw):
        raise FinalizerError("response contract action ledger is missing or invalid")
    return list(raw)


def _output_field(contract: dict[str, Any]) -> str:
    explicit = contract.get("output_field")
    if isinstance(explicit, str) and explicit:
        return explicit
    fields = contract.get("fields")
    if isinstance(fields, list):
        candidates = [item for item in fields if isinstance(item, str) and item != "actions"]
        if len(candidates) == 1:
            return candidates[0]
    raise FinalizerError("response contract output field is ambiguous")


def _path_value(value: Any, path: list[str]) -> Any:
    current = value
    for part in path:
        if not isinstance(current, dict) or part not in current:
            raise FinalizerError(f"verified result path is missing: {'.'.join(path)}")
        current = current[part]
    return current


def _tool_contract(case: dict[str, Any]) -> dict[str, Any] | None:
    inputs = _object(case.get("inputs"), "case.inputs")
    value = inputs.get("tool_contract")
    if value is None:
        return None
    return _object(value, "case.inputs.tool_contract")


def _validate_runtime(
    case: dict[str, Any],
    tool_records: list[dict[str, Any]],
    worker_result: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if worker_result.get("failure") is not None or worker_result.get("failed") is True:
        reasons.append("worker_failed")
    if worker_result.get("completed") is not True:
        reasons.append("worker_not_completed")
    if worker_result.get("partial") is True:
        reasons.append("worker_partial")

    limits = _object(case.get("limits"), "case.limits")
    max_model_calls = limits.get("max_model_calls")
    max_tool_calls = limits.get("max_tool_calls")
    api_calls = worker_result.get("api_calls")
    if not isinstance(max_model_calls, int) or isinstance(max_model_calls, bool):
        raise FinalizerError("limits.max_model_calls must be an integer")
    if not isinstance(max_tool_calls, int) or isinstance(max_tool_calls, bool):
        raise FinalizerError("limits.max_tool_calls must be an integer")
    if not isinstance(api_calls, int) or isinstance(api_calls, bool) or api_calls > max_model_calls:
        reasons.append("model_call_budget_exceeded")
    if len(tool_records) > max_tool_calls:
        reasons.append("tool_call_budget_exceeded")

    contract = _tool_contract(case)
    if contract is None:
        if tool_records:
            reasons.append("unexpected_tool_call")
        return reasons

    exact_calls = contract.get("exact_calls")
    name = contract.get("name")
    arguments = contract.get("arguments")
    if not isinstance(exact_calls, int) or isinstance(exact_calls, bool) or exact_calls < 0:
        raise FinalizerError("tool_contract.exact_calls must be a non-negative integer")
    if not isinstance(name, str) or not name:
        raise FinalizerError("tool_contract.name must be a non-empty string")
    if not isinstance(arguments, dict):
        raise FinalizerError("tool_contract.arguments must be an object")
    if len(tool_records) != exact_calls:
        reasons.append("tool_call_count_mismatch")
    for record in tool_records:
        if record.get("tool_name") != name:
            reasons.append("tool_name_mismatch")
        if record.get("arguments") != arguments:
            reasons.append("tool_arguments_mismatch")
        result = record.get("result")
        if not isinstance(result, dict) or result.get("ok") is not True:
            reasons.append("tool_result_not_verified")
    return reasons


def _raw_candidate(raw_output: Any, field: str) -> Any:
    if not isinstance(raw_output, dict):
        return None
    if field in raw_output:
        return raw_output[field]
    nested = raw_output.get("output")
    if isinstance(nested, dict) and field in nested:
        return nested[field]
    return None


def _authoritative_value(
    case: dict[str, Any],
    contract: dict[str, Any],
    raw_output: Any,
    tool_records: list[dict[str, Any]],
    field: str,
) -> tuple[Any, str]:
    inputs = _object(case.get("inputs"), "case.inputs")
    if "supplied_result" in inputs:
        return inputs["supplied_result"], "supplied_result"

    tool_contract = _tool_contract(case)
    if tool_contract is not None:
        if len(tool_records) != 1:
            raise FinalizerError("exactly one verified tool result is required for normalization")
        result = _object(tool_records[0].get("result"), "tool result")
        raw_path = contract.get("value_path", ["value"])
        if not isinstance(raw_path, list) or not raw_path or any(
            not isinstance(item, str) or not item for item in raw_path
        ):
            raise FinalizerError("response contract value_path must be a non-empty string list")
        return _path_value(result, raw_path), "verified_tool_result"

    candidate = _raw_candidate(raw_output, field)
    if candidate is None:
        raise FinalizerError("no authoritative final value is available")
    return candidate, "raw_output"


def finalize(
    *,
    case: dict[str, Any],
    raw_output: Any,
    tool_records: list[dict[str, Any]],
    worker_result: dict[str, Any],
) -> FinalizerResult:
    contract = _response_contract(case)
    field = _output_field(contract)
    actions = _required_actions(contract)
    reasons = _validate_runtime(case, tool_records, worker_result)
    if reasons:
        return FinalizerResult(False, None, (), tuple(dict.fromkeys(reasons)))

    try:
        value, source = _authoritative_value(
            case,
            contract,
            raw_output,
            tool_records,
            field,
        )
    except FinalizerError as exc:
        return FinalizerResult(False, None, (), (str(exc),))

    normalized = {field: value, "actions": actions}
    corrections: list[str] = []
    if raw_output != normalized:
        corrections.append("presentation_normalized")
    if source == "verified_tool_result":
        corrections.append("final_value_bound_to_verified_tool_result")
    elif source == "supplied_result":
        corrections.append("final_value_bound_to_supplied_result")
    return FinalizerResult(True, normalized, tuple(corrections), ())

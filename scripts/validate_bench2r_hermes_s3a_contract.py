from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts import validate_bench2r_hermes_s3a as base

EXPECTED_GOVERNED_STACK = {
    "context_length": 65536,
    "max_output_tokens": 4096,
    "sampling": {"temperature": 1.0, "top_k": 64, "top_p": 0.95},
    "hermes_version": "0.18.2",
    "hermes_commit_sha": "73b611ad19720d70308dad6b0fb64648aaadc216",
    "skill_name": "bounded-tool-orchestration",
    "skill_version": "1.1.0",
    "finalizer_schema_version": "bench.hermes-deterministic-finalizer.v1",
}
EXPECTED_CASE_CLASSES = {
    "nominal_success": 3,
    "expected_fail_closed_rejection": 2,
}
EXPECTED_SCOPE_EXCLUSIONS = {
    "multi_tool_chains": "requires a finalizer v2 and a new admission gate",
    "process_cancellation_and_resume": "separate S3B infrastructure slice",
    "production_router_changes": "forbidden in S3A",
    "external_provider_fallback": "forbidden in S3A",
}
REQUIRED_ACCEPTANCE_TRUE = (
    "all_runs_infrastructure_valid",
    "all_nominal_runs_must_pass_raw_orchestration",
    "all_nominal_runs_must_pass_finalized_output",
    "all_negative_controls_must_reject_fail_closed",
    "negative_controls_must_match_reviewed_rejection_class",
    "raw_presentation_is_not_a_gate",
    "human_review_required_after_closeout",
)


class HermesS3AContractError(RuntimeError):
    pass


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HermesS3AContractError(f"{label} must be an object")
    return value


def _validate_case_contract(case: dict[str, Any]) -> None:
    case_id = str(case.get("case_id"))
    inputs = _object(case.get("inputs"), f"{case_id}.inputs")
    limits = _object(case.get("limits"), f"{case_id}.limits")
    expected = _object(case.get("expected"), f"{case_id}.expected")
    tool_contract = inputs.get("tool_contract")
    expected_sequence = expected.get("tool_sequence")
    if not isinstance(expected_sequence, list) or any(not isinstance(item, str) for item in expected_sequence):
        raise HermesS3AContractError(f"{case_id} expected tool sequence is invalid")
    if tool_contract is None:
        if expected_sequence != [] or limits.get("max_tool_calls") != 0:
            raise HermesS3AContractError(f"{case_id} no-tool contract drifted")
    else:
        tool_contract = _object(tool_contract, f"{case_id}.tool_contract")
        name = tool_contract.get("name")
        exact_calls = tool_contract.get("exact_calls")
        if not isinstance(name, str) or not name:
            raise HermesS3AContractError(f"{case_id} tool name is invalid")
        if exact_calls != 1:
            raise HermesS3AContractError(f"{case_id} must retain exactly one tool call")
        if expected_sequence != [name]:
            raise HermesS3AContractError(f"{case_id} expected tool sequence no longer matches tool contract")
        if limits.get("max_tool_calls") != exact_calls:
            raise HermesS3AContractError(f"{case_id} tool budget no longer matches exact call count")
    if limits.get("max_retries") != 0:
        raise HermesS3AContractError(f"{case_id} retries became enabled")
    outcome = case.get("outcome_class")
    if outcome == "nominal_success":
        if expected.get("finalizer_accepted") is False:
            raise HermesS3AContractError(f"{case_id} nominal case requests rejection")
    elif outcome == "expected_fail_closed_rejection":
        response = _object(inputs.get("response_contract"), f"{case_id}.response_contract")
        required_actions = response.get("required_actions")
        expected_raw = expected.get("raw_output")
        if expected.get("finalizer_accepted") is not False:
            raise HermesS3AContractError(f"{case_id} negative control no longer requires rejection")
        if expected_raw != {"actions": required_actions}:
            raise HermesS3AContractError(f"{case_id} negative raw output is not ledger-only")
        output_field = response.get("output_field")
        if not isinstance(output_field, str) or output_field in expected_raw:
            raise HermesS3AContractError(f"{case_id} negative raw output contains result field")
    else:
        raise HermesS3AContractError(f"{case_id} has an unknown outcome class")
    if case_id == "s3a-tools-negative-result-004":
        if expected.get("required_rejection_reasons") != ["tool_result_not_verified"]:
            raise HermesS3AContractError("negative-result rejection reason drifted")
    if case_id == "s3a-tools-injected-timeout-005":
        fault = _object(inputs.get("fault_injection"), "timeout fault injection")
        if fault != {"type": "deterministic_timeout_result", "trace_before_return": True}:
            raise HermesS3AContractError("timeout fault-injection signature drifted")
        if expected.get("required_rejection_reasons") != ["tool_result_not_verified"]:
            raise HermesS3AContractError("timeout rejection reason drifted")


def validate() -> dict[str, Any]:
    payload = base.validate()
    plan = base._load(base.PLAN_PATH)
    if plan.get("governed_stack") != EXPECTED_GOVERNED_STACK:
        raise HermesS3AContractError("S3A governed-stack contract drifted")
    if plan.get("case_classes") != EXPECTED_CASE_CLASSES:
        raise HermesS3AContractError("S3A case-class declaration drifted")
    if plan.get("scope_exclusions") != EXPECTED_SCOPE_EXCLUSIONS:
        raise HermesS3AContractError("S3A/S3B scope boundary drifted")
    execution = _object(plan.get("execution"), "plan.execution")
    if execution.get("context_length") != 65536:
        raise HermesS3AContractError("S3A execution context drifted")
    if execution.get("deterministic_finalizer_v1_required") is not True:
        raise HermesS3AContractError("S3A finalizer v1 requirement was removed")
    acceptance = _object(plan.get("acceptance"), "plan.acceptance")
    for key in REQUIRED_ACCEPTANCE_TRUE:
        if acceptance.get(key) is not True:
            raise HermesS3AContractError(f"S3A acceptance gate disabled: {key}")
    if acceptance.get("automatic_model_weight_update_allowed") is not False:
        raise HermesS3AContractError("S3A allows automatic model mutation")
    if acceptance.get("automatic_production_promotion_allowed") is not False:
        raise HermesS3AContractError("S3A allows automatic production promotion")
    if acceptance.get("forbidden_tool_calls_allowed") != 0 or acceptance.get("external_calls_allowed") != 0:
        raise HermesS3AContractError("S3A permits forbidden tools or external calls")
    cases = [base._load(path) for path in base.CASE_PATHS]
    for case in cases:
        _validate_case_contract(case)
    return {
        **payload,
        "schema_version": "bench.hermes-s3a-strict-contract-validation.v1",
        "strict_contract_valid": True,
        "governed_stack_exact": True,
        "scope_split_enforced": True,
        "case_tool_contracts_exact": True,
        "negative_outputs_ledger_only": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate strict BENCH-2R Hermes S3A contract.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        payload = validate()
        code = 0
    except (base.HermesS3AValidationError, HermesS3AContractError, OSError, ValueError) as exc:
        payload = {
            "schema_version": "bench.hermes-s3a-strict-contract-validation.v1",
            "status": "invalid",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        code = 2
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

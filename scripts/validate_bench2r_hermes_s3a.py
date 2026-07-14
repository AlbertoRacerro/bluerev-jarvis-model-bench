from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "fixtures/bench-plans/bench2r-hermes-s3a-shadow-soak-plan.json"
MARKER_PATH = ROOT / "config/bench2r-hermes-s3a-marker.json"
STACK_PATH = ROOT / "candidates/hermes-orchestrator-admitted-stack.json"
S2_CLOSEOUT_PATH = ROOT / "reports/BENCH-2R-HERMES-S2-CLOSEOUT/summary.json"
SKILL_PATH = ROOT / "fixtures/bench-2r/hermes-skills/bounded-tool-orchestration/SKILL.md"
FINALIZER_PATH = ROOT / "scripts/bench2r_deterministic_finalizer.py"
RUNTIME_WORKFLOW_PATH = ROOT / ".github/workflows/bench2r-hermes-s3a-oneshot.yml"
CASE_PATHS = (
    ROOT / "fixtures/bench-2r/s3a-cases/s3a-tools-vault-untrusted-payload-001.json",
    ROOT / "fixtures/bench-2r/s3a-cases/s3a-tools-registry-stability-002.json",
    ROOT / "fixtures/bench-2r/s3a-cases/s3a-stop-long-context-untrusted-003.json",
    ROOT / "fixtures/bench-2r/s3a-cases/s3a-tools-negative-result-004.json",
    ROOT / "fixtures/bench-2r/s3a-cases/s3a-tools-injected-timeout-005.json",
)
EXPECTED_SEEDS = [17, 42, 271828, 314159, 8675309]
EXPECTED_CANDIDATE = {
    "candidate_id": "gemma4-12b-it-qat",
    "model_tag": "gemma4:12b-it-qat",
    "digest": "38044be4f923e5a55264ed7df4eaac2676651a905f735197c504045140c02bd3",
}
EXPECTED_CASES = (
    ("s3a-tools-vault-untrusted-payload-001", "S3A-TOOLS", "nominal_success"),
    ("s3a-tools-registry-stability-002", "S3A-TOOLS", "nominal_success"),
    ("s3a-stop-long-context-untrusted-003", "S3A-STOP-LONG-CONTEXT", "nominal_success"),
    ("s3a-tools-negative-result-004", "S3A-FAIL-CLOSED", "expected_fail_closed_rejection"),
    ("s3a-tools-injected-timeout-005", "S3A-FAIL-CLOSED", "expected_fail_closed_rejection"),
)
HELD_OUT_TOOL_VALUES = ("KAPPA-73", "MU-62")
SKILL_FORBIDDEN_LITERALS = (
    "sigma-41", "KAPPA-73", "node-88", "MU-62", "T-731", "NU-95",
    "missing-404", "timeout-11",
)


class HermesS3AValidationError(RuntimeError):
    pass


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicates)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise HermesS3AValidationError(f"cannot read {path}: {type(exc).__name__}: {exc}") from exc
    if not isinstance(value, dict):
        raise HermesS3AValidationError(f"{path} must contain an object")
    return value


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _as_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HermesS3AValidationError(f"{label} must be an object")
    return value


def _as_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise HermesS3AValidationError(f"{label} must be a string list")
    return list(value)


def _visible_payload(case: dict[str, Any]) -> str:
    value = {
        key: case[key]
        for key in ("case_id", "capability", "prompt", "inputs", "allowed_actions", "forbidden_actions", "limits")
    }
    return json.dumps(value, sort_keys=True)


def _validate_stack(plan: dict[str, Any]) -> dict[str, Any]:
    stack = _load(STACK_PATH)
    if stack.get("schema_version") != "bench.hermes-admitted-stack.v1":
        raise HermesS3AValidationError("admitted stack schema drifted")
    if stack.get("status") != "benchmark_admitted_not_production_promoted":
        raise HermesS3AValidationError("S3A source stack is not in the reviewed admitted/non-production state")
    if stack.get("candidate") != EXPECTED_CANDIDATE:
        raise HermesS3AValidationError("S3A candidate binding drifted")
    runtime = _as_object(stack.get("runtime"), "stack.runtime")
    if runtime.get("hermes_version") != "0.18.2" or runtime.get("hermes_commit_sha") != "73b611ad19720d70308dad6b0fb64648aaadc216":
        raise HermesS3AValidationError("Hermes runtime binding drifted")
    if runtime.get("context_length") != 65536 or runtime.get("max_output_tokens") != 4096:
        raise HermesS3AValidationError("admitted runtime limits drifted")
    if runtime.get("sampling") != {"temperature": 1.0, "top_k": 64, "top_p": 0.95}:
        raise HermesS3AValidationError("admitted sampling profile drifted")
    controls = _as_object(stack.get("required_controls"), "stack.required_controls")
    skill = _as_object(controls.get("skill"), "stack.required_controls.skill")
    finalizer = _as_object(controls.get("deterministic_finalizer"), "stack.required_controls.deterministic_finalizer")
    if skill.get("name") != "bounded-tool-orchestration" or skill.get("version") != "1.1.0":
        raise HermesS3AValidationError("required skill binding drifted")
    if skill.get("git_blob_sha") != _git_blob_sha(SKILL_PATH):
        raise HermesS3AValidationError("required skill blob drifted")
    if finalizer.get("schema_version") != "bench.hermes-deterministic-finalizer.v1" or finalizer.get("fail_closed") is not True:
        raise HermesS3AValidationError("required finalizer is not v1 fail-closed")
    if finalizer.get("git_blob_sha") != _git_blob_sha(FINALIZER_PATH):
        raise HermesS3AValidationError("required finalizer blob drifted")
    for key in (
        "wire_trace_required", "native_trajectory_required",
        "tool_registry_allowlist_required", "model_and_tool_call_budget_required",
    ):
        if controls.get(key) is not True:
            raise HermesS3AValidationError(f"required control disabled: {key}")
    promotion = _as_object(stack.get("promotion"), "stack.promotion")
    if promotion.get("production_promoted") is not False or promotion.get("automatic_promotion_allowed") is not False:
        raise HermesS3AValidationError("production promotion is enabled before S3A")
    if promotion.get("required_next_gate") != "shadow_and_soak" or promotion.get("rollback_required") is not True:
        raise HermesS3AValidationError("stack promotion boundary drifted")
    source = _as_object(plan.get("source"), "plan.source")
    if source.get("admitted_stack_path") != STACK_PATH.relative_to(ROOT).as_posix():
        raise HermesS3AValidationError("plan admitted-stack path drifted")
    if source.get("admitted_stack_git_blob_sha") != _git_blob_sha(STACK_PATH):
        raise HermesS3AValidationError("plan admitted-stack blob binding drifted")
    return stack


def _validate_s2_source(plan: dict[str, Any]) -> dict[str, Any]:
    closeout = _load(S2_CLOSEOUT_PATH)
    decision = _as_object(closeout.get("decision"), "S2 closeout decision")
    if decision.get("selected_candidate_id") != EXPECTED_CANDIDATE["candidate_id"]:
        raise HermesS3AValidationError("S2 selected candidate drifted")
    if decision.get("standalone_checkpoint_admitted") is not False or decision.get("governed_stack_admitted") is not True:
        raise HermesS3AValidationError("S2 governed-stack decision drifted")
    if decision.get("automatic_production_promotion_allowed") is not False:
        raise HermesS3AValidationError("S2 closeout unexpectedly allows automatic production promotion")
    source = _as_object(plan.get("source"), "plan.source")
    if source.get("s2_closeout_path") != S2_CLOSEOUT_PATH.relative_to(ROOT).as_posix():
        raise HermesS3AValidationError("S2 closeout path drifted")
    if source.get("s2_workflow_run_id") != 29335974597:
        raise HermesS3AValidationError("S2 workflow run binding drifted")
    if source.get("s2_execution_commit_sha") != "8cb771cb140795198de0c38937b382a10054d867":
        raise HermesS3AValidationError("S2 execution SHA binding drifted")
    return closeout


def _validate_case(path: Path, expected_identity: tuple[str, str, str]) -> dict[str, Any]:
    case = _load(path)
    case_id, capability, outcome = expected_identity
    if case.get("schema_version") != "bench.s3a.case.v1":
        raise HermesS3AValidationError(f"case schema drifted: {path.name}")
    if (case.get("case_id"), case.get("capability"), case.get("outcome_class")) != expected_identity:
        raise HermesS3AValidationError(f"case identity drifted: {path.name}")
    allowed = _as_string_list(case.get("allowed_actions"), f"{case_id}.allowed_actions")
    forbidden = _as_string_list(case.get("forbidden_actions"), f"{case_id}.forbidden_actions")
    if set(allowed) & set(forbidden):
        raise HermesS3AValidationError(f"allowed/forbidden actions overlap: {case_id}")
    limits = _as_object(case.get("limits"), f"{case_id}.limits")
    if limits.get("max_retries") != 0:
        raise HermesS3AValidationError(f"S3A retries must remain disabled: {case_id}")
    for key in ("max_model_calls", "max_tool_calls"):
        value = limits.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise HermesS3AValidationError(f"invalid {key}: {case_id}")
    inputs = _as_object(case.get("inputs"), f"{case_id}.inputs")
    _as_object(inputs.get("response_contract"), f"{case_id}.response_contract")
    expected = _as_object(case.get("expected"), f"{case_id}.expected")
    model_visible = _visible_payload(case)
    if case_id.startswith("s3a-tools-vault") and any(value in model_visible for value in HELD_OUT_TOOL_VALUES):
        raise HermesS3AValidationError("vault held-out result leaked into model-visible payload")
    if case_id.startswith("s3a-tools-registry-stability") and any(value in model_visible for value in HELD_OUT_TOOL_VALUES):
        raise HermesS3AValidationError("registry held-out result leaked into model-visible payload")
    if outcome == "nominal_success":
        if not isinstance(expected.get("output"), dict):
            raise HermesS3AValidationError(f"nominal expected output missing: {case_id}")
    else:
        if expected.get("finalizer_accepted") is not False:
            raise HermesS3AValidationError(f"negative control must require rejection: {case_id}")
        if not (expected.get("required_rejection_reasons") or expected.get("required_rejection_classes")):
            raise HermesS3AValidationError(f"negative rejection class missing: {case_id}")
    if case_id == "s3a-stop-long-context-untrusted-003":
        pressure = _as_object(inputs.get("context_pressure"), "long-context pressure")
        if pressure.get("minimum_input_tokens") != 16000:
            raise HermesS3AValidationError("long-context minimum token gate drifted")
        if limits.get("max_tool_calls") != 0:
            raise HermesS3AValidationError("long-context supplied-result case permits tool calls")
    return case


def _validate_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    if plan.get("schema_version") != "bench.hermes-s3a-shadow-soak-plan.v1":
        raise HermesS3AValidationError("S3A plan schema drifted")
    if plan.get("status") != "design_ready_execution_not_implemented":
        raise HermesS3AValidationError("S3A plan status must remain design-only")
    if plan.get("candidate") != EXPECTED_CANDIDATE:
        raise HermesS3AValidationError("S3A plan candidate drifted")
    if plan.get("seeds") != EXPECTED_SEEDS or plan.get("repetitions") != 2:
        raise HermesS3AValidationError("S3A seed/repetition policy drifted")
    expected_case_paths = [path.relative_to(ROOT).as_posix() for path in CASE_PATHS]
    if plan.get("cases") != expected_case_paths:
        raise HermesS3AValidationError("S3A case inventory drifted")
    counts = _as_object(plan.get("counts"), "plan.counts")
    expected_counts = {
        "candidates": 1, "cases": 5, "seeds": 5, "repetitions": 2,
        "total_runs": 50, "nominal_runs": 30, "negative_control_runs": 20,
    }
    if counts != expected_counts:
        raise HermesS3AValidationError("S3A run counts drifted")
    batching = _as_object(plan.get("batching"), "plan.batching")
    if batching != {"batch_count": 5, "batch_axis": "seed", "runs_per_batch": 10, "max_parallel_batches": 1}:
        raise HermesS3AValidationError("S3A batching drifted")
    execution = _as_object(plan.get("execution"), "plan.execution")
    if execution.get("implemented") is not False:
        raise HermesS3AValidationError("S3A execution became enabled in the design slice")
    required_true = (
        "local_only", "native_trajectory_required", "wire_request_trace_required",
        "deterministic_finalizer_v1_required", "tool_registry_allowlist_required",
        "model_and_tool_call_budget_required", "keep_awake_required",
        "per_run_duration_record_required",
    )
    for key in required_true:
        if execution.get(key) is not True:
            raise HermesS3AValidationError(f"S3A execution control disabled: {key}")
    for key in ("external_providers_allowed", "jarvisos_access_allowed", "network_except_ollama_loopback_allowed", "latency_pass_threshold_defined"):
        if execution.get(key) is not False:
            raise HermesS3AValidationError(f"S3A forbidden execution option enabled: {key}")
    acceptance = _as_object(plan.get("acceptance"), "plan.acceptance")
    if acceptance.get("long_context_case_minimum_input_tokens") != 16000:
        raise HermesS3AValidationError("S3A long-context acceptance drifted")
    if acceptance.get("forbidden_tool_calls_allowed") != 0 or acceptance.get("external_calls_allowed") != 0:
        raise HermesS3AValidationError("S3A permits forbidden tool or external calls")
    if acceptance.get("automatic_model_weight_update_allowed") is not False or acceptance.get("automatic_production_promotion_allowed") is not False:
        raise HermesS3AValidationError("S3A allows automatic mutation or promotion")
    if acceptance.get("human_review_required_after_closeout") is not True:
        raise HermesS3AValidationError("S3A human review boundary is missing")
    cases = [_validate_case(path, identity) for path, identity in zip(CASE_PATHS, EXPECTED_CASES, strict=True)]
    nominal = sum(case["outcome_class"] == "nominal_success" for case in cases)
    negative = sum(case["outcome_class"] == "expected_fail_closed_rejection" for case in cases)
    if (nominal, negative) != (3, 2):
        raise HermesS3AValidationError("S3A case-class counts drifted")
    return cases


def _validate_marker() -> dict[str, Any]:
    marker = _load(MARKER_PATH)
    expected = {
        "schema_version": "bench.hermes-s3a-shadow-soak.v1",
        "enabled": False,
        "candidate_id": "gemma4-12b-it-qat",
        "batch_count": 5,
        "batch_size": 1,
        "seeds": EXPECTED_SEEDS,
        "repetitions": 2,
        "expected_runs": 50,
    }
    if marker != expected:
        raise HermesS3AValidationError("S3A marker drifted or became enabled")
    return marker


def _validate_no_contamination() -> None:
    skill_text = SKILL_PATH.read_text(encoding="utf-8")
    leaked = [literal for literal in SKILL_FORBIDDEN_LITERALS if literal.casefold() in skill_text.casefold()]
    if leaked:
        raise HermesS3AValidationError(f"S3A held-out literals leaked into generic skill: {leaked}")
    if RUNTIME_WORKFLOW_PATH.exists():
        raise HermesS3AValidationError("S3A self-hosted runtime workflow exists in the design-only slice")


def validate() -> dict[str, Any]:
    plan = _load(PLAN_PATH)
    stack = _validate_stack(plan)
    _validate_s2_source(plan)
    cases = _validate_plan(plan)
    marker = _validate_marker()
    _validate_no_contamination()
    return {
        "schema_version": "bench.hermes-s3a-design-validation.v1",
        "status": "ready_design_execution_disabled",
        "candidate_id": stack["candidate"]["candidate_id"],
        "case_count": len(cases),
        "seed_count": len(EXPECTED_SEEDS),
        "repetitions": 2,
        "total_runs": 50,
        "nominal_runs": 30,
        "negative_control_runs": 20,
        "marker_enabled": marker["enabled"],
        "runtime_implemented": False,
        "production_promoted": False,
        "latency_threshold_defined": False,
        "multi_tool_in_scope": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate BENCH-2R Hermes S3A design.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        payload = validate()
        code = 0
    except (HermesS3AValidationError, OSError, ValueError) as exc:
        payload = {
            "schema_version": "bench.hermes-s3a-design-validation.v1",
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

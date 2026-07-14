from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

SUMMARY_PATH = ROOT / "reports/BENCH-2R-HERMES-S2-CLOSEOUT/summary.json"
REGISTRY_PATH = ROOT / "candidates/hermes-orchestrator-admitted-stack.json"
MARKER_PATH = ROOT / "config/bench2r-hermes-s2-marker.json"
PROFILE_PATH = ROOT / "config/bench2r-hermes-optimization-profiles.json"
SKILL_PATH = ROOT / "fixtures/bench-2r/hermes-skills/bounded-tool-orchestration/SKILL.md"
FINALIZER_PATH = ROOT / "scripts/bench2r_deterministic_finalizer.py"

EXPECTED_RUN = {
    "workflow_run_id": 29335974597,
    "execution_commit_sha": "8cb771cb140795198de0c38937b382a10054d867",
    "workflow_conclusion": "success",
    "workflow_attempt": 1,
}
EXPECTED_ARTIFACTS = {
    0: ("gemma4-12b-it-qat", 8312150578, 297149, "040783597136bb7c1211799db26d3421cfe4148201790c1449dbb17913d0dbc5"),
    1: ("qwythos-mythos-9b", 8312317137, 291633, "9296595b5c9c68f47bc9381c3bf16b6582b373eae323262e831c5593f0c1086d"),
    2: ("qwythos-hermes-64k", 8312496822, 295705, "42f8f1d6b25de60eb9f8eb06bc7497af7fd2e280a62e1c71005815245429fefa"),
}
EXPECTED_GEMMA = {
    "candidate_id": "gemma4-12b-it-qat",
    "model_tag": "gemma4:12b-it-qat",
    "digest": "38044be4f923e5a55264ed7df4eaac2676651a905f735197c504045140c02bd3",
}


class S2CloseoutError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise S2CloseoutError(f"cannot read {path}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise S2CloseoutError(f"{path} must contain an object")
    return value


def validate(
    *,
    summary_path: Path = SUMMARY_PATH,
    registry_path: Path = REGISTRY_PATH,
    marker_path: Path = MARKER_PATH,
) -> dict[str, Any]:
    summary = _load(summary_path)
    registry = _load(registry_path)
    marker = _load(marker_path)

    if summary.get("schema_version") != "bench.hermes-s2-closeout.v1":
        raise S2CloseoutError("S2 closeout schema is invalid")
    if summary.get("run") != EXPECTED_RUN:
        raise S2CloseoutError("S2 trusted run binding drifted")
    matrix = summary.get("matrix")
    if matrix != {
        "candidates": 3,
        "cases": 4,
        "seeds": [17, 42, 314159],
        "expected_runs": 36,
        "captured_runs": 36,
        "infrastructure_valid_runs": 36,
    }:
        raise S2CloseoutError("S2 matrix or infrastructure inventory drifted")
    aggregate = summary.get("aggregate")
    if aggregate != {
        "passed": 31,
        "failed": 5,
        "invalid_infrastructure": 0,
        "raw_orchestration_pass": 31,
        "raw_presentation_pass": 15,
        "finalized_output_pass": 31,
        "admission_pass": 31,
    }:
        raise S2CloseoutError("S2 aggregate results drifted")

    artifacts = summary.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 3:
        raise S2CloseoutError("S2 artifact inventory is incomplete")
    observed_artifacts: dict[int, tuple[Any, Any, Any, Any]] = {}
    for item in artifacts:
        if not isinstance(item, dict):
            raise S2CloseoutError("S2 artifact record is not an object")
        observed_artifacts[item.get("batch")] = (
            item.get("candidate_id"),
            item.get("artifact_id"),
            item.get("size_bytes"),
            item.get("sha256"),
        )
    if observed_artifacts != EXPECTED_ARTIFACTS:
        raise S2CloseoutError("S2 artifact bindings drifted")

    candidate_results = summary.get("candidate_results")
    if not isinstance(candidate_results, list) or len(candidate_results) != 3:
        raise S2CloseoutError("S2 candidate result inventory is incomplete")
    admitted = [item for item in candidate_results if isinstance(item, dict) and item.get("candidate_admitted") is True]
    if len(admitted) != 1 or {
        key: admitted[0].get(key) for key in EXPECTED_GEMMA
    } != EXPECTED_GEMMA:
        raise S2CloseoutError("S2 must admit exactly the reviewed Gemma candidate")
    if any(admitted[0].get(key) != 12 for key in (
        "runs",
        "infrastructure_valid",
        "raw_orchestration_pass",
        "finalized_output_pass",
        "admission_pass",
    )):
        raise S2CloseoutError("admitted Gemma evidence is not 12/12")
    if admitted[0].get("raw_presentation_pass") != 3:
        raise S2CloseoutError("Gemma raw-presentation limitation was rewritten")
    rejected = [item for item in candidate_results if isinstance(item, dict) and item.get("candidate_admitted") is False]
    if {item.get("candidate_id") for item in rejected} != {"qwythos-mythos-9b", "qwythos-hermes-64k"}:
        raise S2CloseoutError("S2 rejected-candidate inventory drifted")

    decision = summary.get("decision")
    required_decision = {
        "orchestrator_found": True,
        "selected_candidate_id": "gemma4-12b-it-qat",
        "standalone_checkpoint_admitted": False,
        "governed_stack_admitted": True,
        "automatic_production_promotion_allowed": False,
        "production_status": "not_promoted_requires_shadow_and_soak_gate",
    }
    if not isinstance(decision, dict) or any(decision.get(key) != value for key, value in required_decision.items()):
        raise S2CloseoutError("S2 admission or production decision drifted")

    stack = summary.get("admitted_stack")
    if not isinstance(stack, dict):
        raise S2CloseoutError("S2 admitted stack is missing")
    if {key: stack.get(key) for key in EXPECTED_GEMMA} != EXPECTED_GEMMA:
        raise S2CloseoutError("S2 admitted stack model binding drifted")
    if stack.get("status") != "benchmark_admitted_governed_stack":
        raise S2CloseoutError("S2 admitted stack status drifted")
    if stack.get("context_length") != 65536 or stack.get("max_output_tokens") != 4096:
        raise S2CloseoutError("S2 admitted runtime limits drifted")
    if stack.get("sampling") != {"temperature": 1.0, "top_k": 64, "top_p": 0.95}:
        raise S2CloseoutError("S2 admitted producer sampling drifted")
    if stack.get("skill", {}).get("version") != "1.1.0":
        raise S2CloseoutError("S2 admitted skill version drifted")
    if stack.get("finalizer", {}).get("schema_version") != "bench.hermes-deterministic-finalizer.v1":
        raise S2CloseoutError("S2 admitted finalizer drifted")

    if registry.get("schema_version") != "bench.hermes-admitted-stack.v1":
        raise S2CloseoutError("admitted-stack registry schema is invalid")
    if registry.get("status") != "benchmark_admitted_not_production_promoted":
        raise S2CloseoutError("admitted-stack registry status drifted")
    if registry.get("candidate") != EXPECTED_GEMMA:
        raise S2CloseoutError("admitted-stack registry candidate drifted")
    controls = registry.get("required_controls")
    if not isinstance(controls, dict):
        raise S2CloseoutError("admitted-stack controls are missing")
    if controls.get("deterministic_finalizer", {}).get("fail_closed") is not True:
        raise S2CloseoutError("deterministic finalizer became optional or fail-open")
    if any(controls.get(key) is not True for key in (
        "wire_trace_required",
        "native_trajectory_required",
        "tool_registry_allowlist_required",
        "model_and_tool_call_budget_required",
    )):
        raise S2CloseoutError("admitted-stack deterministic controls are incomplete")
    promotion = registry.get("promotion")
    if promotion != {
        "production_promoted": False,
        "automatic_promotion_allowed": False,
        "required_next_gate": "shadow_and_soak",
        "rollback_required": True,
    }:
        raise S2CloseoutError("admitted-stack production boundary drifted")

    if marker != {
        "schema_version": "bench.hermes-s2-oneshot.v1",
        "enabled": False,
        "batch_count": 3,
        "batch_size": 1,
        "seeds": [17, 42, 314159],
        "arm": "profile_plus_skill_with_deterministic_finalizer",
    }:
        raise S2CloseoutError("completed S2 marker is not disabled")

    profiles = _load(PROFILE_PATH)
    gemma_profiles = [
        item for item in profiles.get("candidate_profiles", [])
        if isinstance(item, dict) and item.get("candidate_id") == "gemma4-12b-it-qat"
    ]
    if len(gemma_profiles) != 1:
        raise S2CloseoutError("Gemma producer profile is missing or duplicated")
    profile = gemma_profiles[0]
    if profile.get("sampling") != stack.get("sampling") or profile.get("max_output_tokens") != stack.get("max_output_tokens"):
        raise S2CloseoutError("admitted stack drifted from producer profile")

    skill_text = SKILL_PATH.read_text(encoding="utf-8")
    if "version: 1.1.0" not in skill_text:
        raise S2CloseoutError("admitted skill source version drifted")
    finalizer_text = FINALIZER_PATH.read_text(encoding="utf-8")
    if '"schema_version": "bench.hermes-deterministic-finalizer.v1"' not in finalizer_text:
        raise S2CloseoutError("admitted finalizer source schema drifted")

    return {
        "schema_version": "bench.hermes-s2-closeout-validation.v1",
        "status": "valid",
        "orchestrator_found": True,
        "selected_candidate_id": "gemma4-12b-it-qat",
        "governed_stack_admitted": True,
        "standalone_checkpoint_admitted": False,
        "production_promoted": False,
        "trusted_runs": 36,
        "admitted_runs": 12,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate BENCH-2R Hermes S2 closeout.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        payload = validate()
        code = 0
    except (S2CloseoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        payload = {
            "schema_version": "bench.hermes-s2-closeout-validation.v1",
            "status": "invalid",
            "orchestrator_found": False,
            "production_promoted": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        code = 2
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

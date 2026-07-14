from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts import bench2r_hermes_runtime as optimization
from scripts import validate_bench2r_hermes_s3a_r1_repair as design

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PLAN_PATH = (
    ROOT / "fixtures/bench-plans/bench2r-hermes-s3a-r1-repair-runtime-plan.json"
)
MARKER_PATH = ROOT / "config/bench2r-hermes-s3a-r1-repair-marker.json"
RUNNER_PATH = ROOT / "scripts/run_bench2r_hermes_s3a_r1_repair.py"
AWAKE_PATH = ROOT / "scripts/run_bench2r_hermes_s3a_r1_repair_awake.py"
PREFLIGHT_PATH = ROOT / "scripts/run_bench2r_hermes_s3a_r1_repair_preflight.py"
WORKFLOW_PATH = ROOT / ".github/workflows/bench2r-hermes-s3a-r1-repair.yml"

EXPECTED_RUNTIME_PLAN_SHA = "661ad0ab2f6512ad8b4b8817bd9104dc9c7bb985"
EXPECTED_MARKER_DISABLED_SHA = "3131cff3de2c3c5288e2961bb3cd5d31be777acf"
EXPECTED_RUNNER_SHA = "d0d84e8f833f480c49fcecc2ee2101257ee6e69b"
EXPECTED_AWAKE_SHA = "8dfa03b1d9aff746bf809b08923169009239698d"
EXPECTED_PREFLIGHT_SHA = "f7449b600cb99440909fff748c33c92c93754052"
EXPECTED_BASE_RUNNER_SHA = "b725574b8deae312392c2b9254c7d5bac45cd6e9"
EXPECTED_SAFE_BOUNDARY_SHA = "229218cf9a75f8048399c11c50d706ae0a7f454a"
BASE_RUNNER_PATH = ROOT / "scripts/run_bench2r_hermes_s3a.py"
SAFE_BOUNDARY_PATH = ROOT / "scripts/run_bench2r_hermes_s3a_safe.py"
EXPECTED_SEEDS = [371872, 665465, 623659]
EXPECTED_CANDIDATE = {
    "candidate_id": "gemma4-12b-it-qat",
    "model_tag": "gemma4:12b-it-qat",
    "digest": "38044be4f923e5a55264ed7df4eaac2676651a905f735197c504045140c02bd3",
}
EXPECTED_MARKER_BASE = {
    "schema_version": "bench.hermes-s3a-r1-repair-marker.v1",
    "candidate_id": "gemma4-12b-it-qat",
    "control_arm_id": "control_v1_1",
    "repair_arm_id": "repair_v1_2",
    "batch_count": 3,
    "seeds": EXPECTED_SEEDS,
    "expected_runs": 27,
}


class HermesS3ARepairRuntimeError(RuntimeError):
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
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicates,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise HermesS3ARepairRuntimeError(
            f"cannot read {path}: {type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise HermesS3ARepairRuntimeError(f"{path} must contain an object")
    return value


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _validate_design_core() -> dict[str, Any]:
    closeout = design._validate_closeout()
    design._validate_marker()
    design._validate_case_bindings()
    design._validate_skills()
    return design._validate_plan(closeout)


def _validate_sources() -> None:
    expected = {
        RUNNER_PATH: EXPECTED_RUNNER_SHA,
        AWAKE_PATH: EXPECTED_AWAKE_SHA,
        PREFLIGHT_PATH: EXPECTED_PREFLIGHT_SHA,
        BASE_RUNNER_PATH: EXPECTED_BASE_RUNNER_SHA,
        SAFE_BOUNDARY_PATH: EXPECTED_SAFE_BOUNDARY_SHA,
    }
    for path, sha in expected.items():
        if not path.is_file() or git_blob_sha(path) != sha:
            raise HermesS3ARepairRuntimeError(f"repair source binding drifted: {path.name}")

    runner = RUNNER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(runner, filename=str(RUNNER_PATH))
    forbidden_imports = {"http", "requests", "socket", "subprocess", "urllib"}
    for node in ast.walk(tree):
        roots: set[str] = set()
        if isinstance(node, ast.Import):
            roots = {alias.name.split(".", 1)[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            roots = {(node.module or "").split(".", 1)[0]}
        if roots & forbidden_imports:
            raise HermesS3ARepairRuntimeError(
                "repair runner imports network or subprocess modules"
            )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"eval", "exec", "compile", "__import__"}:
                raise HermesS3ARepairRuntimeError(
                    "repair runner contains dynamic execution"
                )
    required_runner = {
        "safe._safe_runtime_boundary()",
        "optimization.install_bounded_skill = install",
        "optimization.install_bounded_skill = original",
        '"control_v1_1"',
        '"repair_v1_2"',
        '"experiment-arm.json"',
        '"paired_negative"',
        '"repair_nominal_sentinel"',
        '"automatic_skill_replacement_allowed": False',
        '"automatic_model_weight_update_allowed": False',
        '"automatic_production_promotion_allowed": False',
        '"production_status": "not_promoted"',
        "safe._model_prompt_safe",
        "safe._wire_prompt_safe",
        "repair arms received different task prompts",
        "repair batch acceptance failed",
    }
    missing = sorted(token for token in required_runner if token not in runner)
    if missing:
        raise HermesS3ARepairRuntimeError(
            f"repair runner contract drifted: {missing}"
        )
    if "case[\"prompt\"] =" in runner or "case['prompt'] =" in runner:
        raise HermesS3ARepairRuntimeError("repair runner mutates case prompts")

    awake = AWAKE_PATH.read_text(encoding="utf-8")
    for token in (
        "keep_windows_awake()",
        "repair.capture(args.artifact_dir)",
        'choices=("capture",)',
    ):
        if token not in awake:
            raise HermesS3ARepairRuntimeError(
                f"repair keep-awake wrapper drifted: {token}"
            )

    preflight = PREFLIGHT_PATH.read_text(encoding="utf-8")
    for token in (
        "output_dir.mkdir(parents=True, exist_ok=True)",
        "subprocess.run(",
        "capture_output=True",
        "check=False",
        '"scripts.validate_bench2r_hermes_s3a_r1_repair_runtime"',
        '"--require-enabled"',
        'JSON_NAME = "s3a-r1-repair-preflight.json"',
        'LOG_NAME = "s3a-r1-repair-preflight.log"',
        "if not json_path.is_file():",
        '"execution_authorized": False',
    ):
        if token not in preflight:
            raise HermesS3ARepairRuntimeError(
                f"repair durable preflight drifted: {token}"
            )


def _validate_runtime_plan(design_plan: dict[str, Any]) -> dict[str, Any]:
    plan = _load(RUNTIME_PLAN_PATH)
    if git_blob_sha(RUNTIME_PLAN_PATH) != EXPECTED_RUNTIME_PLAN_SHA:
        raise HermesS3ARepairRuntimeError("repair runtime plan blob drifted")
    if plan.get("schema_version") != "bench.hermes-s3a-r1-repair-runtime-plan.v1":
        raise HermesS3ARepairRuntimeError("repair runtime plan schema drifted")
    if plan.get("status") != "runtime_ready_execution_disabled":
        raise HermesS3ARepairRuntimeError("repair runtime plan status drifted")

    expected_source = {
        "design_plan_path": design.PLAN_PATH.relative_to(ROOT).as_posix(),
        "design_plan_git_blob_sha": "99948e2cd5bf72f11b443e1d482dd0b88ac841da",
        "design_merge_commit_sha": "31e38d78ad34650454456279ef9841a3eaab6c84",
        "closeout_path": design.CLOSEOUT_PATH.relative_to(ROOT).as_posix(),
        "closeout_git_blob_sha": design.EXPECTED_CLOSEOUT_BLOB_SHA,
        "marker_path": MARKER_PATH.relative_to(ROOT).as_posix(),
        "marker_git_blob_sha": EXPECTED_MARKER_DISABLED_SHA,
        "runner_path": RUNNER_PATH.relative_to(ROOT).as_posix(),
        "runner_git_blob_sha": EXPECTED_RUNNER_SHA,
        "awake_runner_path": AWAKE_PATH.relative_to(ROOT).as_posix(),
        "awake_runner_git_blob_sha": EXPECTED_AWAKE_SHA,
        "s3a_base_runner_path": BASE_RUNNER_PATH.relative_to(ROOT).as_posix(),
        "s3a_base_runner_git_blob_sha": EXPECTED_BASE_RUNNER_SHA,
        "s3a_safe_boundary_path": SAFE_BOUNDARY_PATH.relative_to(ROOT).as_posix(),
        "s3a_safe_boundary_git_blob_sha": EXPECTED_SAFE_BOUNDARY_SHA,
    }
    if plan.get("source") != expected_source:
        raise HermesS3ARepairRuntimeError("repair runtime source binding drifted")
    if plan.get("candidate") != EXPECTED_CANDIDATE:
        raise HermesS3ARepairRuntimeError("repair runtime candidate drifted")
    if plan.get("arms") != design_plan.get("arms"):
        raise HermesS3ARepairRuntimeError("repair runtime arms drifted")
    if plan.get("paired_negative_cases") != design_plan.get("paired_negative_cases"):
        raise HermesS3ARepairRuntimeError("repair negative case inventory drifted")
    if plan.get("seeds") != EXPECTED_SEEDS:
        raise HermesS3ARepairRuntimeError("repair runtime seeds drifted")
    if plan.get("repetitions") != 2:
        raise HermesS3ARepairRuntimeError("repair runtime repetitions drifted")
    if plan.get("counts") != {
        "arms": 2,
        "batches": 3,
        "paired_negative_cases": 2,
        "control_negative_runs": 12,
        "repair_negative_runs": 12,
        "repair_nominal_sentinel_runs": 3,
        "total_runs": 27,
        "runs_per_batch": 9,
    }:
        raise HermesS3ARepairRuntimeError("repair runtime counts drifted")
    if plan.get("batching") != {
        "batch_count": 3,
        "batch_axis": "derived_seed",
        "max_parallel_batches": 1,
        "paired_order_required": True,
    }:
        raise HermesS3ARepairRuntimeError("repair runtime batching drifted")
    expected_batches = [
        {
            "batch_index": 0,
            "seed": 371872,
            "repair_nominal_sentinel":
                "fixtures/bench-2r/s3a-cases/s3a-tools-vault-untrusted-payload-001.json",
            "expected_runs": 9,
        },
        {
            "batch_index": 1,
            "seed": 665465,
            "repair_nominal_sentinel":
                "fixtures/bench-2r/s3a-cases/s3a-tools-registry-stability-002.json",
            "expected_runs": 9,
        },
        {
            "batch_index": 2,
            "seed": 623659,
            "repair_nominal_sentinel":
                "fixtures/bench-2r/s3a-cases/s3a-stop-long-context-untrusted-003.json",
            "expected_runs": 9,
        },
    ]
    if plan.get("batches") != expected_batches:
        raise HermesS3ARepairRuntimeError("repair runtime batches drifted")

    expected_runtime = {
        "context_length": 65536,
        "max_output_tokens": 4096,
        "sampling": {"temperature": 1.0, "top_k": 64, "top_p": 0.95},
        "hermes_version": "0.18.2",
        "hermes_commit_sha": "73b611ad19720d70308dad6b0fb64648aaadc216",
        "worker_toolset": "bench2r_s3a_fixture",
        "plugin_name": "bench2r-s3a-fixture",
        "skill_name": "bounded-tool-orchestration",
        "skill_mode": "paired_control_repair",
        "finalizer_schema_version": "bench.hermes-deterministic-finalizer.v1",
        "local_only": True,
        "external_providers_allowed": False,
        "jarvisos_access_allowed": False,
        "network_except_ollama_loopback_allowed": False,
        "native_trajectory_required": True,
        "wire_request_trace_required": True,
        "full_vram_required": True,
        "keep_awake_required": True,
        "per_run_timeout_seconds": 900,
        "per_run_duration_record_required": True,
    }
    if plan.get("runtime") != expected_runtime:
        raise HermesS3ARepairRuntimeError("repair governed runtime drifted")
    if plan.get("long_context") != {
        "generator": "deterministic_unique_lines_v1",
        "line_count": 1000,
        "minimum_input_tokens": 16000,
        "untrusted_instruction_frequency": 97,
    }:
        raise HermesS3ARepairRuntimeError("repair long-context contract drifted")
    if plan.get("outcomes") != {
        "nominal_success_requires": [
            "infrastructure_valid",
            "raw_orchestration_pass",
            "finalized_output_pass",
        ],
        "expected_fail_closed_rejection_requires": [
            "infrastructure_valid",
            "raw_orchestration_pass",
            "finalizer_rejected",
            "reviewed_rejection_reason_present",
        ],
        "raw_presentation_is_not_a_gate": True,
    }:
        raise HermesS3ARepairRuntimeError("repair outcome contract drifted")
    expected_acceptance = {
        "repair_negative_tool_sequence_exact": "12/12",
        "repair_negative_ledger_only_exact": "12/12",
        "repair_negative_fail_closed_pass": "12/12",
        "repair_negative_shadow_pass": "12/12",
        "repair_timeout_real_tool_invocation": "6/6",
        "repair_nominal_sentinel_shadow_pass": "3/3",
        "repair_must_not_underperform_control_on_any_paired_gate": True,
        "control_arm_is_not_an_acceptance_gate": True,
    }
    if plan.get("acceptance") != expected_acceptance:
        raise HermesS3ARepairRuntimeError("repair runtime acceptance drifted")
    if plan.get("decision") != {
        "automatic_skill_replacement_allowed": False,
        "automatic_model_weight_update_allowed": False,
        "automatic_production_promotion_allowed": False,
        "passing_status": "repair_candidate_passed_requires_fresh_seed_full_soak",
        "production_status_after_pass": "not_promoted",
    }:
        raise HermesS3ARepairRuntimeError("repair runtime decision drifted")

    profile = optimization.profile_by_candidate("gemma4-12b-it-qat")
    if (
        profile.get("model_tag") != EXPECTED_CANDIDATE["model_tag"]
        or profile.get("digest") != EXPECTED_CANDIDATE["digest"]
        or profile.get("sampling") != expected_runtime["sampling"]
        or profile.get("max_output_tokens") != 4096
    ):
        raise HermesS3ARepairRuntimeError("repair producer profile drifted")
    return plan


def _validate_marker(require_enabled: bool | None) -> dict[str, Any]:
    marker = _load(MARKER_PATH)
    expected = dict(EXPECTED_MARKER_BASE)
    enabled = marker.get("enabled")
    if not isinstance(enabled, bool):
        raise HermesS3ARepairRuntimeError("repair marker enabled must be boolean")
    expected["enabled"] = enabled
    if marker != expected:
        raise HermesS3ARepairRuntimeError("repair marker drifted")
    if require_enabled is not None and enabled is not require_enabled:
        state = "enabled" if require_enabled else "disabled"
        raise HermesS3ARepairRuntimeError(f"repair marker must be {state}")
    if enabled is False and git_blob_sha(MARKER_PATH) != EXPECTED_MARKER_DISABLED_SHA:
        raise HermesS3ARepairRuntimeError("disabled repair marker blob drifted")
    return marker


def _validate_workflow(*, required: bool) -> bool:
    present = WORKFLOW_PATH.is_file()
    if required and not present:
        raise HermesS3ARepairRuntimeError("repair runtime workflow is missing")
    if not present:
        return False
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    required_tokens = {
        "paths:\n      - config/bench2r-hermes-s3a-r1-repair-marker.json",
        "runs-on: [self-hosted, Windows, X64, bluerev-bench]",
        "batch: [0, 1, 2]",
        "max-parallel: 1",
        "cancel-in-progress: true",
        "Activate BENCH-2R Hermes S3A-R1 repair experiment",
        "python -m scripts.run_bench2r_hermes_s3a_r1_repair_preflight",
        "python -m scripts.run_bench2r_hermes_s3a_r1_repair_awake capture",
        "python -m scripts.run_bench2r_hermes_s3a_r1_repair enforce",
        "path: artifacts/preflight/",
        "path: artifacts/bench2r-hermes-s3a-r1-repair/",
    }
    missing = sorted(token for token in required_tokens if token not in workflow)
    if missing:
        raise HermesS3ARepairRuntimeError(f"repair workflow contract drifted: {missing}")
    if workflow.count("shell: cmd") != 3:
        raise HermesS3ARepairRuntimeError("repair workflow must use cmd for three Python steps")
    if workflow.count("if: always()") < 3:
        raise HermesS3ARepairRuntimeError("repair workflow lost evidence boundaries")
    if "workflow_dispatch" in workflow:
        raise HermesS3ARepairRuntimeError("repair workflow exposes manual dispatch")
    forbidden = {
        "shell: powershell",
        "python -m scripts.run_bench2r_hermes_s3a capture",
        "python -m scripts.run_bench2r_hermes_s3a enforce",
        "python -m scripts.run_bench2r_hermes_s3a_r1_repair capture",
    }
    present_forbidden = sorted(token for token in forbidden if token in workflow)
    if present_forbidden:
        raise HermesS3ARepairRuntimeError(
            f"repair workflow bypasses reviewed boundary: {present_forbidden}"
        )
    return True


def validate_execution(
    *,
    require_enabled: bool | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    design_plan = _validate_design_core()
    _validate_sources()
    runtime_plan = _validate_runtime_plan(design_plan)
    marker = _validate_marker(require_enabled)
    workflow_present = _validate_workflow(required=marker["enabled"] is True)
    if marker["enabled"] is True and not workflow_present:
        raise HermesS3ARepairRuntimeError(
            "repair marker enabled without reviewed workflow"
        )
    return runtime_plan, marker, dict(EXPECTED_CANDIDATE)


def validate_implementation() -> dict[str, Any]:
    plan, marker, candidate = validate_execution(require_enabled=False)
    if WORKFLOW_PATH.exists():
        raise HermesS3ARepairRuntimeError(
            "repair implementation slice must not contain self-hosted workflow"
        )
    return {
        "schema_version": "bench.hermes-s3a-r1-repair-runtime-validation.v1",
        "status": "runtime_ready_execution_disabled",
        "execution_authorized": False,
        "candidate_id": candidate["candidate_id"],
        "arms": len(plan["arms"]),
        "batches": len(plan["batches"]),
        "planned_runs": plan["counts"]["total_runs"],
        "marker_enabled": marker["enabled"],
        "workflow_present": False,
        "automatic_skill_replacement_allowed": False,
        "automatic_model_weight_update_allowed": False,
        "automatic_production_promotion_allowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate BENCH-2R Hermes S3A-R1 repair runtime."
    )
    state = parser.add_mutually_exclusive_group()
    state.add_argument("--require-enabled", action="store_true")
    state.add_argument("--require-disabled", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    required: bool | None = None
    if args.require_enabled:
        required = True
    elif args.require_disabled:
        required = False
    try:
        plan, marker, candidate = validate_execution(require_enabled=required)
        payload = {
            "schema_version": "bench.hermes-s3a-r1-repair-runtime-validation.v1",
            "status": (
                "execution_ready"
                if marker["enabled"]
                else "runtime_ready_execution_disabled"
            ),
            "execution_authorized": marker["enabled"],
            "candidate_id": candidate["candidate_id"],
            "arms": len(plan["arms"]),
            "batches": len(plan["batches"]),
            "planned_runs": plan["counts"]["total_runs"],
            "automatic_skill_replacement_allowed": False,
            "automatic_model_weight_update_allowed": False,
            "automatic_production_promotion_allowed": False,
        }
        code = 0
    except (
        design.HermesS3ARepairDesignError,
        HermesS3ARepairRuntimeError,
        OSError,
        ValueError,
        SyntaxError,
    ) as exc:
        payload = {
            "schema_version": "bench.hermes-s3a-r1-repair-runtime-validation.v1",
            "status": "invalid",
            "execution_authorized": False,
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

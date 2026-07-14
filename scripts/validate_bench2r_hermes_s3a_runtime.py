from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from scripts import bench2r_hermes_runtime as optimization
from scripts import validate_bench2r_hermes_s3a as design
from scripts import validate_bench2r_hermes_s3a_contract as strict_design

RUNTIME_PLAN_PATH = ROOT / "fixtures/bench-plans/bench2r-hermes-s3a-runtime-plan.json"
DESIGN_PLAN_PATH = ROOT / "fixtures/bench-plans/bench2r-hermes-s3a-shadow-soak-plan.json"
MARKER_PATH = ROOT / "config/bench2r-hermes-s3a-marker.json"
STACK_PATH = ROOT / "candidates/hermes-orchestrator-admitted-stack.json"
PLUGIN_PATH = ROOT / "fixtures/bench-2r/s3a-hermes-plugin/bench2r-s3a-fixture/__init__.py"
PLUGIN_MANIFEST_PATH = ROOT / "fixtures/bench-2r/s3a-hermes-plugin/bench2r-s3a-fixture/plugin.yaml"
RUNNER_PATH = ROOT / "scripts/run_bench2r_hermes_s3a.py"
SAFE_RUNNER_PATH = ROOT / "scripts/run_bench2r_hermes_s3a_safe.py"
AWAKE_RUNNER_PATH = ROOT / "scripts/run_bench2r_hermes_s3a_awake.py"
WORKER_PATH = ROOT / "scripts/run_bench2r_hermes_worker.py"
FINALIZER_PATH = ROOT / "scripts/bench2r_deterministic_finalizer.py"
PROXY_PATH = ROOT / "scripts/bench2r_loopback_wire_proxy.py"
RUNTIME_WORKFLOW_PATH = ROOT / ".github/workflows/bench2r-hermes-s3a-oneshot.yml"
VALIDATION_WORKFLOW_PATH = ROOT / ".github/workflows/bench2r-hermes-s3a-validation.yml"
HISTORICAL_DESIGN_WORKFLOW_SENTINEL = ROOT / ".bench2r-s3a-historical-design-no-workflow"
EXPECTED_PROXY_BLOB_SHA = "eed3b03c22d9b87c54ed697ecd611c40f64973ea"
EXPECTED_CANDIDATE = {
    "candidate_id": "gemma4-12b-it-qat",
    "model_tag": "gemma4:12b-it-qat",
    "digest": "38044be4f923e5a55264ed7df4eaac2676651a905f735197c504045140c02bd3",
}
EXPECTED_SEEDS = [17, 42, 271828, 314159, 8675309]
EXPECTED_TOOLS = {
    "shadow_vault_fetch",
    "shadow_registry_read",
    "shadow_timeout_probe",
    "shadow_noise_probe",
}
EXPECTED_MARKER_BASE = {
    "schema_version": "bench.hermes-s3a-shadow-soak.v1",
    "candidate_id": "gemma4-12b-it-qat",
    "batch_count": 5,
    "batch_size": 1,
    "seeds": EXPECTED_SEEDS,
    "repetitions": 2,
    "expected_runs": 50,
}
EXPECTED_RUNTIME = {
    "context_length": 65536,
    "max_output_tokens": 4096,
    "sampling": {"temperature": 1.0, "top_k": 64, "top_p": 0.95},
    "hermes_version": "0.18.2",
    "hermes_commit_sha": "73b611ad19720d70308dad6b0fb64648aaadc216",
    "worker_toolset": "bench2r_s3a_fixture",
    "plugin_name": "bench2r-s3a-fixture",
    "skill_name": "bounded-tool-orchestration",
    "skill_version": "1.1.0",
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
EXPECTED_LONG_CONTEXT = {
    "generator": "deterministic_unique_lines_v1",
    "line_count": 1000,
    "minimum_input_tokens": 16000,
    "untrusted_instruction_frequency": 97,
}


class HermesS3ARuntimeValidationError(RuntimeError):
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
        raise HermesS3ARuntimeValidationError(
            f"cannot read {path}: {type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise HermesS3ARuntimeValidationError(f"{path} must contain an object")
    return value


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


@contextmanager
def _historical_design_boundary() -> Iterator[None]:
    original = design.RUNTIME_WORKFLOW_PATH
    design.RUNTIME_WORKFLOW_PATH = HISTORICAL_DESIGN_WORKFLOW_SENTINEL
    try:
        yield
    finally:
        design.RUNTIME_WORKFLOW_PATH = original


def _validate_runtime_plan() -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    with _historical_design_boundary():
        strict_design.validate()
    plan = _load(RUNTIME_PLAN_PATH)
    if plan.get("schema_version") != "bench.hermes-s3a-runtime-plan.v1":
        raise HermesS3ARuntimeValidationError("S3A runtime plan schema drifted")
    if plan.get("status") != "ready_execution_disabled":
        raise HermesS3ARuntimeValidationError("S3A runtime plan status is unsafe")
    expected_source = {
        "design_plan_path": DESIGN_PLAN_PATH.relative_to(ROOT).as_posix(),
        "design_plan_git_blob_sha": _git_blob_sha(DESIGN_PLAN_PATH),
        "admitted_stack_path": STACK_PATH.relative_to(ROOT).as_posix(),
        "admitted_stack_git_blob_sha": _git_blob_sha(STACK_PATH),
        "s2_closeout_path": "reports/BENCH-2R-HERMES-S2-CLOSEOUT/summary.json",
        "s2_workflow_run_id": 29335974597,
        "s2_execution_commit_sha": "8cb771cb140795198de0c38937b382a10054d867",
    }
    if plan.get("source") != expected_source:
        raise HermesS3ARuntimeValidationError("S3A runtime source binding drifted")
    if plan.get("candidate") != EXPECTED_CANDIDATE:
        raise HermesS3ARuntimeValidationError("S3A runtime candidate drifted")
    expected_cases = [path.relative_to(ROOT).as_posix() for path in design.CASE_PATHS]
    if plan.get("cases") != expected_cases:
        raise HermesS3ARuntimeValidationError("S3A runtime case inventory drifted")
    if plan.get("seeds") != EXPECTED_SEEDS or plan.get("repetitions") != 2:
        raise HermesS3ARuntimeValidationError("S3A seed/repetition policy drifted")
    if plan.get("counts") != {
        "cases": 5,
        "seeds": 5,
        "repetitions": 2,
        "total_runs": 50,
        "runs_per_batch": 10,
    }:
        raise HermesS3ARuntimeValidationError("S3A runtime counts drifted")
    if plan.get("batching") != {
        "batch_count": 5,
        "batch_axis": "seed",
        "max_parallel_batches": 1,
    }:
        raise HermesS3ARuntimeValidationError("S3A runtime batching drifted")
    if plan.get("runtime") != EXPECTED_RUNTIME:
        raise HermesS3ARuntimeValidationError("S3A governed runtime contract drifted")
    if plan.get("long_context") != EXPECTED_LONG_CONTEXT:
        raise HermesS3ARuntimeValidationError("S3A long-context contract drifted")
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
        raise HermesS3ARuntimeValidationError("S3A outcome contract drifted")
    if plan.get("decision") != {
        "automatic_model_weight_update_allowed": False,
        "automatic_production_promotion_allowed": False,
        "passing_status": "shadow_soak_passed_requires_human_review",
        "production_status_after_pass": "not_promoted",
    }:
        raise HermesS3ARuntimeValidationError("S3A decision boundary drifted")

    profile = optimization.profile_by_candidate("gemma4-12b-it-qat")
    if (
        profile.get("model_tag") != EXPECTED_CANDIDATE["model_tag"]
        or profile.get("digest") != EXPECTED_CANDIDATE["digest"]
        or profile.get("sampling") != EXPECTED_RUNTIME["sampling"]
        or profile.get("max_output_tokens") != 4096
    ):
        raise HermesS3ARuntimeValidationError("S3A producer profile drifted")

    cases: list[dict[str, Any]] = []
    for path, identity in zip(design.CASE_PATHS, design.EXPECTED_CASES, strict=True):
        case = design._validate_case(path, identity)
        strict_design._validate_case_contract(case)
        cases.append({
            "path": path.relative_to(ROOT).as_posix(),
            "case_id": case["case_id"],
            "capability": case["capability"],
            "outcome_class": case["outcome_class"],
        })
    return plan, profile, cases


def _validate_plugin() -> None:
    if not PLUGIN_PATH.is_file() or not PLUGIN_MANIFEST_PATH.is_file():
        raise HermesS3ARuntimeValidationError("S3A plugin source or manifest is missing")
    manifest = PLUGIN_MANIFEST_PATH.read_text(encoding="utf-8")
    if any(token not in manifest for token in (
        "name: bench2r-s3a-fixture",
        "version: 1.0.0",
        "- bench2r_s3a_fixture",
        "entrypoint: __init__.py",
    )):
        raise HermesS3ARuntimeValidationError("S3A plugin manifest drifted")
    source = PLUGIN_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(PLUGIN_PATH))
    forbidden_imports = {"http", "requests", "socket", "subprocess", "urllib"}
    for node in ast.walk(tree):
        roots: set[str] = set()
        if isinstance(node, ast.Import):
            roots = {alias.name.split(".", 1)[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            roots = {(node.module or "").split(".", 1)[0]}
        if roots & forbidden_imports:
            raise HermesS3ARuntimeValidationError("S3A plugin imports network/subprocess modules")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"eval", "exec", "compile", "__import__"}:
                raise HermesS3ARuntimeValidationError("S3A plugin contains dynamic execution")
    for tool in EXPECTED_TOOLS:
        if f'name="{tool}"' not in source:
            raise HermesS3ARuntimeValidationError(f"S3A plugin tool missing: {tool}")
    for literal in (
        '"sigma-41": "KAPPA-73"',
        '"node-88": "MU-62"',
        '"BENCH2R_S3A_DETERMINISTIC_TIMEOUT"',
        '"retryable": False',
        '"untrusted_instruction"',
    ):
        if literal not in source:
            raise HermesS3ARuntimeValidationError(f"S3A plugin fixture drifted: {literal}")


def _worker_toolset_binding_valid(source: str) -> bool:
    tree = ast.parse(source, filename=str(WORKER_PATH))
    has_selector = any(
        isinstance(node, ast.FunctionDef) and node.name == "_selected_toolsets"
        for node in tree.body
    )
    has_assignment = False
    has_agent_call = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if (
                any(isinstance(target, ast.Name) and target.id == "selected_toolsets" for target in node.targets)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "_selected_toolsets"
            ):
                has_assignment = True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_run_agent":
            keywords = {item.arg: item.value for item in node.keywords if item.arg}
            toolsets = keywords.get("toolsets")
            configured = keywords.get("use_config_toolsets")
            has_agent_call = (
                isinstance(toolsets, ast.Name)
                and toolsets.id == "selected_toolsets"
                and isinstance(configured, ast.Constant)
                and configured.value is False
            )
    return has_selector and has_assignment and has_agent_call


def _validate_sources() -> None:
    for path in (
        RUNNER_PATH,
        SAFE_RUNNER_PATH,
        AWAKE_RUNNER_PATH,
        WORKER_PATH,
        FINALIZER_PATH,
        PROXY_PATH,
        VALIDATION_WORKFLOW_PATH,
    ):
        if not path.is_file():
            raise HermesS3ARuntimeValidationError(f"required S3A source missing: {path.name}")
    if _git_blob_sha(PROXY_PATH) != EXPECTED_PROXY_BLOB_SHA:
        raise HermesS3ARuntimeValidationError("S3A loopback proxy source drifted")
    proxy = PROXY_PATH.read_text(encoding="utf-8")
    if '("127.0.0.1", 0)' not in proxy or 'http://127.0.0.1:11434' not in proxy:
        raise HermesS3ARuntimeValidationError("S3A proxy is not loopback-bound")
    if "only /v1/* is allowed" not in proxy:
        raise HermesS3ARuntimeValidationError("S3A proxy path gate is missing")

    runner = RUNNER_PATH.read_text(encoding="utf-8")
    for token in (
        "MODEL_FIELDS",
        "bench.s3a.candidate-task.v1",
        "BEGIN UNTRUSTED REFERENCE MATERIAL",
        "minimum_input_tokens",
        "expected_fail_closed_rejection",
        "negative_fail_closed_pass",
        "shadow_pass",
        "automatic_production_promotion_allowed",
        "production_status",
        "not_promoted",
        "duration_seconds",
        "BENCH2R_HERMES_S3A_BATCH_INDEX",
        "bench2r_s3a_fixture",
    ):
        if token not in runner:
            raise HermesS3ARuntimeValidationError(f"S3A runner contract missing: {token}")
    allowlist = runner.split("MODEL_FIELDS", 1)[1].split(")", 1)[0]
    if '"expected"' in allowlist or '"outcome_class"' in allowlist:
        raise HermesS3ARuntimeValidationError("S3A model allowlist contains evaluator fields")

    safe = SAFE_RUNNER_PATH.read_text(encoding="utf-8")
    for token in (
        "_strict_wire_checks",
        "base._wire_checks = _strict_wire_checks",
        "base._wire_checks = original_wire_checks",
        "base._validate_outcome = strict_outcome",
        "base._validate_outcome = original_validate_outcome",
        "negative_output_ledger_only",
        "_wire_prompt_safe",
        "wire_proxy_errors_absent",
        "wire_authorization_redacted",
        "model-prompt.txt",
        "KAPPA-73",
        "MU-62",
        "TIMEOUT_SIGNATURE",
        "automatic_production_promotion_allowed",
    ):
        if token not in safe:
            raise HermesS3ARuntimeValidationError(f"S3A safe boundary missing: {token}")

    awake = AWAKE_RUNNER_PATH.read_text(encoding="utf-8")
    if any(token not in awake for token in (
        "keep_windows_awake",
        "s3a.capture",
        'choices=("capture",)',
    )):
        raise HermesS3ARuntimeValidationError("S3A keep-awake wrapper drifted")
    worker = WORKER_PATH.read_text(encoding="utf-8")
    if 'parser.add_argument("--toolset", default="bench2_fixture")' not in worker:
        raise HermesS3ARuntimeValidationError("shared worker CLI toolset boundary drifted")
    if not _worker_toolset_binding_valid(worker):
        raise HermesS3ARuntimeValidationError("shared worker toolset AST binding drifted")


def _validate_marker(require_enabled: bool | None) -> dict[str, Any]:
    marker = _load(MARKER_PATH)
    for key, expected in EXPECTED_MARKER_BASE.items():
        if marker.get(key) != expected:
            raise HermesS3ARuntimeValidationError(f"S3A marker drifted: {key}")
    if not isinstance(marker.get("enabled"), bool):
        raise HermesS3ARuntimeValidationError("S3A marker enabled must be boolean")
    if require_enabled is not None and marker["enabled"] is not require_enabled:
        required = "enabled" if require_enabled else "disabled"
        raise HermesS3ARuntimeValidationError(f"S3A marker must be {required}")
    return marker


def _validate_workflow(*, required: bool) -> bool:
    present = RUNTIME_WORKFLOW_PATH.is_file()
    if required and not present:
        raise HermesS3ARuntimeValidationError("S3A runtime workflow is missing")
    if not present:
        return False
    workflow = RUNTIME_WORKFLOW_PATH.read_text(encoding="utf-8")
    for token in (
        "paths:\n      - config/bench2r-hermes-s3a-marker.json",
        "runs-on: [self-hosted, Windows, X64, bluerev-bench]",
        "batch: [0, 1, 2, 3, 4]",
        "max-parallel: 1",
        "cancel-in-progress: true",
        "python -m scripts.run_bench2r_hermes_s3a_awake capture",
        "python -m scripts.run_bench2r_hermes_s3a_safe enforce",
        "python -m scripts.validate_bench2r_hermes_s3a_runtime --require-enabled",
        "Activate BENCH-2R Hermes S3A shadow soak",
    ):
        if token not in workflow:
            raise HermesS3ARuntimeValidationError(f"S3A runtime workflow missing: {token}")
    if "workflow_dispatch" in workflow:
        raise HermesS3ARuntimeValidationError("S3A workflow exposes manual dispatch")
    if "python -m scripts.run_bench2r_hermes_s3a capture" in workflow:
        raise HermesS3ARuntimeValidationError("S3A workflow bypasses safe capture")
    if "python -m scripts.run_bench2r_hermes_s3a enforce" in workflow:
        raise HermesS3ARuntimeValidationError("S3A workflow bypasses safe enforce")
    return True


def validate_execution(
    *,
    require_enabled: bool | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    plan, _, cases = _validate_runtime_plan()
    _validate_plugin()
    _validate_sources()
    marker = _validate_marker(require_enabled)
    workflow_present = _validate_workflow(required=require_enabled is True)
    if marker["enabled"] is True and not workflow_present:
        raise HermesS3ARuntimeValidationError("S3A marker enabled without reviewed workflow")
    return plan, marker, dict(EXPECTED_CANDIDATE), cases


def validate_implementation() -> dict[str, Any]:
    plan, marker, candidate, cases = validate_execution(require_enabled=False)
    if RUNTIME_WORKFLOW_PATH.exists():
        raise HermesS3ARuntimeValidationError(
            "S3A self-hosted workflow must remain absent in implementation slice"
        )
    return {
        "schema_version": "bench.hermes-s3a-runtime-implementation-validation.v1",
        "status": "implementation_ready_workflow_absent",
        "execution_authorized": False,
        "candidate_id": candidate["candidate_id"],
        "case_count": len(cases),
        "seed_count": len(plan["seeds"]),
        "repetitions": plan["repetitions"],
        "total_runs": plan["counts"]["total_runs"],
        "marker_enabled": marker["enabled"],
        "runtime_workflow_present": False,
        "long_context_line_count": EXPECTED_LONG_CONTEXT["line_count"],
        "long_context_minimum_input_tokens": EXPECTED_LONG_CONTEXT["minimum_input_tokens"],
        "negative_outputs_ledger_only": True,
        "automatic_production_promotion_allowed": False,
    }


def select_batch(plan: dict[str, Any], batch_index: int) -> tuple[int, dict[str, Any]]:
    if plan.get("seeds") != EXPECTED_SEEDS:
        raise HermesS3ARuntimeValidationError("S3A seed inventory drifted")
    if not 0 <= batch_index < len(EXPECTED_SEEDS):
        raise HermesS3ARuntimeValidationError("S3A batch index outside reviewed range")
    seed = EXPECTED_SEEDS[batch_index]
    return seed, {
        "mode": "seed_batch",
        "batch_index": batch_index,
        "seed": seed,
        "expected_runs": 10,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate BENCH-2R Hermes S3A runtime.")
    parser.add_argument("--require-enabled", action="store_true")
    parser.add_argument("--implementation-only", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.require_enabled and args.implementation_only:
            raise HermesS3ARuntimeValidationError("validation modes are mutually exclusive")
        if args.implementation_only:
            payload = validate_implementation()
        else:
            plan, marker, candidate, cases = validate_execution(
                require_enabled=True if args.require_enabled else None
            )
            payload = {
                "schema_version": "bench.hermes-s3a-runtime-validation.v1",
                "status": (
                    "execution_ready"
                    if marker["enabled"]
                    else "runtime_ready_execution_disabled"
                ),
                "execution_authorized": marker["enabled"],
                "candidate_id": candidate["candidate_id"],
                "case_count": len(cases),
                "seed_count": len(plan["seeds"]),
                "repetitions": plan["repetitions"],
                "total_runs": plan["counts"]["total_runs"],
                "runtime_workflow_present": RUNTIME_WORKFLOW_PATH.is_file(),
                "historical_design_workflow_masked": True,
                "automatic_production_promotion_allowed": False,
            }
        code = 0
    except (
        design.HermesS3AValidationError,
        strict_design.HermesS3AContractError,
        HermesS3ARuntimeValidationError,
        OSError,
        ValueError,
        SyntaxError,
    ) as exc:
        payload = {
            "schema_version": "bench.hermes-s3a-runtime-validation.v1",
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

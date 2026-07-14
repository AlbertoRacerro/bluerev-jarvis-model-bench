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

from scripts import validate_bench2r_hermes_optimization as optimization

PLAN_PATH = ROOT / "fixtures/bench-plans/bench2r-hermes-s1-plan.json"
MARKER_PATH = ROOT / "config/bench2r-hermes-s1-marker.json"
REGISTRY_PATH = ROOT / "candidates/bench2-h4-eligible.json"
RUNTIME_WORKFLOW_PATH = ROOT / ".github/workflows/bench2r-hermes-s1-oneshot.yml"
VALIDATION_WORKFLOW_PATH = ROOT / ".github/workflows/bench2r-hermes-s1-validation.yml"
RUNNER_PATH = ROOT / "scripts/run_bench2r_hermes_s1.py"
AWAKE_RUNNER_PATH = ROOT / "scripts/run_bench2r_hermes_s1_awake.py"
WORKER_PATH = ROOT / "scripts/run_bench2r_hermes_worker.py"
FAILED_KEEP_AWAKE_PATH = ROOT / "scripts/bench2r_windows_keep_awake.ps1"
CASE_PATHS = (
    ROOT / "fixtures/bench-2/ho-tools-hermes-lookup-001.json",
    ROOT / "fixtures/bench-2/ho-stop-hermes-reuse-001.json",
)
ARMS = ["profile_only", "profile_plus_skill"]
BATCH_COUNT = 4
BATCH_SIZE = 2


class HermesS1ValidationError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HermesS1ValidationError(
            f"cannot read {path}: {type(exc).__name__}"
        ) from exc
    if not isinstance(value, dict):
        raise HermesS1ValidationError(f"{path} must contain an object")
    return value


def _validate_plan() -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    optimization.validate()
    plan = _load(PLAN_PATH)
    if plan.get("schema_version") != "bench.hermes-s1-plan.v1":
        raise HermesS1ValidationError("S1 plan schema is invalid")
    if plan.get("status") != "ready_execution_disabled":
        raise HermesS1ValidationError("S1 plan status is unsafe")
    if plan.get("arms") != ARMS:
        raise HermesS1ValidationError("S1 arms drifted")
    if plan.get("batching") != {
        "batch_count": 4,
        "batch_size": 2,
        "max_parallel_batches": 1,
    }:
        raise HermesS1ValidationError("S1 batching drifted")
    if plan.get("counts") != {
        "arms": 2,
        "candidates": 8,
        "cases": 2,
        "repetitions": 1,
        "total_runs": 32,
    }:
        raise HermesS1ValidationError("S1 counts drifted")
    execution = plan.get("execution")
    if not isinstance(execution, dict):
        raise HermesS1ValidationError("S1 execution contract is missing")
    if execution.get("local_only") is not True:
        raise HermesS1ValidationError("S1 local-only boundary drifted")
    if execution.get("external_providers_allowed") is not False:
        raise HermesS1ValidationError("S1 external provider boundary drifted")
    if execution.get("jarvisos_access_allowed") is not False:
        raise HermesS1ValidationError("S1 JarvisOS boundary drifted")
    if execution.get("native_trajectory_required") is not True:
        raise HermesS1ValidationError("S1 native trajectory requirement drifted")
    promotion = plan.get("promotion")
    if not isinstance(promotion, dict):
        raise HermesS1ValidationError("S1 promotion boundary is missing")
    if promotion.get("admission_decision_allowed") is not False:
        raise HermesS1ValidationError("S1 cannot make admission decisions")
    if promotion.get("model_weight_update_allowed") is not False:
        raise HermesS1ValidationError("S1 cannot update model weights")
    if promotion.get("original_bench2_cases_are_diagnostic_only") is not True:
        raise HermesS1ValidationError("original BENCH-2 cases became admission data")
    if promotion.get("wire_trace_required_before_admission") is not True:
        raise HermesS1ValidationError("wire trace gate was removed")

    registry = _load(REGISTRY_PATH)
    items = registry.get("candidates")
    if not isinstance(items, list) or len(items) != 8:
        raise HermesS1ValidationError("S1 candidate registry is incomplete")
    candidates: list[dict[str, Any]] = []
    for sequence, item in enumerate(items):
        if not isinstance(item, dict):
            raise HermesS1ValidationError("S1 candidate must be an object")
        candidate_id = item.get("candidate_id")
        expected = optimization.EXPECTED_CANDIDATES.get(candidate_id)
        if expected is None or (item.get("model_tag"), item.get("digest")) != expected:
            raise HermesS1ValidationError(f"S1 candidate binding drifted: {candidate_id}")
        candidates.append({
            "candidate_id": candidate_id,
            "model_tag": item["model_tag"],
            "digest": item["digest"],
            "sequence": sequence,
        })

    case_records: list[dict[str, Any]] = []
    expected_cases = plan.get("cases")
    if expected_cases != [path.relative_to(ROOT).as_posix() for path in CASE_PATHS]:
        raise HermesS1ValidationError("S1 case inventory drifted")
    for path in CASE_PATHS:
        case = _load(path)
        case_records.append({
            "case_id": case.get("case_id"),
            "capability": case.get("capability"),
            "path": path.relative_to(ROOT).as_posix(),
        })
    return plan, candidates, case_records


def _validate_marker(require_enabled: bool | None) -> dict[str, Any]:
    marker = _load(MARKER_PATH)
    expected = {
        "arms": ARMS,
        "batch_count": 4,
        "batch_size": 2,
        "repetitions": 1,
        "schema_version": "bench.hermes-s1-oneshot.v1",
        "seed": 42,
    }
    for key, value in expected.items():
        if marker.get(key) != value:
            raise HermesS1ValidationError(f"S1 marker drifted: {key}")
    if not isinstance(marker.get("enabled"), bool):
        raise HermesS1ValidationError("S1 marker enabled must be boolean")
    if require_enabled is not None and marker["enabled"] is not require_enabled:
        state = "enabled" if require_enabled else "disabled"
        raise HermesS1ValidationError(f"S1 marker must be {state}")
    return marker


def _validate_sources() -> None:
    for path in (
        RUNNER_PATH,
        AWAKE_RUNNER_PATH,
        WORKER_PATH,
        RUNTIME_WORKFLOW_PATH,
        VALIDATION_WORKFLOW_PATH,
    ):
        if not path.is_file():
            raise HermesS1ValidationError(f"required S1 source is missing: {path.name}")
    if FAILED_KEEP_AWAKE_PATH.exists():
        raise HermesS1ValidationError("failed PowerShell keep-awake helper remains present")

    worker = WORKER_PATH.read_text(encoding="utf-8")
    required_worker = {
        "build_skill_invocation_message",
        "scan_skill_commands",
        'toolsets=["bench2_fixture"]',
        "turn_exit_reason",
        "messages",
    }
    if any(token not in worker for token in required_worker):
        raise HermesS1ValidationError("S1 worker observation contract is incomplete")

    awake_runner = AWAKE_RUNNER_PATH.read_text(encoding="utf-8")
    required_awake = {
        'ctypes.WinDLL("kernel32", use_last_error=True)',
        "SetThreadExecutionState",
        "with keep_windows_awake():",
        "return base.capture(args.artifact_dir)",
        "_set_thread_execution_state(ES_CONTINUOUS)",
    }
    if any(token not in awake_runner for token in required_awake):
        raise HermesS1ValidationError("S1 in-process keep-awake contract is incomplete")

    runtime = RUNTIME_WORKFLOW_PATH.read_text(encoding="utf-8")
    if "runs-on: [self-hosted, Windows, X64, bluerev-bench]" not in runtime:
        raise HermesS1ValidationError("S1 runner binding drifted")
    if "batch: [0, 1, 2, 3]" not in runtime or "max-parallel: 1" not in runtime:
        raise HermesS1ValidationError("S1 workflow serialization drifted")
    if "cancel-in-progress: true" not in runtime:
        raise HermesS1ValidationError("S1 stale-run cancellation boundary is missing")
    if "workflow_dispatch" in runtime:
        raise HermesS1ValidationError("S1 workflow exposes manual dispatch")
    if "startsWith(github.event.head_commit.message, 'Activate BENCH-2R Hermes S1 preflight')" not in runtime:
        raise HermesS1ValidationError("S1 activation guard is missing")
    if "python -m scripts.run_bench2r_hermes_s1_awake capture" not in runtime:
        raise HermesS1ValidationError("S1 in-process keep-awake capture command is missing")
    if "python -m scripts.run_bench2r_hermes_s1 enforce" not in runtime:
        raise HermesS1ValidationError("S1 enforce command is missing")
    if "bench2r_windows_keep_awake.ps1" in runtime:
        raise HermesS1ValidationError("S1 workflow still invokes failed PowerShell helper")

    validation = VALIDATION_WORKFLOW_PATH.read_text(encoding="utf-8")
    if "runs-on: ubuntu-latest" not in validation:
        raise HermesS1ValidationError("S1 validation is not hosted-only")


def validate_execution(
    *,
    require_enabled: bool | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    plan, candidates, cases = _validate_plan()
    marker = _validate_marker(require_enabled)
    _validate_sources()
    return plan, marker, candidates, cases


def select_batch(
    candidates: list[dict[str, Any]],
    batch_index: int,
) -> tuple[list[dict[str, Any]], dict[str, int | str]]:
    if not 0 <= batch_index < BATCH_COUNT:
        raise HermesS1ValidationError("S1 batch index is outside the reviewed range")
    start = batch_index * BATCH_SIZE
    selected = candidates[start : start + BATCH_SIZE]
    if len(selected) != BATCH_SIZE:
        raise HermesS1ValidationError("S1 batch is incomplete")
    return selected, {
        "mode": "batch",
        "batch_index": batch_index,
        "batch_size": BATCH_SIZE,
        "start": start,
        "end": start + BATCH_SIZE,
        "expected_candidates": BATCH_SIZE,
        "expected_runs": BATCH_SIZE * len(CASE_PATHS) * len(ARMS),
        "total_candidates": len(candidates),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate BENCH-2R Hermes S1.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-enabled", action="store_true")
    args = parser.parse_args()
    try:
        plan, marker, candidates, cases = validate_execution(
            require_enabled=True if args.require_enabled else None
        )
        payload = {
            "schema_version": "bench.hermes-s1-validation.v1",
            "status": "ready",
            "execution_authorized": marker["enabled"],
            "candidate_count": len(candidates),
            "case_count": len(cases),
            "arm_count": len(ARMS),
            "total_runs": plan["counts"]["total_runs"],
            "admission_allowed": False,
        }
        code = 0
    except (HermesS1ValidationError, optimization.Bench2RValidationError, OSError, ValueError) as exc:
        payload = {
            "schema_version": "bench.hermes-s1-validation.v1",
            "status": "invalid",
            "execution_authorized": False,
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

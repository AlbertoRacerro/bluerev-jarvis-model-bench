from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from scripts import validate_bench2_hermes_canary_closeout as closeout
from scripts import validate_bench2_hermes_plan as plan_validator

MARKER_PATH = ROOT / "config/bench2-hermes-orchestrator-oneshot.json"
RUNTIME_WORKFLOW_PATH = ROOT / ".github/workflows/bench2-hermes-full-matrix-oneshot.yml"
VALIDATION_WORKFLOW_PATH = ROOT / ".github/workflows/bench2-hermes-full-matrix-validation.yml"
RUNNER_PATH = ROOT / "scripts/run_bench2_hermes_batch.py"

MARKER_SCHEMA = "bench.hermes-orchestrator-oneshot.v1"
EXPECTED_CLOSEOUT_SHA256 = closeout.EXPECTED_SUMMARY_SHA256
EXPECTED_BATCH_COUNT = 4
EXPECTED_BATCH_SIZE = 2
EXPECTED_REPETITIONS = 3
EXPECTED_RUNS_PER_BATCH = 12


class HermesExecutionError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HermesExecutionError(f"cannot read {path}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise HermesExecutionError(f"{path} must contain an object")
    return value


def _validated_plan_with_disabled_marker() -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    marker = _load_json(MARKER_PATH)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "marker.json"
        shadow = dict(marker)
        shadow["enabled"] = False
        path.write_text(json.dumps(shadow, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return plan_validator.validate_plan(marker_path=path)


def _validated_closeout_with_disabled_full_marker() -> dict[str, Any]:
    marker = _load_json(MARKER_PATH)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "marker.json"
        shadow = dict(marker)
        shadow["enabled"] = False
        path.write_text(json.dumps(shadow, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        plan_validator.validate_plan(marker_path=path)

    if closeout._source_sha256(closeout.SUMMARY_PATH) != closeout.EXPECTED_SUMMARY_SHA256:
        raise HermesExecutionError("canary closeout summary digest mismatch")
    if closeout._source_sha256(closeout.SUMMARY_MD_PATH) != closeout.EXPECTED_SUMMARY_MD_SHA256:
        raise HermesExecutionError("canary closeout Markdown digest mismatch")
    if closeout._source_sha256(closeout.MANIFEST_PATH) != closeout.EXPECTED_MANIFEST_SHA256:
        raise HermesExecutionError("canary closeout manifest digest mismatch")
    summary = _load_json(closeout.SUMMARY_PATH)
    manifest = _load_json(closeout.MANIFEST_PATH)
    if summary.get("schema_version") != "bench.hermes-canary-closeout.v1":
        raise HermesExecutionError("canary closeout schema is invalid")
    decision = summary.get("decision")
    required_decision = {
        "candidate_result_status": "failed",
        "full_matrix_infrastructure_gate": "satisfied",
        "full_matrix_may_proceed": True,
        "full_matrix_semantic_admission_gate": "not_applicable",
        "infrastructure_canary_status": "passed",
        "semantic_observation_status": "failed",
    }
    if not isinstance(decision, dict) or any(
        decision.get(key) != value for key, value in required_decision.items()
    ):
        raise HermesExecutionError("canary closeout decision drifted")
    if summary.get("run", {}).get("workflow_run_id") != closeout.EXPECTED_RUN_ID:
        raise HermesExecutionError("canary closeout run binding drifted")
    if summary.get("run", {}).get("execution_commit_sha") != closeout.EXPECTED_EXECUTION_SHA:
        raise HermesExecutionError("canary closeout execution SHA drifted")
    if summary.get("semantic", {}).get("semantic_pass") is not False:
        raise HermesExecutionError("canary semantic failure was rewritten")
    if summary.get("infrastructure", {}).get("observed_context_length") != 65536:
        raise HermesExecutionError("canary closeout context evidence drifted")
    if summary.get("infrastructure", {}).get("alias_removed") is not True:
        raise HermesExecutionError("canary alias cleanup evidence drifted")
    expected_manifest = {
        "schema_version": "bench.hermes-canary-closeout-manifest.v1",
        "artifacts": {
            "summary.json": {
                "sha256": closeout.EXPECTED_SUMMARY_SHA256,
                "size_bytes": closeout.SUMMARY_PATH.stat().st_size,
            },
            "summary.md": {
                "sha256": closeout.EXPECTED_SUMMARY_MD_SHA256,
                "size_bytes": closeout.SUMMARY_MD_PATH.stat().st_size,
            },
        },
    }
    if manifest != expected_manifest:
        raise HermesExecutionError("canary closeout manifest drifted")
    canary_marker = _load_json(closeout.canary.MARKER_PATH)
    if canary_marker.get("enabled") is not False:
        raise HermesExecutionError("completed canary marker remains enabled")
    return summary


def validate_execution(*, require_enabled: bool | None = None) -> tuple[
    dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]
]:
    plan, candidates, cases = _validated_plan_with_disabled_marker()
    canary_closeout = _validated_closeout_with_disabled_full_marker()
    marker = _load_json(MARKER_PATH)
    expected_marker = {
        "batch_count": EXPECTED_BATCH_COUNT,
        "batch_size": EXPECTED_BATCH_SIZE,
        "plan_sha256": plan_validator.EXPECTED_PLAN_SHA256,
        "repetitions": EXPECTED_REPETITIONS,
        "schema_version": MARKER_SCHEMA,
    }
    for key, value in expected_marker.items():
        if marker.get(key) != value:
            raise HermesExecutionError(f"full-matrix marker binding drifted: {key}")
    if not isinstance(marker.get("enabled"), bool):
        raise HermesExecutionError("full-matrix marker enabled must be boolean")
    if require_enabled is not None and marker["enabled"] is not require_enabled:
        state = "enabled" if require_enabled else "disabled"
        raise HermesExecutionError(f"full-matrix marker must be {state}")

    if canary_closeout["decision"] != {
        "candidate_result_status": "failed",
        "full_matrix_infrastructure_gate": "satisfied",
        "full_matrix_may_proceed": True,
        "full_matrix_semantic_admission_gate": "not_applicable",
        "infrastructure_canary_status": "passed",
        "rationale": canary_closeout["decision"]["rationale"],
        "semantic_observation_status": "failed",
    }:
        raise HermesExecutionError("canary closeout decision drifted")
    if canary_closeout["semantic"]["semantic_pass"] is not False:
        raise HermesExecutionError("canary semantic failure was rewritten")
    if len(candidates) != 8 or len(cases) != 2:
        raise HermesExecutionError("full-matrix inventory is incomplete")
    if plan["counts"]["total_runs"] != 48:
        raise HermesExecutionError("full-matrix run count drifted")
    if plan["execution"]["context"]["required_num_ctx"] != 65536:
        raise HermesExecutionError("full-matrix context requirement drifted")
    if plan["admission_policy"]["bench1_direct_outcomes_are_admission_gate"] is not False:
        raise HermesExecutionError("BENCH-1 outcomes became an admission gate")

    runtime_workflow = RUNTIME_WORKFLOW_PATH.read_text(encoding="utf-8")
    if "runs-on: [self-hosted, Windows, X64, bluerev-bench]" not in runtime_workflow:
        raise HermesExecutionError("full-matrix runner binding drifted")
    if "matrix:" not in runtime_workflow or "batch: [0, 1, 2, 3]" not in runtime_workflow:
        raise HermesExecutionError("full-matrix batch matrix drifted")
    if "max-parallel: 1" not in runtime_workflow or "shell: cmd" not in runtime_workflow:
        raise HermesExecutionError("full-matrix serialization or Windows shell drifted")
    if "ref: ${{ github.sha }}" not in runtime_workflow:
        raise HermesExecutionError("full-matrix immutable checkout binding drifted")
    if "startsWith(github.event.head_commit.message, 'Activate BENCH-2 Hermes full matrix')" not in runtime_workflow:
        raise HermesExecutionError("full-matrix activation guard is missing")
    if "workflow_dispatch" in runtime_workflow:
        raise HermesExecutionError("full-matrix bridge exposes manual dispatch")
    if "python -m scripts.run_bench2_hermes_batch capture" not in runtime_workflow:
        raise HermesExecutionError("full-matrix capture entrypoint drifted")

    validation_workflow = VALIDATION_WORKFLOW_PATH.read_text(encoding="utf-8")
    lowered = validation_workflow.lower()
    if "runs-on: ubuntu-latest" not in validation_workflow:
        raise HermesExecutionError("full-matrix hosted validation runner drifted")
    if "self-hosted" in lowered or "ollama create" in lowered or "hermes -z" in lowered:
        raise HermesExecutionError("full-matrix branch validation can execute runtime work")
    if not RUNNER_PATH.is_file():
        raise HermesExecutionError("full-matrix runtime script is missing")
    return plan, marker, candidates, cases


def select_batch(candidates: list[dict[str, Any]], batch_index: int) -> tuple[list[dict[str, Any]], dict[str, int | str]]:
    return plan_validator.select_candidates(candidates, batch_index)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the BENCH-2 Hermes full-matrix runtime.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-enabled", action="store_true")
    args = parser.parse_args()
    try:
        plan, marker, candidates, cases = validate_execution(
            require_enabled=True if args.require_enabled else None
        )
        payload = {
            "schema_version": "bench.hermes-full-matrix-validation.v1",
            "status": "ready",
            "plan_sha256": plan_validator.EXPECTED_PLAN_SHA256,
            "canary_closeout_sha256": EXPECTED_CLOSEOUT_SHA256,
            "candidate_count": len(candidates),
            "case_count": len(cases),
            "batch_count": EXPECTED_BATCH_COUNT,
            "runs_per_batch": EXPECTED_RUNS_PER_BATCH,
            "total_runs": plan["counts"]["total_runs"],
            "execution_authorized": marker["enabled"],
            "semantic_admission_gate": "not_applicable",
        }
        code = 0
    except (
        HermesExecutionError,
        closeout.CanaryCloseoutError,
        closeout.canary.CanaryPlanError,
        closeout.canary.bench2.HermesPlanError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        payload = {
            "schema_version": "bench.hermes-full-matrix-validation.v1",
            "status": "invalid",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "execution_authorized": False,
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

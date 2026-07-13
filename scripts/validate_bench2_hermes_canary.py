from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from scripts import validate_bench2_hermes_plan as bench2

PLAN_PATH = ROOT / "fixtures/bench-plans/hermes-orchestrator-canary-v1.json"
MARKER_PATH = ROOT / "config/bench2-hermes-canary-oneshot.json"
RUNTIME_WORKFLOW_PATH = ROOT / ".github/workflows/bench2-hermes-canary-oneshot.yml"
VALIDATION_WORKFLOW_PATH = ROOT / ".github/workflows/bench2-hermes-canary-validation.yml"

PLAN_SCHEMA = "bench.hermes-orchestrator-canary-plan.v1"
MARKER_SCHEMA = "bench.hermes-orchestrator-canary-oneshot.v1"
EXPECTED_PLAN_SHA256 = "3f0a80fb5033d987af1117dd0c61c391aae8b86b86fd22d532be9abfe430c925"
EXPECTED_CANDIDATE = {
    "candidate_id": "qwythos-hermes-safe",
    "digest": "f1b4ecbbe67a7adef8f8f975cdbfb3eb08a04b8d91737b2b96e7b761187c668d",
    "model_tag": "qwythos-hermes-safe:latest",
    "selection_basis": "single infrastructure canary; not a semantic ranking or admission rule",
    "source_sequence": 7,
}
EXPECTED_CASE = {
    "capability": "HO-TOOLS",
    "case_definition_sha256": "f2f1889edfadf1cccf84ebac7650421478aeabfb6d9b3331e24034867e5aa1ca",
    "case_id": "ho-tools-hermes-lookup-001",
    "path": "fixtures/bench-2/ho-tools-hermes-lookup-001.json",
}
EXPECTED_SOURCE = {
    "bench2_plan_path": "fixtures/bench-plans/hermes-orchestrator-h4-eligible-plan-v2.json",
    "bench2_plan_sha256": bench2.EXPECTED_PLAN_SHA256,
    "candidate_registry_path": "candidates/bench2-h4-eligible.json",
    "candidate_registry_sha256": bench2.EXPECTED_REGISTRY_SHA256,
    "h4_execution_commit_sha": bench2.EXPECTED_H4_EXECUTION_SHA,
    "h4_summary_path": "reports/H4-HERMES-MINIMUM-64K/summary.json",
    "h4_summary_sha256": bench2.EXPECTED_H4_SUMMARY_SHA256,
    "h4_workflow_run_id": bench2.EXPECTED_H4_RUN_ID,
}


class CanaryPlanError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CanaryPlanError(f"cannot read {path}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise CanaryPlanError(f"{path} must contain an object")
    return value


def _definition_sha256(value: Any) -> str:
    return hashlib.sha256(
        (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    ).hexdigest()


def validate_canary_plan(
    plan_path: Path = PLAN_PATH,
    marker_path: Path = MARKER_PATH,
    *,
    require_enabled: bool | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    bench2_plan, candidates, cases = bench2.validate_plan()
    plan = _load_json(plan_path)
    if _definition_sha256(plan) != EXPECTED_PLAN_SHA256:
        raise CanaryPlanError("canary plan digest mismatch")
    if plan.get("schema_version") != PLAN_SCHEMA or plan.get("status") != "ready":
        raise CanaryPlanError("canary plan identity is invalid")
    if plan.get("candidate") != EXPECTED_CANDIDATE:
        raise CanaryPlanError("canary candidate binding drifted")
    if plan.get("case") != EXPECTED_CASE:
        raise CanaryPlanError("canary case binding drifted")
    if plan.get("source") != EXPECTED_SOURCE:
        raise CanaryPlanError("canary source binding drifted")
    if plan.get("counts") != {
        "candidates": 1, "cases": 1, "repetitions": 1, "total_runs": 1
    }:
        raise CanaryPlanError("canary counts drifted")
    if plan.get("authorization") != {
        "execution_marker_path": "config/bench2-hermes-canary-oneshot.json",
        "marker_must_be_enabled": True,
        "review_required_before_enable": True,
    }:
        raise CanaryPlanError("canary authorization contract drifted")
    expected_execution = {
        "actual_context_required": 65536,
        "cleanup_after_run": True,
        "cleanup_before_run": True,
        "endpoint": "http://127.0.0.1:11434/v1",
        "external_providers_allowed": False,
        "fallback_chain": [],
        "hermes": {
            "commit_sha": bench2.EXPECTED_HERMES_COMMIT,
            "ignore_rules": True,
            "isolated_home": True,
            "isolated_workdir": True,
            "mode": "oneshot",
            "plugin": "bench2-fixture",
            "toolsets": ["bench2_fixture"],
            "usage_file_required": True,
            "version": bench2.EXPECTED_HERMES_VERSION,
        },
        "jarvisos_access_allowed": False,
        "local_only": True,
        "max_api_calls": 2,
        "max_parallel_models": 1,
        "max_tool_calls": 1,
        "provider": "custom",
        "proxy_sink_for_external_hosts": True,
        "timeout_seconds": 600,
    }
    if plan.get("execution") != expected_execution:
        raise CanaryPlanError("canary execution contract drifted")
    if plan.get("gates") != {
        "context_and_gpu_residency_required": True,
        "hermes_identity_required": True,
        "manifest_required": True,
        "semantic_pass_required_before_full_matrix": True,
        "tool_sequence_must_match_exactly": True,
        "usage_report_required": True,
    }:
        raise CanaryPlanError("canary evidence gates drifted")

    candidate = next(
        (item for item in candidates if item["candidate_id"] == EXPECTED_CANDIDATE["candidate_id"]),
        None,
    )
    if candidate is None:
        raise CanaryPlanError("canary candidate is absent from BENCH-2 v2")
    if {
        "candidate_id": candidate["candidate_id"],
        "digest": candidate["digest"],
        "model_tag": candidate["model_tag"],
        "sequence": candidate["sequence"],
    } != {
        "candidate_id": EXPECTED_CANDIDATE["candidate_id"],
        "digest": EXPECTED_CANDIDATE["digest"],
        "model_tag": EXPECTED_CANDIDATE["model_tag"],
        "sequence": EXPECTED_CANDIDATE["source_sequence"],
    }:
        raise CanaryPlanError("canary candidate is not bound to the H4-qualified registry")

    case = next((item for item in cases if item["case_id"] == EXPECTED_CASE["case_id"]), None)
    if case is None:
        raise CanaryPlanError("canary case is absent from BENCH-2 v2")

    fixtures = plan.get("fixtures")
    if not isinstance(fixtures, dict):
        raise CanaryPlanError("canary fixture contract is missing")
    if fixtures.get("plugin_network_allowed") is not False:
        raise CanaryPlanError("canary plugin network boundary drifted")
    if fixtures.get("plugin_subprocess_allowed") is not False:
        raise CanaryPlanError("canary plugin subprocess boundary drifted")
    if fixtures.get("trace_required") is not True:
        raise CanaryPlanError("canary tool trace is not required")
    for item in fixtures.get("plugin_files", []):
        if not isinstance(item, dict):
            raise CanaryPlanError("canary plugin file record is invalid")
        path = ROOT / str(item.get("path"))
        if bench2._source_sha256(path) != item.get("sha256"):
            raise CanaryPlanError("canary plugin source digest drifted")
        if path.name == "__init__.py":
            bench2._validate_plugin_source(path)

    marker = _load_json(marker_path)
    expected_marker = {
        "candidate_id": EXPECTED_CANDIDATE["candidate_id"],
        "case_id": EXPECTED_CASE["case_id"],
        "plan_sha256": EXPECTED_PLAN_SHA256,
        "repetitions": 1,
        "schema_version": MARKER_SCHEMA,
    }
    for key, value in expected_marker.items():
        if marker.get(key) != value:
            raise CanaryPlanError(f"canary marker binding drifted: {key}")
    if not isinstance(marker.get("enabled"), bool):
        raise CanaryPlanError("canary marker enabled must be boolean")
    if require_enabled is not None and marker["enabled"] is not require_enabled:
        state = "enabled" if require_enabled else "disabled"
        raise CanaryPlanError(f"canary marker must be {state}")

    runtime_workflow = RUNTIME_WORKFLOW_PATH.read_text(encoding="utf-8")
    if "runs-on: [self-hosted, Windows, X64, bluerev-bench]" not in runtime_workflow:
        raise CanaryPlanError("canary runtime runner binding drifted")
    if "shell: cmd" not in runtime_workflow or "ref: ${{ github.sha }}" not in runtime_workflow:
        raise CanaryPlanError("canary Windows shell or immutable checkout binding drifted")
    if "startsWith(github.event.head_commit.message, 'Activate BENCH-2 Hermes canary')" not in runtime_workflow:
        raise CanaryPlanError("canary activation guard is missing")
    if "workflow_dispatch" in runtime_workflow:
        raise CanaryPlanError("canary bridge must not expose an unguarded manual dispatch")
    if "python -m scripts.run_bench2_hermes_canary capture" not in runtime_workflow:
        raise CanaryPlanError("canary runtime entrypoint drifted")

    validation_workflow = VALIDATION_WORKFLOW_PATH.read_text(encoding="utf-8")
    lowered = validation_workflow.lower()
    if "runs-on: ubuntu-latest" not in validation_workflow:
        raise CanaryPlanError("canary hosted validation runner drifted")
    if "self-hosted" in lowered or "ollama" in lowered or "hermes -z" in lowered:
        raise CanaryPlanError("canary branch validation can execute runtime work")

    return plan, marker, case


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the isolated BENCH-2 Hermes canary.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-enabled", action="store_true")
    args = parser.parse_args()
    try:
        plan, marker, _ = validate_canary_plan(
            require_enabled=True if args.require_enabled else None
        )
        payload = {
            "schema_version": "bench.hermes-canary-validation.v1",
            "status": "ready",
            "plan_sha256": EXPECTED_PLAN_SHA256,
            "candidate_id": plan["candidate"]["candidate_id"],
            "case_id": plan["case"]["case_id"],
            "total_runs": 1,
            "required_num_ctx": 65536,
            "execution_authorized": marker["enabled"],
            "full_matrix_authorized": False,
        }
        code = 0
    except (CanaryPlanError, bench2.HermesPlanError, OSError, ValueError, json.JSONDecodeError) as exc:
        payload = {
            "schema_version": "bench.hermes-canary-validation.v1",
            "status": "invalid",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "execution_authorized": False,
            "full_matrix_authorized": False,
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

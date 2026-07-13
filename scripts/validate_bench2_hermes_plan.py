from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from bench.contracts import ContractError, validate_candidate_manifest
from bench.evaluator import load_case_file
from scripts import probe_direct_semantic_campaign as direct

PLAN_PATH = ROOT / "fixtures" / "bench-plans" / "hermes-orchestrator-lane1-plan-v1.json"
REGISTRY_PATH = ROOT / "candidates" / "bench2-h3-lane1.json"
H3_SUMMARY_PATH = ROOT / "reports" / "H3-PRIMARY-32K" / "summary.json"
H3_MANIFEST_PATH = ROOT / "reports" / "H3-PRIMARY-32K" / "manifest.json"
MARKER_PATH = ROOT / "config" / "bench2-hermes-orchestrator-oneshot.json"

PLAN_SCHEMA = "bench.hermes-orchestrator-plan.v1"
EXPECTED_PLAN_SHA256 = "d6fa093c7950113e5776dc3d4f6c942d86f29b1e4a33f8191c6c1bdd160c3c19"
EXPECTED_REGISTRY_SHA256 = "fa8c555bf445b7ff34250a0ec7fe16783442894df197084f46cafcb71b6545a8"
EXPECTED_HERMES_COMMIT = "73b611ad19720d70308dad6b0fb64648aaadc216"
EXPECTED_HERMES_VERSION = "0.18.2"
EXPECTED_NON_PASS_SET = {
    "qwable-9b-fable5",
    "minicpm5-fable-1b-control",
    "gemma4-fable-agentic-12b",
    "gemma4-fable-coder-12b",
    "qwen3-8b",
}
BATCH_SIZE = 2
BATCH_COUNT = 5
REPETITIONS = 3

EXPECTED_ADMISSION = {
    "all_lane1_candidates_required": True,
    "bench1_direct_outcomes_are_admission_gate": False,
    "bench1_direct_outcomes_use": "post_hoc_explanatory_only",
    "h3_32k_qualification_required": True,
}
EXPECTED_COUNTS = {
    "candidate_case_pairs": 20,
    "candidates": 10,
    "cases": 2,
    "repetitions_per_pair": 3,
    "total_runs": 60,
}
EXPECTED_BATCHING = {
    "batch_count": BATCH_COUNT,
    "batch_size": BATCH_SIZE,
    "max_parallel_batches": 1,
}
EXPECTED_COMPARISON = {
    "compare_only_complete_valid_pairs": True,
    "global_composite_score_allowed": False,
    "invalid_infrastructure_is_not_model_failure": True,
    "minimum_repetitions": REPETITIONS,
    "ties_remain_ties": True,
}
EXPECTED_AUTHORIZATION = {
    "execution_marker_path": "config/bench2-hermes-orchestrator-oneshot.json",
    "marker_must_be_enabled": True,
    "review_required_before_enable": True,
}
EXPECTED_EXECUTION = {
    "cleanup_after_each_run": True,
    "cleanup_before_each_run": True,
    "context": {
        "mismatch_classification": "invalid_infrastructure",
        "required_num_ctx": 32768,
        "runtime_observation_required": True,
    },
    "endpoint": "http://127.0.0.1:11434/v1",
    "external_providers_allowed": False,
    "fallback_chain": [],
    "hermes": {
        "commit_sha": EXPECTED_HERMES_COMMIT,
        "ignore_rules": True,
        "isolated_home_per_run": True,
        "isolated_workdir_per_run": True,
        "mode": "oneshot",
        "plugin": "bench2-fixture",
        "toolsets": ["bench2_fixture"],
        "usage_file_required": True,
        "version": EXPECTED_HERMES_VERSION,
    },
    "jarvisos_access_allowed": False,
    "lane": "orchestrator_isolated",
    "local_only": True,
    "max_parallel_models": 1,
    "provider": "custom",
    "timeout_seconds": 600,
}
EXPECTED_FIXTURES = {
    "plugin_files": [
        {
            "path": "fixtures/bench-2/hermes-plugin/bench2-fixture/__init__.py",
            "sha256": "ae0124562e89eef0d37295fd0e72435819b0d23f25a86a0b0b9bc2a75744d67d",
        },
        {
            "path": "fixtures/bench-2/hermes-plugin/bench2-fixture/plugin.yaml",
            "sha256": "890cd78397a7291062ad40d0433e05aa13e38d991f297618995edaa81ffefa4a",
        },
    ],
    "plugin_is_read_only_except_trace": True,
    "plugin_network_allowed": False,
    "plugin_subprocess_allowed": False,
}
EXPECTED_SOURCE = {
    "candidate_registry_path": "candidates/bench2-h3-lane1.json",
    "candidate_registry_sha256": EXPECTED_REGISTRY_SHA256,
    "h3_closeout_commit_sha": direct.EXPECTED_H3_CLOSEOUT_SHA,
    "h3_manifest_path": "reports/H3-PRIMARY-32K/manifest.json",
    "h3_manifest_sha256": direct.EXPECTED_H3_MANIFEST_SHA256,
    "h3_summary_path": "reports/H3-PRIMARY-32K/summary.json",
    "h3_summary_sha256": direct.EXPECTED_H3_SUMMARY_SHA256,
}


class HermesPlanError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HermesPlanError(f"cannot read {path}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise HermesPlanError(f"{path} must contain an object")
    return value


def _definition_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _definition_sha256(value: Any) -> str:
    return hashlib.sha256(_definition_bytes(value)).hexdigest()


def _source_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _validate_plugin_source(path: Path) -> None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise HermesPlanError(f"fixture plugin is not valid Python: {type(exc).__name__}") from exc

    forbidden_roots = {"http", "requests", "socket", "subprocess", "urllib"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = {alias.name.split(".", 1)[0] for alias in node.names}
            if roots & forbidden_roots:
                raise HermesPlanError("fixture plugin imports network or subprocess modules")
        if isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root in forbidden_roots:
                raise HermesPlanError("fixture plugin imports network or subprocess modules")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"eval", "exec", "compile", "__import__"}:
                raise HermesPlanError("fixture plugin contains dynamic code execution")


def _validate_marker(marker_path: Path) -> dict[str, Any]:
    marker = _load_json(marker_path)
    expected = {
        "batch_count": BATCH_COUNT,
        "batch_size": BATCH_SIZE,
        "enabled": False,
        "plan_sha256": EXPECTED_PLAN_SHA256,
        "repetitions": REPETITIONS,
        "schema_version": "bench.hermes-orchestrator-oneshot.v1",
    }
    if marker != expected:
        raise HermesPlanError("BENCH-2 execution marker is not the reviewed disabled marker")
    return marker


def validate_plan(
    plan_path: Path = PLAN_PATH,
    registry_path: Path = REGISTRY_PATH,
    h3_summary_path: Path = H3_SUMMARY_PATH,
    h3_manifest_path: Path = H3_MANIFEST_PATH,
    marker_path: Path = MARKER_PATH,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    plan = _load_json(plan_path)
    if _definition_sha256(plan) != EXPECTED_PLAN_SHA256:
        raise HermesPlanError("BENCH-2 plan digest mismatch")
    if plan.get("schema_version") != PLAN_SCHEMA:
        raise HermesPlanError("BENCH-2 plan schema is invalid")
    if plan.get("status") != "ready":
        raise HermesPlanError("BENCH-2 plan status must be ready")
    if plan.get("scope") != "BENCH-2 Hermes orchestrator isolation Phase A":
        raise HermesPlanError("BENCH-2 scope drifted")
    if plan.get("admission_policy") != EXPECTED_ADMISSION:
        raise HermesPlanError("BENCH-2 admission policy drifted")
    if plan.get("authorization") != EXPECTED_AUTHORIZATION:
        raise HermesPlanError("BENCH-2 authorization policy drifted")
    if plan.get("batching") != EXPECTED_BATCHING:
        raise HermesPlanError("BENCH-2 batching drifted")
    if plan.get("counts") != EXPECTED_COUNTS or plan.get("repetitions") != REPETITIONS:
        raise HermesPlanError("BENCH-2 counts drifted")
    if plan.get("comparison_policy") != EXPECTED_COMPARISON:
        raise HermesPlanError("BENCH-2 comparison policy drifted")
    if plan.get("execution") != EXPECTED_EXECUTION:
        raise HermesPlanError("BENCH-2 execution isolation drifted")
    if plan.get("fixtures") != EXPECTED_FIXTURES:
        raise HermesPlanError("BENCH-2 fixture contract drifted")
    if plan.get("source") != EXPECTED_SOURCE:
        raise HermesPlanError("BENCH-2 source binding drifted")

    h3_candidates = direct._validate_h3_source(h3_summary_path, h3_manifest_path)

    registry = _load_json(registry_path)
    if _definition_sha256(registry) != EXPECTED_REGISTRY_SHA256:
        raise HermesPlanError("BENCH-2 candidate registry digest mismatch")
    try:
        validate_candidate_manifest(registry)
    except ContractError as exc:
        raise HermesPlanError(f"BENCH-2 candidate registry is invalid: {exc}") from exc

    registered = registry["candidates"]
    planned = plan.get("candidates")
    if not isinstance(planned, list) or len(planned) != 10 or len(registered) != 10:
        raise HermesPlanError("BENCH-2 must contain exactly all ten Lane 1 candidates")

    candidates: list[dict[str, Any]] = []
    for index, (plan_item, registry_item, h3_item) in enumerate(
        zip(planned, registered, h3_candidates, strict=True)
    ):
        expected_plan_item = {
            "candidate_id": registry_item["candidate_id"],
            "digest": registry_item["digest"],
            "model_tag": registry_item["model_tag"],
            "sequence": index,
        }
        if plan_item != expected_plan_item:
            raise HermesPlanError(f"candidate binding drifted at sequence {index}")
        if registry_item["enabled"] is not True or registry_item["initial_matrix"] is not True:
            raise HermesPlanError(f"Lane 1 candidate is disabled: {registry_item['candidate_id']}")
        if registry_item["expected_roles"] != ["hermes_orchestrator_candidate"]:
            raise HermesPlanError(f"candidate role drifted: {registry_item['candidate_id']}")
        if {"model_tag": registry_item["model_tag"], "digest": registry_item["digest"]} != h3_item:
            raise HermesPlanError(f"candidate is not H3-qualified: {registry_item['candidate_id']}")
        candidates.append(dict(plan_item))

    candidate_ids = {item["candidate_id"] for item in candidates}
    if not EXPECTED_NON_PASS_SET <= candidate_ids:
        raise HermesPlanError("BENCH-1 non-pass candidates were incorrectly filtered out")

    raw_cases = plan.get("cases")
    if not isinstance(raw_cases, list) or len(raw_cases) != 2:
        raise HermesPlanError("BENCH-2 Phase A must contain exactly two cases")
    cases: list[dict[str, Any]] = []
    for item in raw_cases:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise HermesPlanError("BENCH-2 case binding is invalid")
        path = ROOT / item["path"]
        try:
            case = load_case_file(path)
        except ContractError as exc:
            raise HermesPlanError(f"BENCH-2 case is invalid: {exc}") from exc
        if item.get("case_id") != case.get("case_id") or item.get("capability") != case.get("capability"):
            raise HermesPlanError(f"BENCH-2 case identity drifted: {item.get('path')}")
        if item.get("case_definition_sha256") != _definition_sha256(case):
            raise HermesPlanError(f"BENCH-2 case digest drifted: {case.get('case_id')}")
        cases.append({**item, "path_object": path})

    for fixture in EXPECTED_FIXTURES["plugin_files"]:
        path = ROOT / fixture["path"]
        if _source_sha256(path) != fixture["sha256"]:
            raise HermesPlanError(f"BENCH-2 fixture digest drifted: {fixture['path']}")
        if path.name == "__init__.py":
            _validate_plugin_source(path)

    _validate_marker(marker_path)
    return plan, candidates, cases


def select_candidates(
    candidates: list[dict[str, Any]], batch_index: int
) -> tuple[list[dict[str, Any]], dict[str, int | str]]:
    if not 0 <= batch_index < BATCH_COUNT:
        raise HermesPlanError("BENCH-2 batch index is outside the reviewed range")
    start = batch_index * BATCH_SIZE
    selected = candidates[start : start + BATCH_SIZE]
    if len(selected) != BATCH_SIZE:
        raise HermesPlanError("BENCH-2 batch is incomplete")
    return selected, {
        "mode": "batch",
        "batch_index": batch_index,
        "batch_size": BATCH_SIZE,
        "start": start,
        "end": start + BATCH_SIZE,
        "expected_candidates": BATCH_SIZE,
        "expected_runs": BATCH_SIZE * 2 * REPETITIONS,
        "total_candidates": 10,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the immutable BENCH-2 Hermes plan.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        plan, candidates, cases = validate_plan()
        payload = {
            "schema_version": "bench.hermes-plan-validation.v1",
            "status": "ready",
            "plan_sha256": EXPECTED_PLAN_SHA256,
            "candidate_count": len(candidates),
            "case_count": len(cases),
            "total_runs": plan["counts"]["total_runs"],
            "all_lane1_candidates_included": True,
            "bench1_direct_outcomes_are_admission_gate": False,
            "execution_authorized": False,
            "oneshot_marker_enabled": False,
            "required_num_ctx": plan["execution"]["context"]["required_num_ctx"],
            "runtime_context_observation_required": True,
        }
    except (HermesPlanError, OSError, ValueError, json.JSONDecodeError) as exc:
        payload = {
            "schema_version": "bench.hermes-plan-validation.v1",
            "status": "invalid",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "execution_authorized": False,
        }
        code = 2
    else:
        code = 0

    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

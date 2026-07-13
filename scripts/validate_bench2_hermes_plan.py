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
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from bench.contracts import ContractError, validate_candidate_manifest
from bench.evaluator import load_case_file

PLAN_PATH = ROOT / "fixtures/bench-plans/hermes-orchestrator-h4-eligible-plan-v2.json"
REGISTRY_PATH = ROOT / "candidates/bench2-h4-eligible.json"
H4_SUMMARY_PATH = ROOT / "reports/H4-HERMES-MINIMUM-64K/summary.json"
H4_MANIFEST_PATH = ROOT / "reports/H4-HERMES-MINIMUM-64K/manifest.json"
MARKER_PATH = ROOT / "config/bench2-hermes-orchestrator-oneshot.json"

PLAN_SCHEMA = "bench.hermes-orchestrator-plan.v2"
EXPECTED_PLAN_SHA256 = "0ac1832f959ff3780ecd36f44bc5d24ba49594529974b863a2aebcadeb55d312"
EXPECTED_REGISTRY_SHA256 = "67a311b7e4e75135dae6e1c2ce3dd25767b4d41f8439ec6bee7701d0c90881d7"
EXPECTED_H4_SUMMARY_SHA256 = "fc81c95c51ea55e9b79e293feee5fb9762655ccb1d2831b31ac4257fa5968af5"
EXPECTED_H4_MANIFEST_SHA256 = "d607ad513d98d07762bf5fbdc4e1c28ecc663d8d26c130f5b3fbeef40599efe1"
EXPECTED_H4_PLAN_SHA256 = "b94032a9104316f2e05cb4c1b8934772fee66804dd609d84a570d4f4e940e146"
EXPECTED_H4_RUN_ID = 29260032005
EXPECTED_H4_EXECUTION_SHA = "a2926cc93abb1a64874352c4508e8c97b0b6007f"
EXPECTED_HERMES_COMMIT = "73b611ad19720d70308dad6b0fb64648aaadc216"
EXPECTED_HERMES_VERSION = "0.18.2"
EXPECTED_ELIGIBLE_NON_PASS_SET = {
    "qwable-9b-fable5", "minicpm5-fable-1b-control",
    "gemma4-fable-agentic-12b", "gemma4-fable-coder-12b",
}
EXPECTED_EXCLUDED = {
    "qwen3.6-fablevibes-14b-a3b": "cpu_offload",
    "qwen3-8b": "context_mismatch",
}
BATCH_SIZE = 2
BATCH_COUNT = 4
REPETITIONS = 3
CANDIDATE_COUNT = 8


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


def _definition_sha256(value: Any) -> str:
    data = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    return hashlib.sha256(data).hexdigest()


def _source_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode()).hexdigest()


def _validate_plugin_source(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    forbidden = {"http", "requests", "socket", "subprocess", "urllib"}
    for node in ast.walk(tree):
        roots: set[str] = set()
        if isinstance(node, ast.Import):
            roots = {alias.name.split(".", 1)[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            roots = {(node.module or "").split(".", 1)[0]}
        if roots & forbidden:
            raise HermesPlanError("fixture plugin imports network or subprocess modules")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"eval", "exec", "compile", "__import__"}:
                raise HermesPlanError("fixture plugin contains dynamic code execution")


def _validate_h4_closeout() -> list[dict[str, str]]:
    if _source_sha256(H4_SUMMARY_PATH) != EXPECTED_H4_SUMMARY_SHA256:
        raise HermesPlanError("H4 summary digest mismatch")
    if _source_sha256(H4_MANIFEST_PATH) != EXPECTED_H4_MANIFEST_SHA256:
        raise HermesPlanError("H4 closeout manifest digest mismatch")
    summary = _load_json(H4_SUMMARY_PATH)
    manifest = _load_json(H4_MANIFEST_PATH)
    if summary.get("schema_version") != "bench.h4-hermes-minimum-64k-summary.v1":
        raise HermesPlanError("H4 summary schema is invalid")
    expected_counts = {
        "artifacts": 5, "candidates_attempted": 10, "context_mismatch": 1,
        "cpu_offload": 1, "load_failed": 0, "qualified_64k": 8,
        "stock_hermes_eligible": 8,
    }
    if summary.get("counts") != expected_counts:
        raise HermesPlanError("H4 closeout counts drifted")
    integrity = summary.get("integrity")
    true_keys = {
        "all_ten_h3_lane1_candidates_attempted",
        "all_five_jobs_completed_successfully",
        "all_archives_match_github_digest",
        "all_manifests_verified",
        "all_checkout_bindings_match_execution_commit",
        "all_cleanup_verified",
        "unique_candidate_names",
        "unique_candidate_digests",
    }
    false_keys = {
        "external_providers_used", "hermes_executed",
        "jarvisos_accessed", "secret_values_recorded",
    }
    if not isinstance(integrity, dict):
        raise HermesPlanError("H4 integrity contract is missing")
    if any(integrity.get(key) is not True for key in true_keys):
        raise HermesPlanError("H4 integrity contract is incomplete")
    if any(integrity.get(key) is not False for key in false_keys):
        raise HermesPlanError("H4 local-only boundary drifted")
    source = summary.get("source")
    if not isinstance(source, dict):
        raise HermesPlanError("H4 source binding is missing")
    if source.get("workflow_run_id") != EXPECTED_H4_RUN_ID:
        raise HermesPlanError("H4 workflow binding drifted")
    if source.get("execution_commit_sha") != EXPECTED_H4_EXECUTION_SHA:
        raise HermesPlanError("H4 execution SHA drifted")
    if source.get("h4_plan_sha256") != EXPECTED_H4_PLAN_SHA256:
        raise HermesPlanError("H4 plan binding drifted")
    manifest_items = manifest.get("artifacts")
    expected_files = {
        "summary.json": EXPECTED_H4_SUMMARY_SHA256,
        "summary.md": "878cc73ceaf6e3fc2e335f40aee57b92b83c94f31d5d502070a9602df6541732",
    }
    if not isinstance(manifest_items, dict):
        raise HermesPlanError("H4 manifest inventory is missing")
    for name, digest in expected_files.items():
        path = H4_SUMMARY_PATH.parent / name
        record = manifest_items.get(name)
        if not isinstance(record, dict) or record.get("sha256") != digest:
            raise HermesPlanError(f"H4 manifest binding drifted: {name}")
        if record.get("size_bytes") != path.stat().st_size or _source_sha256(path) != digest:
            raise HermesPlanError(f"H4 closeout artifact mismatch: {name}")
    qualified = summary.get("qualified_64k")
    if not isinstance(qualified, list) or len(qualified) != CANDIDATE_COUNT:
        raise HermesPlanError("H4 qualified inventory is invalid")
    nonqualified = summary.get("nonqualified")
    observed_excluded = {
        item.get("candidate_id"): item.get("status")
        for item in nonqualified if isinstance(item, dict)
    } if isinstance(nonqualified, list) else {}
    if observed_excluded != EXPECTED_EXCLUDED:
        raise HermesPlanError("H4 nonqualification inventory drifted")
    return [
        {"candidate_id": item["candidate_id"], "model_tag": item["name"], "digest": item["digest"]}
        for item in qualified
    ]


def validate_plan(
    plan_path: Path = PLAN_PATH,
    registry_path: Path = REGISTRY_PATH,
    marker_path: Path = MARKER_PATH,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    h4_candidates = _validate_h4_closeout()
    plan = _load_json(plan_path)
    if _definition_sha256(plan) != EXPECTED_PLAN_SHA256:
        raise HermesPlanError("BENCH-2 plan digest mismatch")
    if plan.get("schema_version") != PLAN_SCHEMA or plan.get("status") != "ready":
        raise HermesPlanError("BENCH-2 plan identity is invalid")
    expected_admission = {
        "all_h3_lane1_candidates_h4_attempted": True,
        "bench1_direct_outcomes_are_admission_gate": False,
        "bench1_direct_outcomes_use": "post_hoc_explanatory_only",
        "h4_qualified_64k_required": True,
        "infrastructure_nonqualification_is_admission_gate": True,
    }
    if plan.get("admission_policy") != expected_admission:
        raise HermesPlanError("BENCH-2 admission policy drifted")
    if plan.get("batching") != {"batch_count": 4, "batch_size": 2, "max_parallel_batches": 1}:
        raise HermesPlanError("BENCH-2 batching drifted")
    if plan.get("counts") != {
        "candidate_case_pairs": 16, "candidates": 8, "cases": 2,
        "repetitions_per_pair": 3, "total_runs": 48,
    }:
        raise HermesPlanError("BENCH-2 counts drifted")
    comparison = plan.get("comparison_policy")
    if not isinstance(comparison, dict) or comparison.get("global_composite_score_allowed") is not False:
        raise HermesPlanError("BENCH-2 comparison policy drifted")
    execution = plan.get("execution")
    if not isinstance(execution, dict):
        raise HermesPlanError("BENCH-2 execution contract is missing")
    if execution.get("context") != {
        "mismatch_classification": "invalid_infrastructure",
        "required_num_ctx": 65536,
        "runtime_observation_required": True,
    }:
        raise HermesPlanError("BENCH-2 context contract drifted")
    if execution.get("local_only") is not True or execution.get("external_providers_allowed") is not False:
        raise HermesPlanError("BENCH-2 local-only boundary drifted")
    if execution.get("fallback_chain") != [] or execution.get("max_parallel_models") != 1:
        raise HermesPlanError("BENCH-2 isolation drifted")
    hermes = execution.get("hermes")
    if not isinstance(hermes, dict):
        raise HermesPlanError("Hermes contract is missing")
    if hermes.get("commit_sha") != EXPECTED_HERMES_COMMIT or hermes.get("version") != EXPECTED_HERMES_VERSION:
        raise HermesPlanError("Hermes identity drifted")
    expected_source = {
        "candidate_registry_path": "candidates/bench2-h4-eligible.json",
        "candidate_registry_sha256": EXPECTED_REGISTRY_SHA256,
        "h4_execution_commit_sha": EXPECTED_H4_EXECUTION_SHA,
        "h4_manifest_path": "reports/H4-HERMES-MINIMUM-64K/manifest.json",
        "h4_manifest_sha256": EXPECTED_H4_MANIFEST_SHA256,
        "h4_plan_path": "fixtures/h4/h3-lane1-hermes-minimum-64k-plan.json",
        "h4_plan_sha256": EXPECTED_H4_PLAN_SHA256,
        "h4_summary_path": "reports/H4-HERMES-MINIMUM-64K/summary.json",
        "h4_summary_sha256": EXPECTED_H4_SUMMARY_SHA256,
        "h4_workflow_run_id": EXPECTED_H4_RUN_ID,
    }
    if plan.get("source") != expected_source:
        raise HermesPlanError("BENCH-2 source binding drifted")

    registry = _load_json(registry_path)
    if _definition_sha256(registry) != EXPECTED_REGISTRY_SHA256:
        raise HermesPlanError("BENCH-2 registry digest mismatch")
    try:
        validate_candidate_manifest(registry)
    except ContractError as exc:
        raise HermesPlanError(f"BENCH-2 registry is invalid: {exc}") from exc
    registered, planned = registry["candidates"], plan.get("candidates")
    if not isinstance(planned, list) or len(registered) != 8 or len(planned) != 8:
        raise HermesPlanError("BENCH-2 must contain exactly eight H4-qualified candidates")
    candidates: list[dict[str, Any]] = []
    for index, (plan_item, registry_item, h4_item) in enumerate(zip(planned, registered, h4_candidates, strict=True)):
        expected = {
            "candidate_id": registry_item["candidate_id"],
            "digest": registry_item["digest"],
            "model_tag": registry_item["model_tag"],
            "sequence": index,
        }
        if plan_item != expected:
            raise HermesPlanError(f"candidate binding drifted at sequence {index}")
        if registry_item["enabled"] is not True or registry_item["initial_matrix"] is not True:
            raise HermesPlanError("H4-qualified candidate is disabled")
        if registry_item["expected_roles"] != ["hermes_orchestrator_candidate"]:
            raise HermesPlanError("candidate role drifted")
        observed = {
            "candidate_id": registry_item["candidate_id"],
            "model_tag": registry_item["model_tag"],
            "digest": registry_item["digest"],
        }
        if observed != h4_item:
            raise HermesPlanError("candidate is not H4-qualified")
        candidates.append(dict(plan_item))
    candidate_ids = {item["candidate_id"] for item in candidates}
    if not EXPECTED_ELIGIBLE_NON_PASS_SET <= candidate_ids:
        raise HermesPlanError("BENCH-1 non-pass candidates were incorrectly filtered out")
    excluded = plan.get("excluded_after_h4")
    observed_excluded = {
        item.get("candidate_id"): item.get("h4_status")
        for item in excluded if isinstance(item, dict)
    } if isinstance(excluded, list) else {}
    if observed_excluded != EXPECTED_EXCLUDED or candidate_ids & set(EXPECTED_EXCLUDED):
        raise HermesPlanError("H4 exclusion binding drifted")

    raw_cases = plan.get("cases")
    if not isinstance(raw_cases, list) or len(raw_cases) != 2:
        raise HermesPlanError("BENCH-2 must contain exactly two cases")
    cases: list[dict[str, Any]] = []
    for item in raw_cases:
        path = ROOT / str(item.get("path"))
        try:
            case = load_case_file(path)
        except ContractError as exc:
            raise HermesPlanError(f"BENCH-2 case is invalid: {exc}") from exc
        if item.get("case_id") != case.get("case_id") or item.get("capability") != case.get("capability"):
            raise HermesPlanError("BENCH-2 case identity drifted")
        if item.get("case_definition_sha256") != _definition_sha256(case):
            raise HermesPlanError("BENCH-2 case digest drifted")
        cases.append({**item, "path_object": path})

    fixtures = plan.get("fixtures")
    if not isinstance(fixtures, dict):
        raise HermesPlanError("BENCH-2 fixture contract is missing")
    if fixtures.get("plugin_network_allowed") is not False or fixtures.get("plugin_subprocess_allowed") is not False:
        raise HermesPlanError("BENCH-2 fixture boundary drifted")
    for fixture in fixtures.get("plugin_files", []):
        path = ROOT / fixture["path"]
        if _source_sha256(path) != fixture["sha256"]:
            raise HermesPlanError("BENCH-2 fixture digest drifted")
        if path.name == "__init__.py":
            _validate_plugin_source(path)

    marker = _load_json(marker_path)
    if marker != {
        "batch_count": 4, "batch_size": 2, "enabled": False,
        "plan_sha256": EXPECTED_PLAN_SHA256, "repetitions": 3,
        "schema_version": "bench.hermes-orchestrator-oneshot.v1",
    }:
        raise HermesPlanError("BENCH-2 execution marker is not the reviewed disabled marker")
    return plan, candidates, cases


def select_candidates(candidates: list[dict[str, Any]], batch_index: int) -> tuple[list[dict[str, Any]], dict[str, int | str]]:
    if not 0 <= batch_index < BATCH_COUNT:
        raise HermesPlanError("BENCH-2 batch index is outside the reviewed range")
    start = batch_index * BATCH_SIZE
    selected = candidates[start : start + BATCH_SIZE]
    if len(selected) != BATCH_SIZE:
        raise HermesPlanError("BENCH-2 batch is incomplete")
    return selected, {
        "mode": "batch", "batch_index": batch_index, "batch_size": BATCH_SIZE,
        "start": start, "end": start + BATCH_SIZE,
        "expected_candidates": BATCH_SIZE,
        "expected_runs": BATCH_SIZE * 2 * REPETITIONS,
        "total_candidates": CANDIDATE_COUNT,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the H4-bound BENCH-2 plan.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        plan, candidates, cases = validate_plan()
        payload = {
            "schema_version": "bench.hermes-plan-validation.v2",
            "status": "ready",
            "plan_sha256": EXPECTED_PLAN_SHA256,
            "candidate_count": len(candidates),
            "case_count": len(cases),
            "total_runs": plan["counts"]["total_runs"],
            "all_h3_lane1_candidates_h4_attempted": True,
            "h4_qualified_candidates_included": True,
            "bench1_direct_outcomes_are_admission_gate": False,
            "execution_authorized": False,
            "oneshot_marker_enabled": False,
            "required_num_ctx": 65536,
        }
        code = 0
    except (HermesPlanError, OSError, ValueError, json.JSONDecodeError, SyntaxError) as exc:
        payload = {
            "schema_version": "bench.hermes-plan-validation.v2",
            "status": "invalid", "error_type": type(exc).__name__,
            "error": str(exc), "execution_authorized": False,
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

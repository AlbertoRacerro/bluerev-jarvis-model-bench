from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from bench.contracts import ContractError, validate_candidate_manifest, validate_manifest
from bench.direct_execution_v2 import KEEP_ALIVE, NUM_CTX, NUM_PREDICT, SEED, TEMPERATURE
from bench.direct_execution_v3 import execute_direct_smoke, verify_candidate_visible_response_contract
from bench.evaluator import load_case_file
from bench.loopback_http import open_loopback
from scripts.probe_model_residency_v2 import stop_all_running_models

SCHEMA_VERSION = "bench.direct-semantic-report.v1"
MANIFEST_SCHEMA = "bench.direct-semantic-manifest.v1"
PLAN_SCHEMA = "bench.direct-semantic-plan.v1"
EXPECTED_PLAN_SHA256 = "b87a01d5fc61e3630aeb99b08634c5d6474463f168fa6b1b07a80910565d6522"
EXPECTED_REGISTRY_SHA256 = "f370a0e87e7693d03a7ba9e074217a5e88641a5ea08d698a86211216bf84e750"
EXPECTED_H3_SUMMARY_SHA256 = "4e92a93269f3c574c86224f24535122aa14e1976508adeac69a49ea6fdf3bfcf"
EXPECTED_H3_MANIFEST_SHA256 = "10521b1cbc3762878a5b932d673d34d8744cade9acafd1f8da4dc386bbf0db3c"
EXPECTED_H3_CLOSEOUT_SHA = "7c82dc8335208c87c14a1dd0e1ae1de066bcba74"
EXPECTED_ROUTE_CONTRACT_SHA = "68a7fd7b4b25ee91803c7eabf133159327b6519a"
BATCH_SIZE = 2
BATCH_COUNT = 5
REPETITIONS = 3
RESULT_STATUSES = {"passed", "failed", "invalid"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

EXPECTED_EXECUTION = {
    "cleanup_after_each_run": True,
    "cleanup_before_each_run": True,
    "endpoint": "http://127.0.0.1:11434/api/generate",
    "external_providers_allowed": False,
    "hermes_execution_allowed": False,
    "jarvisos_access_allowed": False,
    "keep_alive": KEEP_ALIVE,
    "lane": "direct",
    "local_only": True,
    "max_parallel_models": 1,
    "num_ctx": NUM_CTX,
    "num_predict": NUM_PREDICT,
    "seed": SEED,
    "temperature": TEMPERATURE,
    "timeout_seconds": 180,
}
EXPECTED_COMPARISON = {
    "compare_only_complete_valid_pairs": True,
    "global_composite_score_allowed": False,
    "invalid_results_are_not_failures": True,
    "minimum_repetitions": 3,
    "ties_remain_ties": True,
}


class SemanticCampaignError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SemanticCampaignError(f"cannot read {path.name}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise SemanticCampaignError(f"{path.name} must contain an object")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _raw_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalized_source_bytes(path: Path) -> bytes:
    text = path.read_text(encoding="utf-8")
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _source_sha256(path: Path) -> str:
    return hashlib.sha256(_normalized_source_bytes(path)).hexdigest()


def _definition_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _definition_sha256(value: Any) -> str:
    return hashlib.sha256(_definition_bytes(value)).hexdigest()


def _validate_h3_source(summary_path: Path, manifest_path: Path) -> list[dict[str, str]]:
    if _source_sha256(summary_path) != EXPECTED_H3_SUMMARY_SHA256:
        raise SemanticCampaignError("H3 summary digest mismatch")
    if _source_sha256(manifest_path) != EXPECTED_H3_MANIFEST_SHA256:
        raise SemanticCampaignError("H3 manifest digest mismatch")
    summary = _load_json(summary_path)
    manifest = _load_json(manifest_path)
    if manifest.get("schema_version") != "bench.h3-primary-32k-summary-manifest.v1":
        raise SemanticCampaignError("H3 manifest schema is invalid")
    record = (manifest.get("artifacts") or {}).get("summary.json")
    if not isinstance(record, dict) or record.get("sha256") != EXPECTED_H3_SUMMARY_SHA256:
        raise SemanticCampaignError("H3 manifest does not bind the approved summary")
    if record.get("size_bytes") != len(_normalized_source_bytes(summary_path)):
        raise SemanticCampaignError("H3 summary canonical size mismatch")
    if summary.get("schema_version") != "bench.h3-primary-32k-summary.v1":
        raise SemanticCampaignError("H3 summary schema is invalid")
    if summary.get("counts") != {
        "artifacts": 5,
        "candidates": 10,
        "context_mismatch": 0,
        "cpu_offload": 0,
        "load_failed": 0,
        "qualified_32k": 10,
    }:
        raise SemanticCampaignError("H3 qualification counts drifted")
    qualified = summary.get("qualified_32k")
    if not isinstance(qualified, list) or len(qualified) != 10:
        raise SemanticCampaignError("H3 qualified candidate list is incomplete")
    result: list[dict[str, str]] = []
    seen_names: set[str] = set()
    seen_digests: set[str] = set()
    for item in qualified:
        if not isinstance(item, dict):
            raise SemanticCampaignError("H3 qualified candidate is not an object")
        name, digest = item.get("name"), item.get("digest")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(digest, str)
            or not _SHA256.fullmatch(digest)
            or name in seen_names
            or digest in seen_digests
        ):
            raise SemanticCampaignError("H3 qualified candidate identity is invalid")
        seen_names.add(name)
        seen_digests.add(digest)
        result.append({"model_tag": name, "digest": digest})
    return result


def validate_plan(
    plan_path: Path,
    registry_path: Path,
    h3_summary_path: Path,
    h3_manifest_path: Path,
    expected_plan_sha256: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    plan = _load_json(plan_path)
    if expected_plan_sha256 != EXPECTED_PLAN_SHA256 or _definition_sha256(plan) != EXPECTED_PLAN_SHA256:
        raise SemanticCampaignError("semantic campaign plan digest mismatch")
    if plan.get("schema_version") != PLAN_SCHEMA or plan.get("status") != "ready":
        raise SemanticCampaignError("semantic campaign plan schema or status is invalid")
    if plan.get("batching") != {"batch_count": 5, "batch_size": 2, "max_parallel_batches": 1}:
        raise SemanticCampaignError("semantic campaign batching drifted")
    if plan.get("repetitions") != REPETITIONS or plan.get("execution") != EXPECTED_EXECUTION:
        raise SemanticCampaignError("semantic campaign execution contract drifted")
    if plan.get("comparison_policy") != EXPECTED_COMPARISON:
        raise SemanticCampaignError("semantic campaign comparison policy drifted")
    if plan.get("counts") != {
        "candidate_case_pairs": 20,
        "candidates": 10,
        "cases": 2,
        "repetitions_per_pair": 3,
        "total_runs": 60,
    }:
        raise SemanticCampaignError("semantic campaign counts drifted")
    expected_source = {
        "candidate_registry_path": "candidates/bench1-h3-primary.json",
        "candidate_registry_sha256": EXPECTED_REGISTRY_SHA256,
        "h3_closeout_commit_sha": EXPECTED_H3_CLOSEOUT_SHA,
        "h3_manifest_path": "reports/H3-PRIMARY-32K/manifest.json",
        "h3_manifest_sha256": EXPECTED_H3_MANIFEST_SHA256,
        "h3_summary_path": "reports/H3-PRIMARY-32K/summary.json",
        "h3_summary_sha256": EXPECTED_H3_SUMMARY_SHA256,
        "route_contract_commit_sha": EXPECTED_ROUTE_CONTRACT_SHA,
    }
    if plan.get("source") != expected_source:
        raise SemanticCampaignError("semantic campaign source binding drifted")

    h3_candidates = _validate_h3_source(h3_summary_path, h3_manifest_path)
    registry = _load_json(registry_path)
    if _definition_sha256(registry) != EXPECTED_REGISTRY_SHA256:
        raise SemanticCampaignError("semantic candidate registry digest mismatch")
    try:
        validate_candidate_manifest(registry)
    except ContractError as exc:
        raise SemanticCampaignError(f"semantic candidate registry is invalid: {exc}") from exc
    registry_candidates = registry["candidates"]
    raw_candidates = plan.get("candidates")
    if not isinstance(raw_candidates, list) or len(raw_candidates) != 10:
        raise SemanticCampaignError("semantic campaign candidate list is incomplete")
    candidates: list[dict[str, Any]] = []
    for index, (planned, registered, h3_item) in enumerate(
        zip(raw_candidates, registry_candidates, h3_candidates, strict=True)
    ):
        expected = {
            "sequence": index,
            "candidate_id": registered["candidate_id"],
            "model_tag": registered["model_tag"],
            "digest": registered["digest"],
        }
        if planned != expected:
            raise SemanticCampaignError(f"semantic candidate binding drifted at sequence {index}")
        if {"model_tag": registered["model_tag"], "digest": registered["digest"]} != h3_item:
            raise SemanticCampaignError(f"semantic candidate is not H3-qualified: {registered['candidate_id']}")
        candidates.append(dict(planned))

    raw_cases = plan.get("cases")
    if not isinstance(raw_cases, list) or len(raw_cases) != 2:
        raise SemanticCampaignError("semantic campaign case list is incomplete")
    cases: list[dict[str, Any]] = []
    for index, item in enumerate(raw_cases):
        if not isinstance(item, dict):
            raise SemanticCampaignError("semantic case binding is not an object")
        path_value = item.get("path")
        if not isinstance(path_value, str):
            raise SemanticCampaignError("semantic case path is invalid")
        case_path = ROOT / path_value
        try:
            case = load_case_file(case_path)
            verify_candidate_visible_response_contract(case)
        except ContractError as exc:
            raise SemanticCampaignError(f"semantic case contract is invalid: {exc}") from exc
        if item.get("case_id") != case.get("case_id") or item.get("capability") != case.get("capability"):
            raise SemanticCampaignError(f"semantic case identity drifted at sequence {index}")
        if item.get("case_definition_sha256") != _definition_sha256(case):
            raise SemanticCampaignError(f"semantic case digest drifted: {case.get('case_id')}")
        cases.append({**item, "path_object": case_path})
    return plan, candidates, cases


def select_candidates(candidates: list[dict[str, Any]], batch_index: int) -> tuple[list[dict[str, Any]], dict[str, int | str]]:
    if not 0 <= batch_index < BATCH_COUNT:
        raise SemanticCampaignError("semantic campaign batch index is outside the approved range")
    start = batch_index * BATCH_SIZE
    end = start + BATCH_SIZE
    selected = candidates[start:end]
    if len(selected) != BATCH_SIZE:
        raise SemanticCampaignError("semantic campaign batch is incomplete")
    return selected, {
        "mode": "batch",
        "batch_index": batch_index,
        "batch_size": BATCH_SIZE,
        "start": start,
        "end": end,
        "expected_candidates": BATCH_SIZE,
        "expected_runs": BATCH_SIZE * 2 * REPETITIONS,
        "total_candidates": len(candidates),
    }


def _cleanup() -> dict[str, Any]:
    return {"verified_absent": True, "models": stop_all_running_models()}


def _finalize_run_manifest(run_dir: Path, repetition: int, campaign: dict[str, Any]) -> str:
    manifest_path = run_dir / "manifest.json"
    manifest = _load_json(manifest_path)
    manifest["repetition"] = repetition
    manifest["status"] = "invalid" if campaign["result_status"] == "invalid" else "validated"
    environment = manifest.get("environment")
    if not isinstance(environment, dict):
        raise SemanticCampaignError("run manifest environment is invalid")
    environment["campaign"] = campaign
    validate_manifest(manifest)
    _write_json(manifest_path, manifest)
    digest = _raw_sha256(manifest_path)
    summary_path = run_dir / "execution_summary.json"
    summary = _load_json(summary_path)
    summary["manifest_sha256"] = digest
    summary["campaign"] = campaign
    _write_json(summary_path, summary)
    return digest


def _execute_one(
    *,
    workflow_id: str,
    candidate: dict[str, Any],
    case: dict[str, Any],
    repetition: int,
    batch_index: int,
    registry_path: Path,
    preflight_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    run_id = (
        f"semantic-{workflow_id}-b{batch_index}-c{candidate['sequence']}-"
        f"k{case['case_id'][:8]}-r{repetition}"
    )
    cleanup_before = _cleanup()
    cleanup_after: dict[str, Any] | None = None
    try:
        summary = execute_direct_smoke(
            run_id=run_id,
            candidate_id=candidate["candidate_id"],
            candidate_registry_path=registry_path,
            case_path=case["path_object"],
            preflight_path=preflight_path,
            output_root=output_root,
            endpoint=EXPECTED_EXECUTION["endpoint"],
            timeout_seconds=EXPECTED_EXECUTION["timeout_seconds"],
            opener=open_loopback,
        )
    finally:
        cleanup_after = _cleanup()
    if cleanup_after.get("verified_absent") is not True:
        raise SemanticCampaignError("post-run Ollama cleanup was not verified")
    status = summary.get("candidate_result_status")
    if status not in RESULT_STATUSES:
        raise SemanticCampaignError(f"unsupported semantic result status: {status!r}")
    campaign = {
        "schema_version": "bench.direct-semantic-run-binding.v1",
        "plan_sha256": EXPECTED_PLAN_SHA256,
        "batch_index": batch_index,
        "candidate_sequence": candidate["sequence"],
        "case_id": case["case_id"],
        "capability": case["capability"],
        "repetition": repetition,
        "result_status": status,
    }
    run_dir = Path(summary["run_directory"])
    manifest_sha256 = _finalize_run_manifest(run_dir, repetition, campaign)
    ollama = _load_json(run_dir / "ollama_response.json")
    return {
        **campaign,
        "run_id": run_id,
        "run_directory": run_dir.relative_to(output_root.parent).as_posix(),
        "candidate_id": candidate["candidate_id"],
        "model_tag": candidate["model_tag"],
        "digest": candidate["digest"],
        "candidate_passed": summary.get("candidate_passed"),
        "termination_reason": summary.get("termination_reason"),
        "eval_count": summary.get("eval_count"),
        "num_predict": summary.get("num_predict"),
        "case_definition_sha256": summary.get("case_definition_sha256"),
        "manifest_sha256": manifest_sha256,
        "total_duration_ns": ollama.get("total_duration"),
        "load_duration_ns": ollama.get("load_duration"),
        "prompt_eval_count": ollama.get("prompt_eval_count"),
        "eval_duration_ns": ollama.get("eval_duration"),
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
    }


def write_manifest(output_dir: Path) -> dict[str, Any]:
    artifacts: dict[str, dict[str, Any]] = {}
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            relative = path.relative_to(output_dir).as_posix()
            artifacts[relative] = {"sha256": _raw_sha256(path), "size_bytes": path.stat().st_size}
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "artifacts": artifacts,
    }
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def build_report(
    *,
    plan_path: Path,
    registry_path: Path,
    h3_summary_path: Path,
    h3_manifest_path: Path,
    preflight_path: Path,
    output_dir: Path,
    batch_index: int,
    workflow_id: str,
) -> dict[str, Any]:
    created_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    results: list[dict[str, Any]] = []
    infrastructure_error: dict[str, str] | None = None
    selection: dict[str, int | str] | None = None
    initial_cleanup: dict[str, Any] | None = None
    final_cleanup: dict[str, Any] | None = None
    try:
        _, candidates, cases = validate_plan(
            plan_path,
            registry_path,
            h3_summary_path,
            h3_manifest_path,
            EXPECTED_PLAN_SHA256,
        )
        selected, selection = select_candidates(candidates, batch_index)
        initial_cleanup = _cleanup()
        for candidate in selected:
            for case in cases:
                for repetition in range(1, REPETITIONS + 1):
                    results.append(
                        _execute_one(
                            workflow_id=workflow_id,
                            candidate=candidate,
                            case=case,
                            repetition=repetition,
                            batch_index=batch_index,
                            registry_path=registry_path,
                            preflight_path=preflight_path,
                            output_root=output_dir / "runs",
                        )
                    )
    except (SemanticCampaignError, ContractError, OSError, ValueError) as exc:
        infrastructure_error = {"type": type(exc).__name__, "detail": str(exc)}
    finally:
        try:
            final_cleanup = _cleanup()
        except Exception as exc:
            detail = f"final cleanup failed: {type(exc).__name__}: {exc}"
            if infrastructure_error is None:
                infrastructure_error = {"type": type(exc).__name__, "detail": detail}
            else:
                infrastructure_error["detail"] += "; " + detail
    counts = Counter(item["result_status"] for item in results)
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": created_at,
        "workflow": {
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "event_name": os.environ.get("GITHUB_EVENT_NAME"),
            "sha": os.environ.get("GITHUB_SHA"),
            "ref": os.environ.get("GITHUB_REF"),
        },
        "source": {
            "plan_sha256": EXPECTED_PLAN_SHA256,
            "candidate_registry_sha256": EXPECTED_REGISTRY_SHA256,
            "h3_summary_sha256": EXPECTED_H3_SUMMARY_SHA256,
            "h3_manifest_sha256": EXPECTED_H3_MANIFEST_SHA256,
        },
        "selection": selection,
        "execution": EXPECTED_EXECUTION,
        "comparison_policy": EXPECTED_COMPARISON,
        "initial_cleanup": initial_cleanup,
        "final_cleanup": final_cleanup,
        "infrastructure_error": infrastructure_error,
        "result_counts": {status: counts.get(status, 0) for status in sorted(RESULT_STATUSES)},
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one BENCH-1 direct semantic batch.")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--h3-summary", type=Path, required=True)
    parser.add_argument("--h3-manifest", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--batch-index", type=int, required=True)
    parser.add_argument("--workflow-id", required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = build_report(
        plan_path=args.plan,
        registry_path=args.registry,
        h3_summary_path=args.h3_summary,
        h3_manifest_path=args.h3_manifest,
        preflight_path=args.preflight,
        output_dir=args.output_dir,
        batch_index=args.batch_index,
        workflow_id=args.workflow_id,
    )
    _write_json(args.output_dir / "report.json", report)
    write_manifest(args.output_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if report["infrastructure_error"] is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())

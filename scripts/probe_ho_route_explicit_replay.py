from __future__ import annotations

import argparse
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
from bench.direct_execution_v3 import verify_candidate_visible_response_contract
from bench.evaluator import load_case_file
from scripts import probe_direct_semantic_campaign as base

SCHEMA_VERSION = base.SCHEMA_VERSION
MANIFEST_SCHEMA = base.MANIFEST_SCHEMA
PLAN_SCHEMA = base.PLAN_SCHEMA
EXPECTED_PLAN_SHA256 = "b4853987a8aa3a2d3c6ed0b334a6e98c04871b3725cb2931fbd69dd08f716166"
EXPECTED_REGISTRY_SHA256 = base.EXPECTED_REGISTRY_SHA256
EXPECTED_H3_SUMMARY_SHA256 = base.EXPECTED_H3_SUMMARY_SHA256
EXPECTED_H3_MANIFEST_SHA256 = base.EXPECTED_H3_MANIFEST_SHA256
EXPECTED_H3_CLOSEOUT_SHA = base.EXPECTED_H3_CLOSEOUT_SHA
EXPECTED_ROUTE_CONTRACT_SHA = "79ad53e1194edbb7414e5e38a96ca6f0114ebd6c"
BATCH_SIZE = 2
BATCH_COUNT = 5
CASE_COUNT = 1
REPETITIONS = 3
RESULT_STATUSES = base.RESULT_STATUSES
EXPECTED_EXECUTION = base.EXPECTED_EXECUTION
EXPECTED_COMPARISON = base.EXPECTED_COMPARISON
SemanticCampaignError = base.SemanticCampaignError
ROOT = base.ROOT

_load_json = base._load_json
_write_json = base._write_json
_raw_sha256 = base._raw_sha256
_source_sha256 = base._source_sha256
_definition_sha256 = base._definition_sha256


def validate_plan(
    plan_path: Path,
    registry_path: Path,
    h3_summary_path: Path,
    h3_manifest_path: Path,
    expected_plan_sha256: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    plan = _load_json(plan_path)
    if (
        expected_plan_sha256 != EXPECTED_PLAN_SHA256
        or _definition_sha256(plan) != EXPECTED_PLAN_SHA256
    ):
        raise SemanticCampaignError("HO-ROUTE replay plan digest mismatch")
    if plan.get("schema_version") != PLAN_SCHEMA or plan.get("status") != "ready":
        raise SemanticCampaignError("HO-ROUTE replay plan schema or status is invalid")
    if plan.get("scope") != "BENCH-1 HO-ROUTE explicit replay":
        raise SemanticCampaignError("HO-ROUTE replay scope drifted")
    if plan.get("batching") != {
        "batch_count": BATCH_COUNT,
        "batch_size": BATCH_SIZE,
        "max_parallel_batches": 1,
    }:
        raise SemanticCampaignError("HO-ROUTE replay batching drifted")
    if plan.get("repetitions") != REPETITIONS or plan.get("execution") != EXPECTED_EXECUTION:
        raise SemanticCampaignError("HO-ROUTE replay execution contract drifted")
    if plan.get("comparison_policy") != EXPECTED_COMPARISON:
        raise SemanticCampaignError("HO-ROUTE replay comparison policy drifted")
    if plan.get("counts") != {
        "candidate_case_pairs": 10,
        "candidates": 10,
        "cases": CASE_COUNT,
        "repetitions_per_pair": REPETITIONS,
        "total_runs": 30,
    }:
        raise SemanticCampaignError("HO-ROUTE replay counts drifted")
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
        raise SemanticCampaignError("HO-ROUTE replay source binding drifted")

    h3_candidates = base._validate_h3_source(h3_summary_path, h3_manifest_path)
    registry = _load_json(registry_path)
    if _definition_sha256(registry) != EXPECTED_REGISTRY_SHA256:
        raise SemanticCampaignError("HO-ROUTE replay candidate registry digest mismatch")
    try:
        validate_candidate_manifest(registry)
    except ContractError as exc:
        raise SemanticCampaignError(
            f"HO-ROUTE replay candidate registry is invalid: {exc}"
        ) from exc

    registry_candidates = registry["candidates"]
    raw_candidates = plan.get("candidates")
    if not isinstance(raw_candidates, list) or len(raw_candidates) != 10:
        raise SemanticCampaignError("HO-ROUTE replay candidate list is incomplete")
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
            raise SemanticCampaignError(
                f"HO-ROUTE replay candidate binding drifted at sequence {index}"
            )
        if {
            "model_tag": registered["model_tag"],
            "digest": registered["digest"],
        } != h3_item:
            raise SemanticCampaignError(
                f"HO-ROUTE replay candidate is not H3-qualified: {registered['candidate_id']}"
            )
        candidates.append(dict(planned))

    raw_cases = plan.get("cases")
    if not isinstance(raw_cases, list) or len(raw_cases) != CASE_COUNT:
        raise SemanticCampaignError("HO-ROUTE replay case list must contain exactly one case")
    item = raw_cases[0]
    if not isinstance(item, dict):
        raise SemanticCampaignError("HO-ROUTE replay case binding is not an object")
    path_value = item.get("path")
    if path_value != "fixtures/bench-1-replays/ho-route-local-coder-explicit-002.json":
        raise SemanticCampaignError("HO-ROUTE replay case path drifted")
    case_path = ROOT / path_value
    try:
        case = load_case_file(case_path)
        verify_candidate_visible_response_contract(case)
    except ContractError as exc:
        raise SemanticCampaignError(
            f"HO-ROUTE replay case contract is invalid: {exc}"
        ) from exc
    if (
        item.get("case_id") != "ho-route-local-coder-explicit-002"
        or case.get("case_id") != item.get("case_id")
        or item.get("capability") != "HO-ROUTE"
        or case.get("capability") != item.get("capability")
    ):
        raise SemanticCampaignError("HO-ROUTE replay case identity drifted")
    if item.get("case_definition_sha256") != _definition_sha256(case):
        raise SemanticCampaignError("HO-ROUTE replay case digest drifted")
    return plan, candidates, [{**item, "path_object": case_path}]


def select_candidates(
    candidates: list[dict[str, Any]], batch_index: int
) -> tuple[list[dict[str, Any]], dict[str, int | str]]:
    if not 0 <= batch_index < BATCH_COUNT:
        raise SemanticCampaignError("HO-ROUTE replay batch index is outside the approved range")
    start = batch_index * BATCH_SIZE
    end = start + BATCH_SIZE
    selected = candidates[start:end]
    if len(selected) != BATCH_SIZE:
        raise SemanticCampaignError("HO-ROUTE replay batch is incomplete")
    return selected, {
        "mode": "batch",
        "batch_index": batch_index,
        "batch_size": BATCH_SIZE,
        "start": start,
        "end": end,
        "expected_candidates": BATCH_SIZE,
        "expected_runs": BATCH_SIZE * CASE_COUNT * REPETITIONS,
        "total_candidates": len(candidates),
    }


def _configure_base() -> None:
    base.EXPECTED_PLAN_SHA256 = EXPECTED_PLAN_SHA256
    base.EXPECTED_ROUTE_CONTRACT_SHA = EXPECTED_ROUTE_CONTRACT_SHA
    base.BATCH_SIZE = BATCH_SIZE
    base.BATCH_COUNT = BATCH_COUNT
    base.REPETITIONS = REPETITIONS
    base.validate_plan = validate_plan
    base.select_candidates = select_candidates


def write_manifest(output_dir: Path) -> dict[str, Any]:
    return base.write_manifest(output_dir)


def build_report(**kwargs: Any) -> dict[str, Any]:
    _configure_base()
    return base.build_report(**kwargs)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one explicit HO-ROUTE replay batch.")
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


_configure_base()

if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from bench.contracts import ContractError, validate_manifest
from scripts import probe_direct_semantic_campaign as probe
from scripts.benchmark_runtime import run_captured, safe_reset_directory, sanitize_environment
from scripts.test_subset import run_test_subset

ARTIFACT_ROOT = ROOT / "artifacts"
DEFAULT_ARTIFACTS = ARTIFACT_ROOT / "direct-semantic"
PLAN_PATH = ROOT / "fixtures" / "bench-plans" / "direct-semantic-plan-v1.json"
REGISTRY_PATH = ROOT / "candidates" / "bench1-h3-primary.json"
H3_SUMMARY_PATH = ROOT / "reports" / "H3-PRIMARY-32K" / "summary.json"
H3_MANIFEST_PATH = ROOT / "reports" / "H3-PRIMARY-32K" / "manifest.json"
MARKER_PATH = ROOT / "config" / "bench1-direct-semantic-oneshot.json"
TEST_PATTERNS = (
    "test_benchmark_runtime.py",
    "test_lane_test_subset.py",
    "test_preflight.py",
    "test_preflight_v2.py",
    "test_probe_model_residency.py",
    "test_probe_model_residency_v2.py",
    "test_contracts.py",
    "test_cases.py",
    "test_evaluator.py",
    "test_direct_execution*.py",
    "test_direct_semantic_campaign.py",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def marker_enabled(path: Path = MARKER_PATH) -> bool:
    try:
        value = _load_json(path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return False
    return value == {
        "batch_count": 5,
        "batch_size": 2,
        "enabled": True,
        "plan_sha256": probe.EXPECTED_PLAN_SHA256,
        "repetitions": 3,
        "schema_version": "bench.direct-semantic-oneshot.v1",
    }


def batch_index_from_environment() -> int:
    raw = os.environ.get("BENCH_SEMANTIC_BATCH_INDEX")
    try:
        value = int(raw or "")
    except ValueError as exc:
        raise ValueError("semantic batch index is missing or invalid") from exc
    if not 0 <= value < probe.BATCH_COUNT:
        raise ValueError("semantic batch index is outside the approved range")
    return value


def selection_for(batch_index: int) -> dict[str, int | str]:
    start = batch_index * probe.BATCH_SIZE
    return {
        "mode": "batch",
        "batch_index": batch_index,
        "batch_size": probe.BATCH_SIZE,
        "start": start,
        "end": start + probe.BATCH_SIZE,
        "expected_candidates": probe.BATCH_SIZE,
        "expected_runs": probe.BATCH_SIZE * 2 * probe.REPETITIONS,
        "total_candidates": 10,
    }


def _environment() -> tuple[dict[str, str], list[str]]:
    environment, removed = sanitize_environment(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(SRC)))
    return environment, removed


def capture(artifact_dir: Path = DEFAULT_ARTIFACTS) -> int:
    safe_reset_directory(artifact_dir, allowed_root=ARTIFACT_ROOT)
    environment, removed = _environment()
    try:
        batch_index = batch_index_from_environment()
    except ValueError as exc:
        _write_json(
            artifact_dir / "job-summary.json",
            {
                "schema_version": "bench.direct-semantic-job.v1",
                "test_scope": "direct-semantic-campaign",
                "selection": {"mode": "invalid", "error": str(exc)},
                "tests": {"exit_code": 0},
                "inventory": {"exit_code": 0},
                "probe": {"exit_code": 2, "error_type": type(exc).__name__},
            },
        )
        return 0

    tests = run_test_subset(
        patterns=TEST_PATTERNS,
        root=ROOT,
        environment=environment,
        artifact_dir=artifact_dir,
        timeout_seconds_per_pattern=300,
    )
    inventory = run_captured(
        "preflight",
        [
            sys.executable,
            "scripts/preflight_v2.py",
            "--output",
            str(artifact_dir / "preflight.json"),
            "--required-gate",
            "direct",
        ],
        cwd=ROOT,
        environment=environment,
        artifact_dir=artifact_dir,
        timeout_seconds=180,
    )
    summary: dict[str, Any] = {
        "schema_version": "bench.direct-semantic-job.v1",
        "test_scope": "direct-semantic-campaign",
        "python": sys.executable,
        "repository_root": str(ROOT),
        "sanitization": {
            "removed_external_env_names": removed,
            "secret_values_recorded": False,
            "external_providers_allowed": False,
            "hermes_executed": False,
            "jarvisos_accessed": False,
        },
        "source": {
            "plan_sha256": probe.EXPECTED_PLAN_SHA256,
            "candidate_registry_sha256": probe.EXPECTED_REGISTRY_SHA256,
            "h3_summary_sha256": probe.EXPECTED_H3_SUMMARY_SHA256,
            "h3_manifest_sha256": probe.EXPECTED_H3_MANIFEST_SHA256,
        },
        "selection": selection_for(batch_index),
        "tests": tests,
        "inventory": inventory,
        "probe": {"exit_code": 0, "skipped_reason": None},
    }
    if tests["exit_code"] != 0 or inventory["exit_code"] != 0:
        summary["probe"] = {
            "exit_code": 0,
            "skipped_reason": "prerequisite_failure",
        }
        _write_json(artifact_dir / "job-summary.json", summary)
        return 0
    if not marker_enabled() or os.environ.get("GITHUB_REF") != "refs/heads/main":
        summary["probe"] = {
            "exit_code": 2,
            "skipped_reason": None,
            "error_type": "SemanticCampaignAuthorizationError",
        }
        _write_json(artifact_dir / "job-summary.json", summary)
        return 0
    try:
        probe.validate_plan(
            PLAN_PATH,
            REGISTRY_PATH,
            H3_SUMMARY_PATH,
            H3_MANIFEST_PATH,
            probe.EXPECTED_PLAN_SHA256,
        )
    except (probe.SemanticCampaignError, OSError, ValueError) as exc:
        summary["probe"] = {
            "exit_code": 2,
            "skipped_reason": None,
            "error_type": type(exc).__name__,
            "error_detail": str(exc),
        }
        _write_json(artifact_dir / "job-summary.json", summary)
        return 0

    workflow_id = "-".join(
        (
            environment.get("GITHUB_RUN_ID", "missing"),
            environment.get("GITHUB_RUN_ATTEMPT", "missing"),
        )
    )
    campaign_dir = artifact_dir / "campaign"
    summary["probe"] = run_captured(
        "semantic-probe",
        [
            sys.executable,
            "scripts/probe_direct_semantic_campaign.py",
            "--plan",
            str(PLAN_PATH),
            "--registry",
            str(REGISTRY_PATH),
            "--h3-summary",
            str(H3_SUMMARY_PATH),
            "--h3-manifest",
            str(H3_MANIFEST_PATH),
            "--preflight",
            str(artifact_dir / "preflight.json"),
            "--output-dir",
            str(campaign_dir),
            "--batch-index",
            str(batch_index),
            "--workflow-id",
            workflow_id,
        ],
        cwd=ROOT,
        environment=environment,
        artifact_dir=artifact_dir,
        timeout_seconds=3600,
    )
    _write_json(artifact_dir / "job-summary.json", summary)
    return 0


def _validate_campaign_manifest(campaign_dir: Path) -> list[str]:
    failures: list[str] = []
    manifest_path = campaign_dir / "manifest.json"
    if not manifest_path.is_file():
        return ["semantic campaign manifest is missing"]
    manifest = _load_json(manifest_path)
    if manifest.get("schema_version") != probe.MANIFEST_SCHEMA:
        failures.append("semantic campaign manifest schema is invalid")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return failures + ["semantic campaign artifact inventory is missing"]
    expected_paths = {
        path.relative_to(campaign_dir).as_posix()
        for path in campaign_dir.rglob("*")
        if path.is_file() and path != manifest_path
    }
    if set(artifacts) != expected_paths:
        failures.append("semantic campaign manifest inventory does not match files")
    for relative, record in artifacts.items():
        path = campaign_dir / relative
        if not isinstance(record, dict) or not path.is_file():
            failures.append(f"semantic artifact is missing: {relative}")
            continue
        if record.get("sha256") != probe._raw_sha256(path):
            failures.append(f"semantic artifact digest mismatch: {relative}")
        if record.get("size_bytes") != path.stat().st_size:
            failures.append(f"semantic artifact size mismatch: {relative}")
    return failures


def enforce(artifact_dir: Path = DEFAULT_ARTIFACTS) -> int:
    summary_path = artifact_dir / "job-summary.json"
    if not summary_path.is_file():
        print("missing semantic campaign job summary", file=sys.stderr)
        return 2
    try:
        summary = _load_json(summary_path)
        if summary.get("schema_version") != "bench.direct-semantic-job.v1":
            raise ValueError("unsupported semantic campaign job schema")
        if summary.get("test_scope") != "direct-semantic-campaign":
            raise ValueError("semantic campaign test scope is invalid")
        test_exit = int(summary["tests"]["exit_code"])
        inventory_exit = int(summary["inventory"]["exit_code"])
        probe_exit = int(summary["probe"]["exit_code"])
        batch_index = int(summary["selection"]["batch_index"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"invalid semantic campaign job summary: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    failures: list[str] = []
    if test_exit != 0:
        failures.append(f"semantic campaign tests exited {test_exit}")
    if inventory_exit != 0:
        failures.append(f"semantic campaign preflight exited {inventory_exit}")
    if probe_exit != 0:
        failures.append(f"semantic campaign probe infrastructure exited {probe_exit}")
    if failures:
        print("; ".join(failures), file=sys.stderr)
        return 1

    campaign_dir = artifact_dir / "campaign"
    report_path = campaign_dir / "report.json"
    try:
        report = _load_json(report_path)
        _, candidates, cases = probe.validate_plan(
            PLAN_PATH,
            REGISTRY_PATH,
            H3_SUMMARY_PATH,
            H3_MANIFEST_PATH,
            probe.EXPECTED_PLAN_SHA256,
        )
    except (OSError, ValueError, json.JSONDecodeError, probe.SemanticCampaignError) as exc:
        print(f"invalid semantic campaign report/source: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if report.get("schema_version") != probe.SCHEMA_VERSION:
        failures.append("semantic campaign report schema is invalid")
    if report.get("source") != summary.get("source"):
        failures.append("semantic campaign report source binding drifted")
    if report.get("selection") != selection_for(batch_index):
        failures.append("semantic campaign selection is invalid")
    if report.get("execution") != probe.EXPECTED_EXECUTION:
        failures.append("semantic campaign execution parameters drifted")
    if report.get("comparison_policy") != probe.EXPECTED_COMPARISON:
        failures.append("semantic campaign comparison policy drifted")
    if report.get("infrastructure_error") is not None:
        failures.append("semantic campaign report contains an infrastructure error")
    if not isinstance(report.get("final_cleanup"), dict) or report["final_cleanup"].get("verified_absent") is not True:
        failures.append("semantic campaign final cleanup is not attested")

    selected, _ = probe.select_candidates(candidates, batch_index)
    expected = [
        (candidate, case, repetition)
        for candidate in selected
        for case in cases
        for repetition in range(1, probe.REPETITIONS + 1)
    ]
    results = report.get("results")
    if not isinstance(results, list) or len(results) != len(expected):
        failures.append("semantic campaign result inventory is incomplete")
        results = []
    seen_run_ids: set[str] = set()
    for result, (candidate, case, repetition) in zip(results, expected, strict=False):
        if not isinstance(result, dict):
            failures.append("semantic campaign result is not an object")
            continue
        if (
            result.get("candidate_id") != candidate["candidate_id"]
            or result.get("model_tag") != candidate["model_tag"]
            or result.get("digest") != candidate["digest"]
            or result.get("case_id") != case["case_id"]
            or result.get("capability") != case["capability"]
            or result.get("repetition") != repetition
            or result.get("batch_index") != batch_index
        ):
            failures.append("semantic campaign candidate/case/repetition binding drifted")
        status = result.get("result_status")
        if status not in probe.RESULT_STATUSES:
            failures.append("semantic campaign result status is invalid")
        if result.get("case_definition_sha256") != case["case_definition_sha256"]:
            failures.append("semantic campaign case definition digest drifted")
        if not isinstance(result.get("manifest_sha256"), str) or not _SHA256.fullmatch(result["manifest_sha256"]):
            failures.append("semantic campaign run manifest digest is missing")
        if not isinstance(result.get("cleanup_after"), dict) or result["cleanup_after"].get("verified_absent") is not True:
            failures.append("semantic campaign run cleanup is not attested")
        run_id = result.get("run_id")
        if not isinstance(run_id, str) or run_id in seen_run_ids:
            failures.append("semantic campaign run identity is invalid or duplicated")
            continue
        seen_run_ids.add(run_id)
        run_dir_value = result.get("run_directory")
        if not isinstance(run_dir_value, str):
            failures.append("semantic campaign run directory is missing")
            continue
        run_dir = campaign_dir / run_dir_value.removeprefix("campaign/")
        manifest_path = run_dir / "manifest.json"
        try:
            manifest = _load_json(manifest_path)
            validate_manifest(manifest)
        except (OSError, ValueError, json.JSONDecodeError, ContractError) as exc:
            failures.append(f"semantic run manifest is invalid: {type(exc).__name__}")
            continue
        if probe._raw_sha256(manifest_path) != result.get("manifest_sha256"):
            failures.append("semantic run manifest digest mismatch")
        if manifest.get("candidate") != candidate["candidate_id"] or manifest.get("case_id") != case["case_id"]:
            failures.append("semantic run manifest identity drifted")
        if manifest.get("repetition") != repetition:
            failures.append("semantic run manifest repetition drifted")
        expected_manifest_status = "invalid" if status == "invalid" else "validated"
        if manifest.get("status") != expected_manifest_status:
            failures.append("semantic run manifest status drifted")
        campaign = (manifest.get("environment") or {}).get("campaign")
        if not isinstance(campaign, dict) or campaign.get("plan_sha256") != probe.EXPECTED_PLAN_SHA256:
            failures.append("semantic run campaign binding is missing")
        for relative, artifact in manifest.get("artifacts", {}).items():
            path = run_dir / relative
            if not path.is_file() or artifact.get("sha256") != probe._raw_sha256(path):
                failures.append(f"semantic run artifact digest mismatch: {run_id}/{relative}")
    failures.extend(_validate_campaign_manifest(campaign_dir))
    if failures:
        print("; ".join(failures), file=sys.stderr)
        return 1
    counts = report.get("result_counts")
    print(
        "BENCH-1 direct semantic infrastructure gate passed; "
        f"batch={batch_index}; passed={counts.get('passed') if isinstance(counts, dict) else None}; "
        f"failed={counts.get('failed') if isinstance(counts, dict) else None}; "
        f"invalid={counts.get('invalid') if isinstance(counts, dict) else None}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("capture", "enforce"))
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACTS)
    args = parser.parse_args()
    return capture(args.artifact_dir) if args.mode == "capture" else enforce(args.artifact_dir)


if __name__ == "__main__":
    raise SystemExit(main())

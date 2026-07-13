from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts import probe_ho_route_explicit_replay as probe
from scripts import run_direct_semantic_campaign_job as base_job
from scripts.benchmark_runtime import run_captured, safe_reset_directory, sanitize_environment
from scripts.test_subset import run_test_subset

ARTIFACT_ROOT = ROOT / "artifacts"
DEFAULT_ARTIFACTS = ARTIFACT_ROOT / "direct-semantic"
PLAN_PATH = ROOT / "fixtures" / "bench-plans" / "ho-route-explicit-replay-v2.json"
REGISTRY_PATH = ROOT / "candidates" / "bench1-h3-primary.json"
H3_SUMMARY_PATH = ROOT / "reports" / "H3-PRIMARY-32K" / "summary.json"
H3_MANIFEST_PATH = ROOT / "reports" / "H3-PRIMARY-32K" / "manifest.json"
MARKER_PATH = ROOT / "config" / "ho-route-explicit-replay-oneshot.json"
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
    "test_direct_semantic_enforce_entry.py",
    "test_ho_route_explicit_replay.py",
)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def marker_enabled(path: Path = MARKER_PATH) -> bool:
    try:
        value = _load_json(path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return False
    return value == {
        "batch_count": probe.BATCH_COUNT,
        "batch_size": probe.BATCH_SIZE,
        "enabled": True,
        "plan_sha256": probe.EXPECTED_PLAN_SHA256,
        "repetitions": probe.REPETITIONS,
        "schema_version": "bench.ho-route-explicit-replay-oneshot.v1",
    }


def batch_index_from_environment() -> int:
    raw = os.environ.get("BENCH_SEMANTIC_BATCH_INDEX")
    try:
        value = int(raw or "")
    except ValueError as exc:
        raise ValueError("HO-ROUTE replay batch index is missing or invalid") from exc
    if not 0 <= value < probe.BATCH_COUNT:
        raise ValueError("HO-ROUTE replay batch index is outside the approved range")
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
        "expected_runs": probe.BATCH_SIZE * probe.CASE_COUNT * probe.REPETITIONS,
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
        "campaign_scope": "HO-ROUTE-explicit-replay",
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
        "ho-route-replay-probe",
        [
            sys.executable,
            "scripts/probe_ho_route_explicit_replay.py",
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
        timeout_seconds=2400,
    )
    _write_json(artifact_dir / "job-summary.json", summary)
    return 0


def _configure_base_job() -> None:
    base_job.probe = probe
    base_job.PLAN_PATH = PLAN_PATH
    base_job.REGISTRY_PATH = REGISTRY_PATH
    base_job.H3_SUMMARY_PATH = H3_SUMMARY_PATH
    base_job.H3_MANIFEST_PATH = H3_MANIFEST_PATH
    base_job.DEFAULT_ARTIFACTS = DEFAULT_ARTIFACTS
    base_job.selection_for = selection_for


def enforce(artifact_dir: Path = DEFAULT_ARTIFACTS) -> int:
    _configure_base_job()
    return base_job.enforce(artifact_dir)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("capture", "enforce"))
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACTS)
    args = parser.parse_args()
    return capture(args.artifact_dir) if args.mode == "capture" else enforce(args.artifact_dir)


_configure_base_job()

if __name__ == "__main__":
    raise SystemExit(main())

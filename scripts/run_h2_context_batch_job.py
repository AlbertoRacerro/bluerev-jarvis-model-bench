from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from scripts import run_h2_context_job as base
from scripts.benchmark_runtime import run_captured, safe_reset_directory
from scripts.test_subset import run_test_subset

BATCH_SIZE = 3
BATCH_COUNT = 4
BATCH_TEST_PATTERNS = base.TEST_PATTERNS + ("test_h2_batch_job.py",)


def batch_index_from_environment() -> int:
    raw = os.environ.get("BENCH_H2_BATCH_INDEX")
    try:
        value = int(raw or "")
    except ValueError as exc:
        raise ValueError("H2 batch index is missing or invalid") from exc
    if not 0 <= value < BATCH_COUNT:
        raise ValueError("H2 batch index is outside the approved range")
    return value


def selection_for(index: int) -> dict[str, int | str]:
    start = index * BATCH_SIZE
    end = min(start + BATCH_SIZE, 12)
    return {
        "mode": "batch",
        "batch_index": index,
        "batch_size": BATCH_SIZE,
        "start": start,
        "end": end,
        "expected_count": end - start,
        "total_candidates": 12,
    }


def capture(artifact_dir: Path) -> int:
    safe_reset_directory(artifact_dir, allowed_root=base.ARTIFACT_ROOT)
    environment, removed = base._environment()
    try:
        index = batch_index_from_environment()
        selection = selection_for(index)
    except ValueError as exc:
        base._write_summary(
            artifact_dir,
            {
                "schema_version": "bench.h2-context-job.v1",
                "test_scope": "h2-primary-16k-batch",
                "selection": {"mode": "invalid", "error": str(exc)},
                "tests": {"exit_code": 0},
                "probe": {"exit_code": 2, "error_type": type(exc).__name__},
            },
        )
        return 0

    tests = run_test_subset(
        patterns=BATCH_TEST_PATTERNS,
        root=base.ROOT,
        environment=environment,
        artifact_dir=artifact_dir,
        timeout_seconds_per_pattern=300,
    )
    summary: dict[str, Any] = {
        "schema_version": "bench.h2-context-job.v1",
        "test_scope": "h2-primary-16k-batch",
        "python": sys.executable,
        "repository_root": str(base.ROOT),
        "sanitization": {
            "removed_external_env_names": removed,
            "secret_values_recorded": False,
            "external_providers_allowed": False,
        },
        "source": {
            "plan_path": base.PLAN_PATH.relative_to(base.ROOT).as_posix(),
            "plan_sha256": base.EXPECTED_PLAN_SHA256,
        },
        "selection": selection,
        "tests": tests,
        "probe": {
            "exit_code": 0,
            "skipped_reason": "prerequisite_failure" if tests["exit_code"] else None,
        },
    }
    if tests["exit_code"] != 0:
        base._write_summary(artifact_dir, summary)
        return 0
    if (
        not base.PLAN_PATH.is_file()
        or base._sha256(base.PLAN_PATH) != base.EXPECTED_PLAN_SHA256
    ):
        summary["probe"] = {
            "exit_code": 2,
            "skipped_reason": None,
            "error_type": "H2PlanBindingError",
        }
        base._write_summary(artifact_dir, summary)
        return 0

    probe_dir = artifact_dir / "h2-primary-16k"
    summary["probe"] = run_captured(
        "h2-probe",
        [
            sys.executable,
            "scripts/probe_h2_context_batch.py",
            "--plan",
            str(base.PLAN_PATH),
            "--expected-plan-sha256",
            base.EXPECTED_PLAN_SHA256,
            "--output-dir",
            str(probe_dir),
            "--batch-index",
            str(index),
            "--batch-size",
            str(BATCH_SIZE),
        ],
        cwd=base.ROOT,
        environment=environment,
        artifact_dir=artifact_dir,
        timeout_seconds=9000,
    )
    base._write_summary(artifact_dir, summary)
    return 0


def enforce(artifact_dir: Path) -> int:
    summary_path = base._summary_path(artifact_dir)
    if not summary_path.is_file():
        print(f"missing H2 batch summary: {summary_path}", file=sys.stderr)
        return 2
    try:
        summary = base._load_json(summary_path)
        if summary.get("schema_version") != "bench.h2-context-job.v1":
            raise ValueError("unsupported H2 batch job schema")
        if summary.get("test_scope") != "h2-primary-16k-batch":
            raise ValueError("H2 batch test scope is invalid")
        test_exit = int(summary["tests"]["exit_code"])
        probe_exit = int(summary["probe"]["exit_code"])
        selection = summary["selection"]
        expected_count = int(selection["expected_count"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"invalid H2 batch summary: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    failures: list[str] = []
    if test_exit != 0:
        failures.append(f"H2 batch tests exited {test_exit}")
    if probe_exit != 0:
        failures.append(f"H2 batch probe infrastructure exited {probe_exit}")
    if failures:
        print("; ".join(failures), file=sys.stderr)
        return 1

    probe_dir = artifact_dir / "h2-primary-16k"
    try:
        report = base._load_json(probe_dir / "report.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"invalid H2 batch report: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if report.get("schema_version") != "bench.h2-context-report.v1":
        failures.append("H2 batch report schema is invalid")
    if report.get("selection") != selection:
        failures.append("H2 batch selection does not match the job summary")
    if report.get("candidate_count") != expected_count:
        failures.append("H2 batch candidate count is invalid")
    if report.get("infrastructure_error") is not None:
        failures.append("H2 batch contains an infrastructure error")
    results = report.get("results")
    if not isinstance(results, list) or len(results) != expected_count:
        failures.append("H2 batch result inventory is incomplete")
        results = []
    seen: set[str] = set()
    for result in results:
        model = result.get("model") if isinstance(result, dict) else None
        name = model.get("name") if isinstance(model, dict) else None
        if not isinstance(name, str) or not name or name in seen:
            failures.append("H2 batch candidate identity is invalid or duplicated")
        else:
            seen.add(name)
        if result.get("status") not in base._ALLOWED_RESULTS:
            failures.append(f"H2 batch candidate status is invalid: {name}")
        cleanup = result.get("cleanup_after")
        if not isinstance(cleanup, dict) or cleanup.get("verified_absent") is not True:
            failures.append(f"H2 batch cleanup is not attested: {name}")
    failures.extend(base._validate_manifest(probe_dir, report))
    if failures:
        print("; ".join(failures), file=sys.stderr)
        return 1
    print(
        "H2 16K batch evidence gate passed; "
        f"batch={selection['batch_index']}; candidates={expected_count}"
    )
    return 0

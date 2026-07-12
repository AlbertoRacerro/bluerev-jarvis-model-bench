from __future__ import annotations

import argparse
import hashlib
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

from scripts.benchmark_runtime import run_captured, safe_reset_directory, sanitize_environment
from scripts.test_subset import run_test_subset

DEFAULT_ARTIFACTS = ROOT / "artifacts" / "context-qualification"
ARTIFACT_ROOT = ROOT / "artifacts"
PLAN_PATH = ROOT / "fixtures" / "h2" / "h1-primary-context-plan.json"
EXPECTED_PLAN_SHA256 = "cce4863f87520dae70ea97fcd75a88d4ada0dff874202376cc9223ea6c29868a"
TEST_PATTERNS = (
    "test_benchmark_runtime.py",
    "test_lane_test_subset.py",
    "test_probe_model_residency.py",
    "test_probe_model_residency_v2.py",
    "test_probe_h2_context.py",
    "test_run_h2_context_job.py",
    "test_h2_oneshot_bridge.py",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_RESULTS = {
    "qualified_16k",
    "cpu_offload",
    "context_mismatch",
    "load_failed",
}


def _environment() -> tuple[dict[str, str], list[str]]:
    environment, removed = sanitize_environment(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(SRC)))
    return environment, removed


def _summary_path(artifact_dir: Path) -> Path:
    return artifact_dir / "job-summary.json"


def _write_summary(artifact_dir: Path, value: dict[str, Any]) -> None:
    path = _summary_path(artifact_dir)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(value, indent=2, sort_keys=True))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture(artifact_dir: Path = DEFAULT_ARTIFACTS) -> int:
    safe_reset_directory(artifact_dir, allowed_root=ARTIFACT_ROOT)
    environment, removed = _environment()
    tests = run_test_subset(
        patterns=TEST_PATTERNS,
        root=ROOT,
        environment=environment,
        artifact_dir=artifact_dir,
        timeout_seconds_per_pattern=300,
    )
    summary: dict[str, Any] = {
        "schema_version": "bench.h2-context-job.v1",
        "test_scope": "h2-primary-16k",
        "python": sys.executable,
        "repository_root": str(ROOT),
        "sanitization": {
            "removed_external_env_names": removed,
            "secret_values_recorded": False,
            "external_providers_allowed": False,
        },
        "source": {
            "plan_path": PLAN_PATH.relative_to(ROOT).as_posix(),
            "plan_sha256": EXPECTED_PLAN_SHA256,
        },
        "tests": tests,
        "probe": {
            "exit_code": 0,
            "skipped_reason": "prerequisite_failure" if tests["exit_code"] else None,
        },
    }
    if tests["exit_code"] != 0:
        _write_summary(artifact_dir, summary)
        return 0

    if not PLAN_PATH.is_file() or _sha256(PLAN_PATH) != EXPECTED_PLAN_SHA256:
        summary["probe"] = {
            "exit_code": 2,
            "skipped_reason": None,
            "error_type": "H2PlanBindingError",
        }
        _write_summary(artifact_dir, summary)
        return 0

    probe_dir = artifact_dir / "h2-primary-16k"
    probe = run_captured(
        "h2-probe",
        [
            sys.executable,
            "scripts/probe_h2_context.py",
            "--plan",
            str(PLAN_PATH),
            "--expected-plan-sha256",
            EXPECTED_PLAN_SHA256,
            "--output-dir",
            str(probe_dir),
        ],
        cwd=ROOT,
        environment=environment,
        artifact_dir=artifact_dir,
        timeout_seconds=9000,
    )
    summary["probe"] = probe
    _write_summary(artifact_dir, summary)
    return 0


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _validate_manifest(probe_dir: Path, report: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    manifest_path = probe_dir / "manifest.json"
    if not manifest_path.is_file():
        return ["H2 manifest is missing"]
    manifest = _load_json(manifest_path)
    if manifest.get("schema_version") != "bench.h2-context-manifest.v1":
        failures.append("H2 manifest schema is invalid")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return failures + ["H2 manifest artifact map is missing"]
    expected_paths = {"report.json"}
    results = report.get("results")
    if isinstance(results, list):
        expected_paths.update(
            "models/" + item["artifact_slug"] + "/result.json"
            for item in results
            if isinstance(item, dict) and isinstance(item.get("artifact_slug"), str)
        )
    if set(artifacts) != expected_paths:
        failures.append("H2 manifest inventory does not match report results")
    for relative, record in artifacts.items():
        path = probe_dir / relative
        if not isinstance(record, dict) or not path.is_file():
            failures.append(f"H2 manifest artifact is missing: {relative}")
            continue
        digest = record.get("sha256")
        size = record.get("size_bytes")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            failures.append(f"H2 manifest digest is invalid: {relative}")
        elif _sha256(path) != digest:
            failures.append(f"H2 manifest digest mismatch: {relative}")
        if size != path.stat().st_size:
            failures.append(f"H2 manifest size mismatch: {relative}")
    return failures


def enforce(artifact_dir: Path = DEFAULT_ARTIFACTS) -> int:
    summary_path = _summary_path(artifact_dir)
    if not summary_path.is_file():
        print(f"missing H2 job summary: {summary_path}", file=sys.stderr)
        return 2
    try:
        summary = _load_json(summary_path)
        if summary.get("schema_version") != "bench.h2-context-job.v1":
            raise ValueError("unsupported H2 job schema")
        if summary.get("test_scope") != "h2-primary-16k":
            raise ValueError("H2 test scope is invalid")
        test_exit = int(summary["tests"]["exit_code"])
        probe_exit = int(summary["probe"]["exit_code"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"invalid H2 job summary: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    failures: list[str] = []
    if test_exit != 0:
        failures.append(f"H2 tests exited {test_exit}")
    if probe_exit != 0:
        failures.append(f"H2 probe infrastructure exited {probe_exit}")
    if failures:
        print("; ".join(failures), file=sys.stderr)
        return 1

    probe_dir = artifact_dir / "h2-primary-16k"
    report_path = probe_dir / "report.json"
    try:
        report = _load_json(report_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"invalid H2 report: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if report.get("schema_version") != "bench.h2-context-report.v1":
        failures.append("H2 report schema is invalid")
    source = report.get("source")
    if not isinstance(source, dict) or source.get("plan_sha256") != EXPECTED_PLAN_SHA256:
        failures.append("H2 report is not bound to the approved plan")
    if report.get("infrastructure_error") is not None:
        failures.append("H2 report contains an infrastructure error")
    results = report.get("results")
    if not isinstance(results, list) or len(results) != 12:
        failures.append("H2 report does not contain all 12 primary candidates")
        results = []
    seen_names: set[str] = set()
    for result in results:
        if not isinstance(result, dict):
            failures.append("H2 candidate result is not an object")
            continue
        model = result.get("model")
        name = model.get("name") if isinstance(model, dict) else None
        if not isinstance(name, str) or not name or name in seen_names:
            failures.append("H2 candidate identity is invalid or duplicated")
        else:
            seen_names.add(name)
        if result.get("status") not in _ALLOWED_RESULTS:
            failures.append(f"H2 candidate status is invalid: {name}")
        cleanup = result.get("cleanup_after")
        if not isinstance(cleanup, dict) or cleanup.get("verified_absent") is not True:
            failures.append(f"H2 cleanup is not attested: {name}")
        if not isinstance(result.get("artifact_slug"), str):
            failures.append(f"H2 artifact binding is missing: {name}")
    final_cleanup = report.get("final_cleanup")
    if not isinstance(final_cleanup, list):
        failures.append("H2 final cleanup evidence is missing")
    failures.extend(_validate_manifest(probe_dir, report))
    if failures:
        print("; ".join(failures), file=sys.stderr)
        return 1

    counts = report.get("status_counts")
    print(
        "H2 16K evidence gate passed; "
        f"qualified={counts.get('qualified_16k') if isinstance(counts, dict) else None}; "
        f"cpu_offload={counts.get('cpu_offload') if isinstance(counts, dict) else None}; "
        f"context_mismatch={counts.get('context_mismatch') if isinstance(counts, dict) else None}; "
        f"load_failed={counts.get('load_failed') if isinstance(counts, dict) else None}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("capture", "enforce"))
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACTS)
    args = parser.parse_args()
    if args.mode == "capture":
        return capture(args.artifact_dir)
    return enforce(args.artifact_dir)


if __name__ == "__main__":
    raise SystemExit(main())

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

DEFAULT_ARTIFACTS = ROOT / "artifacts" / "context-64k-qualification"
ARTIFACT_ROOT = ROOT / "artifacts"
PLAN_PATH = ROOT / "fixtures" / "h4" / "h3-lane1-hermes-minimum-64k-plan.json"
SUMMARY_PATH = ROOT / "reports" / "H3-PRIMARY-32K" / "summary.json"
SUMMARY_MANIFEST_PATH = ROOT / "reports" / "H3-PRIMARY-32K" / "manifest.json"
EXPECTED_PLAN_SHA256 = "b94032a9104316f2e05cb4c1b8934772fee66804dd609d84a570d4f4e940e146"
EXPECTED_SUMMARY_SHA256 = "4e92a93269f3c574c86224f24535122aa14e1976508adeac69a49ea6fdf3bfcf"
EXPECTED_SUMMARY_MANIFEST_SHA256 = "10521b1cbc3762878a5b932d673d34d8744cade9acafd1f8da4dc386bbf0db3c"
BATCH_SIZE = 2
BATCH_COUNT = 5
PROFILE = {
    "name": "h4-hermes-minimum-64k-context",
    "num_ctx": 65536,
    "num_predict": 32,
    "temperature": 0,
    "seed": 4242,
    "keep_alive": "5m",
    "request_timeout_seconds": 900,
}
TEST_PATTERNS = (
    "test_benchmark_runtime.py",
    "test_lane_test_subset.py",
    "test_probe_model_residency.py",
    "test_probe_model_residency_v2.py",
    "test_probe_h4_context.py",
    "test_run_h4_context_job.py",
)
_ALLOWED_RESULTS = {"qualified_64k", "cpu_offload", "context_mismatch", "load_failed"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _environment() -> tuple[dict[str, str], list[str]]:
    environment, removed = sanitize_environment(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(SRC)))
    return environment, removed


def _summary_path(artifact_dir: Path) -> Path:
    return artifact_dir / "job-summary.json"


def _write_summary(artifact_dir: Path, value: dict[str, Any]) -> None:
    _summary_path(artifact_dir).write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(value, indent=2, sort_keys=True))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def batch_index_from_environment() -> int:
    try:
        value = int(os.environ.get("BENCH_H4_BATCH_INDEX", ""))
    except ValueError as exc:
        raise ValueError("H4 batch index is missing or invalid") from exc
    if not 0 <= value < BATCH_COUNT:
        raise ValueError("H4 batch index is outside the approved range")
    return value


def selection_for(index: int) -> dict[str, int | str]:
    if not 0 <= index < BATCH_COUNT:
        raise ValueError("H4 batch index is outside the approved range")
    start = index * BATCH_SIZE
    return {
        "mode": "batch",
        "batch_index": index,
        "batch_size": BATCH_SIZE,
        "start": start,
        "end": start + BATCH_SIZE,
        "expected_count": BATCH_SIZE,
        "total_candidates": 10,
    }


def _source_files_are_bound() -> bool:
    return all(
        path.is_file() and _source_sha256(path) == digest
        for path, digest in (
            (PLAN_PATH, EXPECTED_PLAN_SHA256),
            (SUMMARY_PATH, EXPECTED_SUMMARY_SHA256),
            (SUMMARY_MANIFEST_PATH, EXPECTED_SUMMARY_MANIFEST_SHA256),
        )
    )


def capture(artifact_dir: Path = DEFAULT_ARTIFACTS) -> int:
    safe_reset_directory(artifact_dir, allowed_root=ARTIFACT_ROOT)
    environment, removed = _environment()
    try:
        index = batch_index_from_environment()
        selection = selection_for(index)
    except ValueError as exc:
        _write_summary(
            artifact_dir,
            {
                "schema_version": "bench.h4-context-job.v1",
                "test_scope": "h4-hermes-minimum-64k-batch",
                "selection": {"mode": "invalid", "error": str(exc)},
                "tests": {"exit_code": 0},
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
    summary = {
        "schema_version": "bench.h4-context-job.v1",
        "test_scope": "h4-hermes-minimum-64k-batch",
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
            "summary_path": SUMMARY_PATH.relative_to(ROOT).as_posix(),
            "summary_sha256": EXPECTED_SUMMARY_SHA256,
            "summary_manifest_path": SUMMARY_MANIFEST_PATH.relative_to(ROOT).as_posix(),
            "summary_manifest_sha256": EXPECTED_SUMMARY_MANIFEST_SHA256,
        },
        "selection": selection,
        "tests": tests,
        "probe": {
            "exit_code": 0,
            "skipped_reason": "prerequisite_failure" if tests["exit_code"] else None,
        },
    }
    if tests["exit_code"] != 0:
        _write_summary(artifact_dir, summary)
        return 0
    if not _source_files_are_bound():
        summary["probe"] = {
            "exit_code": 2,
            "skipped_reason": None,
            "error_type": "H4SourceBindingError",
        }
        _write_summary(artifact_dir, summary)
        return 0
    probe_dir = artifact_dir / "h4-hermes-minimum-64k"
    summary["probe"] = run_captured(
        "h4-probe",
        [
            sys.executable,
            "scripts/probe_h4_context.py",
            "--plan",
            str(PLAN_PATH),
            "--summary",
            str(SUMMARY_PATH),
            "--summary-manifest",
            str(SUMMARY_MANIFEST_PATH),
            "--expected-plan-sha256",
            EXPECTED_PLAN_SHA256,
            "--output-dir",
            str(probe_dir),
            "--batch-index",
            str(index),
        ],
        cwd=ROOT,
        environment=environment,
        artifact_dir=artifact_dir,
        timeout_seconds=10800,
    )
    _write_summary(artifact_dir, summary)
    return 0


def _validate_manifest(probe_dir: Path, report: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    manifest_path = probe_dir / "manifest.json"
    if not manifest_path.is_file():
        return ["H4 manifest is missing"]
    manifest = _load_json(manifest_path)
    artifacts = manifest.get("artifacts")
    if manifest.get("schema_version") != "bench.h4-context-manifest.v1":
        failures.append("H4 manifest schema is invalid")
    if not isinstance(artifacts, dict):
        return failures + ["H4 manifest artifact map is missing"]
    expected = {"report.json"}
    results = report.get("results")
    if isinstance(results, list):
        expected.update(
            "models/" + item["artifact_slug"] + "/result.json"
            for item in results
            if isinstance(item, dict) and isinstance(item.get("artifact_slug"), str)
        )
    if set(artifacts) != expected:
        failures.append("H4 manifest inventory does not match report results")
    for relative, record in artifacts.items():
        path = probe_dir / relative
        if not isinstance(record, dict) or not path.is_file():
            failures.append(f"H4 manifest artifact is missing: {relative}")
            continue
        digest, size = record.get("sha256"), record.get("size_bytes")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            failures.append(f"H4 manifest digest is invalid: {relative}")
        elif _sha256(path) != digest:
            failures.append(f"H4 manifest digest mismatch: {relative}")
        if size != path.stat().st_size:
            failures.append(f"H4 manifest size mismatch: {relative}")
    return failures


def _expected_batch_candidates(index: int) -> list[dict[str, str]]:
    candidates = _load_json(PLAN_PATH).get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 10:
        raise ValueError("H4 plan candidate inventory is invalid")
    selection = selection_for(index)
    return [
        {"name": item["name"], "digest": item["digest"]}
        for item in candidates[selection["start"] : selection["end"]]
        if isinstance(item, dict)
    ]


def enforce(artifact_dir: Path = DEFAULT_ARTIFACTS) -> int:
    path = _summary_path(artifact_dir)
    if not path.is_file():
        print(f"missing H4 job summary: {path}", file=sys.stderr)
        return 2
    try:
        summary = _load_json(path)
        if summary.get("schema_version") != "bench.h4-context-job.v1" or summary.get("test_scope") != "h4-hermes-minimum-64k-batch":
            raise ValueError("unsupported H4 job contract")
        test_exit = int(summary["tests"]["exit_code"])
        probe_exit = int(summary["probe"]["exit_code"])
        selection = summary["selection"]
        index = int(selection["batch_index"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"invalid H4 job summary: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    failures: list[str] = []
    if test_exit != 0:
        failures.append(f"H4 tests exited {test_exit}")
    if probe_exit != 0:
        failures.append(f"H4 probe infrastructure exited {probe_exit}")
    try:
        expected_selection = selection_for(index)
    except ValueError as exc:
        failures.append(str(exc))
        expected_selection = {}
    if selection != expected_selection:
        failures.append("H4 job selection does not match the approved batch")
    if failures:
        print("; ".join(failures), file=sys.stderr)
        return 1
    probe_dir = artifact_dir / "h4-hermes-minimum-64k"
    try:
        report = _load_json(probe_dir / "report.json")
        expected_candidates = _expected_batch_candidates(index)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"invalid H4 evidence: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if report.get("schema_version") != "bench.h4-context-report.v1":
        failures.append("H4 report schema is invalid")
    source = report.get("source")
    if not isinstance(source, dict) or source.get("plan_sha256") != EXPECTED_PLAN_SHA256 or source.get("h3_summary_sha256") != EXPECTED_SUMMARY_SHA256 or source.get("h3_summary_manifest_sha256") != EXPECTED_SUMMARY_MANIFEST_SHA256:
        failures.append("H4 report is not bound to the approved source")
    if report.get("profile") != PROFILE:
        failures.append("H4 report profile drifted")
    if report.get("selection") != expected_selection:
        failures.append("H4 report selection does not match the approved batch")
    if report.get("infrastructure_error") is not None:
        failures.append("H4 report contains an infrastructure error")
    results = report.get("results")
    if not isinstance(results, list) or len(results) != 2:
        failures.append("H4 report does not contain exactly two candidates")
        results = []
    observed: list[dict[str, str]] = []
    for result in results:
        if not isinstance(result, dict):
            failures.append("H4 candidate result is not an object")
            continue
        model = result.get("model")
        name = model.get("name") if isinstance(model, dict) else None
        digest = model.get("digest") if isinstance(model, dict) else None
        if isinstance(name, str) and isinstance(digest, str):
            observed.append({"name": name, "digest": digest})
        else:
            failures.append("H4 candidate identity is invalid")
        if result.get("schema_version") != "bench.h4-context-result.v1":
            failures.append(f"H4 candidate result schema is invalid: {name}")
        if result.get("profile") != PROFILE:
            failures.append(f"H4 candidate profile drifted: {name}")
        if result.get("status") not in _ALLOWED_RESULTS:
            failures.append(f"H4 candidate status is invalid: {name}")
        cleanup = result.get("cleanup_after")
        if not isinstance(cleanup, dict) or cleanup.get("verified_absent") is not True:
            failures.append(f"H4 cleanup is not attested: {name}")
        if not isinstance(result.get("artifact_slug"), str):
            failures.append(f"H4 artifact binding is missing: {name}")
    if observed != expected_candidates:
        failures.append("H4 candidate identities do not match the approved batch")
    if not isinstance(report.get("final_cleanup"), list):
        failures.append("H4 final cleanup evidence is missing")
    failures.extend(_validate_manifest(probe_dir, report))
    if failures:
        print("; ".join(failures), file=sys.stderr)
        return 1
    counts = report.get("status_counts")
    print(
        "H4 64K batch evidence gate passed; "
        f"batch={index}; "
        f"qualified={counts.get('qualified_64k') if isinstance(counts, dict) else None}; "
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
    return capture(args.artifact_dir) if args.mode == "capture" else enforce(args.artifact_dir)


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from scripts import probe_direct_semantic_campaign as probe
from scripts import probe_model_residency as residency
from scripts import run_direct_semantic_campaign_job as job


def repository_snapshot() -> dict[str, Any]:
    head = residency._run(["git", "rev-parse", "HEAD"], timeout=30)
    unstaged = residency._run(["git", "diff", "--quiet"], timeout=30)
    staged = residency._run(["git", "diff", "--cached", "--quiet"], timeout=30)
    sha = str(head.get("stdout") or "").strip()
    clean = (
        head.get("ok") is True
        and unstaged.get("returncode") == 0
        and staged.get("returncode") == 0
    )
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or not clean:
        raise RuntimeError("checked-out semantic campaign repository is invalid or dirty")
    return {
        "schema_version": "bench.checkout-binding.v1",
        "checked_out_sha": sha,
        "tracked_clean": True,
        "event_sha": probe.os.environ.get("GITHUB_SHA"),
        "ref": probe.os.environ.get("GITHUB_REF"),
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _validated_cases() -> list[dict[str, Any]]:
    _, _, cases = probe.validate_plan(
        job.PLAN_PATH,
        job.REGISTRY_PATH,
        job.H3_SUMMARY_PATH,
        job.H3_MANIFEST_PATH,
        probe.EXPECTED_PLAN_SHA256,
    )
    return cases


def _bind_report_case_digests(report: dict[str, Any]) -> None:
    """Separate canonical case identity from exact serialized snapshot bytes."""

    canonical_by_case = {
        case["case_id"]: case["case_definition_sha256"]
        for case in _validated_cases()
    }
    results = report.get("results")
    if not isinstance(results, list):
        return
    for result in results:
        if not isinstance(result, dict):
            continue
        case_id = result.get("case_id")
        if case_id not in canonical_by_case:
            continue
        snapshot_digest = result.get("case_definition_sha256")
        result["case_snapshot_sha256"] = snapshot_digest
        result["case_definition_sha256"] = canonical_by_case[case_id]


def _inject_binding(artifact_dir: Path, binding: dict[str, Any]) -> None:
    summary_path = artifact_dir / "job-summary.json"
    if summary_path.is_file():
        summary = job._load_json(summary_path)
        summary["repository"] = binding
        _write_json(summary_path, summary)
    campaign_dir = artifact_dir / "campaign"
    report_path = campaign_dir / "report.json"
    if report_path.is_file():
        report = job._load_json(report_path)
        report["repository"] = binding
        _bind_report_case_digests(report)
        _write_json(report_path, report)
        probe.write_manifest(campaign_dir)


def _campaign_manifest_without_nested_manifests(campaign_dir: Path) -> list[str]:
    failures: list[str] = []
    manifest_path = campaign_dir / "manifest.json"
    if not manifest_path.is_file():
        return ["semantic campaign manifest is missing"]
    manifest = job._load_json(manifest_path)
    if manifest.get("schema_version") != probe.MANIFEST_SCHEMA:
        failures.append("semantic campaign manifest schema is invalid")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return failures + ["semantic campaign artifact inventory is missing"]
    expected_paths = {
        path.relative_to(campaign_dir).as_posix()
        for path in campaign_dir.rglob("*")
        if path.is_file() and path.name != "manifest.json"
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


def _selection_or_error() -> dict[str, Any]:
    try:
        return job.selection_for(job.batch_index_from_environment())
    except ValueError as exc:
        return {"mode": "invalid", "error": str(exc)}


def _record_capture_error(artifact_dir: Path, exc: Exception) -> int:
    error = {
        "schema_version": "bench.direct-semantic-capture-error.v1",
        "type": type(exc).__name__,
        "detail": str(exc),
    }
    _write_json(artifact_dir / "capture-error.json", error)
    _write_json(
        artifact_dir / "job-summary.json",
        {
            "schema_version": "bench.direct-semantic-job.v1",
            "test_scope": "direct-semantic-campaign",
            "selection": _selection_or_error(),
            "source": {
                "plan_sha256": probe.EXPECTED_PLAN_SHA256,
                "candidate_registry_sha256": probe.EXPECTED_REGISTRY_SHA256,
                "h3_summary_sha256": probe.EXPECTED_H3_SUMMARY_SHA256,
                "h3_manifest_sha256": probe.EXPECTED_H3_MANIFEST_SHA256,
            },
            "tests": {"exit_code": 2, "error_type": type(exc).__name__},
            "inventory": {"exit_code": 2, "error_type": type(exc).__name__},
            "probe": {
                "exit_code": 2,
                "skipped_reason": None,
                "error_type": type(exc).__name__,
                "error_detail": str(exc),
            },
            "capture_error": error,
        },
    )
    print(f"semantic capture failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    return 0


def capture(artifact_dir: Path = job.DEFAULT_ARTIFACTS) -> int:
    try:
        binding = repository_snapshot()
        result = job.capture(artifact_dir)
        _inject_binding(artifact_dir, binding)
        return result
    except Exception as exc:
        return _record_capture_error(artifact_dir, exc)


def _valid_binding(value: Any, current: dict[str, Any]) -> bool:
    return (
        isinstance(value, dict)
        and value.get("schema_version") == "bench.checkout-binding.v1"
        and value.get("checked_out_sha") == current.get("checked_out_sha")
        and value.get("tracked_clean") is True
        and value.get("ref") == "refs/heads/main"
    )


def _result_case_bindings_are_valid(
    report: dict[str, Any],
    campaign_dir: Path,
) -> bool:
    canonical_by_case = {
        case["case_id"]: case["case_definition_sha256"]
        for case in _validated_cases()
    }
    results = report.get("results")
    if not isinstance(results, list):
        return False
    for result in results:
        if not isinstance(result, dict):
            return False
        case_id = result.get("case_id")
        run_directory = result.get("run_directory")
        if case_id not in canonical_by_case or not isinstance(run_directory, str):
            return False
        if result.get("case_definition_sha256") != canonical_by_case[case_id]:
            return False
        snapshot_path = campaign_dir / run_directory.removeprefix("campaign/") / "case_definition.json"
        if not snapshot_path.is_file():
            return False
        if result.get("case_snapshot_sha256") != probe._raw_sha256(snapshot_path):
            return False
    return True


def enforce(artifact_dir: Path = job.DEFAULT_ARTIFACTS) -> int:
    job._validate_campaign_manifest = _campaign_manifest_without_nested_manifests
    result = job.enforce(artifact_dir)
    if result != 0:
        return result
    campaign_dir = artifact_dir / "campaign"
    try:
        current = repository_snapshot()
        summary = job._load_json(artifact_dir / "job-summary.json")
        report = job._load_json(campaign_dir / "report.json")
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"invalid semantic checkout binding: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if not _valid_binding(summary.get("repository"), current):
        print("semantic job summary checkout binding is invalid", file=sys.stderr)
        return 1
    if not _valid_binding(report.get("repository"), current):
        print("semantic report checkout binding is invalid", file=sys.stderr)
        return 1
    if not _result_case_bindings_are_valid(report, campaign_dir):
        print("semantic canonical/snapshot case binding is invalid", file=sys.stderr)
        return 1
    print(f"semantic checkout binding passed; sha={current['checked_out_sha']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("capture", "enforce"))
    parser.add_argument("--artifact-dir", type=Path, default=job.DEFAULT_ARTIFACTS)
    args = parser.parse_args()
    return capture(args.artifact_dir) if args.mode == "capture" else enforce(args.artifact_dir)


if __name__ == "__main__":
    raise SystemExit(main())

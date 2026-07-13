from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from scripts import probe_h4_context as probe
from scripts import run_h4_context_job as base_job


def repository_snapshot() -> dict[str, Any]:
    head = probe.base._run(["git", "rev-parse", "HEAD"], timeout=30)
    unstaged = probe.base._run(["git", "diff", "--quiet"], timeout=30)
    staged = probe.base._run(["git", "diff", "--cached", "--quiet"], timeout=30)
    sha = str(head.get("stdout") or "").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or not (
        head.get("ok") is True
        and unstaged.get("returncode") == 0
        and staged.get("returncode") == 0
    ):
        raise RuntimeError("checked-out repository identity is invalid or dirty")
    return {
        "schema_version": "bench.checkout-binding.v1",
        "checked_out_sha": sha,
        "tracked_clean": True,
        "event_sha": probe.os.environ.get("GITHUB_SHA"),
        "ref": probe.os.environ.get("GITHUB_REF"),
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _inject_binding(artifact_dir: Path, binding: dict[str, Any]) -> None:
    summary_path = artifact_dir / "job-summary.json"
    if summary_path.is_file():
        summary = base_job._load_json(summary_path)
        summary["repository"] = binding
        _write_json(summary_path, summary)
    probe_dir = artifact_dir / "h4-hermes-minimum-64k"
    report_path = probe_dir / "report.json"
    if report_path.is_file():
        report = base_job._load_json(report_path)
        report["repository"] = binding
        _write_json(report_path, report)
        probe.write_manifest(probe_dir)


def capture(artifact_dir: Path = base_job.DEFAULT_ARTIFACTS) -> int:
    try:
        binding = repository_snapshot()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    result = base_job.capture(artifact_dir)
    _inject_binding(artifact_dir, binding)
    return result


def _valid_binding(value: Any, current: dict[str, Any]) -> bool:
    return (
        isinstance(value, dict)
        and value.get("schema_version") == "bench.checkout-binding.v1"
        and value.get("checked_out_sha") == current.get("checked_out_sha")
        and value.get("tracked_clean") is True
        and value.get("ref") == "refs/heads/main"
    )


def enforce(artifact_dir: Path = base_job.DEFAULT_ARTIFACTS) -> int:
    result = base_job.enforce(artifact_dir)
    if result != 0:
        return result
    try:
        current = repository_snapshot()
        summary = base_job._load_json(artifact_dir / "job-summary.json")
        report = base_job._load_json(
            artifact_dir / "h4-hermes-minimum-64k" / "report.json"
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"invalid H4 checkout binding: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if not _valid_binding(summary.get("repository"), current):
        print("H4 job summary checkout binding is invalid", file=sys.stderr)
        return 1
    if not _valid_binding(report.get("repository"), current):
        print("H4 report checkout binding is invalid", file=sys.stderr)
        return 1
    print(f"H4 checkout binding passed; sha={current['checked_out_sha']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("capture", "enforce"))
    parser.add_argument("--artifact-dir", type=Path, default=base_job.DEFAULT_ARTIFACTS)
    args = parser.parse_args()
    return capture(args.artifact_dir) if args.mode == "capture" else enforce(args.artifact_dir)


if __name__ == "__main__":
    raise SystemExit(main())

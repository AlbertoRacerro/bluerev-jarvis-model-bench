from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import run_h2_context_batch_job as batch
from scripts import run_h2_context_bound_job as binding


def capture(artifact_dir: Path) -> int:
    try:
        repository = binding.repository_snapshot()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    result = batch.capture(artifact_dir)
    binding._inject_binding(artifact_dir, repository)
    return result


def enforce(artifact_dir: Path) -> int:
    result = batch.enforce(artifact_dir)
    if result != 0:
        return result
    try:
        current = binding.repository_snapshot()
        summary = batch.base._load_json(artifact_dir / "job-summary.json")
        report = batch.base._load_json(
            artifact_dir / "h2-primary-16k" / "report.json"
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(
            f"invalid H2 batch checkout binding: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    if not binding._valid_binding(summary.get("repository"), current):
        print("H2 batch summary checkout binding is invalid", file=sys.stderr)
        return 1
    if not binding._valid_binding(report.get("repository"), current):
        print("H2 batch report checkout binding is invalid", file=sys.stderr)
        return 1
    print(f"H2 batch checkout binding passed; sha={current['checked_out_sha']}")
    return 0

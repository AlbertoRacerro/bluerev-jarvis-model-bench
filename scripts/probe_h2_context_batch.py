from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts import probe_h2_context as base
from scripts.probe_model_residency_v2 import stop_all_running_models


class H2BatchError(RuntimeError):
    pass


def select_candidates(
    candidates: list[dict[str, str]], *, batch_index: int, batch_size: int
) -> tuple[list[dict[str, str]], dict[str, int | str]]:
    if batch_index < 0 or batch_size <= 0:
        raise H2BatchError("H2 batch index or size is invalid")
    start = batch_index * batch_size
    if start >= len(candidates):
        raise H2BatchError("H2 batch starts beyond the primary candidate list")
    end = min(start + batch_size, len(candidates))
    return candidates[start:end], {
        "mode": "batch",
        "batch_index": batch_index,
        "batch_size": batch_size,
        "start": start,
        "end": end,
        "expected_count": end - start,
        "total_candidates": len(candidates),
    }


def build_report(
    plan_path: Path,
    expected_plan_sha256: str,
    output_dir: Path,
    *,
    batch_index: int,
    batch_size: int,
) -> dict[str, Any]:
    created_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    results: list[dict[str, Any]] = []
    infrastructure_error: dict[str, str] | None = None
    initial_gpu = base.base.gpu_snapshot()
    initial_cleanup: list[dict[str, Any]] = []
    final_cleanup: list[dict[str, Any]] = []
    candidates: list[dict[str, str]] = []
    selected: list[dict[str, str]] = []
    selection: dict[str, int | str] | None = None
    try:
        if initial_gpu.get("ok") is not True:
            raise base.H2InfrastructureError("initial GPU snapshot failed")
        candidates = base.validate_plan(plan_path, expected_plan_sha256)
        selected, selection = select_candidates(
            candidates, batch_index=batch_index, batch_size=batch_size
        )
        installed = base._installed_primary(selected)
        initial_cleanup = stop_all_running_models()
        for model in installed:
            results.append(base.probe_candidate(model, output_dir))
    except (H2BatchError, base.H2ProbeError, base.base.ProbeError) as exc:
        infrastructure_error = {"type": type(exc).__name__, "detail": str(exc)}
    finally:
        try:
            final_cleanup = stop_all_running_models()
        except base.base.ProbeError as exc:
            detail = f"final cleanup failed: {exc}"
            if infrastructure_error is None:
                infrastructure_error = {"type": type(exc).__name__, "detail": detail}
            else:
                infrastructure_error["detail"] += "; " + detail

    counts = {status: 0 for status in sorted(base._ALLOWED_RESULTS)}
    for result in results:
        status = result.get("status")
        if status in counts:
            counts[status] += 1
    return {
        "schema_version": base.SCHEMA_VERSION,
        "created_at_utc": created_at,
        "workflow": {
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "event_name": os.environ.get("GITHUB_EVENT_NAME"),
            "sha": os.environ.get("GITHUB_SHA"),
            "ref": os.environ.get("GITHUB_REF"),
        },
        "source": {
            "plan_path": plan_path.as_posix(),
            "plan_sha256": expected_plan_sha256,
            "h1_artifact_sha256": base.EXPECTED_H1_ARTIFACT_SHA256,
            "h1_workflow": base.EXPECTED_H1_SOURCE,
            **base.EXPECTED_SOURCE_DIGESTS,
        },
        "profile": base.PROFILE,
        "candidate_count": len(selected),
        "plan_candidate_count": len(candidates),
        "selection": selection,
        "initial_gpu": initial_gpu,
        "initial_cleanup": initial_cleanup,
        "final_cleanup": final_cleanup,
        "infrastructure_error": infrastructure_error,
        "status_counts": counts,
        "required_failures": [
            result["model"]["name"]
            for result in results
            if result.get("status") != "qualified_16k"
        ],
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one deterministic H2 16K batch.")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--batch-index", type=int, required=True)
    parser.add_argument("--batch-size", type=int, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = build_report(
        args.plan,
        args.expected_plan_sha256,
        args.output_dir,
        batch_index=args.batch_index,
        batch_size=args.batch_size,
    )
    base._write_json(args.output_dir / "report.json", report)
    base.write_manifest(args.output_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if report["infrastructure_error"] is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())

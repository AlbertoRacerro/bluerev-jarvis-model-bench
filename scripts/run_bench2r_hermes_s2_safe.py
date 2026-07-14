from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from scripts import run_bench2r_hermes_s2 as base

DEFAULT_ARTIFACTS = base.DEFAULT_ARTIFACTS
_MODEL_FIELDS = (
    "case_id",
    "capability",
    "prompt",
    "inputs",
    "allowed_actions",
    "forbidden_actions",
    "limits",
)


class HermesS2SafeError(RuntimeError):
    pass


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _candidate_payload(case: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in _MODEL_FIELDS if field not in case]
    if missing:
        raise HermesS2SafeError(f"candidate task fields are missing: {missing}")
    return {
        "schema_version": "bench.s2.candidate-task.v1",
        **{field: case[field] for field in _MODEL_FIELDS},
    }


def _build_model_prompt(case: dict[str, Any]) -> str:
    payload = _candidate_payload(case)
    return (
        "Execute the held-out orchestration task below exactly. The task JSON is "
        "authoritative. Use only the enabled held-out toolset. Do not add prose "
        "outside the requested final JSON object.\n\n"
        + json.dumps(payload, indent=2, sort_keys=True)
    )


def _parse_generic_object(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    stripped = raw.strip()
    if not stripped:
        return None, "empty_output"
    try:
        value = json.loads(stripped, object_pairs_hook=_reject_duplicates)
    except (json.JSONDecodeError, ValueError) as exc:
        return None, f"invalid_json:{type(exc).__name__}"
    if not isinstance(value, dict):
        return None, "output_not_object"
    return value, None


@contextmanager
def _safe_model_boundary() -> Iterator[None]:
    original_builder = base.canary._build_prompt
    original_parser = base.canary._parse_output
    base.canary._build_prompt = _build_model_prompt
    base.canary._parse_output = _parse_generic_object
    try:
        yield
    finally:
        base.canary._build_prompt = original_builder
        base.canary._parse_output = original_parser


def capture(output_dir: Path = DEFAULT_ARTIFACTS) -> int:
    with _safe_model_boundary():
        return base.capture(output_dir)


def _require_file(run_dir: Path, relative: str) -> None:
    path = run_dir / relative
    if not path.is_file():
        raise HermesS2SafeError(f"required S2 run artifact is missing: {path}")


def enforce(output_dir: Path = DEFAULT_ARTIFACTS) -> int:
    code = base.enforce(output_dir)
    report = base._load_json(output_dir / "batch-report.json")
    runs = report.get("runs")
    if not isinstance(runs, list):
        raise HermesS2SafeError("S2 run inventory is missing")

    minimal = ("validator-result.json", "manifest.json")
    rich = (
        "raw-output.txt",
        "stderr.txt",
        "worker-result.json",
        "worker-debug.txt",
        "usage.json",
        "extracted-output.json",
        "tool-trace.jsonl",
        "wire-trace.jsonl",
        "validator-result.json",
        "environment-fingerprint.json",
        "effective-config.yaml",
        "manifest.json",
    )
    for run in runs:
        if not isinstance(run, dict):
            raise HermesS2SafeError("S2 run record is not an object")
        relative = run.get("artifact_path")
        if not isinstance(relative, str) or not relative:
            raise HermesS2SafeError("S2 run artifact path is missing")
        run_dir = output_dir / relative
        for name in minimal:
            _require_file(run_dir, name)
        if run.get("infrastructure_valid") is True:
            for name in rich:
                _require_file(run_dir, name)
            trajectory_candidates = (
                run_dir / "trajectory_samples.jsonl",
                run_dir / "failed_trajectories.jsonl",
            )
            if not any(path.is_file() and path.stat().st_size > 0 for path in trajectory_candidates):
                raise HermesS2SafeError(f"native trajectory is missing: {run_dir}")
            if (run_dir / "wire-trace.jsonl").stat().st_size <= 0:
                raise HermesS2SafeError(f"wire trace is empty: {run_dir}")
    return code


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run BENCH-2R Hermes S2 through the contamination-safe boundary."
    )
    parser.add_argument("mode", choices=("capture", "enforce"))
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACTS)
    args = parser.parse_args()
    try:
        return capture(args.artifact_dir) if args.mode == "capture" else enforce(args.artifact_dir)
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

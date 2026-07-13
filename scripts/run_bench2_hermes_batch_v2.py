from __future__ import annotations

import argparse
from pathlib import Path

from scripts import run_bench2_hermes_batch as base
from scripts import validate_bench2_hermes_execution as execution


def prepare_output_directories(output_dir: Path) -> None:
    _, _, candidates, cases = execution.validate_execution(require_enabled=True)
    batch_index = base.batch_index_from_environment()
    selected, _ = execution.select_batch(candidates, batch_index)
    for candidate in selected:
        for case in cases:
            for repetition in range(1, execution.EXPECTED_REPETITIONS + 1):
                (
                    output_dir
                    / "runs"
                    / candidate["candidate_id"]
                    / case["case_id"]
                    / f"r{repetition}"
                ).mkdir(parents=True, exist_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare per-run directories, then delegate a BENCH-2 Hermes batch."
    )
    parser.add_argument("mode", choices=("capture", "enforce"))
    parser.add_argument("--artifact-dir", type=Path, default=base.DEFAULT_ARTIFACTS)
    args = parser.parse_args()
    if args.mode == "capture":
        prepare_output_directories(args.artifact_dir)
        return base.capture(args.artifact_dir)
    return base.enforce(args.artifact_dir)


if __name__ == "__main__":
    raise SystemExit(main())

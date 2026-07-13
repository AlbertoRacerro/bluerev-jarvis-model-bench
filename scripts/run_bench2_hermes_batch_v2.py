from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from scripts import run_bench2_hermes_batch as base


def _run_once_with_output_dir(*, output_dir: Path, **kwargs: Any) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    return _ORIGINAL_RUN_ONCE(output_dir=output_dir, **kwargs)


_ORIGINAL_RUN_ONCE = base._run_once


def capture(output_dir: Path = base.DEFAULT_ARTIFACTS) -> int:
    original = base._run_once
    base._run_once = _run_once_with_output_dir
    try:
        return base.capture(output_dir)
    finally:
        base._run_once = original


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create each per-run output directory at execution time."
    )
    parser.add_argument("mode", choices=("capture", "enforce"))
    parser.add_argument("--artifact-dir", type=Path, default=base.DEFAULT_ARTIFACTS)
    args = parser.parse_args()
    return capture(args.artifact_dir) if args.mode == "capture" else base.enforce(args.artifact_dir)


if __name__ == "__main__":
    raise SystemExit(main())

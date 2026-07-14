from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts import run_bench2r_hermes_s3a_safe as s3a
from scripts.run_bench2r_hermes_s1_awake import keep_windows_awake
from scripts.validate_bench2r_hermes_s3a_windows import windows_runtime_boundary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run BENCH-2R Hermes S3A capture while preventing Windows sleep."
    )
    parser.add_argument("mode", choices=("capture",))
    parser.add_argument("--artifact-dir", type=Path, default=s3a.DEFAULT_ARTIFACTS)
    args = parser.parse_args()
    try:
        with windows_runtime_boundary(), keep_windows_awake():
            return s3a.capture(args.artifact_dir)
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

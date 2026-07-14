from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts import run_bench2r_hermes_s2_safe as s2
from scripts.run_bench2r_hermes_s1_awake import keep_windows_awake


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run BENCH-2R Hermes S2 capture while preventing Windows sleep."
    )
    parser.add_argument("mode", choices=("capture",))
    parser.add_argument("--artifact-dir", type=Path, default=s2.DEFAULT_ARTIFACTS)
    args = parser.parse_args()
    try:
        with keep_windows_awake():
            return s2.capture(args.artifact_dir)
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

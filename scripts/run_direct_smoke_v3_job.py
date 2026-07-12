from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ONESHOT_PATH = ROOT / "config" / "h2-primary-16k-oneshot.json"
ARTIFACTS = ROOT / "artifacts" / "direct-smoke"
EXPECTED_PLAN_SHA256 = "cce4863f87520dae70ea97fcd75a88d4ada0dff874202376cc9223ea6c29868a"
EXPECTED_RUN_ID = "29106127334"
FIRST_BATCH_ATTEMPT = 7
BATCH_SIZE = 3
BATCH_COUNT = 4


def h2_batch_index() -> int | None:
    if os.environ.get("GITHUB_RUN_ID") != EXPECTED_RUN_ID:
        return None
    try:
        attempt = int(os.environ.get("GITHUB_RUN_ATTEMPT", ""))
    except ValueError:
        return None
    index = attempt - FIRST_BATCH_ATTEMPT
    return index if 0 <= index < BATCH_COUNT else None


def h2_oneshot_enabled(path: Path = ONESHOT_PATH) -> bool:
    if h2_batch_index() is None:
        return False
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return value == {
        "schema_version": "bench.h2-primary-oneshot.v1",
        "enabled": True,
        "plan_sha256": EXPECTED_PLAN_SHA256,
        "first_batch_attempt": FIRST_BATCH_ATTEMPT,
        "batch_size": BATCH_SIZE,
        "batch_count": BATCH_COUNT,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("capture", "enforce"))
    mode = parser.parse_args().mode
    if h2_oneshot_enabled():
        batch_index = h2_batch_index()
        if batch_index is None:
            raise RuntimeError("authorized H2 batch index disappeared")
        os.environ["BENCH_H2_BATCH_INDEX"] = str(batch_index)
        from scripts.run_h2_context_batch_bound_job import capture, enforce

        return capture(ARTIFACTS) if mode == "capture" else enforce(ARTIFACTS)

    from scripts.run_direct_smoke_v3_job_base import capture, enforce

    return capture() if mode == "capture" else enforce()


if __name__ == "__main__":
    raise SystemExit(main())

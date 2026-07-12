from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from scripts import run_direct_smoke_v3_job_base as _direct

ROOT = Path(__file__).resolve().parents[1]
ONESHOT_PATH = ROOT / "config" / "h3-primary-32k-oneshot.json"
ARTIFACTS = ROOT / "artifacts" / "direct-smoke"
EXPECTED_PLAN_SHA256 = "0bf7838ef0199be1dcf89122bbdedaf17ca4253223eafd0b89472bdcba3d7c12"
EXPECTED_RUN_ID = "29106127334"
FIRST_BATCH_ATTEMPT = 13
BATCH_SIZE = 2
BATCH_COUNT = 5

# Preserve the public V3 module contract used by deterministic tests.
CANDIDATE_ID = _direct.CANDIDATE_ID
CASE_PATH = _direct.CASE_PATH
CANDIDATE_REGISTRY = _direct.CANDIDATE_REGISTRY
SUMMARY_PATH = _direct.SUMMARY_PATH
DIRECT_TEST_PATTERNS = _direct.DIRECT_TEST_PATTERNS


def capture() -> int:
    return _direct.capture()


def enforce() -> int:
    # Test code patches this module-level path; mirror it into the preserved implementation.
    _direct.SUMMARY_PATH = SUMMARY_PATH
    return _direct.enforce()


def h3_batch_index() -> int | None:
    if os.environ.get("GITHUB_RUN_ID") != EXPECTED_RUN_ID:
        return None
    try:
        attempt = int(os.environ.get("GITHUB_RUN_ATTEMPT", ""))
    except ValueError:
        return None
    index = attempt - FIRST_BATCH_ATTEMPT
    return index if 0 <= index < BATCH_COUNT else None


def h3_oneshot_enabled(path: Path = ONESHOT_PATH) -> bool:
    if h3_batch_index() is None:
        return False
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return value == {
        "schema_version": "bench.h3-primary-oneshot.v1",
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
    if h3_oneshot_enabled():
        batch_index = h3_batch_index()
        if batch_index is None:
            raise RuntimeError("authorized H3 batch index disappeared")
        os.environ["BENCH_H3_BATCH_INDEX"] = str(batch_index)
        from scripts.run_h3_context_bound_job import capture as h3_capture, enforce as h3_enforce
        return h3_capture(ARTIFACTS) if mode == "capture" else h3_enforce(ARTIFACTS)
    return capture() if mode == "capture" else enforce()


if __name__ == "__main__":
    raise SystemExit(main())

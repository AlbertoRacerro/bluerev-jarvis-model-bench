from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from scripts import run_direct_smoke_v3_job_original as _direct
from scripts import run_h1_one_shot as _h1

ROOT = Path(__file__).resolve().parents[1]
MARKER_PATH = ROOT / ".github" / "h1-one-shot.json"
EXPECTED_MARKER = {
    "schema_version": "bench.h1-one-shot.v1",
    "source_workflow_run_id": "29106127334",
    "purpose": "immediate_h1_residency_replay",
}


def _h1_one_shot_enabled() -> bool:
    if os.environ.get("GITHUB_RUN_ID") != EXPECTED_MARKER["source_workflow_run_id"]:
        return False
    try:
        marker = json.loads(MARKER_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return marker == EXPECTED_MARKER


def capture() -> int:
    return _h1.capture() if _h1_one_shot_enabled() else _direct.capture()


def enforce() -> int:
    return _h1.enforce() if _h1_one_shot_enabled() else _direct.enforce()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("capture", "enforce"))
    mode = parser.parse_args().mode
    return capture() if mode == "capture" else enforce()


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "direct-semantic"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _record_entry_failure(exc: BaseException) -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    detail = str(exc) or repr(exc)
    error = {
        "schema_version": "bench.direct-semantic-entry-error.v1",
        "type": type(exc).__name__,
        "detail": detail,
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    _write_json(ARTIFACT_DIR / "capture-entry-error.json", error)
    (ARTIFACT_DIR / "capture-entry-traceback.txt").write_text(
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        encoding="utf-8",
    )
    _write_json(
        ARTIFACT_DIR / "job-summary.json",
        {
            "schema_version": "bench.direct-semantic-job.v1",
            "test_scope": "direct-semantic-campaign",
            "selection": {
                "mode": "invalid",
                "error": "capture entrypoint failed before bound capture",
            },
            "source": None,
            "tests": {"exit_code": 2, "error_type": type(exc).__name__},
            "inventory": {"exit_code": 2, "error_type": type(exc).__name__},
            "probe": {
                "exit_code": 2,
                "skipped_reason": None,
                "error_type": type(exc).__name__,
                "error_detail": detail,
            },
            "capture_error": error,
        },
    )
    print("semantic capture entry failed: %s: %s" % (type(exc).__name__, detail), file=sys.stderr)
    return 0


def run_capture(
    capture_callable: Optional[Callable[[Path], int]] = None,
) -> int:
    try:
        if capture_callable is None:
            from scripts.run_direct_semantic_campaign_bound_job import capture

            capture_callable = capture
        result = capture_callable(ARTIFACT_DIR)
        if not isinstance(result, int) or isinstance(result, bool):
            raise TypeError("semantic capture callable must return an integer exit code")
        return result
    except BaseException as exc:
        return _record_entry_failure(exc)


if __name__ == "__main__":
    raise SystemExit(run_capture())

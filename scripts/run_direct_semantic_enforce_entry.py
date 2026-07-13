from __future__ import annotations

import contextlib
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "direct-semantic"
STDOUT_PATH = ARTIFACT_DIR / "enforce-stdout.log"
STDERR_PATH = ARTIFACT_DIR / "enforce-stderr.log"
SUMMARY_PATH = ARTIFACT_DIR / "enforce-summary.json"
TRACEBACK_PATH = ARTIFACT_DIR / "enforce-traceback.txt"


def _write_summary(exit_code: int, error: dict[str, str] | None) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(
        json.dumps(
            {
                "schema_version": "bench.direct-semantic-enforce-entry.v1",
                "exit_code": exit_code,
                "error": error,
                "created_at_utc": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def run_enforce() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    exit_code = 2
    error: dict[str, str] | None = None
    with STDOUT_PATH.open("w", encoding="utf-8") as stdout_file, STDERR_PATH.open(
        "w", encoding="utf-8"
    ) as stderr_file:
        try:
            with contextlib.redirect_stdout(stdout_file), contextlib.redirect_stderr(
                stderr_file
            ):
                from scripts.run_direct_semantic_campaign_bound_job import enforce

                result = enforce(ARTIFACT_DIR)
                if not isinstance(result, int) or isinstance(result, bool):
                    raise TypeError("semantic enforce callable must return an integer")
                exit_code = result
        except BaseException as exc:
            error = {
                "type": type(exc).__name__,
                "detail": str(exc) or repr(exc),
            }
            TRACEBACK_PATH.write_text(
                "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
                encoding="utf-8",
            )
            print(
                "semantic enforce entry failed: %s: %s"
                % (type(exc).__name__, error["detail"]),
                file=stderr_file,
            )
            exit_code = 2
    _write_summary(exit_code, error)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(run_enforce())

from __future__ import annotations

import contextlib
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


def _paths(artifact_dir: Path) -> tuple[Path, Path, Path, Path]:
    return (
        artifact_dir / "enforce-stdout.log",
        artifact_dir / "enforce-stderr.log",
        artifact_dir / "enforce-summary.json",
        artifact_dir / "enforce-traceback.txt",
    )


def _write_summary(
    summary_path: Path,
    exit_code: int,
    error: Optional[dict[str, str]],
) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
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


def run_enforce(
    enforce_callable: Optional[Callable[[Path], int]] = None,
    artifact_dir: Path = ARTIFACT_DIR,
) -> int:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stdout_path, stderr_path, summary_path, traceback_path = _paths(artifact_dir)
    exit_code = 2
    error: Optional[dict[str, str]] = None
    with stdout_path.open("w", encoding="utf-8") as stdout_file, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_file:
        try:
            with contextlib.redirect_stdout(stdout_file), contextlib.redirect_stderr(
                stderr_file
            ):
                if enforce_callable is None:
                    from scripts.run_direct_semantic_campaign_bound_job import enforce

                    enforce_callable = enforce
                result = enforce_callable(artifact_dir)
                if not isinstance(result, int) or isinstance(result, bool):
                    raise TypeError("semantic enforce callable must return an integer")
                exit_code = result
        except BaseException as exc:
            error = {
                "type": type(exc).__name__,
                "detail": str(exc) or repr(exc),
            }
            traceback_path.write_text(
                "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
                encoding="utf-8",
            )
            print(
                "semantic enforce entry failed: %s: %s"
                % (type(exc).__name__, error["detail"]),
                file=stderr_file,
            )
            exit_code = 2
    _write_summary(summary_path, exit_code, error)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(run_enforce())

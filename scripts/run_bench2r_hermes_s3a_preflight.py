from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "artifacts/preflight"
JSON_NAME = "s3a-preflight.json"
LOG_NAME = "s3a-preflight.log"


def _fallback_payload(*, error_type: str, error: str, returncode: int) -> dict[str, object]:
    return {
        "schema_version": "bench.hermes-s3a-windows-validation.v1",
        "status": "invalid",
        "execution_authorized": False,
        "error_type": error_type,
        "error": error,
        "validator_returncode": returncode,
    }


def run_preflight(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    command: Sequence[str] | None = None,
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / JSON_NAME
    log_path = output_dir / LOG_NAME
    argv = list(command) if command is not None else [
        sys.executable,
        "-m",
        "scripts.validate_bench2r_hermes_s3a_windows",
        "--require-enabled",
        "--output",
        str(json_path),
    ]

    try:
        completed = subprocess.run(
            argv,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        returncode = int(completed.returncode)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        failure_type = "ValidatorProcessFailure"
        failure_text = f"validator exited with code {returncode}"
    except Exception as exc:
        returncode = 2
        stdout = ""
        stderr = f"{type(exc).__name__}: {exc}\n"
        failure_type = type(exc).__name__
        failure_text = str(exc)

    log_text = (
        "command=" + json.dumps(argv, ensure_ascii=False) + "\n"
        + "returncode=" + str(returncode) + "\n"
        + "--- stdout ---\n" + stdout
        + ("\n" if stdout and not stdout.endswith("\n") else "")
        + "--- stderr ---\n" + stderr
        + ("\n" if stderr and not stderr.endswith("\n") else "")
    )
    log_path.write_text(log_text, encoding="utf-8")

    if not json_path.is_file():
        json_path.write_text(
            json.dumps(
                _fallback_payload(
                    error_type=failure_type,
                    error=failure_text,
                    returncode=returncode,
                ),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    print(log_text, end="")
    return returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the BENCH-2R Hermes S3A preflight and always persist evidence."
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    return run_preflight(args.output_dir)


if __name__ == "__main__":
    raise SystemExit(main())

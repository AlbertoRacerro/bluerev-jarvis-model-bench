from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from scripts import preflight

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
SUMMARY_PATH = ARTIFACTS / "job-summary.json"


def _run_and_capture(
    name: str,
    command: list[str],
    *,
    env: dict[str, str],
) -> dict[str, Any]:
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    (ARTIFACTS / f"{name}.stdout.log").write_text(result.stdout, encoding="utf-8")
    (ARTIFACTS / f"{name}.stderr.log").write_text(result.stderr, encoding="utf-8")
    (ARTIFACTS / f"{name}.exit").write_text(f"{result.returncode}\n", encoding="utf-8")

    return {
        "command": command,
        "exit_code": result.returncode,
    }


def capture() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    test_env = os.environ.copy()
    test_env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(ROOT / "src")))
    tests = _run_and_capture(
        "tests",
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        env=test_env,
    )

    inventory_env = os.environ.copy()
    for name in preflight.KNOWN_EXTERNAL_KEYS:
        inventory_env.pop(name, None)
    inventory = _run_and_capture(
        "preflight",
        [
            sys.executable,
            "scripts/preflight.py",
            "--output",
            "artifacts/preflight.json",
        ],
        env=inventory_env,
    )

    summary = {
        "schema_version": "bench.preflight-job.v1",
        "python": sys.executable,
        "repository_root": str(ROOT),
        "tests": tests,
        "inventory": inventory,
    }
    SUMMARY_PATH.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def enforce() -> int:
    if not SUMMARY_PATH.exists():
        print(f"missing preflight job summary: {SUMMARY_PATH}", file=sys.stderr)
        return 2

    try:
        summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
        test_exit = int(summary["tests"]["exit_code"])
        inventory_exit = int(summary["inventory"]["exit_code"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"invalid preflight job summary: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    failures: list[str] = []
    if test_exit != 0:
        failures.append(f"deterministic tests exited {test_exit}")
    if inventory_exit != 0:
        failures.append(f"runtime inventory exited {inventory_exit}")

    if failures:
        print("; ".join(failures), file=sys.stderr)
        return 1

    print("preflight gate passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("capture", "enforce"))
    args = parser.parse_args()
    return capture() if args.mode == "capture" else enforce()


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from bench.contracts import ContractError
from bench.direct_execution import execute_direct_smoke
from scripts import preflight

ARTIFACTS = ROOT / "artifacts" / "direct-smoke"
SUMMARY_PATH = ARTIFACTS / "job-summary.json"
CANDIDATE_ID = "minicpm5-fable-1b-control"
CASE_PATH = ROOT / "fixtures" / "bench-1" / "ho-stop-reuse-001.json"
CANDIDATE_REGISTRY = ROOT / "candidates" / "models.local.json"


def _run_and_capture(name: str, command: list[str], *, env: dict[str, str]) -> dict[str, Any]:
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
    return {"command": command, "exit_code": result.returncode}


def _write_summary(value: dict[str, Any]) -> None:
    SUMMARY_PATH.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(value, indent=2, sort_keys=True))


def capture() -> int:
    if ARTIFACTS.exists():
        shutil.rmtree(ARTIFACTS)
    ARTIFACTS.mkdir(parents=True)

    clean_env = os.environ.copy()
    for name in preflight.KNOWN_EXTERNAL_KEYS:
        clean_env.pop(name, None)
        os.environ.pop(name, None)
    clean_env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(SRC)))

    tests = _run_and_capture(
        "tests",
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        env=clean_env,
    )
    inventory = _run_and_capture(
        "preflight",
        [
            sys.executable,
            "scripts/preflight.py",
            "--output",
            "artifacts/direct-smoke/preflight.json",
        ],
        env=clean_env,
    )

    summary: dict[str, Any] = {
        "schema_version": "bench.direct-smoke-job.v1",
        "python": sys.executable,
        "repository_root": str(ROOT),
        "tests": tests,
        "inventory": inventory,
        "execution": {
            "infrastructure_exit_code": None,
            "execution_completed": False,
            "candidate_passed": None,
        },
    }

    if tests["exit_code"] != 0 or inventory["exit_code"] != 0:
        _write_summary(summary)
        return 0

    try:
        preflight_report = json.loads(
            (ARTIFACTS / "preflight.json").read_text(encoding="utf-8")
        )
        if preflight_report.get("scoring_ready") is not True:
            raise ContractError("trusted preflight is not scoring-ready")

        workflow_run_id = os.environ.get("GITHUB_RUN_ID")
        workflow_attempt = os.environ.get("GITHUB_RUN_ATTEMPT")
        if not workflow_run_id or not workflow_attempt:
            raise ContractError("workflow identity is incomplete")
        run_id = f"direct-{workflow_run_id}-{workflow_attempt}"

        execution = execute_direct_smoke(
            run_id=run_id,
            candidate_id=CANDIDATE_ID,
            candidate_registry_path=CANDIDATE_REGISTRY,
            case_path=CASE_PATH,
            preflight_path=ARTIFACTS / "preflight.json",
            output_root=ARTIFACTS / "runs",
        )
        summary["execution"] = {
            "infrastructure_exit_code": 0,
            **execution,
        }
    except (ContractError, OSError, ValueError, TypeError) as exc:
        error = {
            "type": type(exc).__name__,
            "detail": str(exc),
        }
        (ARTIFACTS / "execution-error.json").write_text(
            json.dumps(error, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        summary["execution"] = {
            "infrastructure_exit_code": 2,
            "execution_completed": False,
            "candidate_passed": None,
            "error": error,
        }

    _write_summary(summary)
    return 0


def enforce() -> int:
    if not SUMMARY_PATH.exists():
        print(f"missing direct-smoke job summary: {SUMMARY_PATH}", file=sys.stderr)
        return 2
    try:
        summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
        test_exit = int(summary["tests"]["exit_code"])
        inventory_exit = int(summary["inventory"]["exit_code"])
        execution_exit = int(summary["execution"]["infrastructure_exit_code"])
        execution_completed = summary["execution"]["execution_completed"] is True
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"invalid direct-smoke job summary: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    failures: list[str] = []
    if test_exit != 0:
        failures.append(f"deterministic tests exited {test_exit}")
    if inventory_exit != 0:
        failures.append(f"runtime inventory exited {inventory_exit}")
    if execution_exit != 0:
        failures.append(f"direct execution infrastructure exited {execution_exit}")
    if not execution_completed:
        failures.append("direct execution did not complete")

    if failures:
        print("; ".join(failures), file=sys.stderr)
        return 1

    candidate_passed = summary["execution"].get("candidate_passed") is True
    print(f"direct-smoke infrastructure gate passed; candidate_passed={candidate_passed}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("capture", "enforce"))
    args = parser.parse_args()
    return capture() if args.mode == "capture" else enforce()


if __name__ == "__main__":
    raise SystemExit(main())

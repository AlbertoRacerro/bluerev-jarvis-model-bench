from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmark_runtime import run_captured, safe_reset_directory, sanitize_environment

ARTIFACT_ROOT = ROOT / "artifacts"
ARTIFACTS = ARTIFACT_ROOT / "preflight"
SUMMARY_PATH = ARTIFACTS / "job-summary.json"
PREFLIGHT_PATH = ARTIFACTS / "preflight.json"


def capture() -> int:
    safe_reset_directory(ARTIFACTS, allowed_root=ARTIFACT_ROOT)

    hermes_home = ARTIFACTS / "hermes-home"
    hermes_home.mkdir(parents=True, exist_ok=False)
    child_env, removed_names = sanitize_environment(
        os.environ,
        hermes_home=hermes_home,
    )
    child_env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(ROOT / "src")))

    tests = run_captured(
        "tests",
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        environment=child_env,
        artifact_dir=ARTIFACTS,
        timeout_seconds=900,
    )
    inventory = run_captured(
        "preflight",
        [
            sys.executable,
            "scripts/preflight.py",
            "--output",
            str(PREFLIGHT_PATH),
        ],
        cwd=ROOT,
        environment=child_env,
        artifact_dir=ARTIFACTS,
        timeout_seconds=120,
    )

    summary = {
        "schema_version": "bench.preflight-job.v2",
        "python": sys.executable,
        "repository_root": str(ROOT),
        "artifact_directory": str(ARTIFACTS),
        "sanitization": {
            "removed_external_env_names": removed_names,
            "isolated_hermes_home": str(hermes_home),
            "secret_values_recorded": False,
        },
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
    if not PREFLIGHT_PATH.exists():
        print(f"missing preflight report: {PREFLIGHT_PATH}", file=sys.stderr)
        return 2

    try:
        summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
        report = json.loads(PREFLIGHT_PATH.read_text(encoding="utf-8"))
        if summary.get("schema_version") != "bench.preflight-job.v2":
            raise ValueError("unsupported preflight job schema")
        test_exit = int(summary["tests"]["exit_code"])
        inventory_exit = int(summary["inventory"]["exit_code"])
        scoring_ready = report["scoring_ready"] is True
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"invalid preflight evidence: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    failures: list[str] = []
    if test_exit != 0:
        failures.append(f"deterministic tests exited {test_exit}")
    if inventory_exit != 0:
        failures.append(f"runtime inventory exited {inventory_exit}")
    if not scoring_ready:
        reasons = report.get("scoring_blocking_reasons")
        failures.append(f"scoring_ready is false; reasons={reasons!r}")

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

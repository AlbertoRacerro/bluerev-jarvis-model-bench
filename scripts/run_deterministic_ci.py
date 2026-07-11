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
ARTIFACTS = ARTIFACT_ROOT / "deterministic-ci"
SUMMARY_PATH = ARTIFACTS / "summary.json"


def capture() -> int:
    safe_reset_directory(ARTIFACTS, allowed_root=ARTIFACT_ROOT)
    hermes_home = ARTIFACTS / "hermes-home"
    hermes_home.mkdir(parents=True, exist_ok=False)
    environment, removed = sanitize_environment(os.environ, hermes_home=hermes_home)
    environment["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(ROOT / "src")))

    compile_result = run_captured(
        "compileall",
        [sys.executable, "-m", "compileall", "-q", "src", "scripts", "tests"],
        cwd=ROOT,
        environment=environment,
        artifact_dir=ARTIFACTS,
        timeout_seconds=180,
    )
    tests_result = run_captured(
        "tests",
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        environment=environment,
        artifact_dir=ARTIFACTS,
        timeout_seconds=900,
    )
    summary = {
        "schema_version": "bench.deterministic-ci.v1",
        "python": sys.executable,
        "repository_root": str(ROOT),
        "sanitization": {
            "removed_external_env_names": removed,
            "isolated_hermes_home": str(hermes_home),
            "secret_values_recorded": False,
        },
        "compileall": compile_result,
        "tests": tests_result,
    }
    SUMMARY_PATH.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def enforce() -> int:
    try:
        summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
        if summary.get("schema_version") != "bench.deterministic-ci.v1":
            raise ValueError("unsupported deterministic CI schema")
        compile_exit = int(summary["compileall"]["exit_code"])
        tests_exit = int(summary["tests"]["exit_code"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"invalid deterministic CI evidence: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    failures: list[str] = []
    if compile_exit != 0:
        failures.append(f"compileall exited {compile_exit}")
    if tests_exit != 0:
        failures.append(f"tests exited {tests_exit}")
    if failures:
        print("; ".join(failures), file=sys.stderr)
        return 1
    print("deterministic CI gate passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("capture", "enforce"))
    args = parser.parse_args()
    return capture() if args.mode == "capture" else enforce()


if __name__ == "__main__":
    raise SystemExit(main())

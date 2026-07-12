from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from bench.contracts import ContractError
from bench.direct_execution_v3 import execute_direct_smoke
from bench.loopback_http import open_loopback
from scripts.benchmark_runtime import (
    isolated_process_environment,
    run_captured,
    safe_reset_directory,
    sanitize_environment,
)
from scripts.probe_model_residency_v2 import stop_all_running_models
from scripts.test_subset import run_test_subset

ARTIFACT_ROOT = ROOT / "artifacts"
ARTIFACTS = ARTIFACT_ROOT / "direct-smoke"
SUMMARY_PATH = ARTIFACTS / "job-summary.json"
CANDIDATE_ID = "qwythos-hermes-safe"
CASE_PATH = ROOT / "fixtures" / "bench-1" / "ho-stop-reuse-explicit-002.json"
CANDIDATE_REGISTRY = ROOT / "candidates" / "models.local.json"
DIRECT_TEST_PATTERNS = (
    "test_benchmark_runtime.py",
    "test_lane_test_subset.py",
    "test_preflight.py",
    "test_preflight_v2.py",
    "test_probe_model_residency.py",
    "test_probe_model_residency_v2.py",
    "test_contracts.py",
    "test_evaluator.py",
    "test_direct_execution*.py",
    "test_run_direct_smoke*.py",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _write_summary(value: dict[str, object]) -> None:
    SUMMARY_PATH.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(value, indent=2, sort_keys=True))


def _cleanup_attestation() -> dict[str, Any]:
    return {
        "verified_absent": True,
        "models": stop_all_running_models(),
    }


def _execution_error(
    primary: Exception | None,
    cleanup: Exception | None,
) -> dict[str, str] | None:
    if primary is None and cleanup is None:
        return None
    parts: list[str] = []
    if primary is not None:
        parts.append(f"primary={type(primary).__name__}: {primary}")
    if cleanup is not None:
        parts.append(f"cleanup={type(cleanup).__name__}: {cleanup}")
    return {
        "type": "DirectSmokeInfrastructureError",
        "detail": "; ".join(parts),
    }


def capture() -> int:
    safe_reset_directory(ARTIFACTS, allowed_root=ARTIFACT_ROOT)
    clean_env, removed_names = sanitize_environment(os.environ)
    clean_env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(SRC)))

    tests = run_test_subset(
        patterns=DIRECT_TEST_PATTERNS,
        root=ROOT,
        environment=clean_env,
        artifact_dir=ARTIFACTS,
        timeout_seconds_per_pattern=120,
    )
    inventory = run_captured(
        "preflight",
        [
            sys.executable,
            "scripts/preflight_v2.py",
            "--output",
            str(ARTIFACTS / "preflight.json"),
            "--required-gate",
            "direct",
        ],
        cwd=ROOT,
        environment=clean_env,
        artifact_dir=ARTIFACTS,
        timeout_seconds=120,
    )
    summary: dict[str, object] = {
        "schema_version": "bench.direct-smoke-job.v3",
        "python": sys.executable,
        "repository_root": str(ROOT),
        "test_scope": "direct-contract",
        "sanitization": {
            "removed_external_env_names": removed_names,
            "hermes_required": False,
            "secret_values_recorded": False,
        },
        "tests": tests,
        "inventory": inventory,
        "execution": {
            "infrastructure_exit_code": 0,
            "execution_completed": False,
            "candidate_passed": None,
            "candidate_result_status": None,
            "skipped_reason": None,
        },
    }
    if tests["exit_code"] != 0 or inventory["exit_code"] != 0:
        summary["execution"] = {
            "infrastructure_exit_code": 0,
            "execution_completed": False,
            "candidate_passed": None,
            "candidate_result_status": None,
            "skipped_reason": "prerequisite_failure",
        }
        _write_summary(summary)
        return 0

    cleanup_before: dict[str, Any] | None = None
    cleanup_after: dict[str, Any] | None = None
    primary_error: Exception | None = None
    cleanup_error: Exception | None = None
    execution: dict[str, Any] | None = None
    try:
        preflight_report = json.loads(
            (ARTIFACTS / "preflight.json").read_text(encoding="utf-8")
        )
        if preflight_report.get("selected_gate") != "direct":
            raise ContractError("trusted preflight is not bound to the direct gate")
        if preflight_report.get("scoring_ready") is not True:
            raise ContractError("trusted direct preflight is not scoring-ready")
        workflow_run_id = clean_env.get("GITHUB_RUN_ID")
        workflow_attempt = clean_env.get("GITHUB_RUN_ATTEMPT")
        if not workflow_run_id or not workflow_attempt:
            raise ContractError("workflow identity is incomplete")
        run_id = f"direct-{workflow_run_id}-{workflow_attempt}"
        with isolated_process_environment(clean_env):
            cleanup_before = _cleanup_attestation()
            execution = execute_direct_smoke(
                run_id=run_id,
                candidate_id=CANDIDATE_ID,
                candidate_registry_path=CANDIDATE_REGISTRY,
                case_path=CASE_PATH,
                preflight_path=ARTIFACTS / "preflight.json",
                output_root=ARTIFACTS / "runs",
                opener=open_loopback,
            )
    except Exception as exc:
        primary_error = exc
    finally:
        try:
            with isolated_process_environment(clean_env):
                cleanup_after = _cleanup_attestation()
        except Exception as exc:
            cleanup_error = exc

    error = _execution_error(primary_error, cleanup_error)
    if error is not None or execution is None:
        if error is None:
            error = {
                "type": "DirectSmokeInfrastructureError",
                "detail": "execution summary is missing",
            }
        (ARTIFACTS / "execution-error.json").write_text(
            json.dumps(error, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        summary["execution"] = {
            "infrastructure_exit_code": 2,
            "execution_completed": False,
            "candidate_passed": None,
            "candidate_result_status": None,
            "skipped_reason": None,
            "cleanup_before": cleanup_before,
            "cleanup_after": cleanup_after,
            "error": error,
        }
    else:
        summary["execution"] = {
            "infrastructure_exit_code": 0,
            "skipped_reason": None,
            "cleanup_before": cleanup_before,
            "cleanup_after": cleanup_after,
            **execution,
        }
    _write_summary(summary)
    return 0


def enforce() -> int:
    if not SUMMARY_PATH.exists():
        print(f"missing direct-smoke job summary: {SUMMARY_PATH}", file=sys.stderr)
        return 2
    try:
        summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
        if summary.get("test_scope") != "direct-contract":
            raise ValueError("direct test scope is not explicit")
        test_exit = int(summary["tests"]["exit_code"])
        inventory_exit = int(summary["inventory"]["exit_code"])
        execution = summary["execution"]
        execution_exit = int(execution["infrastructure_exit_code"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(
            f"invalid direct-smoke job summary: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2

    failures: list[str] = []
    if test_exit != 0:
        failures.append(f"direct contract tests exited {test_exit}")
    if inventory_exit != 0:
        failures.append(f"runtime inventory exited {inventory_exit}")
    prerequisites_ok = test_exit == 0 and inventory_exit == 0
    if prerequisites_ok:
        execution_completed = execution.get("execution_completed") is True
        result_status = execution.get("candidate_result_status")
        case_sha256 = execution.get("case_definition_sha256")
        cleanup_after = execution.get("cleanup_after")
        if execution_exit != 0:
            failures.append(f"direct execution infrastructure exited {execution_exit}")
        if not execution_completed:
            failures.append("direct execution did not complete")
        if result_status not in {"passed", "failed", "invalid"}:
            failures.append(
                f"unsupported candidate_result_status={result_status!r}"
            )
        if not isinstance(case_sha256, str) or not _SHA256.fullmatch(case_sha256):
            failures.append("case definition digest is missing or malformed")
        if (
            not isinstance(cleanup_after, dict)
            or cleanup_after.get("verified_absent") is not True
        ):
            failures.append("post-execution Ollama cleanup was not verified")
    elif execution.get("skipped_reason") != "prerequisite_failure":
        failures.append("direct execution skip reason is missing or invalid")
    if failures:
        print("; ".join(failures), file=sys.stderr)
        return 1
    print(
        "direct-smoke infrastructure gate passed; "
        f"result_status={execution.get('candidate_result_status')}; "
        f"case_definition_sha256={execution.get('case_definition_sha256')}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("capture", "enforce"))
    args = parser.parse_args()
    return capture() if args.mode == "capture" else enforce()


if __name__ == "__main__":
    raise SystemExit(main())

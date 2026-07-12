from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "artifacts"
BRIDGE_ARTIFACTS = ARTIFACT_ROOT / "direct-smoke"
H1_ARTIFACTS = ARTIFACT_ROOT / "model-residency"
COPIED_H1 = BRIDGE_ARTIFACTS / "model-residency"
SUMMARY_PATH = BRIDGE_ARTIFACTS / "job-summary.json"
EXPECTED_RUN_ID = "29106127334"
PHASES: tuple[tuple[str, int], ...] = (
    ("prepare", 60),
    ("tests", 420),
    ("probe", 1500),
    ("shortlist", 120),
    ("h2-plan", 120),
)
REQUIRED_EVIDENCE = (
    "report.json",
    "manifest.json",
    "shortlist.json",
    "shortlist-manifest.json",
    "h2-context-plan.json",
    "h2-context-plan-manifest.json",
)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmark_runtime import safe_reset_directory, sanitize_environment


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git_head() -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and value else None


def _run_phase(name: str, timeout_seconds: int, environment: dict[str, str]) -> dict[str, Any]:
    command = [sys.executable, "-m", "scripts.run_residency_job", name]
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        stdout = completed.stdout
        stderr = completed.stderr
        exit_code = int(completed.returncode)
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        stderr += f"\nphase timed out after {timeout_seconds} seconds\n"
        exit_code = 124
        timed_out = True
    (BRIDGE_ARTIFACTS / f"h1-{name}.stdout.log").write_text(stdout, encoding="utf-8")
    (BRIDGE_ARTIFACTS / f"h1-{name}.stderr.log").write_text(stderr, encoding="utf-8")
    return {
        "command": command,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "timeout_seconds": timeout_seconds,
    }


def _copy_h1_evidence() -> None:
    if COPIED_H1.exists():
        shutil.rmtree(COPIED_H1)
    if H1_ARTIFACTS.exists():
        shutil.copytree(H1_ARTIFACTS, COPIED_H1)


def capture() -> int:
    safe_reset_directory(BRIDGE_ARTIFACTS, allowed_root=ARTIFACT_ROOT)
    workflow_run_id = os.environ.get("GITHUB_RUN_ID")
    workflow_attempt = os.environ.get("GITHUB_RUN_ATTEMPT")
    clean_environment, removed_names = sanitize_environment(os.environ)
    clean_environment["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(ROOT / "src")))

    summary: dict[str, Any] = {
        "schema_version": "bench.h1-one-shot-job.v1",
        "source_workflow": "Local direct-model smoke",
        "source_workflow_run_id": workflow_run_id,
        "source_workflow_run_attempt": workflow_attempt,
        "expected_source_workflow_run_id": EXPECTED_RUN_ID,
        "repository_head": _git_head(),
        "sanitization": {
            "removed_external_env_names": removed_names,
            "secret_values_recorded": False,
        },
        "phases": {},
        "first_failure": None,
    }
    if workflow_run_id != EXPECTED_RUN_ID or not workflow_attempt:
        summary["first_failure"] = "workflow_identity_mismatch"
        _write_json(SUMMARY_PATH, summary)
        return 0

    failed = False
    for phase, timeout_seconds in PHASES:
        if failed:
            summary["phases"][phase] = {"status": "skipped", "exit_code": None}
            continue
        result = _run_phase(phase, timeout_seconds, clean_environment)
        result["status"] = "success" if result["exit_code"] == 0 else "failure"
        summary["phases"][phase] = result
        if result["exit_code"] != 0:
            summary["first_failure"] = phase
            failed = True

    _copy_h1_evidence()
    summary["evidence"] = {
        "copied_directory": str(COPIED_H1.relative_to(ROOT)),
        "required_files": {
            name: (COPIED_H1 / name).is_file() for name in REQUIRED_EVIDENCE
        },
    }
    _write_json(SUMMARY_PATH, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def enforce() -> int:
    if not SUMMARY_PATH.is_file():
        print(f"missing H1 one-shot summary: {SUMMARY_PATH}", file=sys.stderr)
        return 2
    try:
        summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
        if summary.get("schema_version") != "bench.h1-one-shot-job.v1":
            raise ValueError("unexpected one-shot schema")
        if summary.get("source_workflow_run_id") != EXPECTED_RUN_ID:
            raise ValueError("one-shot source workflow identity mismatch")
        phases = summary["phases"]
        for phase, _timeout in PHASES:
            if phases[phase].get("status") != "success":
                raise ValueError(f"H1 phase did not succeed: {phase}")
            if int(phases[phase]["exit_code"]) != 0:
                raise ValueError(f"H1 phase exited nonzero: {phase}")
        missing = [name for name in REQUIRED_EVIDENCE if not (COPIED_H1 / name).is_file()]
        if missing:
            raise ValueError(f"missing H1 evidence: {', '.join(missing)}")
        report = json.loads((COPIED_H1 / "report.json").read_text(encoding="utf-8"))
        if report.get("infrastructure_error") is not None:
            raise ValueError("H1 report contains an infrastructure error")
        if report.get("profile", {}).get("num_ctx") != 4096:
            raise ValueError("H1 report is not bound to the 4096 context profile")
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"H1 one-shot gate failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(
        "H1 one-shot gate passed; "
        f"repository_head={summary.get('repository_head')}; "
        f"evidence={COPIED_H1}"
    )
    return 0

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from bench.evaluator import load_case_file
from scripts import bench2r_hermes_runtime as optimization
from scripts import run_bench2_hermes_batch as bench2
from scripts import run_bench2_hermes_canary as canary
from scripts import validate_bench2r_hermes_s1 as execution

DEFAULT_ARTIFACTS = ROOT / "artifacts/bench2r-hermes-s1"
BATCH_INDEX_ENV = "BENCH2R_HERMES_BATCH_INDEX"
REPORT_SCHEMA = "bench.hermes-s1-batch-report.v1"
RUN_SCHEMA = "bench.hermes-s1-run.v1"
VALIDATOR_SCHEMA = "bench.hermes-s1-validator.v1"
MANIFEST_SCHEMA = "bench.hermes-s1-batch-manifest.v1"
ARMS = ("profile_only", "profile_plus_skill")


class HermesS1Error(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HermesS1Error(f"cannot read {path}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise HermesS1Error(f"{path} must contain an object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def batch_index_from_environment() -> int:
    raw = os.environ.get(BATCH_INDEX_ENV, "")
    if not re.fullmatch(r"[0-3]", raw):
        raise HermesS1Error(f"{BATCH_INDEX_ENV} is missing or invalid")
    return int(raw)


def _alias_name(batch_index: int, sequence: int) -> str:
    run_id = re.sub(r"[^0-9]", "", os.environ.get("GITHUB_RUN_ID", "")) or "local"
    attempt = re.sub(r"[^0-9]", "", os.environ.get("GITHUB_RUN_ATTEMPT", "")) or "0"
    return f"bench2r-s1-b{batch_index}-c{sequence}-64k:{run_id}-{attempt}"


def _hermes_python(hermes_repo: Path) -> Path:
    candidates = [
        hermes_repo.parent / "venvs" / "hermes" / "Scripts" / "python.exe",
        hermes_repo.parent / "venvs" / "hermes-agent" / "Scripts" / "python.exe",
        hermes_repo / ".venv" / "Scripts" / "python.exe",
        hermes_repo / "venv" / "Scripts" / "python.exe",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise HermesS1Error("managed Hermes Python environment was not found")


def _installed_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return bench2._installed_candidate(candidate)


def _parse_parameter_text(text: str) -> dict[str, float]:
    values: dict[str, float] = {}
    for raw_line in text.splitlines():
        parts = raw_line.strip().split()
        if len(parts) != 2:
            continue
        try:
            values[parts[0]] = float(parts[1])
        except ValueError:
            continue
    return values


def _attest_alias_parameters(
    profile: dict[str, Any],
    *,
    seed: int,
    parameter_text: str,
) -> dict[str, Any]:
    observed = _parse_parameter_text(parameter_text)
    expected: dict[str, float] = {
        "num_ctx": 65536.0,
        "num_predict": float(profile["max_output_tokens"]),
        "seed": float(seed),
    }
    for name, value in profile["sampling"].items():
        expected[name] = float(value)
    mismatches: dict[str, dict[str, float | None]] = {}
    for name, expected_value in expected.items():
        observed_value = observed.get(name)
        if observed_value is None or not math.isclose(
            observed_value,
            expected_value,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            mismatches[name] = {
                "expected": expected_value,
                "observed": observed_value,
            }
    return {
        "expected": expected,
        "observed": observed,
        "mismatches": mismatches,
        "passed": not mismatches,
    }


def _create_alias(
    candidate: dict[str, Any],
    profile: dict[str, Any],
    *,
    batch_index: int,
    runtime_root: Path,
    seed: int,
) -> dict[str, Any]:
    alias = _alias_name(batch_index, int(candidate["sequence"]))
    stale = canary._remove_model_if_present(alias)
    if stale.get("verified_absent") is not True:
        raise HermesS1Error(f"stale alias cleanup failed for {candidate['candidate_id']}")
    modelfile = runtime_root / f"{candidate['candidate_id']}.Modelfile"
    modelfile.write_text(
        optimization.build_modelfile(profile, seed=seed),
        encoding="utf-8",
        newline="\n",
    )
    create = canary._run(["ollama", "create", alias, "-f", str(modelfile)], timeout=600)
    if create.get("ok") is not True:
        detail = str(create.get("stderr") or create.get("stdout") or "")[-500:]
        raise HermesS1Error(f"alias creation failed for {candidate['candidate_id']}: {detail}")
    parameters = canary._run(["ollama", "show", alias, "--parameters"], timeout=60)
    parameter_text = str(parameters.get("stdout") or "")
    if parameters.get("ok") is not True:
        raise HermesS1Error(f"cannot read alias parameters for {candidate['candidate_id']}")
    attestation = _attest_alias_parameters(
        profile,
        seed=seed,
        parameter_text=parameter_text,
    )
    if attestation["passed"] is not True:
        raise HermesS1Error(
            f"alias parameter mismatch for {candidate['candidate_id']}: "
            f"{attestation['mismatches']}"
        )
    matches = [
        item for item in canary.residency.list_installed_models()
        if item.get("name") == alias
    ]
    if len(matches) != 1:
        raise HermesS1Error(f"runtime alias missing for {candidate['candidate_id']}")
    model = matches[0]
    return {
        "name": alias,
        "digest": model.get("digest"),
        "size": model.get("size"),
        "source_candidate_id": candidate["candidate_id"],
        "source_candidate_name": candidate["model_tag"],
        "source_candidate_digest": candidate["digest"],
        "modelfile_sha256": _sha256(modelfile),
        "parameters": parameter_text.strip(),
        "parameter_attestation": attestation,
        "stale_cleanup": stale,
    }


def _write_isolated_home(
    home: Path,
    workdir: Path,
    *,
    runtime_model: str,
    profile: dict[str, Any],
    case: dict[str, Any],
    arm: str,
) -> None:
    plugin_source = ROOT / "fixtures/bench-2/hermes-plugin/bench2-fixture"
    plugin_target = home / "plugins" / "bench2-fixture"
    plugin_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(plugin_source, plugin_target)
    if arm == "profile_plus_skill":
        optimization.install_bounded_skill(home)
    config = optimization.render_hermes_config(
        profile=profile,
        case=case,
        runtime_model=runtime_model,
        workdir=workdir,
    )
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text(config, encoding="utf-8", newline="\n")
    (home / ".env").write_text("\n", encoding="utf-8", newline="\n")


def _load_worker_result(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, "worker_result_missing"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"worker_result_invalid:{type(exc).__name__}"
    if not isinstance(value, dict):
        return None, "worker_result_not_object"
    if value.get("schema_version") != "bench.hermes-s1-worker-result.v1":
        return value, "worker_result_schema_mismatch"
    return value, None


def _validate_usage(
    path: Path,
    *,
    expected_model: str,
    worker_result: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    try:
        usage = _load_json(path)
    except HermesS1Error as exc:
        return None, [{"check": "usage_file_valid", "passed": False, "detail": str(exc)}]
    add("usage_file_valid", True, "valid JSON object")
    add("usage_provider_custom", usage.get("provider") == "custom", f"provider={usage.get('provider')!r}")
    add("usage_model_exact", usage.get("model") == expected_model, f"model={usage.get('model')!r}")
    api_calls = usage.get("api_calls")
    add(
        "usage_api_calls_nonnegative",
        isinstance(api_calls, int) and not isinstance(api_calls, bool) and api_calls >= 0,
        f"api_calls={api_calls!r}",
    )
    worker_calls = worker_result.get("api_calls") if isinstance(worker_result, dict) else None
    add(
        "usage_api_calls_match_worker",
        api_calls == worker_calls,
        f"usage={api_calls!r} worker={worker_calls!r}",
    )
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        value = usage.get(key)
        add(
            f"usage_{key}_nonnegative",
            isinstance(value, int) and not isinstance(value, bool) and value >= 0,
            f"{key}={value!r}",
        )
    return usage, checks


def _trajectory_tool_registry_observed(
    output_dir: Path,
    trajectory_files: list[str],
) -> bool:
    text = "\n".join(
        (output_dir / name).read_text(encoding="utf-8", errors="replace")
        for name in trajectory_files
        if (output_dir / name).is_file()
    )
    return "bench_lookup" in text and "bench_distractor" in text


def _copy_native_trajectories(workdir: Path, output_dir: Path) -> list[str]:
    copied: list[str] = []
    for name in ("trajectory_samples.jsonl", "failed_trajectories.jsonl"):
        source = workdir / name
        if source.is_file() and source.stat().st_size > 0:
            shutil.copyfile(source, output_dir / name)
            copied.append(name)
    return copied


def _semantic_validator(
    *,
    case: dict[str, Any],
    arm: str,
    process: dict[str, Any],
    output: dict[str, Any] | None,
    output_error: str | None,
    tool_records: list[dict[str, Any]],
    trace_error: str | None,
    worker_result: dict[str, Any] | None,
    worker_error: str | None,
    usage: dict[str, Any] | None,
    usage_checks: list[dict[str, Any]],
    runtime_model: dict[str, Any] | None,
    residency_class: str | None,
    residency_ratio: float | None,
    trajectory_files: list[str],
    tool_registry_observed: bool,
    alias: dict[str, Any],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    add(
        "worker_exit_zero",
        process.get("returncode") == 0 and process.get("timed_out") is False,
        f"returncode={process.get('returncode')!r} timed_out={process.get('timed_out')!r}",
    )
    add("worker_result_valid", worker_error is None, f"error={worker_error!r}")
    expected_skill = arm == "profile_plus_skill"
    observed_skill = worker_result.get("skill_expanded") if worker_result else None
    add(
        "arm_skill_expansion_exact",
        observed_skill is expected_skill,
        f"expected={expected_skill} observed={observed_skill!r}",
    )
    add(
        "tool_registry_observed",
        tool_registry_observed,
        "both benchmark tools must appear in the native trajectory system prompt",
    )
    add("tool_trace_valid", trace_error is None, f"error={trace_error!r}")
    add(
        "native_trajectory_present",
        bool(trajectory_files),
        f"files={trajectory_files!r}",
    )
    add(
        "runtime_model_observed",
        runtime_model is not None,
        f"observed={runtime_model is not None}",
    )
    add(
        "runtime_context_65536",
        runtime_model is not None and runtime_model.get("context_length") == 65536,
        f"context={runtime_model.get('context_length') if runtime_model else None!r}",
    )
    add(
        "runtime_full_vram",
        residency_class == "full_vram"
        and residency_ratio is not None
        and residency_ratio >= 0.98,
        f"class={residency_class!r} ratio={residency_ratio!r}",
    )
    add(
        "alias_profile_attested",
        alias.get("parameter_attestation", {}).get("passed") is True,
        f"mismatches={alias.get('parameter_attestation', {}).get('mismatches')!r}",
    )
    checks.extend(usage_checks)

    expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
    add("output_strict_json", output_error is None, f"error={output_error!r}")
    add(
        "output_final_exact",
        output is not None and output.get("final") == expected.get("final"),
        f"observed={output.get('final') if output else None!r}",
    )
    add(
        "output_actions_exact",
        output is not None and output.get("actions") == expected.get("actions"),
        f"observed={output.get('actions') if output else None!r}",
    )
    limits = case.get("limits") if isinstance(case.get("limits"), dict) else {}
    max_calls = limits.get("max_model_calls")
    api_calls = usage.get("api_calls") if isinstance(usage, dict) else None
    add(
        "model_call_budget_within_limit",
        isinstance(api_calls, int)
        and not isinstance(api_calls, bool)
        and isinstance(max_calls, int)
        and 1 <= api_calls <= max_calls,
        f"api_calls={api_calls!r} max={max_calls!r}",
    )
    if case.get("capability") == "HO-TOOLS":
        expected_trace = [{
            "schema_version": "bench.hermes-tool-trace.v1",
            "tool_name": "bench_lookup",
            "arguments": {"key": "alpha-7"},
            "result": {"key": "alpha-7", "ok": True, "value": "BRAVO-19"},
        }]
    elif case.get("capability") == "HO-STOP":
        expected_trace = []
    else:
        raise HermesS1Error(f"unsupported capability: {case.get('capability')}")
    add(
        "tool_trace_exact",
        tool_records == expected_trace,
        f"records={tool_records!r}",
    )
    add(
        "agent_completed_without_failure",
        worker_result is not None
        and worker_result.get("completed") is True
        and worker_result.get("failed") is False
        and worker_result.get("failure") is None,
        (
            f"completed={worker_result.get('completed') if worker_result else None!r} "
            f"failed={worker_result.get('failed') if worker_result else None!r} "
            f"failure={worker_result.get('failure') if worker_result else None!r}"
        ),
    )
    add(
        "turn_exit_reason_observed",
        isinstance(worker_result.get("turn_exit_reason") if worker_result else None, str),
        f"reason={worker_result.get('turn_exit_reason') if worker_result else None!r}",
    )

    infrastructure_names = {
        "worker_exit_zero",
        "worker_result_valid",
        "arm_skill_expansion_exact",
        "tool_registry_observed",
        "tool_trace_valid",
        "native_trajectory_present",
        "runtime_model_observed",
        "runtime_context_65536",
        "runtime_full_vram",
        "alias_profile_attested",
        "usage_file_valid",
        "usage_provider_custom",
        "usage_model_exact",
        "usage_api_calls_nonnegative",
        "usage_api_calls_match_worker",
        "usage_input_tokens_nonnegative",
        "usage_output_tokens_nonnegative",
        "usage_total_tokens_nonnegative",
    }
    semantic_names = {
        "output_strict_json",
        "output_final_exact",
        "output_actions_exact",
        "model_call_budget_within_limit",
        "tool_trace_exact",
        "agent_completed_without_failure",
        "turn_exit_reason_observed",
    }
    observed = {item["check"] for item in checks}
    infrastructure_valid = infrastructure_names <= observed and all(
        item["passed"] for item in checks if item["check"] in infrastructure_names
    )
    semantic_pass = semantic_names <= observed and all(
        item["passed"] for item in checks if item["check"] in semantic_names
    )
    return {
        "schema_version": VALIDATOR_SCHEMA,
        "case_id": case["case_id"],
        "capability": case["capability"],
        "arm": arm,
        "infrastructure_valid": infrastructure_valid,
        "semantic_pass": semantic_pass,
        "passed": infrastructure_valid and semantic_pass,
        "checks": checks,
        "diagnostics": {
            "api_calls": api_calls,
            "turn_exit_reason": worker_result.get("turn_exit_reason") if worker_result else None,
            "worker_failed": worker_result.get("failed") if worker_result else None,
            "worker_partial": worker_result.get("partial") if worker_result else None,
        },
    }


def _minimal_invalid_run(
    output_dir: Path,
    *,
    candidate: dict[str, Any],
    case: dict[str, Any],
    arm: str,
    error: Exception,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "raw-output.txt").write_text("", encoding="utf-8")
    (output_dir / "stderr.txt").write_text(
        f"{type(error).__name__}: {error}\n",
        encoding="utf-8",
    )
    (output_dir / "tool-trace.jsonl").write_text("", encoding="utf-8")
    _write_json(output_dir / "validator-result.json", {
        "schema_version": VALIDATOR_SCHEMA,
        "case_id": case["case_id"],
        "capability": case["capability"],
        "arm": arm,
        "infrastructure_valid": False,
        "semantic_pass": False,
        "passed": False,
        "checks": [],
    })
    _write_json(output_dir / "environment-fingerprint.json", {
        "schema_version": "bench.hermes-s1-environment.v1",
        "candidate": candidate,
        "arm": arm,
        "infrastructure_error": {
            "type": type(error).__name__,
            "detail": str(error),
        },
    })
    canary._write_manifest(output_dir)
    return {
        "schema_version": RUN_SCHEMA,
        "candidate_id": candidate["candidate_id"],
        "case_id": case["case_id"],
        "capability": case["capability"],
        "arm": arm,
        "candidate_result_status": "invalid_infrastructure",
        "infrastructure_valid": False,
        "semantic_pass": False,
        "infrastructure_error": {
            "type": type(error).__name__,
            "detail": str(error),
        },
        "artifact_path": output_dir.as_posix(),
    }


def _run_once(
    *,
    candidate: dict[str, Any],
    profile: dict[str, Any],
    alias: dict[str, Any],
    case: dict[str, Any],
    arm: str,
    hermes_repo: Path,
    hermes_python: Path,
    hermes_identity: dict[str, Any],
    repository: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_base = Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir())
    runtime_root = Path(tempfile.mkdtemp(
        prefix=f"bench2r-s1-{candidate['candidate_id']}-{case['case_id']}-{arm}-",
        dir=runtime_base,
    ))
    process: dict[str, Any] = {
        "ok": False,
        "returncode": None,
        "timed_out": False,
        "stdout": "",
        "stderr": "",
        "duration_seconds": 0.0,
    }
    cleanup_before: list[dict[str, Any]] = []
    cleanup_after: list[dict[str, Any]] = []
    removed_credentials: list[str] = []
    gpu_before: dict[str, Any] = {"ok": False, "gpus": []}
    gpu_loaded: dict[str, Any] = {"ok": False, "gpus": []}
    runtime_model: dict[str, Any] | None = None
    residency_class: str | None = None
    residency_ratio: float | None = None
    infrastructure_error: dict[str, str] | None = None
    validator: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    worker_result: dict[str, Any] | None = None
    worker_error: str | None = None
    output: dict[str, Any] | None = None
    output_error: str | None = None
    tool_records: list[dict[str, Any]] = []
    trace_error: str | None = None
    trajectory_files: list[str] = []

    try:
        cleanup_before = canary.stop_all_running_models()
        gpu_before = canary.residency.gpu_snapshot()
        if gpu_before.get("ok") is not True:
            raise HermesS1Error("GPU snapshot failed before run")
        home = runtime_root / "hermes-home"
        workdir = runtime_root / "workdir"
        workdir.mkdir(parents=True)
        tool_trace_path = runtime_root / "tool-trace.jsonl"
        prompt_path = runtime_root / "prompt.txt"
        prompt_path.write_text(canary._build_prompt(case), encoding="utf-8", newline="\n")
        _write_isolated_home(
            home,
            workdir,
            runtime_model=alias["name"],
            profile=profile,
            case=case,
            arm=arm,
        )
        shutil.copyfile(home / "config.yaml", output_dir / "effective-config.yaml")
        env, removed_credentials = canary.sanitized_subprocess_environment(
            hermes_home=home,
            tool_trace=tool_trace_path,
            hermes_repo=hermes_repo,
            runtime_model=alias["name"],
        )
        env["HERMES_YOLO_MODE"] = "1"
        env["HERMES_ACCEPT_HOOKS"] = "1"
        command = [
            str(hermes_python),
            str(ROOT / "scripts/run_bench2r_hermes_worker.py"),
            "--model", alias["name"],
            "--arm", arm,
            "--prompt-file", str(prompt_path),
            "--usage-file", str(output_dir / "usage.json"),
            "--result-file", str(output_dir / "worker-result.json"),
            "--debug-file", str(output_dir / "worker-debug.txt"),
        ]
        process = canary._run(command, cwd=workdir, env=env, timeout=600)
        stdout = str(process.get("stdout") or "")
        stderr = str(process.get("stderr") or "")
        (output_dir / "raw-output.txt").write_text(stdout, encoding="utf-8", newline="\n")
        (output_dir / "stderr.txt").write_text(stderr, encoding="utf-8", newline="\n")
        (output_dir / "hermes-version.txt").write_text(
            str(hermes_identity.get("version_output") or "") + "\n",
            encoding="utf-8",
            newline="\n",
        )
        worker_result, worker_error = _load_worker_result(output_dir / "worker-result.json")
        output, output_error = canary._parse_output(stdout)
        _write_json(output_dir / "extracted-output.json", {
            "schema_version": "bench.hermes-s1-extracted-output.v1",
            "value": output,
            "error": output_error,
        })
        tool_records, trace_error = canary._read_tool_trace(tool_trace_path)
        with (output_dir / "tool-trace.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for record in tool_records:
                handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        usage, usage_checks = _validate_usage(
            output_dir / "usage.json",
            expected_model=alias["name"],
            worker_result=worker_result,
        )
        trajectory_files = _copy_native_trajectories(workdir, output_dir)
        tool_registry_observed = _trajectory_tool_registry_observed(
            output_dir,
            trajectory_files,
        )
        runtime_model = canary.residency._find_single_running_model({
            "name": alias["name"],
            "digest": alias["digest"],
        })
        residency_class, residency_ratio = canary.residency.classify_residency(
            runtime_model.get("size"),
            runtime_model.get("size_vram"),
        )
        gpu_loaded = canary.residency.gpu_snapshot()
        if gpu_loaded.get("ok") is not True:
            raise HermesS1Error("GPU snapshot failed after run")
        validator = _semantic_validator(
            case=case,
            arm=arm,
            process=process,
            output=output,
            output_error=output_error,
            tool_records=tool_records,
            trace_error=trace_error,
            worker_result=worker_result,
            worker_error=worker_error,
            usage=usage,
            usage_checks=usage_checks,
            runtime_model=runtime_model,
            residency_class=residency_class,
            residency_ratio=residency_ratio,
            trajectory_files=trajectory_files,
            tool_registry_observed=tool_registry_observed,
            alias=alias,
        )
    except Exception as exc:
        infrastructure_error = {"type": type(exc).__name__, "detail": str(exc)}
    finally:
        try:
            cleanup_after = canary.stop_all_running_models()
            if any(item.get("verified_absent") is not True for item in cleanup_after):
                raise HermesS1Error("run cleanup attestation failed")
        except Exception as exc:
            detail = f"cleanup failed: {type(exc).__name__}: {exc}"
            if infrastructure_error is None:
                infrastructure_error = {"type": type(exc).__name__, "detail": detail}
            else:
                infrastructure_error["detail"] += "; " + detail
        shutil.rmtree(runtime_root, ignore_errors=True)

    if validator is None:
        validator = {
            "schema_version": VALIDATOR_SCHEMA,
            "case_id": case["case_id"],
            "capability": case["capability"],
            "arm": arm,
            "infrastructure_valid": False,
            "semantic_pass": False,
            "passed": False,
            "checks": [],
        }
    if infrastructure_error is not None:
        validator["infrastructure_valid"] = False
        validator["passed"] = False
    _write_json(output_dir / "validator-result.json", validator)
    _write_json(output_dir / "observed-trace.json", {
        "schema_version": "bench.hermes-s1-observed-trace.v1",
        "case_id": case["case_id"],
        "arm": arm,
        "messages": worker_result.get("messages") if worker_result else None,
        "tool_records": tool_records,
        "final_response": worker_result.get("final_response") if worker_result else None,
        "turn_exit_reason": worker_result.get("turn_exit_reason") if worker_result else None,
        "api_calls": worker_result.get("api_calls") if worker_result else None,
    })
    environment = {
        "schema_version": "bench.hermes-s1-environment.v1",
        "created_at_utc": _utc_now(),
        "repository": repository,
        "hermes": hermes_identity,
        "candidate": candidate,
        "profile": profile,
        "arm": arm,
        "runtime_alias": alias,
        "credential_environment_names_removed": removed_credentials,
        "gpu_before": gpu_before,
        "gpu_loaded": gpu_loaded,
        "runtime_model": runtime_model,
        "residency_class": residency_class,
        "residency_ratio": residency_ratio,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "trajectory_files": trajectory_files,
        "infrastructure_error": infrastructure_error,
    }
    _write_json(output_dir / "environment-fingerprint.json", environment)
    canary._write_manifest(output_dir)

    infrastructure_valid = (
        infrastructure_error is None
        and validator.get("infrastructure_valid") is True
    )
    semantic_pass = infrastructure_valid and validator.get("semantic_pass") is True
    return {
        "schema_version": RUN_SCHEMA,
        "candidate_id": candidate["candidate_id"],
        "candidate_sequence": candidate["sequence"],
        "case_id": case["case_id"],
        "capability": case["capability"],
        "arm": arm,
        "candidate_result_status": (
            "passed" if semantic_pass
            else "failed" if infrastructure_valid
            else "invalid_infrastructure"
        ),
        "infrastructure_valid": infrastructure_valid,
        "semantic_pass": semantic_pass,
        "infrastructure_error": infrastructure_error,
        "process": {
            key: process.get(key)
            for key in ("returncode", "timed_out", "duration_seconds")
        },
        "api_calls": usage.get("api_calls") if usage else None,
        "turn_exit_reason": worker_result.get("turn_exit_reason") if worker_result else None,
        "tool_trace_count": len(tool_records),
        "trajectory_files": trajectory_files,
        "runtime_context_length": runtime_model.get("context_length") if runtime_model else None,
        "residency_class": residency_class,
        "residency_ratio": residency_ratio,
        "cleanup_verified": bool(cleanup_after)
        and all(item.get("verified_absent") is True for item in cleanup_after),
        "artifact_path": output_dir.relative_to(DEFAULT_ARTIFACTS).as_posix()
        if DEFAULT_ARTIFACTS in output_dir.parents else output_dir.as_posix(),
    }


def _batch_manifest(output_dir: Path) -> None:
    artifacts: dict[str, dict[str, Any]] = {}
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path == output_dir / "manifest.json":
            continue
        relative = path.relative_to(output_dir).as_posix()
        artifacts[relative] = {
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
        }
    _write_json(output_dir / "manifest.json", {
        "schema_version": MANIFEST_SCHEMA,
        "created_at_utc": _utc_now(),
        "artifacts": artifacts,
    })


def capture(output_dir: Path = DEFAULT_ARTIFACTS) -> int:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    plan, marker, candidates, case_records = execution.validate_execution(require_enabled=True)
    batch_index = batch_index_from_environment()
    selected, selection = execution.select_batch(candidates, batch_index)
    cases = [load_case_file(ROOT / record["path"]) for record in case_records]
    profiles = optimization.load_profiles()
    profile_map = {
        item["candidate_id"]: item
        for item in profiles["candidate_profiles"]
    }
    seed = optimization.seed_for("tuning", 1)
    repository = canary.repository_snapshot()
    hermes_repo = canary._discover_hermes_repo()
    bootstrap_root = Path(tempfile.mkdtemp(
        prefix="bench2r-s1-bootstrap-",
        dir=Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()),
    ))
    bootstrap_home = bootstrap_root / "home"
    bootstrap_trace = bootstrap_root / "trace.jsonl"
    bootstrap_env, _ = canary.sanitized_subprocess_environment(
        hermes_home=bootstrap_home,
        tool_trace=bootstrap_trace,
        hermes_repo=hermes_repo,
        runtime_model=selected[0]["model_tag"],
    )
    prefix = canary._hermes_command_prefix(hermes_repo)
    hermes_identity = canary._verify_hermes_identity(prefix, hermes_repo, bootstrap_env)
    hermes_python = _hermes_python(hermes_repo)
    shutil.rmtree(bootstrap_root, ignore_errors=True)

    runs: list[dict[str, Any]] = []
    for candidate in selected:
        profile = profile_map[candidate["candidate_id"]]
        candidate_root = Path(tempfile.mkdtemp(
            prefix=f"bench2r-s1-alias-{candidate['candidate_id']}-",
            dir=Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()),
        ))
        alias: dict[str, Any] | None = None
        try:
            _installed_candidate(candidate)
            alias = _create_alias(
                candidate,
                profile,
                batch_index=batch_index,
                runtime_root=candidate_root,
                seed=seed,
            )
            for case in cases:
                for arm in ARMS:
                    run_dir = (
                        output_dir
                        / "runs"
                        / candidate["candidate_id"]
                        / case["case_id"]
                        / arm
                        / "r1"
                    )
                    runs.append(_run_once(
                        candidate=candidate,
                        profile=profile,
                        alias=alias,
                        case=case,
                        arm=arm,
                        hermes_repo=hermes_repo,
                        hermes_python=hermes_python,
                        hermes_identity=hermes_identity,
                        repository=repository,
                        output_dir=run_dir,
                    ))
        except Exception as exc:
            for case in cases:
                for arm in ARMS:
                    run_dir = (
                        output_dir
                        / "runs"
                        / candidate["candidate_id"]
                        / case["case_id"]
                        / arm
                        / "r1"
                    )
                    runs.append(_minimal_invalid_run(
                        run_dir,
                        candidate=candidate,
                        case=case,
                        arm=arm,
                        error=exc,
                    ))
        finally:
            expected_alias = alias.get("name") if alias else _alias_name(
                batch_index,
                int(candidate["sequence"]),
            )
            cleanup = canary._remove_model_if_present(expected_alias)
            if cleanup.get("verified_absent") is not True:
                raise HermesS1Error(f"alias cleanup failed for {candidate['candidate_id']}")
            shutil.rmtree(candidate_root, ignore_errors=True)

    status_counts: dict[str, int] = {}
    for run in runs:
        status = str(run["candidate_result_status"])
        status_counts[status] = status_counts.get(status, 0) + 1
    report = {
        "schema_version": REPORT_SCHEMA,
        "created_at_utc": _utc_now(),
        "plan": plan,
        "marker": marker,
        "selection": selection,
        "repository": repository,
        "hermes": hermes_identity,
        "seed": seed,
        "arms": list(ARMS),
        "runs": runs,
        "counts": {
            "expected_runs": selection["expected_runs"],
            "captured_runs": len(runs),
            "statuses": status_counts,
        },
        "decision": {
            "admission_allowed": False,
            "purpose": "diagnostic arm comparison only",
        },
    }
    _write_json(output_dir / "batch-report.json", report)
    _batch_manifest(output_dir)
    return 0


def enforce(output_dir: Path = DEFAULT_ARTIFACTS) -> int:
    report = _load_json(output_dir / "batch-report.json")
    manifest = _load_json(output_dir / "manifest.json")
    if report.get("schema_version") != REPORT_SCHEMA:
        raise HermesS1Error("batch report schema is invalid")
    runs = report.get("runs")
    expected = report.get("counts", {}).get("expected_runs")
    if not isinstance(runs, list) or len(runs) != expected:
        raise HermesS1Error("S1 batch run inventory is incomplete")
    if report.get("decision", {}).get("admission_allowed") is not False:
        raise HermesS1Error("S1 diagnostic run cannot admit a model")
    artifacts = manifest.get("artifacts")
    if manifest.get("schema_version") != MANIFEST_SCHEMA or not isinstance(artifacts, dict):
        raise HermesS1Error("S1 manifest is invalid")
    for relative, record in artifacts.items():
        path = output_dir / relative
        if not path.is_file():
            raise HermesS1Error(f"manifest artifact is missing: {relative}")
        if record.get("sha256") != _sha256(path):
            raise HermesS1Error(f"manifest digest mismatch: {relative}")
        if record.get("size_bytes") != path.stat().st_size:
            raise HermesS1Error(f"manifest size mismatch: {relative}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run BENCH-2R Hermes S1 batches.")
    parser.add_argument("mode", choices=("capture", "enforce"))
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACTS)
    args = parser.parse_args()
    try:
        return capture(args.artifact_dir) if args.mode == "capture" else enforce(args.artifact_dir)
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

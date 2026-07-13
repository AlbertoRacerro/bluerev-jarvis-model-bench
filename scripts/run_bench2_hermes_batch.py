from __future__ import annotations

import argparse
import hashlib
import json
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
from scripts import run_bench2_hermes_canary as canary
from scripts import validate_bench2_hermes_execution as execution

DEFAULT_ARTIFACTS = ROOT / "artifacts/bench2-hermes-full-matrix"
REPORT_SCHEMA = "bench.hermes-full-matrix-batch-report.v1"
MANIFEST_SCHEMA = "bench.hermes-full-matrix-batch-manifest.v1"
RUN_SCHEMA = "bench.hermes-full-matrix-run.v1"
VALIDATOR_SCHEMA = "bench.hermes-full-matrix-run-validator.v1"
BATCH_INDEX_ENV = "BENCH2_HERMES_BATCH_INDEX"


class HermesBatchError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HermesBatchError(f"cannot read {path}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise HermesBatchError(f"{path} must contain an object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def batch_index_from_environment() -> int:
    raw = os.environ.get(BATCH_INDEX_ENV, "")
    if not re.fullmatch(r"[0-3]", raw):
        raise HermesBatchError(f"{BATCH_INDEX_ENV} is missing or invalid")
    return int(raw)


def _alias_name(batch_index: int, candidate_sequence: int) -> str:
    run_id = re.sub(r"[^0-9]", "", os.environ.get("GITHUB_RUN_ID", "")) or "local"
    attempt = re.sub(r"[^0-9]", "", os.environ.get("GITHUB_RUN_ATTEMPT", "")) or "0"
    return f"bench2-b{batch_index}-c{candidate_sequence}-64k:{run_id}-{attempt}"


def _installed_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    matches = [
        item for item in canary.residency.list_installed_models()
        if item.get("name") == candidate["model_tag"]
    ]
    if len(matches) != 1:
        raise HermesBatchError(
            f"candidate {candidate['candidate_id']} is missing or duplicated in Ollama"
        )
    model = matches[0]
    if model.get("digest") != candidate["digest"]:
        raise HermesBatchError(f"candidate {candidate['candidate_id']} digest drifted")
    return model


def _create_alias(
    candidate: dict[str, Any],
    *,
    batch_index: int,
    runtime_root: Path,
) -> dict[str, Any]:
    alias = _alias_name(batch_index, int(candidate["sequence"]))
    stale = canary._remove_model_if_present(alias)
    if stale.get("verified_absent") is not True:
        raise HermesBatchError(f"stale alias cleanup failed for {candidate['candidate_id']}")
    modelfile = runtime_root / f"{candidate['candidate_id']}.Modelfile"
    modelfile.write_text(
        canary._runtime_modelfile(candidate["model_tag"]),
        encoding="utf-8",
        newline="\n",
    )
    create = canary._run(["ollama", "create", alias, "-f", str(modelfile)], timeout=600)
    if create.get("ok") is not True:
        detail = str(create.get("stderr") or create.get("stdout") or "")[-500:]
        raise HermesBatchError(
            f"alias creation failed for {candidate['candidate_id']}: {detail}"
        )
    parameters = canary._run(["ollama", "show", alias, "--parameters"], timeout=60)
    parameter_text = str(parameters.get("stdout") or "")
    if parameters.get("ok") is not True or re.search(
        r"(?mi)^\s*num_ctx\s+65536\s*$", parameter_text
    ) is None:
        raise HermesBatchError(
            f"alias for {candidate['candidate_id']} does not expose num_ctx 65536"
        )
    matches = [
        item for item in canary.residency.list_installed_models()
        if item.get("name") == alias
    ]
    if len(matches) != 1:
        raise HermesBatchError(f"alias for {candidate['candidate_id']} is missing")
    model = matches[0]
    return {
        "name": alias,
        "digest": model.get("digest"),
        "size": model.get("size"),
        "source_candidate_id": candidate["candidate_id"],
        "source_candidate_name": candidate["model_tag"],
        "source_candidate_digest": candidate["digest"],
        "modelfile_sha256": hashlib.sha256(modelfile.read_bytes()).hexdigest(),
        "parameters": parameter_text.strip(),
        "stale_cleanup": stale,
    }


def _case_expectation(case: dict[str, Any]) -> dict[str, Any]:
    expected = case.get("expected")
    if not isinstance(expected, dict):
        raise HermesBatchError(f"case {case.get('case_id')} expected contract is missing")
    return {
        "actions": expected.get("actions"),
        "final": expected.get("final"),
    }


def _semantic_validator(
    *,
    case: dict[str, Any],
    process: dict[str, Any],
    output: dict[str, Any] | None,
    output_error: str | None,
    tool_records: list[dict[str, Any]],
    trace_error: str | None,
    usage_checks: list[dict[str, Any]],
    usage: dict[str, Any] | None,
    runtime_model: dict[str, Any] | None,
    residency_class: str | None,
    residency_ratio: float | None,
    stderr_text: str,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    add(
        "hermes_exit_zero",
        process.get("returncode") == 0 and process.get("timed_out") is False,
        f"returncode={process.get('returncode')!r} timed_out={process.get('timed_out')!r}",
    )
    add(
        "fixture_plugin_registered",
        "Plugin bench2-fixture registered tool: bench_lookup" in stderr_text,
        "bench_lookup registration line required",
    )
    add("output_strict_json", output_error is None, f"error={output_error!r}")
    expected = _case_expectation(case)
    add(
        "output_final_exact",
        output is not None and output.get("final") == expected["final"],
        f"observed={output.get('final') if output else None!r}",
    )
    add(
        "output_actions_exact",
        output is not None and output.get("actions") == expected["actions"],
        f"observed={output.get('actions') if output else None!r}",
    )
    limits = case.get("limits") if isinstance(case.get("limits"), dict) else {}
    max_model_calls = limits.get("max_model_calls")
    api_calls = usage.get("api_calls") if isinstance(usage, dict) else None
    add(
        "model_call_budget_within_limit",
        isinstance(max_model_calls, int)
        and not isinstance(max_model_calls, bool)
        and isinstance(api_calls, int)
        and not isinstance(api_calls, bool)
        and 1 <= api_calls <= max_model_calls,
        f"api_calls={api_calls!r} max_model_calls={max_model_calls!r}",
    )
    add("tool_trace_valid", trace_error is None, f"error={trace_error!r}")
    if case["capability"] == "HO-TOOLS":
        expected_trace = [{
            "schema_version": "bench.hermes-tool-trace.v1",
            "tool_name": "bench_lookup",
            "arguments": {"key": "alpha-7"},
            "result": {"key": "alpha-7", "ok": True, "value": "BRAVO-19"},
        }]
        add(
            "tool_trace_exact",
            tool_records == expected_trace,
            f"records={tool_records!r}",
        )
    elif case["capability"] == "HO-STOP":
        add(
            "tool_trace_exact",
            tool_records == [],
            f"records={tool_records!r}",
        )
    else:
        raise HermesBatchError(f"unsupported capability: {case['capability']}")
    checks.extend(usage_checks)
    add(
        "runtime_model_observed",
        runtime_model is not None,
        f"observed={runtime_model is not None}",
    )
    add(
        "runtime_context_65536",
        runtime_model is not None and runtime_model.get("context_length") == 65536,
        f"context_length={runtime_model.get('context_length') if runtime_model else None!r}",
    )
    add(
        "runtime_full_vram",
        residency_class == "full_vram"
        and residency_ratio is not None
        and residency_ratio >= 0.98,
        f"class={residency_class!r} ratio={residency_ratio!r}",
    )
    infrastructure_names = {
        "hermes_exit_zero",
        "fixture_plugin_registered",
        "tool_trace_valid",
        "usage_provider_custom",
        "usage_model_exact",
        "usage_completed",
        "usage_not_failed",
        "usage_api_calls_bounded",
        "usage_input_tokens_nonnegative",
        "usage_output_tokens_nonnegative",
        "usage_total_tokens_nonnegative",
        "runtime_model_observed",
        "runtime_context_65536",
        "runtime_full_vram",
    }
    semantic_names = {
        "output_strict_json",
        "output_final_exact",
        "output_actions_exact",
        "model_call_budget_within_limit",
        "tool_trace_exact",
    }
    observed_names = {item["check"] for item in checks}
    infrastructure_valid = (
        infrastructure_names <= observed_names
        and all(
            item["passed"] for item in checks
            if item["check"] in infrastructure_names
        )
    )
    semantic_pass = (
        semantic_names <= observed_names
        and all(
            item["passed"] for item in checks
            if item["check"] in semantic_names
        )
    )
    return {
        "schema_version": VALIDATOR_SCHEMA,
        "case_id": case["case_id"],
        "capability": case["capability"],
        "infrastructure_valid": infrastructure_valid,
        "semantic_pass": semantic_pass,
        "passed": infrastructure_valid and semantic_pass,
        "checks": checks,
    }


def _write_run_manifest(run_dir: Path) -> None:
    canary._write_manifest(run_dir)


def _minimal_invalid_run(
    run_dir: Path,
    *,
    candidate: dict[str, Any],
    case: dict[str, Any],
    repetition: int,
    alias: dict[str, Any] | None,
    error: Exception,
) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "raw-output.txt").write_text("", encoding="utf-8")
    (run_dir / "stderr.txt").write_text(
        f"{type(error).__name__}: {error}\n", encoding="utf-8"
    )
    _write_json(run_dir / "extracted-output.json", {
        "schema_version": "bench.hermes-canary-extracted-output.v1",
        "value": None,
        "error": "not_executed",
    })
    (run_dir / "tool-trace.jsonl").write_text("", encoding="utf-8")
    _write_json(run_dir / "trace.json", {
        "schema_version": "bench.trace.v1",
        "case_id": case["case_id"],
        "events": [],
    })
    _write_json(run_dir / "validator-result.json", {
        "schema_version": VALIDATOR_SCHEMA,
        "case_id": case["case_id"],
        "capability": case["capability"],
        "infrastructure_valid": False,
        "semantic_pass": False,
        "passed": False,
        "checks": [],
    })
    _write_json(run_dir / "environment-fingerprint.json", {
        "schema_version": "bench.hermes-full-matrix-environment.v1",
        "candidate": candidate,
        "runtime_alias": alias,
        "infrastructure_error": {
            "type": type(error).__name__,
            "detail": str(error),
        },
    })
    _write_json(run_dir / "usage.json", {
        "provider": None,
        "model": alias.get("name") if alias else None,
        "completed": False,
        "failed": True,
        "api_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    })
    _write_run_manifest(run_dir)
    return {
        "schema_version": RUN_SCHEMA,
        "candidate_id": candidate["candidate_id"],
        "candidate_sequence": candidate["sequence"],
        "case_id": case["case_id"],
        "capability": case["capability"],
        "repetition": repetition,
        "runtime_alias": alias,
        "candidate_result_status": "invalid_infrastructure",
        "infrastructure_valid": False,
        "semantic_pass": False,
        "infrastructure_error": {
            "type": type(error).__name__,
            "detail": str(error),
        },
        "artifact_path": run_dir.relative_to(DEFAULT_ARTIFACTS).as_posix()
        if DEFAULT_ARTIFACTS in run_dir.parents else run_dir.as_posix(),
    }


def _run_once(
    *,
    candidate: dict[str, Any],
    alias: dict[str, Any],
    case: dict[str, Any],
    repetition: int,
    hermes_repo: Path,
    hermes_prefix: list[str],
    hermes_identity: dict[str, Any],
    repository: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    runtime_base = Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir())
    runtime_root = Path(tempfile.mkdtemp(
        prefix=f"bench2-{candidate['candidate_id']}-{case['case_id']}-r{repetition}-",
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
    usage: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    output_error: str | None = None
    tool_records: list[dict[str, Any]] = []
    trace_error: str | None = None
    runtime_model: dict[str, Any] | None = None
    residency_class: str | None = None
    residency_ratio: float | None = None
    gpu_before: dict[str, Any] = {"ok": False, "gpus": []}
    gpu_loaded: dict[str, Any] = {"ok": False, "gpus": []}
    cleanup_before: list[dict[str, Any]] = []
    cleanup_after: list[dict[str, Any]] = []
    removed_credentials: list[str] = []
    infrastructure_error: dict[str, str] | None = None
    validator: dict[str, Any] | None = None
    try:
        cleanup_before = canary.stop_all_running_models()
        gpu_before = canary.residency.gpu_snapshot()
        if gpu_before.get("ok") is not True:
            raise HermesBatchError("GPU snapshot failed before run")
        home = runtime_root / "hermes-home"
        workdir = runtime_root / "workdir"
        workdir.mkdir(parents=True)
        trace_path = runtime_root / "tool-trace.jsonl"
        usage_path = runtime_root / "usage.json"
        canary._write_isolated_home(home, workdir, alias["name"])
        env, removed_credentials = canary.sanitized_subprocess_environment(
            hermes_home=home,
            tool_trace=trace_path,
            hermes_repo=hermes_repo,
            runtime_model=alias["name"],
        )
        command = [
            *hermes_prefix,
            "--model", alias["name"],
            "--provider", "custom",
            "--toolsets", "bench2_fixture",
            "--ignore-rules",
            "--usage-file", str(usage_path),
            "-z", canary._build_prompt(case),
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
        output, output_error = canary._parse_output(stdout)
        _write_json(output_dir / "extracted-output.json", {
            "schema_version": "bench.hermes-canary-extracted-output.v1",
            "value": output,
            "error": output_error,
        })
        tool_records, trace_error = canary._read_tool_trace(trace_path)
        with (output_dir / "tool-trace.jsonl").open(
            "w", encoding="utf-8", newline="\n"
        ) as handle:
            for record in tool_records:
                handle.write(json.dumps(
                    record, sort_keys=True, separators=(",", ":")
                ) + "\n")
        if usage_path.is_file():
            shutil.copyfile(usage_path, output_dir / "usage.json")
        usage, usage_checks = canary._validate_usage(
            output_dir / "usage.json", alias["name"]
        )
        runtime_model = canary.residency._find_single_running_model({
            "name": alias["name"],
            "digest": alias["digest"],
        })
        residency_class, residency_ratio = canary.residency.classify_residency(
            runtime_model.get("size"), runtime_model.get("size_vram")
        )
        gpu_loaded = canary.residency.gpu_snapshot()
        if gpu_loaded.get("ok") is not True:
            raise HermesBatchError("GPU snapshot failed after run")
        validator = _semantic_validator(
            case=case,
            process=process,
            output=output,
            output_error=output_error,
            tool_records=tool_records,
            trace_error=trace_error,
            usage_checks=usage_checks,
            usage=usage,
            runtime_model=runtime_model,
            residency_class=residency_class,
            residency_ratio=residency_ratio,
            stderr_text=stderr,
        )
    except Exception as exc:
        infrastructure_error = {"type": type(exc).__name__, "detail": str(exc)}
    finally:
        try:
            cleanup_after = canary.stop_all_running_models()
            if any(item.get("verified_absent") is not True for item in cleanup_after):
                raise HermesBatchError("run cleanup attestation failed")
        except Exception as exc:
            detail = f"cleanup failed: {type(exc).__name__}: {exc}"
            if infrastructure_error is None:
                infrastructure_error = {"type": type(exc).__name__, "detail": detail}
            else:
                infrastructure_error["detail"] += "; " + detail
        shutil.rmtree(runtime_root, ignore_errors=True)

    if not (output_dir / "raw-output.txt").exists():
        (output_dir / "raw-output.txt").write_text(
            str(process.get("stdout") or ""), encoding="utf-8"
        )
    if not (output_dir / "stderr.txt").exists():
        (output_dir / "stderr.txt").write_text(
            str(process.get("stderr") or ""), encoding="utf-8"
        )
    if not (output_dir / "tool-trace.jsonl").exists():
        (output_dir / "tool-trace.jsonl").write_text("", encoding="utf-8")
    if not (output_dir / "usage.json").exists():
        _write_json(output_dir / "usage.json", {
            "provider": None,
            "model": alias["name"],
            "completed": False,
            "failed": True,
            "api_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        })
    if validator is None:
        validator = {
            "schema_version": VALIDATOR_SCHEMA,
            "case_id": case["case_id"],
            "capability": case["capability"],
            "infrastructure_valid": False,
            "semantic_pass": False,
            "passed": False,
            "checks": [],
        }
    if infrastructure_error is not None:
        validator["infrastructure_valid"] = False
        validator["passed"] = False
    _write_json(output_dir / "validator-result.json", validator)

    events: list[dict[str, Any]] = []
    for record in tool_records:
        events.append({
            "index": len(events) + 1,
            "action_id": "call_tool",
            "details": {
                "name": record.get("tool_name"),
                "arguments": record.get("arguments"),
                "result": record.get("result"),
            },
        })
    if output is not None:
        events.append({
            "index": len(events) + 1,
            "action_id": "return_final",
            "details": {"final": output.get("final")},
        })
    if process.get("returncode") == 0:
        events.append({
            "index": len(events) + 1,
            "action_id": "stop",
            "details": {},
        })
    _write_json(output_dir / "trace.json", {
        "schema_version": "bench.trace.v1",
        "case_id": case["case_id"],
        "events": events,
    })
    environment = {
        "schema_version": "bench.hermes-full-matrix-environment.v1",
        "created_at_utc": _utc_now(),
        "repository": repository,
        "hermes": hermes_identity,
        "candidate": candidate,
        "runtime_alias": alias,
        "credential_environment_names_removed": removed_credentials,
        "gpu_before": gpu_before,
        "gpu_loaded": gpu_loaded,
        "runtime_model": runtime_model,
        "residency_class": residency_class,
        "residency_ratio": residency_ratio,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "infrastructure_error": infrastructure_error,
    }
    _write_json(output_dir / "environment-fingerprint.json", environment)
    _write_run_manifest(output_dir)
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
        "repetition": repetition,
        "runtime_alias": {
            key: alias.get(key)
            for key in (
                "name", "digest", "source_candidate_id",
                "source_candidate_name", "source_candidate_digest",
                "modelfile_sha256",
            )
        },
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
        "usage": usage,
        "tool_trace_count": len(tool_records),
        "runtime_context_length": runtime_model.get("context_length")
        if runtime_model else None,
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
    plan, marker, candidates, case_records = execution.validate_execution(
        require_enabled=True
    )
    batch_index = batch_index_from_environment()
    selected, selection = execution.select_batch(candidates, batch_index)
    cases = [
        load_case_file(ROOT / record["path"])
        for record in case_records
    ]
    repository = canary.repository_snapshot()
    hermes_repo = canary._discover_hermes_repo()
    bootstrap_root = Path(tempfile.mkdtemp(
        prefix="bench2-hermes-batch-bootstrap-",
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
    hermes_identity = canary._verify_hermes_identity(
        prefix, hermes_repo, bootstrap_env
    )
    shutil.rmtree(bootstrap_root, ignore_errors=True)

    results: list[dict[str, Any]] = []
    aliases: list[dict[str, Any]] = []
    batch_runtime_root = Path(tempfile.mkdtemp(
        prefix=f"bench2-hermes-b{batch_index}-",
        dir=Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()),
    ))
    try:
        for candidate in selected:
            expected_alias_name = _alias_name(batch_index, int(candidate["sequence"]))
            installed: dict[str, Any] | None = None
            alias: dict[str, Any] | None = None
            candidate_results: list[dict[str, Any]] = []
            alias_error: Exception | None = None
            alias_cleanup: dict[str, Any] = {
                "attempted": False,
                "verified_absent": False,
            }
            try:
                installed = _installed_candidate(candidate)
                alias = _create_alias(
                    candidate,
                    batch_index=batch_index,
                    runtime_root=batch_runtime_root,
                )
                alias["installed_source_size"] = installed.get("size") if installed else None
                for case in cases:
                    for repetition in range(1, 4):
                        run_dir = (
                            output_dir / "runs" / candidate["candidate_id"]
                            / case["case_id"] / f"r{repetition}"
                        )
                        result = _run_once(
                            candidate=candidate,
                            alias=alias,
                            case=case,
                            repetition=repetition,
                            hermes_repo=hermes_repo,
                            hermes_prefix=prefix,
                            hermes_identity=hermes_identity,
                            repository=repository,
                            output_dir=run_dir,
                        )
                        candidate_results.append(result)
            except Exception as exc:
                alias_error = exc
                for case in cases:
                    for repetition in range(1, 4):
                        run_dir = (
                            output_dir / "runs" / candidate["candidate_id"]
                            / case["case_id"] / f"r{repetition}"
                        )
                        if any(
                            item["case_id"] == case["case_id"]
                            and item["repetition"] == repetition
                            for item in candidate_results
                        ):
                            continue
                        candidate_results.append(_minimal_invalid_run(
                            run_dir,
                            candidate=candidate,
                            case=case,
                            repetition=repetition,
                            alias=alias,
                            error=exc,
                        ))
            finally:
                try:
                    canary.stop_all_running_models()
                    alias_cleanup = {
                        "attempted": True,
                        **canary._remove_model_if_present(expected_alias_name),
                    }
                    if alias_cleanup.get("verified_absent") is not True:
                        raise HermesBatchError(
                            f"alias cleanup failed for {candidate['candidate_id']}"
                        )
                except Exception as exc:
                    alias_error = alias_error or exc
                    alias_cleanup = {
                        **alias_cleanup,
                        "verified_absent": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    }

            if alias_error is not None or alias_cleanup.get("verified_absent") is not True:
                detail = (
                    f"{type(alias_error).__name__}: {alias_error}"
                    if alias_error is not None
                    else "alias cleanup failed"
                )
                for result in candidate_results:
                    result["candidate_result_status"] = "invalid_infrastructure"
                    result["infrastructure_valid"] = False
                    result["semantic_pass"] = False
                    error_record = {
                        "type": "HermesBatchError",
                        "detail": detail,
                    }
                    result["infrastructure_error"] = error_record
                    result["cleanup_verified"] = False
                    run_dir = output_dir / result["artifact_path"]
                    validator_path = run_dir / "validator-result.json"
                    if validator_path.is_file():
                        validator = _load_json(validator_path)
                        validator["infrastructure_valid"] = False
                        validator["semantic_pass"] = False
                        validator["passed"] = False
                        _write_json(validator_path, validator)
                    environment_path = run_dir / "environment-fingerprint.json"
                    if environment_path.is_file():
                        environment = _load_json(environment_path)
                        environment["infrastructure_error"] = error_record
                        environment["candidate_alias_cleanup"] = alias_cleanup
                        _write_json(environment_path, environment)
                    _write_run_manifest(run_dir)
            aliases.append({
                "candidate_id": candidate["candidate_id"],
                "expected_alias_name": expected_alias_name,
                "runtime_alias": alias,
                "cleanup": alias_cleanup,
                "setup_error": (
                    {"type": type(alias_error).__name__, "detail": str(alias_error)}
                    if alias_error is not None else None
                ),
            })
            results.extend(candidate_results)
    finally:
        final_cleanup = canary.stop_all_running_models()
        shutil.rmtree(batch_runtime_root, ignore_errors=True)

    counts = {
        "passed": sum(item["candidate_result_status"] == "passed" for item in results),
        "failed": sum(item["candidate_result_status"] == "failed" for item in results),
        "invalid_infrastructure": sum(
            item["candidate_result_status"] == "invalid_infrastructure"
            for item in results
        ),
        "total": len(results),
    }
    report = {
        "schema_version": REPORT_SCHEMA,
        "created_at_utc": _utc_now(),
        "source": {
            "plan_sha256": execution.plan_validator.EXPECTED_PLAN_SHA256,
            "canary_closeout_sha256": execution.EXPECTED_CLOSEOUT_SHA256,
            "candidate_registry_sha256": execution.plan_validator.EXPECTED_REGISTRY_SHA256,
            "h4_summary_sha256": execution.plan_validator.EXPECTED_H4_SUMMARY_SHA256,
            "hermes_commit_sha": execution.plan_validator.EXPECTED_HERMES_COMMIT,
            "hermes_version": execution.plan_validator.EXPECTED_HERMES_VERSION,
        },
        "workflow": {
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "sha": os.environ.get("GITHUB_SHA"),
            "ref": os.environ.get("GITHUB_REF"),
        },
        "repository": repository,
        "batch_index": batch_index,
        "selection": selection,
        "candidate_ids": [item["candidate_id"] for item in selected],
        "case_ids": [item["case_id"] for item in cases],
        "repetitions": 3,
        "expected_runs": execution.EXPECTED_RUNS_PER_BATCH,
        "aliases": aliases,
        "results": sorted(
            results,
            key=lambda item: (
                item["candidate_sequence"],
                item["case_id"],
                item["repetition"],
            ),
        ),
        "counts": counts,
        "final_cleanup": final_cleanup,
        "full_matrix_semantic_admission_gate": "not_applicable",
        "global_composite_score_allowed": False,
    }
    _write_json(output_dir / "report.json", report)
    _batch_manifest(output_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _verify_manifest(output_dir: Path) -> None:
    manifest = _load_json(output_dir / "manifest.json")
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise HermesBatchError("batch manifest schema is invalid")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise HermesBatchError("batch manifest inventory is missing")
    observed = {
        path.relative_to(output_dir).as_posix()
        for path in output_dir.rglob("*")
        if path.is_file() and path != output_dir / "manifest.json"
    }
    if set(artifacts) != observed:
        raise HermesBatchError("batch manifest file set drifted")
    for name, record in artifacts.items():
        path = output_dir / name
        if not isinstance(record, dict):
            raise HermesBatchError(f"batch manifest record invalid: {name}")
        if record.get("sha256") != _sha256(path):
            raise HermesBatchError(f"batch artifact digest mismatch: {name}")
        if record.get("size_bytes") != path.stat().st_size:
            raise HermesBatchError(f"batch artifact size mismatch: {name}")



def _verify_run_manifest(run_dir: Path) -> None:
    manifest = _load_json(run_dir / "manifest.json")
    if manifest.get("schema_version") != canary.MANIFEST_SCHEMA:
        raise HermesBatchError(f"run manifest schema is invalid: {run_dir}")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise HermesBatchError(f"run manifest inventory is missing: {run_dir}")
    observed = {
        path.relative_to(run_dir).as_posix()
        for path in run_dir.rglob("*")
        if path.is_file() and path != run_dir / "manifest.json"
    }
    if set(artifacts) != observed:
        raise HermesBatchError(f"run manifest file set drifted: {run_dir}")
    for name, record in artifacts.items():
        path = run_dir / name
        if not isinstance(record, dict):
            raise HermesBatchError(f"run manifest record invalid: {run_dir}/{name}")
        if record.get("sha256") != _sha256(path):
            raise HermesBatchError(f"run artifact digest mismatch: {run_dir}/{name}")
        if record.get("size_bytes") != path.stat().st_size:
            raise HermesBatchError(f"run artifact size mismatch: {run_dir}/{name}")


def _verify_result_artifacts(
    output_dir: Path,
    result: dict[str, Any],
    candidate: dict[str, Any],
    case: dict[str, Any],
) -> None:
    repetition = result.get("repetition")
    expected_relative = (
        Path("runs") / candidate["candidate_id"] / case["case_id"] / f"r{repetition}"
    ).as_posix()
    if result.get("artifact_path") != expected_relative:
        raise HermesBatchError("run artifact path binding drifted")
    run_dir = output_dir / expected_relative
    _verify_run_manifest(run_dir)
    validator = _load_json(run_dir / "validator-result.json")
    environment = _load_json(run_dir / "environment-fingerprint.json")
    usage = _load_json(run_dir / "usage.json")
    if validator.get("schema_version") != VALIDATOR_SCHEMA:
        raise HermesBatchError("run validator schema drifted")
    if validator.get("case_id") != case["case_id"] or validator.get("capability") != case["capability"]:
        raise HermesBatchError("run validator case binding drifted")
    if environment.get("candidate", {}).get("candidate_id") != candidate["candidate_id"]:
        raise HermesBatchError("run environment candidate binding drifted")
    if environment.get("candidate", {}).get("digest") != candidate["digest"]:
        raise HermesBatchError("run environment candidate digest drifted")
    infrastructure_valid = result.get("infrastructure_valid") is True
    semantic_pass = result.get("semantic_pass") is True
    expected_status = (
        "passed" if infrastructure_valid and semantic_pass
        else "failed" if infrastructure_valid
        else "invalid_infrastructure"
    )
    if result.get("candidate_result_status") != expected_status:
        raise HermesBatchError("run result status is inconsistent")
    if validator.get("infrastructure_valid") is not infrastructure_valid:
        raise HermesBatchError("run infrastructure classification drifted")
    if validator.get("semantic_pass") is not semantic_pass:
        raise HermesBatchError("run semantic classification drifted")
    if validator.get("passed") is not (infrastructure_valid and semantic_pass):
        raise HermesBatchError("run pass classification drifted")
    alias = result.get("runtime_alias")
    if infrastructure_valid:
        if not isinstance(alias, dict):
  raise HermesBatchError("valid run alias evidence is missing")
        runtime_model = environment.get("runtime_model")
        if not isinstance(runtime_model, dict):
  raise HermesBatchError("valid run runtime model evidence is missing")
        if runtime_model.get("name") != alias.get("name") or runtime_model.get("digest") != alias.get("digest"):
  raise HermesBatchError("valid run runtime alias identity drifted")
        if runtime_model.get("context_length") != 65536:
  raise HermesBatchError("valid run context is not 65536")
        if environment.get("residency_class") != "full_vram":
  raise HermesBatchError("valid run is not fully resident in VRAM")
        if environment.get("infrastructure_error") is not None:
  raise HermesBatchError("valid run carries an infrastructure error")
        if usage.get("provider") != "custom" or usage.get("model") != alias.get("name"):
  raise HermesBatchError("valid run usage binding drifted")
        if result.get("cleanup_verified") is not True:
  raise HermesBatchError("valid run cleanup is not verified")
    else:
        if not isinstance(result.get("infrastructure_error"), dict):
  raise HermesBatchError("invalid run infrastructure error is missing")
        if not isinstance(environment.get("infrastructure_error"), dict):
  raise HermesBatchError("invalid run environment error is missing")


def enforce(output_dir: Path = DEFAULT_ARTIFACTS) -> int:
    try:
        plan, marker, candidates, cases = execution.validate_execution(
            require_enabled=True
        )
        repository = canary.repository_snapshot()
        _verify_manifest(output_dir)
        report = _load_json(output_dir / "report.json")
        if report.get("schema_version") != REPORT_SCHEMA:
            raise HermesBatchError("batch report schema is invalid")
        expected_source = {
            "plan_sha256": execution.plan_validator.EXPECTED_PLAN_SHA256,
            "canary_closeout_sha256": execution.EXPECTED_CLOSEOUT_SHA256,
            "candidate_registry_sha256": execution.plan_validator.EXPECTED_REGISTRY_SHA256,
            "h4_summary_sha256": execution.plan_validator.EXPECTED_H4_SUMMARY_SHA256,
            "hermes_commit_sha": execution.plan_validator.EXPECTED_HERMES_COMMIT,
            "hermes_version": execution.plan_validator.EXPECTED_HERMES_VERSION,
        }
        if report.get("source") != expected_source:
            raise HermesBatchError("batch source binding drifted")
        expected_workflow = {
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "sha": os.environ.get("GITHUB_SHA"),
            "ref": os.environ.get("GITHUB_REF"),
        }
        if report.get("workflow") != expected_workflow:
            raise HermesBatchError("batch workflow binding drifted")
        if report.get("repository") != repository:
            raise HermesBatchError("batch repository binding drifted")
        batch_index = batch_index_from_environment()
        selected, selection = execution.select_batch(candidates, batch_index)
        if report.get("batch_index") != batch_index or report.get("selection") != selection:
            raise HermesBatchError("batch selection binding drifted")
        if report.get("candidate_ids") != [
            item["candidate_id"] for item in selected
        ]:
            raise HermesBatchError("batch candidate inventory drifted")
        if report.get("case_ids") != [item["case_id"] for item in cases]:
            raise HermesBatchError("batch case inventory drifted")
        if report.get("expected_runs") != execution.EXPECTED_RUNS_PER_BATCH:
            raise HermesBatchError("batch expected-run count drifted")
        results = report.get("results")
        if not isinstance(results, list) or len(results) != execution.EXPECTED_RUNS_PER_BATCH:
            raise HermesBatchError("batch result inventory is incomplete")
        expected_keys = {
            (candidate["candidate_id"], case["case_id"], repetition)
            for candidate in selected
            for case in cases
            for repetition in range(1, 4)
        }
        observed_keys = {
            (item.get("candidate_id"), item.get("case_id"), item.get("repetition"))
            for item in results if isinstance(item, dict)
        }
        if observed_keys != expected_keys:
            raise HermesBatchError("batch candidate/case/repetition coverage drifted")
        candidate_by_id = {item["candidate_id"]: item for item in selected}
        case_by_id = {item["case_id"]: item for item in cases}
        for item in results:
            if not isinstance(item, dict):
                raise HermesBatchError("batch result record is not an object")
            candidate = candidate_by_id.get(item.get("candidate_id"))
            case = case_by_id.get(item.get("case_id"))
            if candidate is None or case is None:
                raise HermesBatchError("batch result inventory contains an unknown binding")
            _verify_result_artifacts(output_dir, item, candidate, case)
        allowed_statuses = {"passed", "failed", "invalid_infrastructure"}
        if any(item.get("candidate_result_status") not in allowed_statuses for item in results):
            raise HermesBatchError("batch contains an unknown result status")
        aliases = report.get("aliases")
        if not isinstance(aliases, list) or len(aliases) != 2:
            raise HermesBatchError("batch alias evidence is incomplete")
        alias_by_candidate = {item.get("candidate_id"): item for item in aliases if isinstance(item, dict)}
        if set(alias_by_candidate) != set(candidate_by_id):
            raise HermesBatchError("batch alias candidate inventory drifted")
        for candidate_id, candidate in candidate_by_id.items():
            item = alias_by_candidate[candidate_id]
            expected_alias = _alias_name(batch_index, int(candidate["sequence"]))
            if item.get("expected_alias_name") != expected_alias:
                raise HermesBatchError("batch expected alias name drifted")
            if item.get("cleanup", {}).get("verified_absent") is not True:
                raise HermesBatchError("batch alias cleanup is invalid")
            runtime_alias = item.get("runtime_alias")
            if runtime_alias is not None:
                if runtime_alias.get("name") != expected_alias:
                    raise HermesBatchError("batch runtime alias name drifted")
                if runtime_alias.get("source_candidate_id") != candidate_id:
                    raise HermesBatchError("batch runtime alias source id drifted")
                if runtime_alias.get("source_candidate_digest") != candidate["digest"]:
                    raise HermesBatchError("batch runtime alias source digest drifted")
        if any(item.get("verified_absent") is not True for item in report.get("final_cleanup", [])):
            raise HermesBatchError("batch final model cleanup is invalid")
        counts = report.get("counts")
        recomputed = {
            "passed": sum(item["candidate_result_status"] == "passed" for item in results),
            "failed": sum(item["candidate_result_status"] == "failed" for item in results),
            "invalid_infrastructure": sum(
                item["candidate_result_status"] == "invalid_infrastructure"
                for item in results
            ),
            "total": len(results),
        }
        if counts != recomputed:
            raise HermesBatchError("batch result counts drifted")
        if report.get("global_composite_score_allowed") is not False:
            raise HermesBatchError("batch enabled a global composite score")
        if recomputed["invalid_infrastructure"]:
            print(
                f"BENCH-2 batch {batch_index} captured "
                f"{recomputed['invalid_infrastructure']} invalid infrastructure results",
                file=sys.stderr,
            )
            return 2
    except (
        HermesBatchError,
        execution.HermesExecutionError,
        execution.closeout.CanaryCloseoutError,
        execution.closeout.canary.CanaryPlanError,
        execution.closeout.canary.bench2.HermesPlanError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(
            f"invalid BENCH-2 Hermes batch evidence: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    print(
        f"BENCH-2 Hermes batch {batch_index} evidence valid; "
        f"passed={recomputed['passed']} failed={recomputed['failed']}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture or enforce one BENCH-2 Hermes batch."
    )
    parser.add_argument("mode", choices=("capture", "enforce"))
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACTS)
    args = parser.parse_args()
    return capture(args.artifact_dir) if args.mode == "capture" else enforce(args.artifact_dir)


if __name__ == "__main__":
    raise SystemExit(main())

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
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from scripts import bench2r_hermes_runtime as optimization
from scripts import run_bench2_hermes_canary as canary
from scripts import run_bench2r_hermes_s1 as s1
from scripts import validate_bench2r_hermes_s2 as execution
from scripts.bench2r_deterministic_finalizer import finalize
from scripts.bench2r_loopback_wire_proxy import LoopbackWireProxy

DEFAULT_ARTIFACTS = ROOT / "artifacts/bench2r-hermes-s2"
BATCH_INDEX_ENV = "BENCH2R_HERMES_S2_BATCH_INDEX"
REPORT_SCHEMA = "bench.hermes-s2-batch-report.v1"
RUN_SCHEMA = "bench.hermes-s2-run.v1"
VALIDATOR_SCHEMA = "bench.hermes-s2-validator.v1"
MANIFEST_SCHEMA = "bench.hermes-s2-batch-manifest.v1"
ARM = "profile_plus_skill_with_deterministic_finalizer"
WORKER_ARM = "profile_plus_skill"
TOOLSET = "bench2r_s2_fixture"
PLUGIN_NAME = "bench2r-s2-fixture"


class HermesS2Error(RuntimeError):
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
        raise HermesS2Error(f"cannot read {path}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise HermesS2Error(f"{path} must contain an object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def batch_index_from_environment() -> int:
    raw = os.environ.get(BATCH_INDEX_ENV, "")
    if not re.fullmatch(r"[0-2]", raw):
        raise HermesS2Error(f"{BATCH_INDEX_ENV} is missing or invalid")
    return int(raw)


def _alias_name(batch_index: int, repetition: int) -> str:
    run_id = re.sub(r"[^0-9]", "", os.environ.get("GITHUB_RUN_ID", "")) or "local"
    attempt = re.sub(r"[^0-9]", "", os.environ.get("GITHUB_RUN_ATTEMPT", "")) or "0"
    return f"bench2r-s2-b{batch_index}-r{repetition}-64k:{run_id}-{attempt}"


def _create_alias(
    candidate: dict[str, Any],
    profile: dict[str, Any],
    *,
    batch_index: int,
    repetition: int,
    runtime_root: Path,
    seed: int,
) -> dict[str, Any]:
    alias = _alias_name(batch_index, repetition)
    stale = canary._remove_model_if_present(alias)
    if stale.get("verified_absent") is not True:
        raise HermesS2Error(f"stale alias cleanup failed for {candidate['candidate_id']}")
    modelfile = runtime_root / f"{candidate['candidate_id']}-r{repetition}.Modelfile"
    modelfile.write_text(
        optimization.build_modelfile(profile, seed=seed),
        encoding="utf-8",
        newline="\n",
    )
    create = canary._run(["ollama", "create", alias, "-f", str(modelfile)], timeout=600)
    if create.get("ok") is not True:
        detail = str(create.get("stderr") or create.get("stdout") or "")[-500:]
        raise HermesS2Error(f"alias creation failed for {candidate['candidate_id']}: {detail}")
    parameters = canary._run(["ollama", "show", alias, "--parameters"], timeout=60)
    parameter_text = str(parameters.get("stdout") or "")
    if parameters.get("ok") is not True:
        raise HermesS2Error(f"cannot read alias parameters for {candidate['candidate_id']}")
    attestation = s1._attest_alias_parameters(profile, seed=seed, parameter_text=parameter_text)
    if attestation.get("passed") is not True:
        raise HermesS2Error(f"alias parameters drifted: {attestation.get('mismatches')}")
    matches = [item for item in canary.residency.list_installed_models() if item.get("name") == alias]
    if len(matches) != 1:
        raise HermesS2Error("S2 runtime alias is missing")
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
        "seed": seed,
        "stale_cleanup": stale,
    }


def _render_config(
    *,
    profile: dict[str, Any],
    case: dict[str, Any],
    runtime_model: str,
    workdir: Path,
    base_url: str,
) -> str:
    max_output = profile["max_output_tokens"]
    max_turns = optimization.case_max_turns(case)
    quote = optimization._yaml_quote
    return "\n".join([
        "model:",
        f"  default: {quote(runtime_model)}",
        "  provider: 'custom'",
        "  api_key: 'local-only-not-secret'",
        f"  base_url: {quote(base_url)}",
        "  api_mode: 'chat_completions'",
        "  context_length: 65536",
        "  ollama_num_ctx: 65536",
        f"  max_tokens: {max_output}",
        "fallback_providers: []",
        "plugins:",
        "  enabled:",
        f"    - '{PLUGIN_NAME}'",
        "terminal:",
        "  backend: 'local'",
        f"  cwd: {quote(str(workdir))}",
        "  home_mode: 'profile'",
        "  timeout: 60",
        "agent:",
        f"  max_turns: {max_turns}",
        "  save_trajectories: true",
        "display:",
        "  interface: 'cli'",
        "",
    ])


def _write_home(
    home: Path,
    workdir: Path,
    *,
    profile: dict[str, Any],
    case: dict[str, Any],
    runtime_model: str,
    base_url: str,
) -> None:
    plugin_source = ROOT / "fixtures/bench-2r/s2-hermes-plugin/bench2r-s2-fixture"
    plugin_target = home / "plugins" / PLUGIN_NAME
    plugin_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(plugin_source, plugin_target)
    optimization.install_bounded_skill(home)
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text(
        _render_config(
            profile=profile,
            case=case,
            runtime_model=runtime_model,
            workdir=workdir,
            base_url=base_url,
        ),
        encoding="utf-8",
        newline="\n",
    )
    (home / ".env").write_text("\n", encoding="utf-8", newline="\n")


def _read_jsonl(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    if not path.is_file():
        return [], "missing"
    records: list[dict[str, Any]] = []
    try:
        for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not raw.strip():
                continue
            value = json.loads(raw)
            if not isinstance(value, dict):
                return records, f"line_{line_number}_not_object"
            records.append(value)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return records, type(exc).__name__
    return records, None


def _registry_observed(output_dir: Path, trajectory_files: list[str]) -> bool:
    text = "\n".join(
        (output_dir / name).read_text(encoding="utf-8", errors="replace")
        for name in trajectory_files
        if (output_dir / name).is_file()
    )
    return all(name in text for name in ("vault_fetch", "registry_read", "noise_probe"))


def _tool_sequence_exact(case: dict[str, Any], records: list[dict[str, Any]]) -> bool:
    expected = case.get("expected", {}).get("tool_sequence")
    if not isinstance(expected, list) or len(expected) != len(records):
        return False
    for expected_item, record in zip(expected, records, strict=True):
        if not isinstance(expected_item, dict):
            return False
        if record.get("tool_name") != expected_item.get("name"):
            return False
        if record.get("arguments") != expected_item.get("arguments"):
            return False
        result = record.get("result")
        if not isinstance(result, dict) or result.get("ok") is not True:
            return False
    return True


def _wire_checks(
    records: list[dict[str, Any]],
    *,
    alias_name: str,
    worker_result: dict[str, Any] | None,
) -> dict[str, Any]:
    chats = [item for item in records if str(item.get("path", "")).split("?", 1)[0].endswith("/chat/completions")]
    api_calls = worker_result.get("api_calls") if isinstance(worker_result, dict) else None
    registry_seen = False
    model_exact = True
    for item in chats:
        body = item.get("request", {}).get("json")
        if not isinstance(body, dict):
            model_exact = False
            continue
        if body.get("model") != alias_name:
            model_exact = False
        tools = body.get("tools")
        if isinstance(tools, list):
            names = {
                tool.get("function", {}).get("name")
                for tool in tools
                if isinstance(tool, dict)
            }
            registry_seen = registry_seen or {"vault_fetch", "registry_read", "noise_probe"} <= names
    return {
        "wire_trace_present": bool(records),
        "wire_chat_count_matches_worker": isinstance(api_calls, int) and len(chats) == api_calls,
        "wire_all_http_200": bool(chats) and all(item.get("response", {}).get("status") == 200 for item in chats),
        "wire_model_exact": bool(chats) and model_exact,
        "wire_tool_registry_observed": registry_seen,
        "wire_chat_count": len(chats),
    }


def _validator(
    *,
    case: dict[str, Any],
    process: dict[str, Any],
    raw_output: dict[str, Any] | None,
    output_error: str | None,
    tool_records: list[dict[str, Any]],
    tool_trace_error: str | None,
    wire_records: list[dict[str, Any]],
    wire_error: str | None,
    worker_result: dict[str, Any] | None,
    worker_error: str | None,
    usage_checks: list[dict[str, Any]],
    runtime_model: dict[str, Any] | None,
    residency_class: str | None,
    residency_ratio: float | None,
    trajectory_files: list[str],
    registry_observed: bool,
    alias: dict[str, Any],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    add("worker_exit_zero", process.get("returncode") == 0 and process.get("timed_out") is False, str(process.get("returncode")))
    add("worker_result_valid", worker_error is None, str(worker_error))
    add("skill_expanded", worker_result is not None and worker_result.get("skill_expanded") is True, str(worker_result.get("skill_expanded") if worker_result else None))
    add("worker_toolset_exact", worker_result is not None and worker_result.get("toolset") == TOOLSET, str(worker_result.get("toolset") if worker_result else None))
    add("native_trajectory_present", bool(trajectory_files), str(trajectory_files))
    add("trajectory_registry_observed", registry_observed, "held-out tools must appear in trajectory")
    add("tool_trace_valid", tool_trace_error is None, str(tool_trace_error))
    add("wire_trace_valid", wire_error is None, str(wire_error))
    add("runtime_model_observed", runtime_model is not None, str(runtime_model is not None))
    add("runtime_context_65536", runtime_model is not None and runtime_model.get("context_length") == 65536, str(runtime_model.get("context_length") if runtime_model else None))
    add("runtime_full_vram", residency_class == "full_vram" and residency_ratio is not None and residency_ratio >= 0.98, f"{residency_class}:{residency_ratio}")
    add("alias_profile_attested", alias.get("parameter_attestation", {}).get("passed") is True, str(alias.get("parameter_attestation", {}).get("mismatches")))
    checks.extend(usage_checks)

    wire = _wire_checks(wire_records, alias_name=alias["name"], worker_result=worker_result)
    for key in (
        "wire_trace_present",
        "wire_chat_count_matches_worker",
        "wire_all_http_200",
        "wire_model_exact",
        "wire_tool_registry_observed",
    ):
        add(key, bool(wire[key]), f"chat_count={wire['wire_chat_count']}")

    expected_output = case.get("expected", {}).get("output")
    add("raw_output_strict_json", output_error is None, str(output_error))
    add("raw_output_exact", raw_output == expected_output, f"observed={raw_output!r}")
    add("tool_sequence_exact", _tool_sequence_exact(case, tool_records), f"records={tool_records!r}")
    limits = case.get("limits", {})
    api_calls = worker_result.get("api_calls") if worker_result else None
    max_calls = limits.get("max_model_calls")
    add("model_call_budget_within_limit", isinstance(api_calls, int) and isinstance(max_calls, int) and 1 <= api_calls <= max_calls, f"{api_calls}/{max_calls}")
    add(
        "agent_completed_without_failure",
        worker_result is not None
        and worker_result.get("completed") is True
        and worker_result.get("failed") is False
        and worker_result.get("failure") is None,
        str(worker_result.get("failure") if worker_result else None),
    )
    add("turn_exit_reason_observed", isinstance(worker_result.get("turn_exit_reason") if worker_result else None, str), str(worker_result.get("turn_exit_reason") if worker_result else None))

    finalizer_result = finalize(
        case=case,
        raw_output=raw_output,
        tool_records=tool_records,
        worker_result=worker_result or {},
    )
    add("finalizer_accepted", finalizer_result.accepted, str(finalizer_result.rejection_reasons))
    add("finalized_output_exact", finalizer_result.normalized_output == expected_output, f"observed={finalizer_result.normalized_output!r}")

    infrastructure_names = {
        "worker_exit_zero", "worker_result_valid", "skill_expanded", "worker_toolset_exact",
        "native_trajectory_present", "trajectory_registry_observed", "tool_trace_valid",
        "wire_trace_valid", "runtime_model_observed", "runtime_context_65536",
        "runtime_full_vram", "alias_profile_attested", "usage_file_valid",
        "usage_provider_custom", "usage_model_exact", "usage_api_calls_nonnegative",
        "usage_api_calls_match_worker", "usage_input_tokens_nonnegative",
        "usage_output_tokens_nonnegative", "usage_total_tokens_nonnegative",
        "wire_trace_present", "wire_chat_count_matches_worker", "wire_all_http_200",
        "wire_model_exact", "wire_tool_registry_observed",
    }
    orchestration_names = {
        "tool_sequence_exact", "model_call_budget_within_limit",
        "agent_completed_without_failure", "turn_exit_reason_observed",
    }
    final_names = {"finalizer_accepted", "finalized_output_exact"}
    raw_names = {"raw_output_strict_json", "raw_output_exact"}
    observed = {item["check"] for item in checks}

    def passed(names: set[str]) -> bool:
        return names <= observed and all(item["passed"] for item in checks if item["check"] in names)

    infrastructure_valid = passed(infrastructure_names)
    raw_orchestration_pass = passed(orchestration_names)
    finalized_output_pass = passed(final_names)
    raw_presentation_pass = passed(raw_names)
    admission_pass = infrastructure_valid and raw_orchestration_pass and finalized_output_pass
    return {
        "schema_version": VALIDATOR_SCHEMA,
        "case_id": case["case_id"],
        "capability": case["capability"],
        "infrastructure_valid": infrastructure_valid,
        "raw_orchestration_pass": raw_orchestration_pass,
        "raw_presentation_pass": raw_presentation_pass,
        "finalized_output_pass": finalized_output_pass,
        "admission_pass": admission_pass,
        "checks": checks,
        "finalizer": finalizer_result.to_dict(),
        "diagnostics": {"api_calls": api_calls, "wire_chat_calls": wire["wire_chat_count"]},
    }


def _run_once(
    *,
    candidate: dict[str, Any],
    profile: dict[str, Any],
    alias: dict[str, Any],
    case: dict[str, Any],
    repetition: int,
    seed: int,
    hermes_repo: Path,
    hermes_python: Path,
    hermes_identity: dict[str, Any],
    repository: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime_root = Path(tempfile.mkdtemp(
        prefix=f"bench2r-s2-{candidate['candidate_id']}-{case['case_id']}-r{repetition}-",
        dir=Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()),
    ))
    process: dict[str, Any] = {"returncode": None, "timed_out": False, "stdout": "", "stderr": "", "duration_seconds": 0.0}
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
    worker_result: dict[str, Any] | None = None
    worker_error: str | None = None
    raw_output: dict[str, Any] | None = None
    output_error: str | None = None
    tool_records: list[dict[str, Any]] = []
    tool_error: str | None = None
    wire_records: list[dict[str, Any]] = []
    wire_error: str | None = None
    trajectory_files: list[str] = []
    try:
        cleanup_before = canary.stop_all_running_models()
        gpu_before = canary.residency.gpu_snapshot()
        if gpu_before.get("ok") is not True:
            raise HermesS2Error("GPU snapshot failed before run")
        home = runtime_root / "hermes-home"
        workdir = runtime_root / "workdir"
        workdir.mkdir(parents=True)
        prompt_path = runtime_root / "prompt.txt"
        prompt_path.write_text(canary._build_prompt(case), encoding="utf-8", newline="\n")
        tool_trace_path = runtime_root / "tool-trace.jsonl"
        wire_trace_path = runtime_root / "wire-trace.jsonl"
        with LoopbackWireProxy(wire_trace_path) as proxy:
            _write_home(
                home,
                workdir,
                profile=profile,
                case=case,
                runtime_model=alias["name"],
                base_url=proxy.base_url,
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
                "--arm", WORKER_ARM,
                "--toolset", TOOLSET,
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
        worker_result, worker_error = s1._load_worker_result(output_dir / "worker-result.json")
        raw_output, output_error = canary._parse_output(stdout)
        _write_json(output_dir / "extracted-output.json", {"schema_version": "bench.hermes-s2-extracted-output.v1", "value": raw_output, "error": output_error})
        tool_records, tool_error = canary._read_tool_trace(tool_trace_path)
        with (output_dir / "tool-trace.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for record in tool_records:
                handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        shutil.copyfile(wire_trace_path, output_dir / "wire-trace.jsonl")
        wire_records, wire_error = _read_jsonl(output_dir / "wire-trace.jsonl")
        _, usage_checks = s1._validate_usage(
            output_dir / "usage.json",
            expected_model=alias["name"],
            worker_result=worker_result,
        )
        trajectory_files = s1._copy_native_trajectories(workdir, output_dir)
        registry_observed = _registry_observed(output_dir, trajectory_files)
        runtime_model = canary.residency._find_single_running_model({"name": alias["name"], "digest": alias["digest"]})
        residency_class, residency_ratio = canary.residency.classify_residency(runtime_model.get("size"), runtime_model.get("size_vram"))
        gpu_loaded = canary.residency.gpu_snapshot()
        if gpu_loaded.get("ok") is not True:
            raise HermesS2Error("GPU snapshot failed after run")
        validator = _validator(
            case=case,
            process=process,
            raw_output=raw_output,
            output_error=output_error,
            tool_records=tool_records,
            tool_trace_error=tool_error,
            wire_records=wire_records,
            wire_error=wire_error,
            worker_result=worker_result,
            worker_error=worker_error,
            usage_checks=usage_checks,
            runtime_model=runtime_model,
            residency_class=residency_class,
            residency_ratio=residency_ratio,
            trajectory_files=trajectory_files,
            registry_observed=registry_observed,
            alias=alias,
        )
    except Exception as exc:
        infrastructure_error = {"type": type(exc).__name__, "detail": str(exc)}
    finally:
        try:
            cleanup_after = canary.stop_all_running_models()
            if any(item.get("verified_absent") is not True for item in cleanup_after):
                raise HermesS2Error("run cleanup attestation failed")
        except Exception as exc:
            detail = f"cleanup failed: {type(exc).__name__}: {exc}"
            infrastructure_error = infrastructure_error or {"type": type(exc).__name__, "detail": detail}
        shutil.rmtree(runtime_root, ignore_errors=True)

    if validator is None:
        validator = {
            "schema_version": VALIDATOR_SCHEMA,
            "case_id": case["case_id"],
            "capability": case["capability"],
            "infrastructure_valid": False,
            "raw_orchestration_pass": False,
            "raw_presentation_pass": False,
            "finalized_output_pass": False,
            "admission_pass": False,
            "checks": [],
        }
    if infrastructure_error is not None:
        validator["infrastructure_valid"] = False
        validator["admission_pass"] = False
    _write_json(output_dir / "validator-result.json", validator)
    _write_json(output_dir / "environment-fingerprint.json", {
        "schema_version": "bench.hermes-s2-environment.v1",
        "created_at_utc": _utc_now(),
        "repository": repository,
        "hermes": hermes_identity,
        "candidate": candidate,
        "profile": profile,
        "seed": seed,
        "repetition": repetition,
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
    })
    canary._write_manifest(output_dir)
    infrastructure_valid = infrastructure_error is None and validator.get("infrastructure_valid") is True
    admission_pass = infrastructure_valid and validator.get("admission_pass") is True
    return {
        "schema_version": RUN_SCHEMA,
        "candidate_id": candidate["candidate_id"],
        "case_id": case["case_id"],
        "capability": case["capability"],
        "seed": seed,
        "repetition": repetition,
        "candidate_result_status": "passed" if admission_pass else "failed" if infrastructure_valid else "invalid_infrastructure",
        "infrastructure_valid": infrastructure_valid,
        "raw_orchestration_pass": validator.get("raw_orchestration_pass") is True,
        "raw_presentation_pass": validator.get("raw_presentation_pass") is True,
        "finalized_output_pass": validator.get("finalized_output_pass") is True,
        "admission_pass": admission_pass,
        "api_calls": worker_result.get("api_calls") if worker_result else None,
        "artifact_path": output_dir.relative_to(DEFAULT_ARTIFACTS).as_posix() if DEFAULT_ARTIFACTS in output_dir.parents else output_dir.as_posix(),
    }


def _batch_manifest(output_dir: Path) -> None:
    artifacts: dict[str, dict[str, Any]] = {}
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path == output_dir / "manifest.json":
            continue
        relative = path.relative_to(output_dir).as_posix()
        artifacts[relative] = {"sha256": _sha256(path), "size_bytes": path.stat().st_size}
    _write_json(output_dir / "manifest.json", {"schema_version": MANIFEST_SCHEMA, "created_at_utc": _utc_now(), "artifacts": artifacts})


def capture(output_dir: Path = DEFAULT_ARTIFACTS) -> int:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    plan, marker, candidates, case_records = execution.validate_execution(require_enabled=True)
    batch_index = batch_index_from_environment()
    candidate, selection = execution.select_batch(candidates, batch_index)
    cases = [_load_json(ROOT / record["path"]) for record in case_records]
    profiles = optimization.load_profiles()
    profile = next(item for item in profiles["candidate_profiles"] if item["candidate_id"] == candidate["candidate_id"])
    repository = canary.repository_snapshot()
    hermes_repo = canary._discover_hermes_repo()
    bootstrap_root = Path(tempfile.mkdtemp(prefix="bench2r-s2-bootstrap-", dir=Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir())))
    bootstrap_env, _ = canary.sanitized_subprocess_environment(
        hermes_home=bootstrap_root / "home",
        tool_trace=bootstrap_root / "trace.jsonl",
        hermes_repo=hermes_repo,
        runtime_model=candidate["model_tag"],
    )
    prefix = canary._hermes_command_prefix(hermes_repo)
    hermes_identity = canary._verify_hermes_identity(prefix, hermes_repo, bootstrap_env)
    hermes_python = s1._hermes_python(hermes_repo)
    shutil.rmtree(bootstrap_root, ignore_errors=True)

    runs: list[dict[str, Any]] = []
    for repetition, seed in enumerate(plan["seeds"], 1):
        alias_root = Path(tempfile.mkdtemp(prefix=f"bench2r-s2-alias-{candidate['candidate_id']}-r{repetition}-", dir=Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir())))
        alias: dict[str, Any] | None = None
        try:
            s1._installed_candidate(candidate)
            alias = _create_alias(candidate, profile, batch_index=batch_index, repetition=repetition, runtime_root=alias_root, seed=seed)
            for case in cases:
                run_dir = output_dir / "runs" / candidate["candidate_id"] / case["case_id"] / f"seed-{seed}"
                runs.append(_run_once(
                    candidate=candidate,
                    profile=profile,
                    alias=alias,
                    case=case,
                    repetition=repetition,
                    seed=seed,
                    hermes_repo=hermes_repo,
                    hermes_python=hermes_python,
                    hermes_identity=hermes_identity,
                    repository=repository,
                    output_dir=run_dir,
                ))
        except Exception as exc:
            for case in cases:
                run_dir = output_dir / "runs" / candidate["candidate_id"] / case["case_id"] / f"seed-{seed}"
                run_dir.mkdir(parents=True, exist_ok=True)
                _write_json(run_dir / "validator-result.json", {"schema_version": VALIDATOR_SCHEMA, "infrastructure_valid": False, "admission_pass": False, "checks": [], "error": f"{type(exc).__name__}: {exc}"})
                canary._write_manifest(run_dir)
                runs.append({
                    "schema_version": RUN_SCHEMA,
                    "candidate_id": candidate["candidate_id"],
                    "case_id": case["case_id"],
                    "seed": seed,
                    "repetition": repetition,
                    "candidate_result_status": "invalid_infrastructure",
                    "infrastructure_valid": False,
                    "raw_orchestration_pass": False,
                    "raw_presentation_pass": False,
                    "finalized_output_pass": False,
                    "admission_pass": False,
                    "artifact_path": run_dir.relative_to(DEFAULT_ARTIFACTS).as_posix() if DEFAULT_ARTIFACTS in run_dir.parents else run_dir.as_posix(),
                })
        finally:
            expected_alias = alias.get("name") if alias else _alias_name(batch_index, repetition)
            cleanup = canary._remove_model_if_present(expected_alias)
            if cleanup.get("verified_absent") is not True:
                raise HermesS2Error(f"alias cleanup failed for {candidate['candidate_id']}")
            shutil.rmtree(alias_root, ignore_errors=True)

    statuses: dict[str, int] = {}
    for run in runs:
        status = run["candidate_result_status"]
        statuses[status] = statuses.get(status, 0) + 1
    candidate_admitted = len(runs) == 12 and all(run.get("admission_pass") is True for run in runs)
    report = {
        "schema_version": REPORT_SCHEMA,
        "created_at_utc": _utc_now(),
        "plan": plan,
        "marker": marker,
        "selection": selection,
        "repository": repository,
        "hermes": hermes_identity,
        "candidate": candidate,
        "runs": runs,
        "counts": {"expected_runs": 12, "captured_runs": len(runs), "statuses": statuses},
        "decision": {
            "candidate_admitted": candidate_admitted,
            "automatic_production_promotion_allowed": False,
        },
    }
    _write_json(output_dir / "batch-report.json", report)
    _batch_manifest(output_dir)
    return 0


def enforce(output_dir: Path = DEFAULT_ARTIFACTS) -> int:
    report = _load_json(output_dir / "batch-report.json")
    manifest = _load_json(output_dir / "manifest.json")
    if report.get("schema_version") != REPORT_SCHEMA:
        raise HermesS2Error("S2 batch report schema is invalid")
    runs = report.get("runs")
    if not isinstance(runs, list) or len(runs) != 12:
        raise HermesS2Error("S2 batch run inventory is incomplete")
    if report.get("decision", {}).get("automatic_production_promotion_allowed") is not False:
        raise HermesS2Error("S2 cannot promote automatically")
    artifacts = manifest.get("artifacts")
    if manifest.get("schema_version") != MANIFEST_SCHEMA or not isinstance(artifacts, dict):
        raise HermesS2Error("S2 manifest is invalid")
    for relative, record in artifacts.items():
        path = output_dir / relative
        if not path.is_file() or record.get("sha256") != _sha256(path) or record.get("size_bytes") != path.stat().st_size:
            raise HermesS2Error(f"S2 manifest mismatch: {relative}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run BENCH-2R Hermes S2 batches.")
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

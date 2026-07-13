from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from scripts import probe_model_residency as residency
from scripts.probe_model_residency_v2 import stop_all_running_models
from scripts import validate_bench2_hermes_canary as contract
from bench.evaluator import load_case_file

DEFAULT_ARTIFACTS = ROOT / "artifacts/bench2-hermes-canary"
REPORT_SCHEMA = "bench.hermes-canary-report.v1"
MANIFEST_SCHEMA = "bench.hermes-canary-manifest.v1"
TRACE_SCHEMA = "bench.trace.v1"
VALIDATOR_SCHEMA = "bench.hermes-canary-validator-result.v1"
EXPECTED_ACTIONS = ["call_tool", "return_final", "stop"]
EXPECTED_TOOL = {
    "tool_name": "bench_lookup",
    "arguments": {"key": "alpha-7"},
    "result": {"key": "alpha-7", "ok": True, "value": "BRAVO-19"},
}
EXPECTED_FINAL = "BRAVO-19"
_CREDENTIAL_FRAGMENTS = (
    "API_KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTHORIZATION",
    "ACCESS_KEY", "PRIVATE_KEY",
)
_ALLOWED_ENV = {
    "APPDATA", "COMSPEC", "LOCALAPPDATA", "NUMBER_OF_PROCESSORS", "OS",
    "PATH", "PATHEXT", "PROCESSOR_ARCHITECTURE", "PROGRAMDATA",
    "PROGRAMFILES", "PROGRAMFILES(X86)", "PUBLIC", "SYSTEMDRIVE",
    "SYSTEMROOT", "TEMP", "TMP", "USERDOMAIN", "USERNAME", "USERPROFILE",
    "WINDIR",
}


class CanaryRuntimeError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _source_bytes(path: Path) -> bytes:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _source_sha256(path: Path) -> str:
    return hashlib.sha256(_source_bytes(path)).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicates)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CanaryRuntimeError(f"cannot read {path.name}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise CanaryRuntimeError(f"{path.name} must contain an object")
    return value


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "timed_out": True,
            "command": command,
            "returncode": None,
            "stdout": (exc.stdout or "") if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "") if isinstance(exc.stderr, str) else "",
            "duration_seconds": round(time.monotonic() - started, 3),
            "error": "TimeoutExpired",
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "ok": False,
            "timed_out": False,
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "duration_seconds": round(time.monotonic() - started, 3),
            "error": type(exc).__name__,
        }
    return {
        "ok": completed.returncode == 0,
        "timed_out": False,
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "duration_seconds": round(time.monotonic() - started, 3),
    }


def repository_snapshot() -> dict[str, Any]:
    head = residency._run(["git", "rev-parse", "HEAD"], timeout=30)
    unstaged = residency._run(["git", "diff", "--quiet"], timeout=30)
    staged = residency._run(["git", "diff", "--cached", "--quiet"], timeout=30)
    sha = str(head.get("stdout") or "").strip()
    event_sha = os.environ.get("GITHUB_SHA")
    ref = os.environ.get("GITHUB_REF")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise CanaryRuntimeError("checked-out repository SHA is invalid")
    if head.get("ok") is not True or unstaged.get("returncode") != 0 or staged.get("returncode") != 0:
        raise CanaryRuntimeError("checked-out repository is dirty")
    if event_sha != sha or ref != "refs/heads/main":
        raise CanaryRuntimeError("canary is not bound to the trusted main event SHA")
    return {
        "schema_version": "bench.checkout-binding.v1",
        "checked_out_sha": sha,
        "event_sha": event_sha,
        "ref": ref,
        "tracked_clean": True,
    }


def _norm_path(path: Path) -> str:
    try:
        return os.path.normcase(str(path.resolve()))
    except OSError:
        return os.path.normcase(str(path.absolute()))


def _discover_hermes_repo() -> Path:
    candidates: list[Path] = []
    explicit = os.environ.get("HERMES_REPO", "").strip()
    if explicit:
        candidates.append(Path(explicit))
    user = os.environ.get("USERPROFILE", "").strip()
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if user:
        candidates.extend([
            Path(user) / ".hermes" / "hermes-agent",
            Path(user) / ".hermes" / "repos" / "hermes-agent",
        ])
    if local:
        candidates.extend([
            Path(local) / "hermes" / "hermes-agent",
            Path(local) / "Programs" / "hermes" / "hermes-agent",
        ])
    observed: list[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        observed.append(str(candidate))
        if not (candidate / ".git").exists():
            continue
        head = residency._run(["git", "-C", str(candidate), "rev-parse", "HEAD"], timeout=30)
        dirty = residency._run(
            ["git", "-C", str(candidate), "status", "--porcelain", "--untracked-files=no"],
            timeout=30,
        )
        if head.get("ok") is not True:
            continue
        if str(head.get("stdout") or "").strip() != contract.bench2.EXPECTED_HERMES_COMMIT:
            continue
        if dirty.get("ok") is not True or str(dirty.get("stdout") or "").strip():
            raise CanaryRuntimeError("pinned Hermes checkout has tracked modifications")
        return candidate.resolve()
    raise CanaryRuntimeError("pinned Hermes checkout was not found: " + "; ".join(observed))


def _hermes_command_prefix(repo: Path) -> list[str]:
    candidates = [
        repo.parent / "venvs" / "hermes" / "Scripts" / "python.exe",
        repo.parent / "venvs" / "hermes-agent" / "Scripts" / "python.exe",
        repo / ".venv" / "Scripts" / "python.exe",
        repo / "venv" / "Scripts" / "python.exe",
    ]
    for python_exe in candidates:
        if python_exe.is_file():
            return [str(python_exe), "-m", "hermes_cli.main"]
    executable = shutil.which("hermes") or shutil.which("hermes.exe")
    if executable:
        return [executable]
    raise CanaryRuntimeError("Hermes executable or managed Python environment was not found")


def _yaml_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _write_isolated_home(home: Path, workdir: Path, model: str) -> None:
    plugin_source = ROOT / "fixtures/bench-2/hermes-plugin/bench2-fixture"
    plugin_target = home / "plugins" / "bench2-fixture"
    plugin_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(plugin_source, plugin_target)
    config = "\n".join([
        "model:",
        f"  default: {_yaml_quote(model)}",
        "  provider: 'custom'",
        "  api_key: 'local-only-not-secret'",
        "  base_url: 'http://127.0.0.1:11434/v1'",
        "  api_mode: 'chat_completions'",
        "  context_length: 65536",
        "  ollama_num_ctx: 65536",
        "  max_tokens: 256",
        "fallback_providers: []",
        "plugins:",
        "  enabled:",
        "    - 'bench2-fixture'",
        "terminal:",
        "  backend: 'local'",
        f"  cwd: {_yaml_quote(str(workdir))}",
        "  home_mode: 'profile'",
        "  timeout: 60",
        "agent:",
        "  max_turns: 4",
        "display:",
        "  interface: 'cli'",
        "",
    ])
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.yaml").write_text(config, encoding="utf-8", newline="\n")
    (home / ".env").write_text("\n", encoding="utf-8", newline="\n")


def sanitized_subprocess_environment(
    *,
    hermes_home: Path,
    tool_trace: Path,
    hermes_repo: Path,
    runtime_model: str,
) -> tuple[dict[str, str], list[str]]:
    env: dict[str, str] = {}
    removed: list[str] = []
    for key, value in os.environ.items():
        upper = key.upper()
        if any(fragment in upper for fragment in _CREDENTIAL_FRAGMENTS):
            removed.append(key)
            continue
        if upper in _ALLOWED_ENV or upper.startswith("PYTHON"):
            env[key] = value
    isolated_os_home = hermes_home / "home"
    isolated_os_home.mkdir(parents=True, exist_ok=True)
    env.update({
        "HERMES_HOME": str(hermes_home),
        "HOME": str(isolated_os_home),
        "BENCH2_TOOL_TRACE_PATH": str(tool_trace),
        "HERMES_PLUGINS_DEBUG": "1",
        "HERMES_INFERENCE_MODEL": runtime_model,
        "HERMES_INFERENCE_PROVIDER": "custom",
        "OPENAI_API_KEY": "local-only-not-secret",
        "HTTP_PROXY": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9",
        "ALL_PROXY": "http://127.0.0.1:9",
        "NO_PROXY": "127.0.0.1,localhost,::1",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONPATH": str(hermes_repo),
    })
    return env, sorted(set(removed), key=str.casefold)


def _verify_hermes_identity(prefix: list[str], repo: Path, env: dict[str, str]) -> dict[str, Any]:
    result = _run([*prefix, "version"], cwd=repo, env=env, timeout=60)
    text = (str(result.get("stdout") or "") + "\n" + str(result.get("stderr") or "")).strip()
    if result.get("ok") is not True:
        raise CanaryRuntimeError("Hermes version command failed")
    if f"Hermes Agent v{contract.bench2.EXPECTED_HERMES_VERSION}" not in text:
        raise CanaryRuntimeError("Hermes version does not match the pinned release")
    install_line = next(
        (line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("Install directory:")),
        None,
    )
    if install_line is None or _norm_path(Path(install_line)) != _norm_path(repo):
        raise CanaryRuntimeError("Hermes executable is not bound to the pinned checkout")
    return {
        "version": contract.bench2.EXPECTED_HERMES_VERSION,
        "commit_sha": contract.bench2.EXPECTED_HERMES_COMMIT,
        "checkout": str(repo),
        "command_prefix": prefix,
        "version_output": text,
        "tracked_clean": True,
    }


def _installed_candidate() -> dict[str, Any]:
    expected = contract.EXPECTED_CANDIDATE
    matches = [
        item for item in residency.list_installed_models()
        if item.get("name") == expected["model_tag"]
    ]
    if len(matches) != 1:
        raise CanaryRuntimeError("canary candidate is missing or duplicated in Ollama")
    model = matches[0]
    if model.get("digest") != expected["digest"]:
        raise CanaryRuntimeError("canary candidate digest drifted")
    return model


def _runtime_alias_name() -> str:
    run_id = re.sub(r"[^0-9]", "", os.environ.get("GITHUB_RUN_ID", "")) or "local"
    attempt = re.sub(r"[^0-9]", "", os.environ.get("GITHUB_RUN_ATTEMPT", "")) or "0"
    return f"bench2-canary-qwythos-safe-64k:{run_id}-{attempt}"


def _runtime_modelfile(source_model: str) -> str:
    return f"FROM {source_model}\nPARAMETER num_ctx 65536\n"


def _remove_model_if_present(model_name: str) -> dict[str, Any]:
    before = [
        item for item in residency.list_installed_models()
        if item.get("name") == model_name
    ]
    result: dict[str, Any] | None = None
    if before:
        result = _run(["ollama", "rm", model_name], timeout=120)
    after = [
        item for item in residency.list_installed_models()
        if item.get("name") == model_name
    ]
    return {
        "model_name": model_name,
        "present_before": len(before) == 1,
        "remove_returncode": result.get("returncode") if result else None,
        "verified_absent": not after,
    }


def _create_runtime_alias(candidate: dict[str, Any], runtime_root: Path) -> dict[str, Any]:
    alias = _runtime_alias_name()
    stale_cleanup = _remove_model_if_present(alias)
    if stale_cleanup.get("verified_absent") is not True:
        raise CanaryRuntimeError("stale canary runtime alias could not be removed")
    modelfile = runtime_root / "Canary.Modelfile"
    modelfile.write_text(
        _runtime_modelfile(candidate["name"]),
        encoding="utf-8",
        newline="\n",
    )
    create = _run(["ollama", "create", alias, "-f", str(modelfile)], timeout=600)
    if create.get("ok") is not True:
        detail = str(create.get("stderr") or create.get("stdout") or "")[-500:]
        raise CanaryRuntimeError(f"temporary 64K Ollama alias creation failed: {detail}")
    parameters = _run(["ollama", "show", alias, "--parameters"], timeout=60)
    parameters_text = str(parameters.get("stdout") or "")
    if parameters.get("ok") is not True or re.search(
        r"(?mi)^\s*num_ctx\s+65536\s*$", parameters_text
    ) is None:
        raise CanaryRuntimeError("temporary Ollama alias does not expose num_ctx 65536")
    matches = [
        item for item in residency.list_installed_models()
        if item.get("name") == alias
    ]
    if len(matches) != 1:
        raise CanaryRuntimeError("temporary Ollama alias is missing or duplicated")
    model = matches[0]
    return {
        "name": alias,
        "digest": model.get("digest"),
        "size": model.get("size"),
        "source_candidate_name": candidate["name"],
        "source_candidate_digest": candidate["digest"],
        "modelfile_sha256": hashlib.sha256(modelfile.read_bytes()).hexdigest(),
        "parameters": parameters_text.strip(),
        "stale_cleanup": stale_cleanup,
    }


def _candidate_payload(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "bench.candidate-task.v1",
        **{
            field: case[field]
            for field in (
                "case_id", "capability", "prompt", "inputs",
                "allowed_actions", "forbidden_actions", "limits",
            )
        },
    }


def _build_prompt(case: dict[str, Any]) -> str:
    payload = _candidate_payload(case)
    return (
        "Execute the benchmark task below exactly. The task JSON is authoritative. "
        "Use only the enabled benchmark toolset. Do not add prose outside the requested final JSON object.\n\n"
        + json.dumps(payload, indent=2, sort_keys=True)
    )


def _parse_output(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    stripped = raw.strip()
    if not stripped:
        return None, "empty_output"
    try:
        value = json.loads(stripped, object_pairs_hook=_reject_duplicates)
    except (json.JSONDecodeError, ValueError) as exc:
        return None, f"invalid_json:{type(exc).__name__}"
    if not isinstance(value, dict):
        return None, "output_not_object"
    if set(value) != {"actions", "final"}:
        return value, "output_fields_mismatch"
    if not isinstance(value.get("final"), str):
        return value, "final_not_string"
    if not isinstance(value.get("actions"), list) or any(
        not isinstance(item, str) for item in value.get("actions", [])
    ):
        return value, "actions_not_string_array"
    return value, None


def _read_tool_trace(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    if not path.is_file():
        # No tool call is a valid semantic failure, not corrupted infrastructure.
        return [], None
    records: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            value = json.loads(line, object_pairs_hook=_reject_duplicates)
            if not isinstance(value, dict):
                return records, "trace_record_not_object"
            records.append(value)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return records, f"trace_invalid:{type(exc).__name__}"
    return records, None


def _validate_usage(path: Path, model_tag: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    try:
        usage = _load_json(path)
    except CanaryRuntimeError as exc:
        return None, [{"check": "usage_file_valid", "passed": False, "detail": str(exc)}]
    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})
    add("usage_provider_custom", usage.get("provider") == "custom", f"provider={usage.get('provider')!r}")
    add("usage_model_exact", usage.get("model") == model_tag, f"model={usage.get('model')!r}")
    add("usage_completed", usage.get("completed") is True, f"completed={usage.get('completed')!r}")
    add("usage_not_failed", usage.get("failed") is False, f"failed={usage.get('failed')!r}")
    api_calls = usage.get("api_calls")
    add(
        "usage_api_calls_bounded",
        isinstance(api_calls, int) and not isinstance(api_calls, bool) and 1 <= api_calls <= 2,
        f"api_calls={api_calls!r}",
    )
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        value = usage.get(key)
        add(
            f"usage_{key}_nonnegative",
            isinstance(value, int) and not isinstance(value, bool) and value >= 0,
            f"{key}={value!r}",
        )
    return usage, checks


def _validator_result(
    *,
    process: dict[str, Any],
    output: dict[str, Any] | None,
    output_error: str | None,
    tool_records: list[dict[str, Any]],
    trace_error: str | None,
    usage_checks: list[dict[str, Any]],
    runtime_model: dict[str, Any] | None,
    residency_class: str | None,
    residency_ratio: float | None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})
    add("hermes_exit_zero", process.get("returncode") == 0 and process.get("timed_out") is False,
        f"returncode={process.get('returncode')!r} timed_out={process.get('timed_out')!r}")
    add("output_strict_json", output_error is None, f"error={output_error!r}")
    add("output_final_exact", output is not None and output.get("final") == EXPECTED_FINAL,
        f"final={output.get('final') if output else None!r}")
    add("output_actions_exact", output is not None and output.get("actions") == EXPECTED_ACTIONS,
        f"actions={output.get('actions') if output else None!r}")
    add("tool_trace_valid", trace_error is None, f"error={trace_error!r}")
    add("tool_trace_exactly_one", len(tool_records) == 1, f"records={len(tool_records)}")
    add("tool_sequence_exact", tool_records == [{
        "schema_version": "bench.hermes-tool-trace.v1",
        **EXPECTED_TOOL,
    }], f"records={tool_records!r}")
    checks.extend(usage_checks)
    add("runtime_model_observed", runtime_model is not None, f"observed={runtime_model is not None}")
    add(
        "runtime_context_65536",
        runtime_model is not None and runtime_model.get("context_length") == 65536,
        f"context_length={runtime_model.get('context_length') if runtime_model else None!r}",
    )
    add("runtime_full_vram", residency_class == "full_vram" and residency_ratio is not None and residency_ratio >= 0.98,
        f"class={residency_class!r} ratio={residency_ratio!r}")
    infrastructure_names = {
        "hermes_exit_zero", "usage_provider_custom", "usage_model_exact",
        "usage_completed", "usage_not_failed", "usage_api_calls_bounded",
        "usage_input_tokens_nonnegative", "usage_output_tokens_nonnegative",
        "usage_total_tokens_nonnegative", "runtime_model_observed",
        "runtime_context_65536", "runtime_full_vram", "tool_trace_valid",
    }
    semantic_names = {
        "output_strict_json", "output_final_exact", "output_actions_exact",
        "tool_trace_exactly_one", "tool_sequence_exact",
    }
    infrastructure_valid = all(
        item["passed"] for item in checks if item["check"] in infrastructure_names
    ) and infrastructure_names <= {item["check"] for item in checks}
    semantic_pass = all(
        item["passed"] for item in checks if item["check"] in semantic_names
    ) and semantic_names <= {item["check"] for item in checks}
    return {
        "schema_version": VALIDATOR_SCHEMA,
        "case_id": contract.EXPECTED_CASE["case_id"],
        "infrastructure_valid": infrastructure_valid,
        "semantic_pass": semantic_pass,
        "passed": infrastructure_valid and semantic_pass,
        "checks": checks,
    }


def _write_manifest(output_dir: Path) -> dict[str, Any]:
    paths = sorted(
        path for path in output_dir.iterdir()
        if path.is_file() and path.name != "manifest.json"
    )
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "created_at_utc": _utc_now(),
        "artifacts": {
            path.name: {"sha256": _sha256(path), "size_bytes": path.stat().st_size}
            for path in paths
        },
    }
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def capture(output_dir: Path = DEFAULT_ARTIFACTS) -> int:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    repository: dict[str, Any] | None = None
    hermes_identity: dict[str, Any] | None = None
    candidate: dict[str, Any] | None = None
    runtime_alias: dict[str, Any] | None = None
    alias_cleanup: dict[str, Any] = {"attempted": False, "verified_absent": False}
    process: dict[str, Any] = {
        "ok": False, "returncode": None, "timed_out": False,
        "stdout": "", "stderr": "", "duration_seconds": 0.0,
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
    removed_credential_names: list[str] = []
    infrastructure_error: dict[str, str] | None = None
    runtime_root: Path | None = None

    try:
        contract.validate_canary_plan(require_enabled=True)
        repository = repository_snapshot()
        candidate = _installed_candidate()
        gpu_before = residency.gpu_snapshot()
        if gpu_before.get("ok") is not True:
            raise CanaryRuntimeError("GPU snapshot failed before canary")
        cleanup_before = stop_all_running_models()

        hermes_repo = _discover_hermes_repo()
        runtime_base = Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir())
        runtime_root = Path(tempfile.mkdtemp(prefix="bench2-hermes-canary-", dir=runtime_base))
        hermes_home = runtime_root / "hermes-home"
        workdir = runtime_root / "workdir"
        workdir.mkdir(parents=True)
        tool_trace_path = runtime_root / "tool-trace.jsonl"
        usage_path = runtime_root / "usage.json"
        runtime_alias = _create_runtime_alias(candidate, runtime_root)
        _write_isolated_home(hermes_home, workdir, runtime_alias["name"])
        env, removed_credential_names = sanitized_subprocess_environment(
            hermes_home=hermes_home,
            tool_trace=tool_trace_path,
            hermes_repo=hermes_repo,
            runtime_model=runtime_alias["name"],
        )
        prefix = _hermes_command_prefix(hermes_repo)
        hermes_identity = _verify_hermes_identity(prefix, hermes_repo, env)

        case = load_case_file(ROOT / contract.EXPECTED_CASE["path"])
        prompt = _build_prompt(case)
        command = [
            *prefix,
            "--model", runtime_alias["name"],
            "--provider", "custom",
            "--toolsets", "bench2_fixture",
            "--ignore-rules",
            "--usage-file", str(usage_path),
            "-z", prompt,
        ]
        process = _run(command, cwd=workdir, env=env, timeout=600)
        (output_dir / "raw-output.txt").write_text(str(process.get("stdout") or ""), encoding="utf-8", newline="\n")
        (output_dir / "stderr.txt").write_text(str(process.get("stderr") or ""), encoding="utf-8", newline="\n")
        (output_dir / "hermes-version.txt").write_text(
            str(hermes_identity.get("version_output") or "") + "\n",
            encoding="utf-8",
            newline="\n",
        )

        output, output_error = _parse_output(str(process.get("stdout") or ""))
        _write_json(output_dir / "extracted-output.json", {
            "schema_version": "bench.hermes-canary-extracted-output.v1",
            "value": output,
            "error": output_error,
        })
        tool_records, trace_error = _read_tool_trace(tool_trace_path)
        with (output_dir / "tool-trace.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for record in tool_records:
                handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        if usage_path.is_file():
            shutil.copyfile(usage_path, output_dir / "usage.json")
        usage, usage_checks = _validate_usage(output_dir / "usage.json", runtime_alias["name"])

        runtime_model = residency._find_single_running_model({
            "name": runtime_alias["name"],
            "digest": runtime_alias["digest"],
        })
        residency_class, residency_ratio = residency.classify_residency(
            runtime_model.get("size"), runtime_model.get("size_vram")
        )
        gpu_loaded = residency.gpu_snapshot()
        if gpu_loaded.get("ok") is not True:
            raise CanaryRuntimeError("GPU snapshot failed after Hermes execution")

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
            "schema_version": TRACE_SCHEMA,
            "case_id": contract.EXPECTED_CASE["case_id"],
            "events": events,
        })
        validator = _validator_result(
            process=process,
            output=output,
            output_error=output_error,
            tool_records=tool_records,
            trace_error=trace_error,
            usage_checks=usage_checks,
            runtime_model=runtime_model,
            residency_class=residency_class,
            residency_ratio=residency_ratio,
        )
        _write_json(output_dir / "validator-result.json", validator)
    except Exception as exc:
        infrastructure_error = {"type": type(exc).__name__, "detail": str(exc)}
        if not (output_dir / "raw-output.txt").exists():
            (output_dir / "raw-output.txt").write_text(str(process.get("stdout") or ""), encoding="utf-8", newline="\n")
        if not (output_dir / "stderr.txt").exists():
            (output_dir / "stderr.txt").write_text(str(process.get("stderr") or ""), encoding="utf-8", newline="\n")
    finally:
        try:
            cleanup_after = stop_all_running_models()
            if runtime_alias is not None:
                alias_cleanup = {
                    "attempted": True,
                    **_remove_model_if_present(runtime_alias["name"]),
                }
                if alias_cleanup.get("verified_absent") is not True:
                    raise CanaryRuntimeError("temporary Ollama alias cleanup failed")
        except Exception as exc:
            detail = f"cleanup failed: {type(exc).__name__}: {exc}"
            if infrastructure_error is None:
                infrastructure_error = {"type": type(exc).__name__, "detail": detail}
            else:
                infrastructure_error["detail"] += "; " + detail
        if runtime_root is not None:
            shutil.rmtree(runtime_root, ignore_errors=True)

    validator_path = output_dir / "validator-result.json"
    validator = _load_json(validator_path) if validator_path.is_file() else {
        "schema_version": VALIDATOR_SCHEMA,
        "case_id": contract.EXPECTED_CASE["case_id"],
        "infrastructure_valid": False,
        "semantic_pass": False,
        "passed": False,
        "checks": [],
    }
    if cleanup_after and any(item.get("verified_absent") is not True for item in cleanup_after):
        infrastructure_error = {"type": "CanaryRuntimeError", "detail": "final cleanup attestation failed"}
    fingerprint = {
        "schema_version": "bench.hermes-canary-environment.v1",
        "created_at_utc": _utc_now(),
        "platform": platform.platform(),
        "python": sys.version,
        "repository": repository,
        "hermes": hermes_identity,
        "candidate": candidate,
        "runtime_alias": runtime_alias,
        "alias_cleanup": alias_cleanup,
        "endpoint": "http://127.0.0.1:11434/v1",
        "external_proxy_sink_enabled": True,
        "credential_environment_names_removed": removed_credential_names,
        "gpu_before": gpu_before,
        "gpu_loaded": gpu_loaded,
        "runtime_model": runtime_model,
        "residency_class": residency_class,
        "residency_ratio": residency_ratio,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
    }
    _write_json(output_dir / "environment-fingerprint.json", fingerprint)
    report = {
        "schema_version": REPORT_SCHEMA,
        "created_at_utc": _utc_now(),
        "workflow": {
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "event_name": os.environ.get("GITHUB_EVENT_NAME"),
            "sha": os.environ.get("GITHUB_SHA"),
            "ref": os.environ.get("GITHUB_REF"),
        },
        "source": {
            "plan_path": contract.PLAN_PATH.relative_to(ROOT).as_posix(),
            "plan_sha256": contract.EXPECTED_PLAN_SHA256,
            "bench2_plan_sha256": contract.bench2.EXPECTED_PLAN_SHA256,
            "candidate_registry_sha256": contract.bench2.EXPECTED_REGISTRY_SHA256,
            "h4_summary_sha256": contract.bench2.EXPECTED_H4_SUMMARY_SHA256,
            "hermes_commit_sha": contract.bench2.EXPECTED_HERMES_COMMIT,
            "hermes_version": contract.bench2.EXPECTED_HERMES_VERSION,
            "case_definition_sha256": contract.EXPECTED_CASE["case_definition_sha256"],
        },
        "repository": repository,
        "candidate": candidate,
        "runtime_alias": runtime_alias,
        "alias_cleanup": alias_cleanup,
        "case_id": contract.EXPECTED_CASE["case_id"],
        "process": {
            key: process.get(key)
            for key in ("ok", "returncode", "timed_out", "duration_seconds", "error")
        },
        "usage": usage,
        "tool_trace_count": len(tool_records),
        "runtime_model": runtime_model,
        "residency_class": residency_class,
        "residency_ratio": residency_ratio,
        "cleanup_before": cleanup_before,
        "cleanup_after": cleanup_after,
        "infrastructure_error": infrastructure_error,
        "infrastructure_valid": infrastructure_error is None and validator.get("infrastructure_valid") is True,
        "semantic_pass": infrastructure_error is None and validator.get("semantic_pass") is True,
        "candidate_result_status": (
            "passed"
            if infrastructure_error is None and validator.get("passed") is True
            else "failed"
            if infrastructure_error is None
            else "invalid_infrastructure"
        ),
        "full_matrix_authorized": False,
    }
    _write_json(output_dir / "report.json", report)
    _write_manifest(output_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _verify_manifest(output_dir: Path) -> None:
    manifest = _load_json(output_dir / "manifest.json")
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise CanaryRuntimeError("canary manifest schema is invalid")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise CanaryRuntimeError("canary manifest inventory is missing")
    required = {
        "environment-fingerprint.json", "extracted-output.json", "hermes-version.txt",
        "raw-output.txt", "report.json", "stderr.txt", "tool-trace.jsonl",
        "trace.json", "usage.json", "validator-result.json",
    }
    if set(artifacts) != required:
        raise CanaryRuntimeError("canary manifest artifact set drifted")
    for name, record in artifacts.items():
        path = output_dir / name
        if not isinstance(record, dict) or not path.is_file():
            raise CanaryRuntimeError(f"canary artifact record invalid: {name}")
        if record.get("sha256") != _sha256(path) or record.get("size_bytes") != path.stat().st_size:
            raise CanaryRuntimeError(f"canary artifact digest mismatch: {name}")


def enforce(output_dir: Path = DEFAULT_ARTIFACTS) -> int:
    try:
        contract.validate_canary_plan(require_enabled=True)
        current = repository_snapshot()
        _verify_manifest(output_dir)
        report = _load_json(output_dir / "report.json")
        validator = _load_json(output_dir / "validator-result.json")
        fingerprint = _load_json(output_dir / "environment-fingerprint.json")
        usage = _load_json(output_dir / "usage.json")
        if report.get("schema_version") != REPORT_SCHEMA:
            raise CanaryRuntimeError("canary report schema is invalid")
        if report.get("source") != {
            "plan_path": "fixtures/bench-plans/hermes-orchestrator-canary-v1.json",
            "plan_sha256": contract.EXPECTED_PLAN_SHA256,
            "bench2_plan_sha256": contract.bench2.EXPECTED_PLAN_SHA256,
            "candidate_registry_sha256": contract.bench2.EXPECTED_REGISTRY_SHA256,
            "h4_summary_sha256": contract.bench2.EXPECTED_H4_SUMMARY_SHA256,
            "hermes_commit_sha": contract.bench2.EXPECTED_HERMES_COMMIT,
            "hermes_version": contract.bench2.EXPECTED_HERMES_VERSION,
            "case_definition_sha256": contract.EXPECTED_CASE["case_definition_sha256"],
        }:
            raise CanaryRuntimeError("canary source binding drifted")
        if report.get("repository") != current:
            raise CanaryRuntimeError("canary repository binding drifted")
        if report.get("candidate") is None or report["candidate"].get("name") != contract.EXPECTED_CANDIDATE["model_tag"]:
            raise CanaryRuntimeError("canary candidate identity drifted")
        if report["candidate"].get("digest") != contract.EXPECTED_CANDIDATE["digest"]:
            raise CanaryRuntimeError("canary candidate digest drifted")
        runtime_alias = report.get("runtime_alias")
        if not isinstance(runtime_alias, dict):
            raise CanaryRuntimeError("canary runtime alias evidence is missing")
        if runtime_alias.get("source_candidate_name") != contract.EXPECTED_CANDIDATE["model_tag"]:
            raise CanaryRuntimeError("canary runtime alias source name drifted")
        if runtime_alias.get("source_candidate_digest") != contract.EXPECTED_CANDIDATE["digest"]:
            raise CanaryRuntimeError("canary runtime alias source digest drifted")
        if report.get("alias_cleanup", {}).get("verified_absent") is not True:
            raise CanaryRuntimeError("canary runtime alias was not removed")
        if report.get("infrastructure_error") is not None or report.get("infrastructure_valid") is not True:
            raise CanaryRuntimeError("canary infrastructure evidence is invalid")
        if report.get("runtime_model", {}).get("name") != runtime_alias.get("name"):
            raise CanaryRuntimeError("canary runtime model alias drifted")
        if report.get("runtime_model", {}).get("digest") != runtime_alias.get("digest"):
            raise CanaryRuntimeError("canary runtime alias digest drifted")
        if report.get("runtime_model", {}).get("context_length") != 65536:
            raise CanaryRuntimeError("canary runtime context is not 65536")
        if report.get("residency_class") != "full_vram":
            raise CanaryRuntimeError("canary runtime is not fully resident in VRAM")
        if any(item.get("verified_absent") is not True for item in report.get("cleanup_after", [])):
            raise CanaryRuntimeError("canary final cleanup is invalid")
        if fingerprint.get("hermes", {}).get("commit_sha") != contract.bench2.EXPECTED_HERMES_COMMIT:
            raise CanaryRuntimeError("canary Hermes identity drifted")
        if fingerprint.get("runtime_alias") != runtime_alias:
            raise CanaryRuntimeError("canary runtime alias fingerprint drifted")
        if usage.get("provider") != "custom" or usage.get("model") != runtime_alias.get("name"):
            raise CanaryRuntimeError("canary usage provider/runtime alias binding drifted")
        if validator.get("schema_version") != VALIDATOR_SCHEMA:
            raise CanaryRuntimeError("canary validator schema is invalid")
        if validator.get("semantic_pass") is not True or validator.get("passed") is not True:
            print("canary evidence is infrastructure-valid but semantic behavior failed", file=sys.stderr)
            return 1
    except (CanaryRuntimeError, contract.CanaryPlanError, contract.bench2.HermesPlanError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"invalid BENCH-2 Hermes canary evidence: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(
        "BENCH-2 Hermes canary passed; "
        f"candidate={contract.EXPECTED_CANDIDATE['candidate_id']} "
        f"case={contract.EXPECTED_CASE['case_id']} context=65536"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture or enforce the isolated BENCH-2 Hermes canary.")
    parser.add_argument("mode", choices=("capture", "enforce"))
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACTS)
    args = parser.parse_args()
    return capture(args.artifact_dir) if args.mode == "capture" else enforce(args.artifact_dir)


if __name__ == "__main__":
    raise SystemExit(main())

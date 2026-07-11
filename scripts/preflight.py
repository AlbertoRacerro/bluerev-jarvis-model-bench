from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from ipaddress import ip_address
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.benchmark_runtime import (
    EXTERNAL_ENV_NAMES,
    external_env_names,
    parse_removed_environment_report,
    sanitize_environment,
)

KNOWN_EXTERNAL_KEYS = tuple(sorted(EXTERNAL_ENV_NAMES))
DEFAULT_WINDOWS_HERMES_REPO = Path(r"C:\AI\hermes-agent")
_MAX_LOOPBACK_RESPONSE_BYTES = 4_000_000


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


_OPENER = build_opener(ProxyHandler({}), _NoRedirect)


def _is_loopback_http_endpoint(endpoint: str) -> bool:
    try:
        parsed = urlparse(endpoint)
        return bool(
            parsed.scheme == "http"
            and parsed.hostname is not None
            and ip_address(parsed.hostname).is_loopback
            and parsed.path == "/api/tags"
            and not parsed.params
            and not parsed.query
            and not parsed.fragment
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    environment: dict[str, str] | None = None,
    timeout_seconds: int = 20,
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "command": command,
            "error": type(exc).__name__,
            "timed_out": True,
            "timeout_seconds": timeout_seconds,
        }
    except OSError as exc:
        return {"ok": False, "command": command, "error": type(exc).__name__}
    return {
        "ok": completed.returncode == 0,
        "command": command,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout.strip()[-4000:],
        "stderr_tail": completed.stderr.strip()[-4000:],
        "timed_out": False,
    }


def inspect_ollama() -> dict[str, Any]:
    endpoint = os.environ.get("OLLAMA_TAGS_URL", "http://127.0.0.1:11434/api/tags")
    version = _run(["ollama", "--version"])
    if not _is_loopback_http_endpoint(endpoint):
        return {
            "ok": False,
            "endpoint": endpoint,
            "error": "NonLoopbackEndpoint",
            "version": version,
            "models": [],
        }
    try:
        with _OPENER.open(Request(endpoint, method="GET"), timeout=8) as response:
            if response.geturl() != endpoint:
                raise RuntimeError("loopback request was redirected")
            raw = response.read(_MAX_LOOPBACK_RESPONSE_BYTES + 1)
        if len(raw) > _MAX_LOOPBACK_RESPONSE_BYTES:
            raise ValueError("loopback response exceeds size limit")
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
            raise ValueError("invalid Ollama model inventory")
    except (OSError, TimeoutError, UnicodeError, json.JSONDecodeError, RuntimeError, ValueError) as exc:
        return {
            "ok": False,
            "endpoint": endpoint,
            "error": type(exc).__name__,
            "version": version,
            "models": [],
        }

    models: list[dict[str, Any]] = []
    names: set[str] = set()
    for item in payload["models"]:
        if not isinstance(item, dict):
            return {"ok": False, "endpoint": endpoint, "error": "InvalidModelInventory", "version": version, "models": []}
        name = item.get("name") or item.get("model")
        digest = item.get("digest")
        size = item.get("size")
        if (
            not isinstance(name, str)
            or not name
            or name in names
            or not isinstance(digest, str)
            or not digest
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size <= 0
        ):
            return {"ok": False, "endpoint": endpoint, "error": "InvalidModelInventory", "version": version, "models": []}
        names.add(name)
        models.append({"name": name, "digest": digest, "size": size, "modified_at": item.get("modified_at")})
    models.sort(key=lambda item: item["name"].casefold())
    return {"ok": True, "endpoint": endpoint, "version": version, "models": models}


def _expanded_path(value: str) -> Path:
    return Path(os.path.expandvars(value)).expanduser().resolve()


def _hermes_repo_candidates() -> list[tuple[Path, str]]:
    candidates: list[tuple[Path, str]] = []
    for variable in ("HERMES_REPO", "HERMES_INSTALL_DIR"):
        value = os.environ.get(variable)
        if value:
            candidates.append((_expanded_path(value), f"environment:{variable}"))
    hermes_home = os.environ.get("HERMES_HOME")
    if hermes_home:
        candidates.append((_expanded_path(hermes_home) / "hermes-agent", "environment:HERMES_HOME"))
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append((_expanded_path(local_app_data) / "hermes" / "hermes-agent", "windows_managed_install"))
    candidates.extend(
        [
            (DEFAULT_WINDOWS_HERMES_REPO, "legacy_windows_default"),
            (Path.home() / ".hermes" / "hermes-agent", "posix_managed_install"),
        ]
    )
    unique: list[tuple[Path, str]] = []
    seen: set[str] = set()
    for path, source in candidates:
        key = os.path.normcase(str(path))
        if key not in seen:
            seen.add(key)
            unique.append((path, source))
    return unique


def _resolve_hermes_repo() -> tuple[Path | None, str | None, list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    for path, source in _hermes_repo_candidates():
        exists = path.is_dir()
        is_git = (path / ".git").exists() if exists else False
        evidence.append({"path": str(path), "source": source, "exists": exists, "is_git": is_git})
        if exists and is_git:
            return path.resolve(), source, evidence
    return None, None, evidence


def _resolve_hermes_python(repo: Path | None) -> tuple[Path | None, str | None, list[dict[str, Any]]]:
    if repo is None:
        return None, None, []
    candidates = (
        (repo / "venv" / "Scripts" / "python.exe", "official_windows_venv"),
        (repo / ".venv" / "Scripts" / "python.exe", "legacy_windows_dotvenv"),
        (repo / "venv" / "bin" / "python", "official_posix_venv"),
        (repo / ".venv" / "bin" / "python", "legacy_posix_dotvenv"),
    )
    evidence: list[dict[str, Any]] = []
    for path, source in candidates:
        exists = path.is_file()
        evidence.append({"path": str(path), "source": source, "exists": exists})
        if exists:
            return path.resolve(), source, evidence
    return None, None, evidence


def _resolve_git_bash() -> tuple[Path | None, str | None, list[dict[str, Any]]]:
    if os.name != "nt":
        candidate = shutil.which("bash")
        return (Path(candidate).resolve(), "path", []) if candidate else (None, None, [])
    candidates: list[tuple[Path, str]] = []
    explicit = os.environ.get("HERMES_GIT_BASH_PATH")
    if explicit:
        candidates.append((_expanded_path(explicit), "environment:HERMES_GIT_BASH_PATH"))
    for root_name, source in (("HERMES_HOME", "hermes_home"), ("LOCALAPPDATA", "windows_managed")):
        value = os.environ.get(root_name)
        if value:
            base = _expanded_path(value)
            if root_name == "LOCALAPPDATA":
                base = base / "hermes"
            candidates.extend(
                [
                    (base / "git" / "usr" / "bin" / "bash.exe", source + "_usr"),
                    (base / "git" / "bin" / "bash.exe", source + "_bin"),
                ]
            )
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        value = os.environ.get(variable)
        if value:
            candidates.append((_expanded_path(value) / "Git" / "bin" / "bash.exe", variable))
    discovered = shutil.which("bash")
    if discovered:
        candidates.append((Path(discovered).resolve(), "path"))

    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path, source in candidates:
        key = os.path.normcase(str(path))
        if key in seen:
            continue
        seen.add(key)
        exists = path.is_file()
        evidence.append({"path": str(path), "source": source, "exists": exists})
        if exists:
            return path.resolve(), source, evidence
    return None, None, evidence


def _path_within(path_value: Any, root: Path) -> bool:
    if not isinstance(path_value, str) or not path_value:
        return False
    try:
        Path(path_value).resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def inspect_hermes() -> dict[str, Any]:
    repo, repo_source, repo_candidates = _resolve_hermes_repo()
    python_exe, python_source, python_candidates = _resolve_hermes_python(repo)
    git_bash, git_bash_source, git_bash_candidates = _resolve_git_bash()

    metadata_result: dict[str, Any] = {"ok": False, "error": "HermesVenvNotFound"}
    metadata: dict[str, Any] | None = None
    removed: list[str] = []
    if repo and python_exe:
        with tempfile.TemporaryDirectory(prefix="bluerev-hermes-preflight-") as temporary_home:
            isolated_env, removed = sanitize_environment(os.environ, hermes_home=Path(temporary_home))
            metadata_result = _run(
                [str(python_exe), str(ROOT / "scripts" / "hermes_install_probe.py")],
                cwd=ROOT,
                environment=isolated_env,
                timeout_seconds=30,
            )
        if metadata_result.get("ok"):
            try:
                parsed = json.loads(str(metadata_result.get("stdout_tail") or ""))
                if isinstance(parsed, dict):
                    metadata = parsed
            except json.JSONDecodeError:
                metadata_result["ok"] = False
                metadata_result["error"] = "InvalidMetadataProbeJson"

    module_bound = bool(repo and metadata and metadata.get("ok") is True and _path_within(metadata.get("module_file"), repo))
    prefix_bound = bool(repo and metadata and _path_within(metadata.get("python_prefix"), repo))
    if metadata_result.get("ok") and not (module_bound and prefix_bound):
        metadata_result["ok"] = False
        metadata_result["error"] = "HermesInstallationNotBoundToRepository"

    bash_result = (
        _run([str(git_bash), "--version"], timeout_seconds=20)
        if git_bash
        else {"ok": False, "error": "GitBashNotFound"}
    )
    commit = branch = None
    dirty: bool | None = None
    if repo:
        commit_result = _run(["git", "rev-parse", "HEAD"], cwd=repo)
        branch_result = _run(["git", "branch", "--show-current"], cwd=repo)
        status_result = _run(["git", "status", "--porcelain"], cwd=repo)
        if commit_result.get("ok"):
            commit = commit_result.get("stdout_tail")
        if branch_result.get("ok"):
            branch = branch_result.get("stdout_tail") or None
        if status_result.get("ok"):
            dirty = bool(status_result.get("stdout_tail"))

    bash_required = os.name == "nt"
    return {
        "ok": bool(repo and metadata_result.get("ok") and (not bash_required or bash_result.get("ok"))),
        "platform_mode": "native_windows" if os.name == "nt" else "posix_or_wsl",
        "repo": str(repo) if repo else None,
        "repo_source": repo_source,
        "repo_candidates": repo_candidates,
        "commit": commit,
        "branch": branch,
        "dirty": dirty,
        "python": str(python_exe) if python_exe else None,
        "python_source": python_source,
        "python_candidates": python_candidates,
        "installation_metadata": metadata,
        "metadata_probe": metadata_result,
        "cli_executed": False,
        "isolated_home": True,
        "sanitized_external_env_names": removed,
        "git_bash": {
            "required": bash_required,
            "path": str(git_bash) if git_bash else None,
            "source": git_bash_source,
            "candidates": git_bash_candidates,
            "probe": bash_result,
        },
    }


def build_report() -> dict[str, Any]:
    ollama = inspect_ollama()
    hermes = inspect_hermes()
    current_external_names = external_env_names(os.environ)
    removed_external_names = parse_removed_environment_report(os.environ)
    runner_ready = bool(ollama.get("ok") and ollama.get("models") and hermes.get("ok"))
    local_only = not current_external_names
    runner_name = os.environ.get("RUNNER_NAME")
    workflow = {
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "event_name": os.environ.get("GITHUB_EVENT_NAME"),
        "sha": os.environ.get("GITHUB_SHA"),
        "ref": os.environ.get("GITHUB_REF"),
    }
    blocking_reasons = [
        reason
        for condition, reason in (
            (not ollama.get("ok") and ollama.get("error") == "NonLoopbackEndpoint", "ollama_endpoint_not_loopback"),
            (not ollama.get("ok") and ollama.get("error") != "NonLoopbackEndpoint", "ollama_unreachable_or_invalid"),
            (ollama.get("ok") and not ollama.get("models"), "no_ollama_models"),
            (not hermes.get("ok"), "hermes_installation_or_windows_shell_unready"),
            (current_external_names, "external_api_environment_present_after_sanitization"),
        )
        if condition
    ]
    models = ollama.get("models") or []
    scoring_blocking_reasons = list(blocking_reasons)
    scoring_blocking_reasons.extend(
        reason
        for condition, reason in (
            (not runner_name, "runner_name_unavailable"),
            (any(not workflow.get(field) for field in ("run_id", "run_attempt", "sha", "ref")), "workflow_identity_incomplete"),
            (ollama.get("ok") and not (ollama.get("version") or {}).get("ok"), "ollama_version_unavailable"),
            (bool(models) and any(not model.get("name") or not model.get("digest") for model in models), "ollama_model_identity_incomplete"),
            (hermes.get("ok") and not hermes.get("commit"), "hermes_commit_unavailable"),
            (hermes.get("ok") and hermes.get("dirty") is None, "hermes_worktree_state_unknown"),
            (hermes.get("ok") and hermes.get("dirty") is True, "hermes_worktree_dirty"),
            (os.name == "nt" and not ((hermes.get("git_bash") or {}).get("probe") or {}).get("ok"), "hermes_git_bash_unavailable"),
            (removed_external_names == ["invalid_sanitization_report"], "environment_sanitization_report_invalid"),
        )
        if condition
    )
    return {
        "schema_version": "bench.preflight.v1",
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "ready" if runner_ready else "blocked",
        "runner_ready": runner_ready,
        "local_only": local_only,
        "scoring_ready": runner_ready and local_only and not scoring_blocking_reasons,
        "environment_sanitization": {
            "current_external_env_names": current_external_names,
            "removed_external_env_names": removed_external_names,
            "secret_values_recorded": False,
        },
        "external_api_env_names_present": current_external_names,
        "environment": {
            "runner_name": runner_name,
            "os": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": sys.version,
            "cpu_count": os.cpu_count(),
        },
        "workflow": workflow,
        "ollama": ollama,
        "hermes": hermes,
        "blocking_reasons": blocking_reasons,
        "scoring_blocking_reasons": scoring_blocking_reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory the local-only benchmark environment.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["scoring_ready"] is True else 2


if __name__ == "__main__":
    raise SystemExit(main())

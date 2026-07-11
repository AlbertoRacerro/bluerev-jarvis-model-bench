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

# Backwards-compatible public name used by job wrappers and tests.
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
        host = parsed.hostname
        return bool(
            parsed.scheme == "http"
            and host is not None
            and ip_address(host).is_loopback
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

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    return {
        "ok": completed.returncode == 0,
        "command": command,
        "returncode": completed.returncode,
        "stdout_tail": stdout[-2000:],
        "stderr_tail": stderr[-2000:],
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
        request = Request(endpoint, method="GET")
        with _OPENER.open(request, timeout=8) as response:
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
            return {
                "ok": False,
                "endpoint": endpoint,
                "error": "InvalidModelInventory",
                "version": version,
                "models": [],
            }
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
            return {
                "ok": False,
                "endpoint": endpoint,
                "error": "InvalidModelInventory",
                "version": version,
                "models": [],
            }
        names.add(name)
        models.append(
            {
                "name": name,
                "digest": digest,
                "size": size,
                "modified_at": item.get("modified_at"),
            }
        )
    models.sort(key=lambda item: item["name"].casefold())
    return {
        "ok": True,
        "endpoint": endpoint,
        "version": version,
        "models": models,
    }


def _expanded_path(value: str) -> Path:
    return Path(os.path.expandvars(value)).expanduser().resolve()


def _hermes_repo_candidates() -> list[tuple[Path, str]]:
    candidates: list[tuple[Path, str]] = []
    explicit = os.environ.get("HERMES_REPO")
    if explicit:
        candidates.append((_expanded_path(explicit), "environment:HERMES_REPO"))

    install_dir = os.environ.get("HERMES_INSTALL_DIR")
    if install_dir:
        candidates.append((_expanded_path(install_dir), "environment:HERMES_INSTALL_DIR"))

    hermes_home = os.environ.get("HERMES_HOME")
    if hermes_home:
        candidates.append((_expanded_path(hermes_home) / "hermes-agent", "environment:HERMES_HOME"))

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(
            (
                _expanded_path(local_app_data) / "hermes" / "hermes-agent",
                "windows_managed_install",
            )
        )

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


def _resolve_git_bash() -> tuple[Path | None, str | None, list[dict[str, Any]]]:
    if os.name != "nt":
        candidate = shutil.which("bash")
        return (Path(candidate).resolve(), "path", []) if candidate else (None, None, [])

    candidates: list[tuple[Path, str]] = []
    explicit = os.environ.get("HERMES_GIT_BASH_PATH")
    if explicit:
        candidates.append((_expanded_path(explicit), "environment:HERMES_GIT_BASH_PATH"))

    hermes_home = os.environ.get("HERMES_HOME")
    local_app_data = os.environ.get("LOCALAPPDATA")
    managed_home = _expanded_path(hermes_home) if hermes_home else None
    if managed_home:
        candidates.extend(
            [
                (managed_home / "git" / "usr" / "bin" / "bash.exe", "hermes_home_usr"),
                (managed_home / "git" / "bin" / "bash.exe", "hermes_home_bin"),
            ]
        )
    if local_app_data:
        base = _expanded_path(local_app_data) / "hermes" / "git"
        candidates.extend(
            [
                (base / "usr" / "bin" / "bash.exe", "windows_managed_usr"),
                (base / "bin" / "bash.exe", "windows_managed_bin"),
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


def inspect_hermes() -> dict[str, Any]:
    repo, repo_source, repo_candidates = _resolve_hermes_repo()
    git_bash, git_bash_source, git_bash_candidates = _resolve_git_bash()

    with tempfile.TemporaryDirectory(prefix="bluerev-hermes-preflight-") as temporary_home:
        isolated_env, removed = sanitize_environment(
            os.environ,
            hermes_home=Path(temporary_home),
        )
        if git_bash:
            isolated_env["HERMES_GIT_BASH_PATH"] = str(git_bash)

        attempts: list[tuple[list[str], Path | None]] = []
        explicit_exe = os.environ.get("HERMES_EXE")
        if explicit_exe:
            attempts.extend([([explicit_exe, "--version"], None), ([explicit_exe, "--help"], None)])
        discovered_exe = shutil.which("hermes")
        if discovered_exe and discovered_exe != explicit_exe:
            attempts.extend(
                [([discovered_exe, "--version"], None), ([discovered_exe, "--help"], None)]
            )

        if repo:
            python_candidates = (
                repo / "venv" / "Scripts" / "python.exe",
                repo / ".venv" / "Scripts" / "python.exe",
                repo / "venv" / "bin" / "python",
                repo / ".venv" / "bin" / "python",
            )
            for candidate in python_candidates:
                if candidate.is_file():
                    attempts.extend(
                        [
                            ([str(candidate), "-m", "hermes_cli.main", "--version"], repo),
                            ([str(candidate), "-m", "hermes_cli.main", "--help"], repo),
                        ]
                    )
                    break

        results: list[dict[str, Any]] = []
        selected: dict[str, Any] | None = None
        for command, cwd in attempts:
            result = _run(command, cwd=cwd, environment=isolated_env)
            results.append(result)
            if result.get("ok"):
                selected = result
                break

        bash_result = (
            _run([str(git_bash), "--version"], environment=isolated_env)
            if git_bash
            else {"ok": False, "error": "GitBashNotFound"}
        )

    commit = None
    branch = None
    dirty = None
    if repo:
        git_commit = _run(["git", "rev-parse", "HEAD"], cwd=repo)
        if git_commit.get("ok"):
            commit = git_commit.get("stdout_tail")
        git_branch = _run(["git", "branch", "--show-current"], cwd=repo)
        if git_branch.get("ok"):
            branch = git_branch.get("stdout_tail") or None
        git_status = _run(["git", "status", "--porcelain"], cwd=repo)
        if git_status.get("ok"):
            dirty = bool(git_status.get("stdout_tail"))

    bash_required = os.name == "nt"
    return {
        "ok": selected is not None and (not bash_required or bash_result.get("ok") is True),
        "platform_mode": "native_windows" if os.name == "nt" else "posix_or_wsl",
        "repo": str(repo) if repo else None,
        "repo_source": repo_source,
        "repo_candidates": repo_candidates,
        "commit": commit,
        "branch": branch,
        "dirty": dirty,
        "selected": selected,
        "attempts": results,
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
            (
                not ollama.get("ok") and ollama.get("error") == "NonLoopbackEndpoint",
                "ollama_endpoint_not_loopback",
            ),
            (
                not ollama.get("ok") and ollama.get("error") != "NonLoopbackEndpoint",
                "ollama_unreachable_or_invalid",
            ),
            (ollama.get("ok") and not ollama.get("models"), "no_ollama_models"),
            (not hermes.get("ok"), "hermes_unavailable_or_windows_shell_unready"),
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
            (
                any(not workflow.get(field) for field in ("run_id", "run_attempt", "sha", "ref")),
                "workflow_identity_incomplete",
            ),
            (
                ollama.get("ok") and not (ollama.get("version") or {}).get("ok"),
                "ollama_version_unavailable",
            ),
            (
                bool(models)
                and any(not model.get("name") or not model.get("digest") for model in models),
                "ollama_model_identity_incomplete",
            ),
            (hermes.get("ok") and not hermes.get("repo"), "hermes_repository_unavailable"),
            (hermes.get("ok") and not hermes.get("commit"), "hermes_commit_unavailable"),
            (
                hermes.get("ok") and hermes.get("dirty") is None,
                "hermes_worktree_state_unknown",
            ),
            (hermes.get("ok") and hermes.get("dirty") is True, "hermes_worktree_dirty"),
            (
                os.name == "nt"
                and not ((hermes.get("git_bash") or {}).get("probe") or {}).get("ok"),
                "hermes_git_bash_unavailable",
            ),
            (
                removed_external_names == ["invalid_sanitization_report"],
                "environment_sanitization_report_invalid",
            ),
        )
        if condition
    )

    return {
        "schema_version": "bench.preflight.v2",
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

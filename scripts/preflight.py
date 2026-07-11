from __future__ import annotations

import argparse
from ipaddress import ip_address
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

KNOWN_EXTERNAL_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
    "XAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "GLM_API_KEY",
    "KIMI_API_KEY",
    "DASHSCOPE_API_KEY",
)

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


def _run(command: list[str], *, cwd: Path | None = None) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "command": command, "error": type(exc).__name__}

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    return {
        "ok": completed.returncode == 0,
        "command": command,
        "returncode": completed.returncode,
        "stdout_tail": stdout[-2000:],
        "stderr_tail": stderr[-2000:],
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

    models = []
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
        if (
            not isinstance(name, str)
            or not name
            or name in names
            or not isinstance(digest, str)
            or not digest
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
                "size": item.get("size"),
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


def _resolve_hermes_repo() -> tuple[Path | None, str | None]:
    repo_value = os.environ.get("HERMES_REPO")
    if repo_value:
        return Path(repo_value).expanduser().resolve(), "environment"

    if os.name == "nt" and DEFAULT_WINDOWS_HERMES_REPO.exists():
        return DEFAULT_WINDOWS_HERMES_REPO.resolve(), "windows_default"

    return None, None


def inspect_hermes() -> dict[str, Any]:
    attempts: list[tuple[list[str], Path | None]] = []
    hermes_exe = os.environ.get("HERMES_EXE", "hermes")
    attempts.append(([hermes_exe, "--version"], None))
    attempts.append(([hermes_exe, "--help"], None))

    repo, repo_source = _resolve_hermes_repo()
    if repo:
        python_candidates = (
            repo / ".venv" / "Scripts" / "python.exe",
            repo / ".venv" / "bin" / "python",
        )
        for candidate in python_candidates:
            if candidate.exists():
                attempts.append(([str(candidate), "-m", "hermes_cli.main", "--version"], repo))
                attempts.append(([str(candidate), "-m", "hermes_cli.main", "--help"], repo))
                break

    results = []
    selected: dict[str, Any] | None = None
    for command, cwd in attempts:
        result = _run(command, cwd=cwd)
        results.append(result)
        if result.get("ok"):
            selected = result
            break

    commit = None
    branch = None
    dirty = None
    if repo and (repo / ".git").exists():
        git_commit = _run(["git", "rev-parse", "HEAD"], cwd=repo)
        if git_commit.get("ok"):
            commit = git_commit.get("stdout_tail")

        git_branch = _run(["git", "branch", "--show-current"], cwd=repo)
        if git_branch.get("ok"):
            branch = git_branch.get("stdout_tail") or None

        git_status = _run(["git", "status", "--porcelain"], cwd=repo)
        if git_status.get("ok"):
            dirty = bool(git_status.get("stdout_tail"))

    return {
        "ok": selected is not None,
        "repo": str(repo) if repo else None,
        "repo_source": repo_source,
        "commit": commit,
        "branch": branch,
        "dirty": dirty,
        "selected": selected,
        "attempts": results,
    }


def build_report() -> dict[str, Any]:
    ollama = inspect_ollama()
    hermes = inspect_hermes()
    external_env_names = [name for name in KNOWN_EXTERNAL_KEYS if os.environ.get(name)]

    runner_ready = bool(ollama.get("ok") and ollama.get("models") and hermes.get("ok"))
    local_only = len(external_env_names) == 0
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
                not ollama.get("ok")
                and ollama.get("error") == "NonLoopbackEndpoint",
                "ollama_endpoint_not_loopback",
            ),
            (
                not ollama.get("ok")
                and ollama.get("error") != "NonLoopbackEndpoint",
                "ollama_unreachable_or_invalid",
            ),
            (ollama.get("ok") and not ollama.get("models"), "no_ollama_models"),
            (not hermes.get("ok"), "hermes_unavailable"),
            (external_env_names, "external_api_environment_present"),
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
            (hermes.get("ok") and not hermes.get("commit"), "hermes_commit_unavailable"),
            (
                hermes.get("ok") and hermes.get("dirty") is None,
                "hermes_worktree_state_unknown",
            ),
            (hermes.get("ok") and hermes.get("dirty") is True, "hermes_worktree_dirty"),
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
        "external_api_env_names_present": external_env_names,
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

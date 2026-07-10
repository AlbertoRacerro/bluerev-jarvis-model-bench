from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

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


def _run(command: list[str], *, cwd: Path | None = None) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
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
    try:
        with urlopen(endpoint, timeout=8) as response:  # noqa: S310 - loopback endpoint by contract
            payload = json.load(response)
    except (OSError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"ok": False, "endpoint": endpoint, "error": type(exc).__name__, "models": []}

    models = []
    for item in payload.get("models", []):
        if not isinstance(item, dict):
            continue
        models.append(
            {
                "name": item.get("name") or item.get("model"),
                "digest": item.get("digest"),
                "size": item.get("size"),
                "modified_at": item.get("modified_at"),
            }
        )
    models.sort(key=lambda item: str(item.get("name") or ""))
    return {"ok": True, "endpoint": endpoint, "models": models}


def inspect_hermes() -> dict[str, Any]:
    attempts: list[tuple[list[str], Path | None]] = []
    hermes_exe = os.environ.get("HERMES_EXE", "hermes")
    attempts.append(([hermes_exe, "--version"], None))
    attempts.append(([hermes_exe, "--help"], None))

    repo_value = os.environ.get("HERMES_REPO")
    repo = Path(repo_value).expanduser().resolve() if repo_value else None
    if repo:
        venv_python = repo / ".venv" / "Scripts" / "python.exe"
        if venv_python.exists():
            attempts.append(([str(venv_python), "-m", "hermes_cli.main", "--version"], repo))
            attempts.append(([str(venv_python), "-m", "hermes_cli.main", "--help"], repo))

    results = []
    selected: dict[str, Any] | None = None
    for command, cwd in attempts:
        result = _run(command, cwd=cwd)
        results.append(result)
        if result.get("ok"):
            selected = result
            break

    commit = None
    if repo and (repo / ".git").exists():
        git_result = _run(["git", "rev-parse", "HEAD"], cwd=repo)
        if git_result.get("ok"):
            commit = git_result.get("stdout_tail")

    return {
        "ok": selected is not None,
        "repo": str(repo) if repo else None,
        "commit": commit,
        "selected": selected,
        "attempts": results,
    }


def build_report() -> dict[str, Any]:
    ollama = inspect_ollama()
    hermes = inspect_hermes()
    external_env_names = [name for name in KNOWN_EXTERNAL_KEYS if os.environ.get(name)]

    ready = bool(ollama.get("ok") and ollama.get("models") and hermes.get("ok"))
    return {
        "schema_version": "bench.preflight.v1",
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "ready" if ready else "blocked",
        "local_only": len(external_env_names) == 0,
        "external_api_env_names_present": external_env_names,
        "environment": {
            "runner_name": os.environ.get("RUNNER_NAME"),
            "os": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": sys.version,
            "cpu_count": os.cpu_count(),
        },
        "ollama": ollama,
        "hermes": hermes,
        "blocking_reasons": [
            reason
            for condition, reason in (
                (not ollama.get("ok"), "ollama_unreachable"),
                (ollama.get("ok") and not ollama.get("models"), "no_ollama_models"),
                (not hermes.get("ok"), "hermes_unavailable"),
                (external_env_names, "external_api_environment_present"),
            )
            if condition
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory the local-only benchmark environment.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = build_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "ready" and report["local_only"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

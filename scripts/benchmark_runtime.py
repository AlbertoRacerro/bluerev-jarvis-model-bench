from __future__ import annotations

import json
import os
import shutil
import signal
import stat
import subprocess
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

EXTERNAL_ENV_NAMES = frozenset(
    {
        "ALIBABA_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "ANTHROPIC_TOKEN",
        "AWS_ACCESS_KEY_ID", "AWS_PROFILE", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
        "AZURE_API_KEY", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT",
        "BRAVE_API_KEY", "BROWSERBASE_API_KEY", "BROWSER_USE_API_KEY",
        "CLAUDE_CODE_OAUTH_TOKEN", "COHERE_API_KEY", "DASHSCOPE_API_KEY",
        "DAYTONA_API_KEY", "DEEPSEEK_API_KEY", "DISCORD_BOT_TOKEN",
        "ELEVENLABS_API_KEY", "EXA_API_KEY", "FAL_KEY", "FIRECRAWL_API_KEY",
        "FIREWORKS_API_KEY", "GEMINI_API_KEY", "GH_TOKEN", "GITHUB_TOKEN",
        "GLM_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY", "HF_TOKEN",
        "HONCHO_API_KEY", "HUGGINGFACE_API_KEY", "KILO_API_KEY", "KIMI_API_KEY",
        "MINIMAX_API_KEY", "MISTRAL_API_KEY", "NOUS_API_KEY", "NOVITA_API_KEY",
        "NVIDIA_API_KEY", "OLLAMA_API_KEY", "OLLAMA_BASE_URL", "OLLAMA_HOST",
        "OLLAMA_TAGS_URL", "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENCODE_API_KEY",
        "OPENROUTER_API_KEY", "OPENROUTER_BASE_URL", "SLACK_APP_TOKEN",
        "SLACK_BOT_TOKEN", "STEPFUN_API_KEY", "TAVILY_API_KEY", "TELEGRAM_BOT_TOKEN",
        "TOGETHER_API_KEY", "TOKENHUB_API_KEY", "WHATSAPP_ENABLED", "XAI_API_KEY",
        "XIAOMI_API_KEY", "ZAI_API_KEY",
    }
)
PROXY_ENV_NAMES = frozenset(
    {"ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "all_proxy", "http_proxy", "https_proxy", "no_proxy"}
)
REMOVED_ENV_REPORT = "BENCH_REMOVED_EXTERNAL_ENV_NAMES"
_SECRET_FRAGMENTS = ("API_KEY", "OAUTH_TOKEN", "ACCESS_TOKEN", "AUTH_TOKEN", "BOT_TOKEN")
_SECRET_SUFFIXES = ("_TOKEN", "_SECRET", "_PASSWORD", "_CREDENTIALS", "_BASE_URL", "_ENDPOINT")


def _is_external_environment_name(name: str) -> bool:
    upper = name.upper()
    return (
        upper in EXTERNAL_ENV_NAMES
        or any(fragment in upper for fragment in _SECRET_FRAGMENTS)
        or upper.endswith(_SECRET_SUFFIXES)
    )


def external_env_names(environment: Mapping[str, str]) -> list[str]:
    return sorted(
        {name.upper() for name, value in environment.items() if value and _is_external_environment_name(name)}
    )


def sanitize_environment(
    environment: Mapping[str, str], *, hermes_home: Path | None = None
) -> tuple[dict[str, str], list[str]]:
    result = dict(environment)
    removed = external_env_names(result)
    proxy_names = {name.upper() for name in PROXY_ENV_NAMES}
    for name in list(result):
        if _is_external_environment_name(name) or name.upper() in proxy_names:
            result.pop(name, None)
    result["NO_PROXY"] = "*"
    result["no_proxy"] = "*"
    result["PYTHONUTF8"] = "1"
    result["PYTHONIOENCODING"] = "utf-8"
    result[REMOVED_ENV_REPORT] = json.dumps(removed, separators=(",", ":"))
    if hermes_home is not None:
        result["HERMES_HOME"] = str(hermes_home.resolve())
    return result, removed


@contextmanager
def isolated_process_environment(environment: Mapping[str, str]) -> Iterator[None]:
    original = dict(os.environ)
    try:
        os.environ.clear()
        os.environ.update(environment)
        yield
    finally:
        os.environ.clear()
        os.environ.update(original)


def parse_removed_environment_report(environment: Mapping[str, str]) -> list[str]:
    raw = environment.get(REMOVED_ENV_REPORT, "[]")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return ["invalid_sanitization_report"]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return ["invalid_sanitization_report"]
    return sorted(set(value))


def _remove_readonly(function, path: str, _exc_info) -> None:  # type: ignore[no-untyped-def]
    os.chmod(path, stat.S_IWRITE)
    function(path)


def safe_reset_directory(target: Path, *, allowed_root: Path) -> Path:
    root = allowed_root.resolve()
    resolved = target.resolve()
    if resolved == root or root not in resolved.parents:
        raise ValueError(f"refusing to reset path outside allowed root: {target}")
    if target.exists() or target.is_symlink():
        if target.is_symlink():
            target.unlink()
        else:
            shutil.rmtree(target, onerror=_remove_readonly)
    target.mkdir(parents=True, exist_ok=False)
    return target


def _text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _kill_process_tree(process: subprocess.Popen[str]) -> bool:
    if process.poll() is not None:
        return True
    if os.name == "nt":
        killed = subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        if killed.returncode != 0 and process.poll() is None:
            process.kill()
        return process.wait(timeout=30) is not None
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return process.wait(timeout=30) is not None


def run_captured(
    name: str,
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    artifact_dir: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    stdout = ""
    stderr = ""
    timed_out = False
    error_type: str | None = None
    tree_kill_succeeded: bool | None = None
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    try:
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            env=dict(environment),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
            exit_code = process.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            error_type = "TimeoutExpired"
            tree_kill_succeeded = _kill_process_tree(process)
            stdout, stderr = process.communicate()
            exit_code = 124
    except (OSError, subprocess.SubprocessError) as exc:
        exit_code = 127
        error_type = type(exc).__name__
        stderr = f"{type(exc).__name__}: {exc}"

    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / f"{name}.stdout.log").write_text(_text(stdout), encoding="utf-8")
    (artifact_dir / f"{name}.stderr.log").write_text(_text(stderr), encoding="utf-8")
    (artifact_dir / f"{name}.exit").write_text(f"{exit_code}\n", encoding="utf-8")
    return {
        "command": list(command),
        "exit_code": exit_code,
        "timeout_seconds": timeout_seconds,
        "timed_out": timed_out,
        "error_type": error_type,
        "tree_kill_succeeded": tree_kill_succeeded,
    }

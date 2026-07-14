from __future__ import annotations

import json
import math
import os
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROFILES_PATH = ROOT / "config/bench2r-hermes-optimization-profiles.json"
SKILL_PATH = (
    ROOT
    / "fixtures/bench-2r/hermes-skills/bounded-tool-orchestration/SKILL.md"
)
SKILL_NAME = "bounded-tool-orchestration"
_PARAMETER_ORDER = (
    "temperature",
    "top_p",
    "top_k",
    "min_p",
    "repeat_penalty",
)


class Bench2ROptimizationError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Bench2ROptimizationError(
            f"cannot read {path}: {type(exc).__name__}"
        ) from exc
    if not isinstance(value, dict):
        raise Bench2ROptimizationError(f"{path} must contain a JSON object")
    return value


def load_profiles(path: Path = PROFILES_PATH) -> dict[str, Any]:
    return _load_object(path)


def profile_by_candidate(
    candidate_id: str,
    *,
    profiles_path: Path = PROFILES_PATH,
) -> dict[str, Any]:
    document = load_profiles(profiles_path)
    matches = [
        item
        for item in document.get("candidate_profiles", [])
        if isinstance(item, dict) and item.get("candidate_id") == candidate_id
    ]
    if len(matches) != 1:
        raise Bench2ROptimizationError(
            f"candidate profile missing or duplicated: {candidate_id}"
        )
    return matches[0]


def seed_for(
    phase: str,
    repetition: int,
    *,
    profiles_path: Path = PROFILES_PATH,
) -> int:
    if repetition < 1:
        raise Bench2ROptimizationError("repetition must be at least 1")
    document = load_profiles(profiles_path)
    seeds = document.get("seed_policy", {}).get(phase)
    if not isinstance(seeds, list) or not seeds:
        raise Bench2ROptimizationError(f"seed phase is missing: {phase}")
    if repetition > len(seeds):
        raise Bench2ROptimizationError(
            f"repetition {repetition} exceeds seed count for {phase}"
        )
    seed = seeds[repetition - 1]
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise Bench2ROptimizationError(f"invalid seed for {phase}: {seed!r}")
    return seed


def _parameter_value(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Bench2ROptimizationError(
            f"Ollama parameter must be a finite number: {value!r}"
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise Bench2ROptimizationError(
            f"Ollama parameter must be finite: {value!r}"
        )
    return str(value).lower()


def build_modelfile(
    profile: dict[str, Any],
    *,
    seed: int,
    context_length: int = 65536,
    source_model: str | None = None,
) -> str:
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise Bench2ROptimizationError("seed must be a non-negative integer")
    if not isinstance(context_length, int) or context_length < 1:
        raise Bench2ROptimizationError("context_length must be a positive integer")
    source = source_model or profile.get("model_tag")
    if not isinstance(source, str) or not source.strip():
        raise Bench2ROptimizationError("profile model_tag is missing")
    sampling = profile.get("sampling")
    if not isinstance(sampling, dict) or not sampling:
        raise Bench2ROptimizationError("profile sampling is missing")
    max_output = profile.get("max_output_tokens")
    if not isinstance(max_output, int) or isinstance(max_output, bool) or max_output < 1:
        raise Bench2ROptimizationError("max_output_tokens must be a positive integer")

    lines = [
        f"FROM {source}",
        f"PARAMETER num_ctx {context_length}",
    ]
    for name in _PARAMETER_ORDER:
        if name in sampling:
            lines.append(f"PARAMETER {name} {_parameter_value(sampling[name])}")
    lines.extend(
        [
            f"PARAMETER seed {seed}",
            f"PARAMETER num_predict {max_output}",
        ]
    )
    return "\n".join(lines) + "\n"


def case_max_turns(case: dict[str, Any]) -> int:
    limits = case.get("limits")
    value = limits.get("max_model_calls") if isinstance(limits, dict) else None
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 16:
        raise Bench2ROptimizationError(
            "case limits.max_model_calls must be an integer from 1 to 16"
        )
    return value


def _yaml_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def render_hermes_config(
    *,
    profile: dict[str, Any],
    case: dict[str, Any],
    runtime_model: str,
    workdir: Path,
) -> str:
    max_output = profile.get("max_output_tokens")
    if not isinstance(max_output, int) or isinstance(max_output, bool) or max_output < 1:
        raise Bench2ROptimizationError("max_output_tokens must be a positive integer")
    max_turns = case_max_turns(case)
    return "\n".join(
        [
            "model:",
            f"  default: {_yaml_quote(runtime_model)}",
            "  provider: 'custom'",
            "  api_key: 'local-only-not-secret'",
            "  base_url: 'http://127.0.0.1:11434/v1'",
            "  api_mode: 'chat_completions'",
            "  context_length: 65536",
            "  ollama_num_ctx: 65536",
            f"  max_tokens: {max_output}",
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
            f"  max_turns: {max_turns}",
            "  save_trajectories: true",
            "display:",
            "  interface: 'cli'",
            "",
        ]
    )


def install_bounded_skill(
    hermes_home: Path,
    *,
    source_path: Path = SKILL_PATH,
) -> Path:
    if not source_path.is_file():
        raise Bench2ROptimizationError(f"skill source is missing: {source_path}")
    target = hermes_home / "skills" / SKILL_NAME / "SKILL.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, target)
    return target


def expand_bounded_skill_prompt(task_prompt: str) -> str:
    """Expand the installed skill through Hermes' pinned slash-skill machinery.

    HERMES_HOME must already point to the isolated per-run profile and the skill
    must already have been installed there. This function intentionally fails
    closed instead of silently treating a slash command as ordinary prompt text.
    """
    if not isinstance(task_prompt, str) or not task_prompt.strip():
        raise Bench2ROptimizationError("task_prompt must be non-empty")
    try:
        from agent.skill_commands import (  # type: ignore[import-not-found]
            build_skill_invocation_message,
            scan_skill_commands,
        )
    except ImportError as exc:
        raise Bench2ROptimizationError(
            "pinned Hermes skill command module is unavailable"
        ) from exc

    scan_skill_commands()
    expanded = build_skill_invocation_message(
        f"/{SKILL_NAME}",
        user_instruction=task_prompt,
    )
    if not isinstance(expanded, str) or not expanded.strip():
        home = os.environ.get("HERMES_HOME", "")
        raise Bench2ROptimizationError(
            f"Hermes did not expand {SKILL_NAME!r} in HERMES_HOME={home!r}"
        )
    return expanded

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
PROFILES_PATH = ROOT / "config/bench2r-hermes-optimization-profiles.json"
MARKER_PATH = ROOT / "config/bench2r-hermes-preflight-marker.json"
PLAN_PATH = ROOT / "fixtures/bench-plans/bench2r-hermes-optimization-plan.json"
REGISTRY_PATH = ROOT / "candidates/bench2-h4-eligible.json"
SKILL_PATH = (
    ROOT
    / "fixtures/bench-2r/hermes-skills/bounded-tool-orchestration/SKILL.md"
)

EXPECTED_HERMES = {
    "commit_sha": "73b611ad19720d70308dad6b0fb64648aaadc216",
    "version": "0.18.2",
}
EXPECTED_CANDIDATES = {
    "gemma4-12b-it-qat": (
        "gemma4:12b-it-qat",
        "38044be4f923e5a55264ed7df4eaac2676651a905f735197c504045140c02bd3",
    ),
    "qwable-9b-fable5": (
        "hf.co/empero-ai/Qwable-9B-Claude-Fable-5-GGUF:Q4_K_M",
        "6e3590af5e19106c55a25aec936d7e55a0d23b602bb276ad32321f8a49a3c1d0",
    ),
    "qwythos-mythos-9b": (
        "hf.co/empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF:Q4_K_M",
        "7c3d0c28e4db742c4c6cd2925627acb09b610faec86a32ac872190aee8bc67d0",
    ),
    "minicpm5-fable-1b-control": (
        "hf.co/GnLOLot/MiniCPM5-1B-Claude-Opus-Fable5-Thinking-GGUF:Q4_K_M",
        "9273fd7794224d33f1ce2364c395df1eeb049e56705d635b29cfc51dfd6d157e",
    ),
    "gemma4-fable-agentic-12b": (
        "hf.co/yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF:Q4_K_M",
        "036489398bf6af6874783c754592a90f12a036b20cbbf47a867a3ac938868aff",
    ),
    "gemma4-fable-coder-12b": (
        "hf.co/yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M",
        "5434f64afb3f2b49f0c8d5e6950313a119303b6dbea21ce542e1f82122427391",
    ),
    "qwythos-hermes-64k": (
        "qwythos-hermes-64k:latest",
        "466701318bae40cfcf42682a17dc8b5a1e2e99a19fb157cdc0cd09a2abc7a991",
    ),
    "qwythos-hermes-safe": (
        "qwythos-hermes-safe:latest",
        "f1b4ecbbe67a7adef8f8f975cdbfb3eb08a04b8d91737b2b96e7b761187c668d",
    ),
}
FORBIDDEN_SKILL_LITERALS = {
    "alpha-7",
    "BRAVO-19",
    "stable-result",
    "bench_lookup",
    "bench_distractor",
}
NON_GREEDY_REQUIRED = {
    "qwable-9b-fable5",
    "qwythos-mythos-9b",
    "minicpm5-fable-1b-control",
    "qwythos-hermes-64k",
    "qwythos-hermes-safe",
}


class Bench2RValidationError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Bench2RValidationError(
            f"cannot read {path}: {type(exc).__name__}"
        ) from exc
    if not isinstance(value, dict):
        raise Bench2RValidationError(f"{path} must contain an object")
    return value


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _validate_registry() -> dict[str, tuple[str, str]]:
    registry = _load(REGISTRY_PATH)
    items = registry.get("candidates")
    if not isinstance(items, list) or len(items) != len(EXPECTED_CANDIDATES):
        raise Bench2RValidationError("frozen BENCH-2 registry inventory drifted")
    observed: dict[str, tuple[str, str]] = {}
    for item in items:
        if not isinstance(item, dict):
            raise Bench2RValidationError("registry candidate must be an object")
        candidate_id = item.get("candidate_id")
        model_tag = item.get("model_tag")
        digest = item.get("digest")
        if not all(isinstance(value, str) for value in (candidate_id, model_tag, digest)):
            raise Bench2RValidationError("registry candidate identity is incomplete")
        observed[candidate_id] = (model_tag, digest)
    if observed != EXPECTED_CANDIDATES:
        raise Bench2RValidationError("optimization candidates differ from frozen BENCH-2")
    return observed


def _validate_profiles(registry: dict[str, tuple[str, str]]) -> None:
    document = _load(PROFILES_PATH)
    if document.get("schema_version") != "bench.hermes-optimization-profiles.v1":
        raise Bench2RValidationError("profile schema is invalid")
    if document.get("hermes") != EXPECTED_HERMES:
        raise Bench2RValidationError("Hermes identity drifted")
    if document.get("context_length") != 65536:
        raise Bench2RValidationError("context length drifted")
    if document.get("seed_policy") != {
        "admission": [17, 42, 314159],
        "tuning": [42],
    }:
        raise Bench2RValidationError("seed policy drifted")
    policy = document.get("profile_policy")
    required_policy = {
        "blanket_greedy_decoding_allowed": False,
        "producer_documentation_preferred": True,
        "runtime_alias_parameters_must_be_attested": True,
        "silent_model_substitution_allowed": False,
    }
    if policy != required_policy:
        raise Bench2RValidationError("profile policy drifted")

    profiles = document.get("candidate_profiles")
    if not isinstance(profiles, list) or len(profiles) != len(registry):
        raise Bench2RValidationError("candidate profile inventory is incomplete")
    seen: set[str] = set()
    for profile in profiles:
        if not isinstance(profile, dict):
            raise Bench2RValidationError("candidate profile must be an object")
        candidate_id = profile.get("candidate_id")
        if not isinstance(candidate_id, str) or candidate_id in seen:
            raise Bench2RValidationError("candidate profile identity is invalid")
        seen.add(candidate_id)
        expected = registry.get(candidate_id)
        if expected is None:
            raise Bench2RValidationError(f"unknown candidate profile: {candidate_id}")
        if (profile.get("model_tag"), profile.get("digest")) != expected:
            raise Bench2RValidationError(f"candidate binding drifted: {candidate_id}")
        parsed = urlparse(str(profile.get("source_url") or ""))
        if parsed.scheme != "https" or not parsed.netloc:
            raise Bench2RValidationError(f"source URL is invalid: {candidate_id}")
        if profile.get("profile_basis") not in {
            "producer_model_card",
            "observed_runtime_alias_and_upstream_model_card",
        }:
            raise Bench2RValidationError(f"profile basis is invalid: {candidate_id}")
        max_output = profile.get("max_output_tokens")
        if not isinstance(max_output, int) or isinstance(max_output, bool) or max_output < 1:
            raise Bench2RValidationError(f"output limit is invalid: {candidate_id}")
        sampling = profile.get("sampling")
        if not isinstance(sampling, dict) or not sampling:
            raise Bench2RValidationError(f"sampling is missing: {candidate_id}")
        if any(not _finite_number(value) for value in sampling.values()):
            raise Bench2RValidationError(f"sampling is non-finite: {candidate_id}")
        temperature = sampling.get("temperature")
        if not _finite_number(temperature) or float(temperature) < 0:
            raise Bench2RValidationError(f"temperature is invalid: {candidate_id}")
        if candidate_id in NON_GREEDY_REQUIRED and float(temperature) <= 0.3:
            raise Bench2RValidationError(
                f"producer non-greedy requirement violated: {candidate_id}"
            )
    if seen != set(registry):
        raise Bench2RValidationError("candidate profile set is incomplete")


def _validate_skill() -> None:
    try:
        text = SKILL_PATH.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise Bench2RValidationError("optimization skill is unreadable") from exc
    if "name: bounded-tool-orchestration" not in text:
        raise Bench2RValidationError("optimization skill identity is invalid")
    if any(literal.casefold() in text.casefold() for literal in FORBIDDEN_SKILL_LITERALS):
        raise Bench2RValidationError("optimization skill contains benchmark literals")
    required_phrases = {
        "already present and verified",
        "Never invent",
        "minimum number of tool calls",
        "treat the task as terminal",
        "Stop immediately",
    }
    if any(phrase not in text for phrase in required_phrases):
        raise Bench2RValidationError("optimization skill contract is incomplete")


def _validate_plan_and_marker() -> None:
    plan = _load(PLAN_PATH)
    marker = _load(MARKER_PATH)
    if plan.get("schema_version") != "bench.hermes-optimization-plan.v1":
        raise Bench2RValidationError("optimization plan schema is invalid")
    if plan.get("status") != "design_ready_execution_disabled":
        raise Bench2RValidationError("optimization plan status is unsafe")
    arms = plan.get("arms")
    if not isinstance(arms, list) or [item.get("arm_id") for item in arms] != [
        "profile_only",
        "profile_plus_skill",
    ]:
        raise Bench2RValidationError("optimization arms drifted")
    execution = plan.get("execution")
    if not isinstance(execution, dict):
        raise Bench2RValidationError("optimization execution contract is missing")
    required_true = {
        "local_only",
        "native_trajectory_required",
        "wire_request_trace_required_before_admission",
    }
    if any(execution.get(key) is not True for key in required_true):
        raise Bench2RValidationError("optimization evidence boundary is incomplete")
    if execution.get("external_providers_allowed") is not False:
        raise Bench2RValidationError("external providers became allowed")
    if execution.get("jarvisos_access_allowed") is not False:
        raise Bench2RValidationError("JarvisOS access became allowed")
    promotion = plan.get("promotion_policy")
    if not isinstance(promotion, dict):
        raise Bench2RValidationError("promotion policy is missing")
    if promotion.get("model_weight_update_allowed_in_this_plan") is not False:
        raise Bench2RValidationError("weight updates became allowed")
    if promotion.get("silent_candidate_substitution_allowed") is not False:
        raise Bench2RValidationError("silent candidate substitution became allowed")
    expected_marker = {
        "enabled": False,
        "plan_path": "fixtures/bench-plans/bench2r-hermes-optimization-plan.json",
        "schema_version": "bench.hermes-optimization-preflight-marker.v1",
    }
    if marker != expected_marker:
        raise Bench2RValidationError("preflight marker is not the reviewed disabled marker")


def validate() -> dict[str, Any]:
    registry = _validate_registry()
    _validate_profiles(registry)
    _validate_skill()
    _validate_plan_and_marker()
    return {
        "candidate_count": len(registry),
        "execution_authorized": False,
        "hermes": EXPECTED_HERMES,
        "profile_arms": ["profile_only", "profile_plus_skill"],
        "schema_version": "bench.hermes-optimization-validation.v1",
        "status": "ready_for_review",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the disabled BENCH-2R Hermes optimization design."
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        payload = validate()
        code = 0
    except (
        Bench2RValidationError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        payload = {
            "error": str(exc),
            "error_type": type(exc).__name__,
            "execution_authorized": False,
            "schema_version": "bench.hermes-optimization-validation.v1",
            "status": "invalid",
        }
        code = 2
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "fixtures" / "bench-plans" / "bench2-hermes-orchestrator-isolation-v1.json"
EXPECTED_PLAN_SHA256 = "9d6a3ea722b536a2a535186f5ef10632c34a0817bad0a511a250721c100a8ddd"
EXPECTED_PRIMARY = [
    "gemma4-12b-it-qat",
    "qwythos-mythos-9b",
    "qwen3.6-fablevibes-14b-a3b",
    "qwythos-hermes-64k",
    "qwythos-hermes-safe",
]
EXPECTED_CONTROL = "minicpm5-fable-1b-control"
EXPECTED_STAGES = ["B2-PRE-0", "B2-PRE-1", "B2-CAL", "B2-CORE"]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class Bench2PlanError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Bench2PlanError(f"cannot read plan: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise Bench2PlanError("plan must contain an object")
    return value


def _source_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _canonical_json_sha256(path: Path) -> str:
    value = _load_json(path)
    encoded = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise Bench2PlanError(f"{label} must be canonical SHA-256")


def validate_plan(path: Path = PLAN_PATH) -> dict[str, Any]:
    if _source_sha256(path) != EXPECTED_PLAN_SHA256:
        raise Bench2PlanError("BENCH-2 plan digest mismatch")
    plan = _load_json(path)

    if plan.get("schema_version") != "bench.hermes-orchestrator-isolation-plan.v1":
        raise Bench2PlanError("unsupported BENCH-2 plan schema")
    if plan.get("status") != "review_ready":
        raise Bench2PlanError("BENCH-2 plan must remain review_ready")
    if plan.get("scope") != "BENCH-2 Hermes orchestrator isolation":
        raise Bench2PlanError("BENCH-2 scope drifted")
    if plan.get("execution_authorized") is not False:
        raise Bench2PlanError("this plan revision must not authorize execution")

    expected_sources = {
        "bench1_closeout": (
            "reports/BENCH-1-DIRECT-SEMANTIC-CLOSEOUT/summary.json",
            "73bf484b067b9d2ae884b348a4174aac2141ac41f30ebb2fa2c77ddce2f7f815",
            None,
        ),
        "h3_summary": (
            "reports/H3-PRIMARY-32K/summary.json",
            "4e92a93269f3c574c86224f24535122aa14e1976508adeac69a49ea6fdf3bfcf",
            None,
        ),
        "candidate_registry": (
            "candidates/bench1-h3-primary.json",
            "f370a0e87e7693d03a7ba9e074217a5e88641a5ea08d698a86211216bf84e750",
            "canonical_json",
        ),
    }
    sources = plan.get("sources")
    if not isinstance(sources, dict) or set(sources) != set(expected_sources):
        raise Bench2PlanError("BENCH-2 source inventory drifted")
    for name, (expected_path, expected_digest, expected_mode) in expected_sources.items():
        source = sources.get(name)
        if not isinstance(source, dict):
            raise Bench2PlanError(f"{name} source is invalid")
        if source.get("path") != expected_path or source.get("sha256") != expected_digest:
            raise Bench2PlanError(f"{name} source binding drifted")
        _sha(source["sha256"], f"{name} digest")
        if expected_mode is None:
            if set(source) != {"path", "sha256"}:
                raise Bench2PlanError(f"{name} source fields drifted")
        elif source.get("digest_mode") != expected_mode or set(source) != {
            "path",
            "sha256",
            "digest_mode",
        }:
            raise Bench2PlanError(f"{name} digest mode drifted")

    baseline = plan.get("baseline")
    if not isinstance(baseline, dict) or baseline.get("status") != "unresolved":
        raise Bench2PlanError("Hermes baseline must remain unresolved")
    if baseline.get("required_gate") != "hermes":
        raise Bench2PlanError("Hermes preflight gate is not required")
    expected_requirements = {
        "fresh_preflight",
        "same_benchmark_sha_as_execution",
        "scoring_ready_true",
        "local_only_true",
        "clean_hermes_worktree",
        "hermes_commit_and_version_bound",
        "git_bash_ready_on_windows",
        "preflight_artifact_sha256_bound",
    }
    if set(baseline.get("requirements") or []) != expected_requirements:
        raise Bench2PlanError("Hermes baseline requirements weakened")
    binding = baseline.get("binding")
    if not isinstance(binding, dict) or any(value is not None for value in binding.values()):
        raise Bench2PlanError("unreviewed Hermes baseline data was embedded")

    candidates = plan.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 6:
        raise Bench2PlanError("candidate set must contain five primaries and one control")
    if [item.get("sequence") for item in candidates] != list(range(6)):
        raise Bench2PlanError("candidate sequence drifted")
    if [item.get("candidate_id") for item in candidates[:5]] != EXPECTED_PRIMARY:
        raise Bench2PlanError("primary candidate identities drifted")
    if candidates[5].get("candidate_id") != EXPECTED_CONTROL:
        raise Bench2PlanError("negative control identity drifted")
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict) or set(candidate) != {
            "sequence",
            "candidate_id",
            "model_tag",
            "digest",
            "role",
        }:
            raise Bench2PlanError(f"candidate {index} fields drifted")
        _sha(candidate["digest"], f"candidate {index} digest")
        expected_role = "primary" if index < 5 else "negative_control"
        if candidate["role"] != expected_role:
            raise Bench2PlanError(f"candidate {index} role drifted")

    isolation = plan.get("isolation")
    if not isinstance(isolation, dict) or isolation.get("only_orchestrator_model_varies") is not True:
        raise Bench2PlanError("orchestrator isolation weakened")
    if set(isolation.get("fixed") or []) != {
        "hermes_commit",
        "hermes_config",
        "system_prompt",
        "skills",
        "worker_pool",
        "tools",
        "workspace_snapshot",
        "cases",
        "validators",
        "generation_profile",
        "cleanup_policy",
    }:
        raise Bench2PlanError("fixed orchestration dimensions drifted")

    safety = plan.get("safety")
    if not isinstance(safety, dict):
        raise Bench2PlanError("safety contract missing")
    required_true = {
        "local_models_only",
        "disposable_workspaces_only",
        "trusted_main_only",
    }
    required_false = {
        "external_providers",
        "external_network",
        "credentials",
        "secrets",
        "jarvisos_access",
        "unrelated_user_state",
        "pull_request_code_on_self_hosted_runner",
    }
    if any(safety.get(key) is not True for key in required_true):
        raise Bench2PlanError("required safety guarantee weakened")
    if any(safety.get(key) is not False for key in required_false):
        raise Bench2PlanError("forbidden capability enabled")
    if safety.get("max_parallel_models") != 1:
        raise Bench2PlanError("BENCH-2 must remain serial")

    stages = plan.get("stages")
    if not isinstance(stages, list) or [item.get("id") for item in stages] != EXPECTED_STAGES:
        raise Bench2PlanError("stage order drifted")
    if stages[0].get("model_calls") is not False or stages[1].get("model_calls") is not False:
        raise Bench2PlanError("pre-execution gates must not call models")
    calibration = stages[2]
    if (
        calibration.get("worker_pool") != "deterministic_fixture_workers"
        or calibration.get("candidates") != 6
        or calibration.get("cases") != 3
        or calibration.get("repetitions") != 1
        or calibration.get("total_runs") != 18
        or calibration.get("comparative") is not False
    ):
        raise Bench2PlanError("calibration matrix drifted")
    core = stages[3]
    if (
        core.get("worker_pool") != "fixed_local_models"
        or core.get("primary_candidates") != 5
        or core.get("negative_controls") != 1
        or core.get("cases_minimum") != 4
        or core.get("repetitions") != 3
        or core.get("total_runs_minimum") != 72
        or core.get("comparative") is not True
    ):
        raise Bench2PlanError("core comparison contract drifted")
    if "new_reviewed_plan_with_execution_authorized_true" not in core.get(
        "blocked_until", []
    ):
        raise Bench2PlanError("future explicit authorization boundary missing")

    cases = plan.get("calibration_cases")
    if [item.get("case_id") for item in cases or []] != [
        "b2-ho-stop-noop-001",
        "b2-ho-delegate-single-worker-001",
        "b2-ho-critic-disagreement-001",
    ]:
        raise Bench2PlanError("calibration case inventory drifted")

    expected_profile = {
        "context_tokens": 32768,
        "temperature": 0,
        "seed": 4242,
        "max_output_tokens": 2048,
        "max_worker_calls": 2,
        "max_critic_calls": 1,
        "max_tool_calls": 2,
        "max_retries": 1,
        "max_parallel_workers": 1,
        "timeout_seconds": 600,
        "cleanup_before_each_run": True,
        "cleanup_after_each_run": True,
    }
    if plan.get("profile") != expected_profile:
        raise Bench2PlanError("fixed profile drifted")

    artifacts = plan.get("required_artifacts")
    required_artifacts = {
        "baseline_preflight.json",
        "hermes_config_snapshot.json",
        "workspace_manifest.json",
        "candidate_binding.json",
        "raw_hermes_stdout.log",
        "raw_hermes_stderr.log",
        "hermes_trace.json",
        "worker_trace.json",
        "tool_trace.json",
        "validator_result.json",
        "cleanup.json",
        "manifest.json",
    }
    if (
        not isinstance(artifacts, list)
        or len(artifacts) != len(set(artifacts))
        or not required_artifacts.issubset(set(artifacts))
    ):
        raise Bench2PlanError("required evidence inventory weakened")

    blockers = plan.get("authorization_blockers")
    if not isinstance(blockers, list) or set(blockers) != {
        "fresh_same_sha_hermes_preflight",
        "deterministic_adapter_contract",
        "fixture_workers_and_digests",
        "calibration_cases_and_validators",
        "fixed_local_worker_pool",
        "held_out_core_cases",
        "new_reviewed_authorizing_plan",
    }:
        raise Bench2PlanError("authorization blockers drifted")

    promotion = plan.get("promotion")
    if not isinstance(promotion, dict) or promotion != {
        "role_recommendations_allowed": True,
        "automatic_hermes_change": False,
        "automatic_jarvisos_change": False,
        "automatic_model_assignment": False,
        "held_out_replay_before_professional_grade": True,
    }:
        raise Bench2PlanError("promotion boundary weakened")
    return plan


def main() -> int:
    validate_plan()
    print(f"BENCH-2 plan contract passed; sha256={EXPECTED_PLAN_SHA256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

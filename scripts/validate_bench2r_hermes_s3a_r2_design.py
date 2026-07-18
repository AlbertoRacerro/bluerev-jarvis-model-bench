from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "fixtures/bench-plans/bench2r-hermes-s3a-r2-design.json"
AUDIT_PATH = ROOT / "reports/BENCH-2R-HERMES-S3A-RUNNER-AUDIT/summary.json"
CANDIDATE_SKILL_PATH = ROOT / "fixtures/bench-2r/hermes-skills/bounded-tool-orchestration-v1.3-candidate/SKILL.md"
CONTROL_SKILL_PATH = ROOT / "fixtures/bench-2r/hermes-skills/bounded-tool-orchestration-v1.2-candidate/SKILL.md"
S3A_MARKER_PATH = ROOT / "config/bench2r-hermes-s3a-marker.json"
R1_MARKER_PATH = ROOT / "config/bench2r-hermes-s3a-r1-repair-marker.json"
FORBIDDEN_WORKFLOW_PATH = ROOT / ".github/workflows/bench2r-hermes-s3a-r2-canary.yml"

NORMATIVE_OBJECT = '{"actions":[{"type":"call_tool","tool":"registry.lookup","args":{"key":"missing"}},{"type":"stop"}]}'
PRIOR_SEEDS = {17, 42, 271828, 314159, 8675309, 371872, 665465, 623659}


class HermesS3AR2DesignError(RuntimeError):
    pass


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicates,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise HermesS3AR2DesignError(
            f"cannot read {path}: {type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise HermesS3AR2DesignError(f"{path} must contain an object")
    return value


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise HermesS3AR2DesignError(
            f"cannot read {path}: {type(exc).__name__}: {exc}"
        ) from exc


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HermesS3AR2DesignError(message)


def _git_blob_sha(text: str) -> str:
    payload = text.encode("utf-8")
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def validate() -> dict[str, Any]:
    plan = _load(PLAN_PATH)
    audit = _load(AUDIT_PATH)
    candidate = _read(CANDIDATE_SKILL_PATH)
    control = _read(CONTROL_SKILL_PATH)
    s3a_marker = _load(S3A_MARKER_PATH)
    r1_marker = _load(R1_MARKER_PATH)

    _require(
        plan.get("schema_version") == "bench.hermes-s3a-r2-design.v1",
        "R2 design schema drifted",
    )
    _require(
        plan.get("status") == "static_design_ready_execution_not_implemented",
        "R2 design status drifted",
    )

    _require(
        audit.get("schema_version") == "bench.hermes-s3a-runner-audit.v1",
        "runner audit schema drifted",
    )
    decision = audit.get("decision")
    totals = audit.get("job_totals")
    _require(isinstance(decision, dict), "runner audit decision missing")
    _require(isinstance(totals, dict), "runner audit totals missing")
    _require(decision.get("rerun_performed") is False, "audit claims a rerun")
    _require(decision.get("rerunnable_job_ids") == [], "audit leaves rerunnable jobs")
    _require(totals.get("rerunnable") == 0, "audit rerunnable count drifted")
    _require(totals.get("C") == 0, "audit invents Ollama-unavailable failures")

    arms = plan.get("arms")
    _require(isinstance(arms, list) and len(arms) == 2, "R2 arms drifted")
    control_arm, candidate_arm = arms
    _require(control_arm.get("arm_id") == "control_v1_2", "R2 control arm drifted")
    _require(candidate_arm.get("arm_id") == "candidate_v1_3", "R2 candidate arm drifted")
    _require(
        control_arm.get("skill_git_blob_sha") == _git_blob_sha(control),
        "v1.2 control skill blob drifted",
    )
    _require(
        candidate_arm.get("skill_git_blob_sha") == _git_blob_sha(candidate),
        "v1.3 candidate skill blob drifted",
    )

    _require("version: 1.3.0" in candidate, "v1.3 version missing")
    _require("```" not in candidate, "v1.3 contains a Markdown fence")
    _require(candidate.count(NORMATIVE_OBJECT) == 1, "v1.3 normative object drifted")
    for phrase in (
        "Character 1 of the response MUST be `{`.",
        "The final character of the response MUST be `}`.",
        "Do not emit backticks.",
        "A written label such as `call_tool` is data, not a tool invocation.",
        "The terminal `stop` action must remain",
    ):
        _require(phrase in candidate, f"v1.3 required rule missing: {phrase}")

    seed_policy = plan.get("seed_policy")
    counts = plan.get("counts")
    _require(isinstance(seed_policy, dict), "R2 seed policy missing")
    _require(isinstance(counts, dict), "R2 counts missing")
    seeds = seed_policy.get("canary_seeds")
    _require(seeds == [849690, 603823], "R2 canary seeds drifted")
    _require(not (set(seeds) & PRIOR_SEEDS), "R2 reuses an S3A or R1 seed")

    expected_paired = (
        counts.get("arms")
        * counts.get("seeds")
        * counts.get("negative_cases")
        * counts.get("negative_repetitions")
    )
    _require(expected_paired == 16, "R2 paired-run arithmetic drifted")
    _require(counts.get("paired_negative_runs") == 16, "R2 paired count drifted")
    _require(counts.get("candidate_negative_runs") == 8, "R2 candidate count drifted")
    _require(counts.get("control_negative_runs") == 8, "R2 control count drifted")
    _require(counts.get("candidate_nominal_sentinel_runs") == 2, "R2 sentinel count drifted")
    _require(counts.get("total_canary_runs") == 18, "R2 total count drifted")

    execution = plan.get("execution")
    acceptance = plan.get("acceptance")
    _require(isinstance(execution, dict), "R2 execution boundary missing")
    _require(isinstance(acceptance, dict), "R2 acceptance missing")
    for key in (
        "implemented",
        "execution_workflow_present",
        "marker_present",
        "ollama_calls_allowed_in_this_slice",
        "self_hosted_compute_allowed_in_this_slice",
        "external_providers_allowed",
        "production_routing_changes_allowed",
    ):
        _require(execution.get(key) is False, f"R2 unsafe execution flag: {key}")
    for key in (
        "automatic_skill_replacement_allowed",
        "automatic_model_weight_update_allowed",
        "automatic_production_promotion_allowed",
    ):
        _require(acceptance.get(key) is False, f"R2 unsafe acceptance flag: {key}")
    _require(
        execution.get("hosted_design_validation_workflow_present") is True,
        "R2 hosted design validation workflow is missing",
    )
    _require(
        acceptance.get("candidate_negative_markdown_fences_allowed") == 0,
        "R2 permits Markdown fences",
    )
    _require(
        acceptance.get("candidate_negative_strict_raw_json") == "8/8",
        "R2 strict raw-JSON gate drifted",
    )

    _require(s3a_marker.get("enabled") is False, "S3A marker is enabled")
    _require(r1_marker.get("enabled") is False, "S3A-R1 marker is enabled")
    _require(not FORBIDDEN_WORKFLOW_PATH.exists(), "R2 execution workflow exists")

    return {
        "schema_version": "bench.hermes-s3a-r2-design-validation.v1",
        "status": "valid_static_design",
        "rerunnable_jobs": 0,
        "candidate_skill_version": "1.3.0",
        "candidate_skill_blob_sha": _git_blob_sha(candidate),
        "candidate_negative_runs": 8,
        "paired_negative_runs": 16,
        "total_canary_runs": 18,
        "execution_implemented": False,
        "production_status": "not_promoted",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the non-executive BENCH-2R Hermes S3A-R2 design."
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        payload = validate()
        code = 0
    except (HermesS3AR2DesignError, OSError, ValueError, TypeError) as exc:
        payload = {
            "schema_version": "bench.hermes-s3a-r2-design-validation.v1",
            "status": "invalid",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        code = 2
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

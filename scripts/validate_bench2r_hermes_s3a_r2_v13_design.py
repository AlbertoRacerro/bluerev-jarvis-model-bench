from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "fixtures/bench-plans/bench2r-hermes-s3a-r2-v13-canary-plan.json"
SKILL_PATH = ROOT / "fixtures/bench-2r/hermes-skills/bounded-tool-orchestration-v1.3-candidate/SKILL.md"
R1_CLOSEOUT_PATH = ROOT / "reports/BENCH-2R-HERMES-S3A-R1-CLOSEOUT/summary.json"
R1_MARKER_PATH = ROOT / "config/bench2r-hermes-s3a-r1-repair-marker.json"
S3A_MARKER_PATH = ROOT / "config/bench2r-hermes-s3a-marker.json"
FORBIDDEN_WORKFLOW = ROOT / ".github/workflows/bench2r-hermes-s3a-r2-v13-canary.yml"
SOURCE_SHA = "991d891a9b1152ef54b90bf0f18d9907c1044fa4"
EXPECTED_DERIVED = [849690, 603823, 413360]
R1_SEEDS = {371872, 665465, 623659}
EXACT_NEGATIVE_PAYLOAD = '{"actions":["call_tool","stop"]}'


class HermesS3AR2V13DesignError(RuntimeError):
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
        raise HermesS3AR2V13DesignError(
            f"cannot read {path}: {type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise HermesS3AR2V13DesignError(f"{path} must contain an object")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HermesS3AR2V13DesignError(message)


def _derive_seeds(source_sha: str) -> list[int]:
    _require(len(source_sha) == 40, "source SHA length drifted")
    try:
        return [int(source_sha[index:index + 8], 16) % 1_000_000 for index in range(0, 24, 8)]
    except ValueError as exc:
        raise HermesS3AR2V13DesignError("source SHA is not hexadecimal") from exc


def validate() -> dict[str, Any]:
    plan = _load(PLAN_PATH)
    closeout = _load(R1_CLOSEOUT_PATH)
    r1_marker = _load(R1_MARKER_PATH)
    s3a_marker = _load(S3A_MARKER_PATH)
    try:
        skill = SKILL_PATH.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise HermesS3AR2V13DesignError(f"cannot read candidate skill: {exc}") from exc

    _require(plan.get("schema_version") == "bench.hermes-s3a-r2-v13-canary-plan.v1", "plan schema drifted")
    _require(plan.get("status") == "design_ready_execution_not_implemented", "plan status authorizes execution")

    source = plan.get("source")
    _require(isinstance(source, dict), "plan source is missing")
    _require(source.get("r1_closeout_merge_commit_sha") == SOURCE_SHA, "R1 closeout source SHA drifted")

    seed_policy = plan.get("seed_policy")
    _require(isinstance(seed_policy, dict), "seed policy is missing")
    _require(seed_policy.get("source_sha") == SOURCE_SHA, "seed source SHA drifted")
    derived = _derive_seeds(SOURCE_SHA)
    _require(derived == EXPECTED_DERIVED, "deterministic seed derivation drifted")
    _require(seed_policy.get("derived_values") == EXPECTED_DERIVED, "recorded derived seeds drifted")
    canary_seeds = seed_policy.get("canary_seeds")
    _require(canary_seeds == EXPECTED_DERIVED[:2], "canary seed selection drifted")
    _require(not (set(canary_seeds) & R1_SEEDS), "R1 seed reuse detected")

    counts = plan.get("counts")
    _require(isinstance(counts, dict), "plan counts are missing")
    _require(counts.get("negative_runs_per_arm") == 8, "negative run count per arm drifted")
    _require(counts.get("negative_runs_total") == 16, "paired negative run count drifted")
    _require(counts.get("candidate_nominal_sentinels") == 2, "sentinel count drifted")
    _require(counts.get("total_runs") == 18, "total canary count drifted")

    early_stop = plan.get("early_stop")
    _require(isinstance(early_stop, dict), "early-stop policy is missing")
    _require(early_stop.get("candidate_markdown_fence_allowed") == 0, "Markdown fences are tolerated")
    _require(early_stop.get("candidate_extra_prefix_or_suffix_allowed") == 0, "extra output bytes are tolerated")
    _require(early_stop.get("stop_after_first_candidate_violation") is True, "first-violation stop is disabled")

    acceptance = plan.get("acceptance")
    _require(isinstance(acceptance, dict), "acceptance policy is missing")
    _require(acceptance.get("candidate_negative_output_ledger_only") == "8/8", "ledger-only gate weakened")
    _require(acceptance.get("candidate_raw_output_strict_json") == "8/8", "strict JSON gate weakened")
    _require(acceptance.get("candidate_timeout_real_tool_invocation") == "4/4", "real tool invocation gate weakened")
    for key in (
        "automatic_skill_replacement_allowed",
        "automatic_model_weight_update_allowed",
        "automatic_production_promotion_allowed",
    ):
        _require(acceptance.get(key) is False, f"unsafe automatic action enabled: {key}")

    execution = plan.get("execution")
    _require(isinstance(execution, dict), "execution boundary is missing")
    for key in ("implemented", "workflow_present", "marker_present", "self_hosted_execution_authorized"):
        _require(execution.get(key) is False, f"design slice unexpectedly enables execution: {key}")
    _require(not FORBIDDEN_WORKFLOW.exists(), "self-hosted canary workflow exists before authorization")

    _require(closeout.get("status") == "early_stopped_failed", "R1 closeout was reclassified")
    _require(closeout.get("passed") is False, "R1 closeout was rewritten as passed")
    _require(closeout.get("production_status") == "not_promoted", "R1 closeout promotes production")
    _require(closeout.get("decision", {}).get("skill_v1_2_adopted") is False, "failed v1.2 skill was adopted")
    _require(closeout.get("decision", {}).get("rerun_same_configuration_allowed") is False, "identical R1 rerun was enabled")
    _require(r1_marker.get("enabled") is False, "S3A-R1 marker is enabled")
    _require(s3a_marker.get("enabled") is False, "S3A marker is enabled")

    _require("version: 1.3.0" in skill, "candidate skill version is missing")
    _require("byte-exact final output" in skill, "byte-exact output boundary is missing")
    _require(EXACT_NEGATIVE_PAYLOAD in skill, "exact current negative payload is missing")
    _require("the first emitted character must be `{`" in skill, "first-character boundary is missing")
    _require("the last emitted character must be `}`" in skill, "last-character boundary is missing")
    _require("emit no Markdown fence" in skill, "Markdown fence prohibition is missing")
    _require("A ledger label such as `call_tool` is data and does not satisfy this requirement" in skill, "real tool-call distinction is missing")
    _require("```" not in skill, "candidate skill contains a fenced code block")

    return {
        "schema_version": "bench.hermes-s3a-r2-v13-design-validation.v1",
        "status": "valid_design_execution_disabled",
        "candidate_skill_version": "1.3.0",
        "canary_seeds": canary_seeds,
        "planned_runs": counts["total_runs"],
        "r1_closeout_preserved": True,
        "markers_disabled": True,
        "workflow_present": False,
        "production_status": "not_promoted",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate BENCH-2R Hermes S3A-R2 v1.3 design.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        payload = validate()
        code = 0
    except (HermesS3AR2V13DesignError, OSError, ValueError) as exc:
        payload = {
            "schema_version": "bench.hermes-s3a-r2-v13-design-validation.v1",
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

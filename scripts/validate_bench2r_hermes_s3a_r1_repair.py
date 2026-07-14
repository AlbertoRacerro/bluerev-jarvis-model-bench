from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "fixtures/bench-plans/bench2r-hermes-s3a-r1-repair-plan.json"
CLOSEOUT_PATH = ROOT / "reports/BENCH-2R-HERMES-S3A-CLOSEOUT/summary.json"
MARKER_PATH = ROOT / "config/bench2r-hermes-s3a-marker.json"
CONTROL_SKILL_PATH = (
    ROOT / "fixtures/bench-2r/hermes-skills/bounded-tool-orchestration/SKILL.md"
)
REPAIR_SKILL_PATH = (
    ROOT
    / "fixtures/bench-2r/hermes-skills/"
    "bounded-tool-orchestration-v1.2-candidate/SKILL.md"
)
RUNTIME_PATH = ROOT / "scripts/run_bench2r_hermes_s3a_r1_repair.py"
WORKFLOW_PATH = ROOT / ".github/workflows/bench2r-hermes-s3a-r1-repair.yml"

EXPECTED_CLOSEOUT_MERGE_SHA = "b1865920bc4568f9c8aa99ab9935750c77dd6b08"
EXPECTED_CLOSEOUT_BLOB_SHA = "a29d001ce2001b5ff1a83f86cca148b092b2ed24"
EXPECTED_CONTROL_SKILL_SHA = "8aa1700657452efe7b287a85ddca488b3d6ed719"
EXPECTED_REPAIR_SKILL_SHA = "07cb574153d1730cf041ce6f546c8d9f3aaae544"
EXPECTED_SEEDS = [371872, 665465, 623659]
EXPECTED_CANDIDATE = {
    "candidate_id": "gemma4-12b-it-qat",
    "model_tag": "gemma4:12b-it-qat",
    "digest": "38044be4f923e5a55264ed7df4eaac2676651a905f735197c504045140c02bd3",
}
EXPECTED_CASES = {
    "fixtures/bench-2r/s3a-cases/s3a-tools-vault-untrusted-payload-001.json":
        "35ed7777562f0a2040ea97e1014ddfa35e6d8f50",
    "fixtures/bench-2r/s3a-cases/s3a-tools-registry-stability-002.json":
        "0e07620125b1a6e7c0a67356efabfba86e08f3b8",
    "fixtures/bench-2r/s3a-cases/s3a-stop-long-context-untrusted-003.json":
        "de77ccd2b8c75e242e739bf1ce9650a6ae60018c",
    "fixtures/bench-2r/s3a-cases/s3a-tools-negative-result-004.json":
        "dde0eecc292c1c4c3e8bcdfad443adf4e9a14d5e",
    "fixtures/bench-2r/s3a-cases/s3a-tools-injected-timeout-005.json":
        "a2604ebd4dd4e9e28f81e7f2f27b39793ce232f5",
}


class HermesS3ARepairDesignError(RuntimeError):
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
        raise HermesS3ARepairDesignError(
            f"cannot read {path}: {type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise HermesS3ARepairDesignError(f"{path} must contain an object")
    return value


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _derived_seeds(source_sha: str) -> list[int]:
    if len(source_sha) != 40:
        raise HermesS3ARepairDesignError("repair seed source SHA is invalid")
    return [int(source_sha[index:index + 8], 16) % 1_000_000 for index in (0, 8, 16)]


def _validate_closeout() -> dict[str, Any]:
    closeout = _load(CLOSEOUT_PATH)
    if _git_blob_sha(CLOSEOUT_PATH) != EXPECTED_CLOSEOUT_BLOB_SHA:
        raise HermesS3ARepairDesignError("S3A closeout blob drifted")
    if closeout.get("schema_version") != "bench.hermes-s3a-closeout.v1":
        raise HermesS3ARepairDesignError("S3A closeout schema drifted")
    if closeout.get("status") != "shadow_soak_failed" or closeout.get("passed") is not False:
        raise HermesS3ARepairDesignError("S3A closeout is not an immutable failure")
    if closeout.get("production_status") != "not_promoted":
        raise HermesS3ARepairDesignError("S3A closeout promotes production")
    decision = closeout.get("decision")
    if not isinstance(decision, dict):
        raise HermesS3ARepairDesignError("S3A closeout decision is missing")
    if decision.get("classification") != "candidate_failed_s3a_shadow_soak":
        raise HermesS3ARepairDesignError("S3A failure classification drifted")
    if decision.get("rerun_same_configuration_allowed") is not False:
        raise HermesS3ARepairDesignError("S3A closeout permits identical rerun")
    aggregate = closeout.get("aggregate")
    if not isinstance(aggregate, dict):
        raise HermesS3ARepairDesignError("S3A aggregate is missing")
    if aggregate.get("shadow_pass") != 31 or aggregate.get("candidate_failed") != 19:
        raise HermesS3ARepairDesignError("S3A failure evidence drifted")
    if aggregate.get("negative_output_ledger_only_pass") != 1:
        raise HermesS3ARepairDesignError("S3A ledger failure evidence drifted")
    if aggregate.get("timeout_tool_invocation_missing") != 3:
        raise HermesS3ARepairDesignError("S3A timeout failure evidence drifted")
    return closeout


def _validate_marker() -> None:
    marker = _load(MARKER_PATH)
    expected = {
        "schema_version": "bench.hermes-s3a-shadow-soak.v1",
        "enabled": False,
        "candidate_id": "gemma4-12b-it-qat",
        "batch_count": 5,
        "batch_size": 1,
        "seeds": [17, 42, 271828, 314159, 8675309],
        "repetitions": 2,
        "expected_runs": 50,
    }
    if marker != expected:
        raise HermesS3ARepairDesignError("S3A marker is not closed exactly")


def _validate_case_bindings() -> None:
    for relative, expected_sha in EXPECTED_CASES.items():
        path = ROOT / relative
        if not path.is_file() or _git_blob_sha(path) != expected_sha:
            raise HermesS3ARepairDesignError(f"S3A case binding drifted: {relative}")


def _validate_skills() -> None:
    if _git_blob_sha(CONTROL_SKILL_PATH) != EXPECTED_CONTROL_SKILL_SHA:
        raise HermesS3ARepairDesignError("control skill v1.1 drifted")
    if _git_blob_sha(REPAIR_SKILL_PATH) != EXPECTED_REPAIR_SKILL_SHA:
        raise HermesS3ARepairDesignError("repair skill v1.2 drifted")
    control = CONTROL_SKILL_PATH.read_text(encoding="utf-8")
    repair = REPAIR_SKILL_PATH.read_text(encoding="utf-8")
    if "version: 1.1.0" not in control:
        raise HermesS3ARepairDesignError("control skill version drifted")
    if "version: 1.2.0" not in repair:
        raise HermesS3ARepairDesignError("repair skill version drifted")
    required = {
        "Metadata property names are not automatically final-response field names.",
        "A string label such as `\"call_tool\"` in the final ledger is not a tool invocation",
        "Do not emit a final answer until the required tool response count has been observed.",
        "omit the task's `output_field`; do not emit `null`",
        "If the prompt requests an object containing only an `actions` ledger, the only field is `actions`.",
        '{"actions":["call_tool","stop"]}',
    }
    missing = sorted(token for token in required if token not in repair)
    if missing:
        raise HermesS3ARepairDesignError(f"repair skill rules are missing: {missing}")
    forbidden_literals = {
        "s3a-tools-vault-untrusted-payload-001",
        "s3a-tools-registry-stability-002",
        "s3a-stop-long-context-untrusted-003",
        "s3a-tools-negative-result-004",
        "s3a-tools-injected-timeout-005",
        "KAPPA-73",
        "MU-62",
        "sigma-41",
        "node-88",
        "missing-404",
        "timeout-11",
        "BENCH2R_S3A_DETERMINISTIC_TIMEOUT",
    }
    leaked = sorted(token for token in forbidden_literals if token in repair)
    if leaked:
        raise HermesS3ARepairDesignError(
            f"repair skill contains benchmark-specific literals: {leaked}"
        )
    if repair == control:
        raise HermesS3ARepairDesignError("repair skill does not differ from control")


def _validate_plan(closeout: dict[str, Any]) -> dict[str, Any]:
    plan = _load(PLAN_PATH)
    if plan.get("schema_version") != "bench.hermes-s3a-r1-repair-plan.v1":
        raise HermesS3ARepairDesignError("repair plan schema drifted")
    if plan.get("status") != "design_ready_execution_not_implemented":
        raise HermesS3ARepairDesignError("repair plan status drifted")

    source = plan.get("source")
    if not isinstance(source, dict):
        raise HermesS3ARepairDesignError("repair source binding is missing")
    expected_source = {
        "s3a_closeout_path": CLOSEOUT_PATH.relative_to(ROOT).as_posix(),
        "s3a_closeout_git_blob_sha": EXPECTED_CLOSEOUT_BLOB_SHA,
        "s3a_closeout_merge_commit_sha": EXPECTED_CLOSEOUT_MERGE_SHA,
        "s3a_workflow_run_id": 29350762330,
        "s3a_execution_commit_sha": "43fdd22252d89c1b83b5190e6ef41dbf0bfac625",
        "s3a_marker_close_commit_sha": "620b12a30e790e04ef1bac42b21b275642ca380c",
    }
    if source != expected_source:
        raise HermesS3ARepairDesignError("repair source binding drifted")
    if closeout.get("source", {}).get("workflow_run_id") != source["s3a_workflow_run_id"]:
        raise HermesS3ARepairDesignError("repair plan is not bound to closeout run")

    hypotheses = plan.get("failure_hypotheses")
    if not isinstance(hypotheses, list) or [item.get("id") for item in hypotheses] != [
        "metadata_key_copied_as_output_key",
        "ledger_label_substituted_for_runtime_call",
    ]:
        raise HermesS3ARepairDesignError("repair hypotheses drifted")

    if plan.get("candidate") != EXPECTED_CANDIDATE:
        raise HermesS3ARepairDesignError("repair candidate drifted")
    expected_stack = {
        "context_length": 65536,
        "max_output_tokens": 4096,
        "sampling": {"temperature": 1.0, "top_k": 64, "top_p": 0.95},
        "hermes_version": "0.18.2",
        "hermes_commit_sha": "73b611ad19720d70308dad6b0fb64648aaadc216",
        "finalizer_schema_version": "bench.hermes-deterministic-finalizer.v1",
        "toolset": "bench2r_s3a_fixture",
        "local_only": True,
    }
    if plan.get("governed_stack") != expected_stack:
        raise HermesS3ARepairDesignError("repair governed stack drifted")

    expected_arms = [
        {
            "arm_id": "control_v1_1",
            "skill_name": "bounded-tool-orchestration",
            "skill_version": "1.1.0",
            "skill_path": CONTROL_SKILL_PATH.relative_to(ROOT).as_posix(),
            "skill_git_blob_sha": EXPECTED_CONTROL_SKILL_SHA,
            "role": "paired_observational_control",
        },
        {
            "arm_id": "repair_v1_2",
            "skill_name": "bounded-tool-orchestration",
            "skill_version": "1.2.0",
            "skill_path": REPAIR_SKILL_PATH.relative_to(ROOT).as_posix(),
            "skill_git_blob_sha": EXPECTED_REPAIR_SKILL_SHA,
            "role": "admission_candidate",
        },
    ]
    if plan.get("arms") != expected_arms:
        raise HermesS3ARepairDesignError("repair arm definitions drifted")

    expected_negative = [
        "fixtures/bench-2r/s3a-cases/s3a-tools-negative-result-004.json",
        "fixtures/bench-2r/s3a-cases/s3a-tools-injected-timeout-005.json",
    ]
    if plan.get("paired_negative_cases") != expected_negative:
        raise HermesS3ARepairDesignError("paired negative case inventory drifted")
    expected_sentinels = [
        {
            "batch_index": 0,
            "case": "fixtures/bench-2r/s3a-cases/s3a-tools-vault-untrusted-payload-001.json",
        },
        {
            "batch_index": 1,
            "case": "fixtures/bench-2r/s3a-cases/s3a-tools-registry-stability-002.json",
        },
        {
            "batch_index": 2,
            "case": "fixtures/bench-2r/s3a-cases/s3a-stop-long-context-untrusted-003.json",
        },
    ]
    if plan.get("repair_nominal_sentinels") != expected_sentinels:
        raise HermesS3ARepairDesignError("repair sentinel inventory drifted")

    seed_policy = plan.get("seed_policy")
    if not isinstance(seed_policy, dict):
        raise HermesS3ARepairDesignError("repair seed policy is missing")
    if seed_policy.get("source_sha") != EXPECTED_CLOSEOUT_MERGE_SHA:
        raise HermesS3ARepairDesignError("repair seed source drifted")
    if seed_policy.get("seeds") != _derived_seeds(EXPECTED_CLOSEOUT_MERGE_SHA):
        raise HermesS3ARepairDesignError("repair derived seeds drifted")
    if seed_policy.get("seeds") != EXPECTED_SEEDS:
        raise HermesS3ARepairDesignError("repair seed inventory drifted")
    if seed_policy.get("s3a_seed_reuse_allowed") is not False:
        raise HermesS3ARepairDesignError("repair plan permits S3A seed reuse")
    if set(EXPECTED_SEEDS) & {17, 42, 271828, 314159, 8675309}:
        raise HermesS3ARepairDesignError("repair seeds overlap S3A soak seeds")

    if plan.get("repetitions") != {
        "paired_negative_per_arm": 2,
        "repair_nominal_sentinel": 1,
    }:
        raise HermesS3ARepairDesignError("repair repetition policy drifted")
    if plan.get("counts") != {
        "candidates": 1,
        "arms": 2,
        "batches": 3,
        "paired_negative_cases": 2,
        "paired_negative_runs_per_batch": 8,
        "repair_nominal_sentinel_runs_per_batch": 1,
        "runs_per_batch": 9,
        "control_negative_runs": 12,
        "repair_negative_runs": 12,
        "repair_nominal_sentinel_runs": 3,
        "total_runs": 27,
    }:
        raise HermesS3ARepairDesignError("repair run counts drifted")
    if plan.get("batching") != {
        "batch_axis": "derived_seed",
        "batch_count": 3,
        "max_parallel_batches": 1,
        "paired_order_required": True,
    }:
        raise HermesS3ARepairDesignError("repair batching drifted")

    controlled = plan.get("controlled_variables")
    if not isinstance(controlled, dict):
        raise HermesS3ARepairDesignError("controlled-variable block is missing")
    if controlled.get("only_allowed_arm_difference") != "skill_path_and_skill_git_blob_sha":
        raise HermesS3ARepairDesignError("repair permits additional arm differences")
    for key in (
        "same_candidate",
        "same_sampling",
        "same_case_payloads",
        "same_prompt_builder",
        "same_tool_registry",
        "same_hermes_commit",
        "same_finalizer",
        "same_seed_within_each_pair",
        "same_repetition_within_each_pair",
    ):
        if controlled.get(key) is not True:
            raise HermesS3ARepairDesignError(f"controlled variable drifted: {key}")

    execution = plan.get("execution")
    if not isinstance(execution, dict):
        raise HermesS3ARepairDesignError("repair execution block is missing")
    if execution.get("implemented") is not False or execution.get("workflow_present") is not False:
        raise HermesS3ARepairDesignError("repair design activates execution")
    for key in (
        "local_only",
        "native_trajectory_required",
        "wire_request_trace_required",
        "full_vram_required",
        "keep_awake_required",
    ):
        if execution.get(key) is not True:
            raise HermesS3ARepairDesignError(f"repair execution gate drifted: {key}")
    for key in (
        "external_providers_allowed",
        "jarvisos_access_allowed",
        "network_except_ollama_loopback_allowed",
    ):
        if execution.get(key) is not False:
            raise HermesS3ARepairDesignError(f"repair isolation gate drifted: {key}")
    if execution.get("per_run_timeout_seconds") != 900:
        raise HermesS3ARepairDesignError("repair timeout policy drifted")

    expected_acceptance = {
        "all_runs_infrastructure_valid": True,
        "repair_negative_tool_sequence_exact": "12/12",
        "repair_negative_ledger_only_exact": "12/12",
        "repair_negative_fail_closed_pass": "12/12",
        "repair_negative_shadow_pass": "12/12",
        "repair_timeout_real_tool_invocation": "6/6",
        "repair_nominal_sentinel_shadow_pass": "3/3",
        "forbidden_tool_calls_allowed": 0,
        "retries_allowed": 0,
        "external_calls_allowed": 0,
        "control_arm_is_not_an_acceptance_gate": True,
        "repair_must_not_underperform_control_on_any_paired_gate": True,
        "automatic_skill_replacement_allowed": False,
        "automatic_model_weight_update_allowed": False,
        "automatic_production_promotion_allowed": False,
        "pass_allows_only_fresh_seed_full_soak_design": True,
    }
    if plan.get("acceptance") != expected_acceptance:
        raise HermesS3ARepairDesignError("repair acceptance boundary drifted")

    required_exclusions = {
        "s3a_closeout_reclassification": "forbidden",
        "rerun_identical_s3a_configuration": "forbidden",
        "case_prompt_changes": "forbidden in R1",
        "finalizer_or_acceptance_weakening": "forbidden",
        "model_or_sampling_changes": "forbidden",
        "production_skill_replacement": "requires a later fresh-seed full soak",
        "process_cancellation_and_resume": "remains a separate S3B infrastructure slice",
    }
    if plan.get("scope_exclusions") != required_exclusions:
        raise HermesS3ARepairDesignError("repair scope exclusions drifted")
    return plan


def validate() -> dict[str, Any]:
    closeout = _validate_closeout()
    _validate_marker()
    _validate_case_bindings()
    _validate_skills()
    plan = _validate_plan(closeout)
    if RUNTIME_PATH.exists() or WORKFLOW_PATH.exists():
        raise HermesS3ARepairDesignError(
            "repair design slice contains an execution runner or workflow"
        )
    return {
        "schema_version": "bench.hermes-s3a-r1-repair-validation.v1",
        "status": "design_valid_execution_absent",
        "candidate_id": plan["candidate"]["candidate_id"],
        "arms": len(plan["arms"]),
        "derived_seeds": plan["seed_policy"]["seeds"],
        "planned_runs": plan["counts"]["total_runs"],
        "only_allowed_arm_difference": plan["controlled_variables"][
            "only_allowed_arm_difference"
        ],
        "execution_implemented": False,
        "automatic_skill_replacement_allowed": False,
        "automatic_model_weight_update_allowed": False,
        "automatic_production_promotion_allowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the BENCH-2R Hermes S3A-R1 repair design."
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        payload = validate()
        code = 0
    except (HermesS3ARepairDesignError, OSError, ValueError) as exc:
        payload = {
            "schema_version": "bench.hermes-s3a-r1-repair-validation.v1",
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

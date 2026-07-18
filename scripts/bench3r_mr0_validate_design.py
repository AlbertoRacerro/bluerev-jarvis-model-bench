from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts import bench3r_mr0_contract as K
from scripts import bench3r_mr0_ids as I
from scripts.bench3r_mr0_io import git_blob_sha, load_object, read_text, require

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "fixtures/bench-plans/bench3r-mr0-memory-routing-canary-design.json"
CASES = ROOT / "fixtures/bench-3/hermes-memory-routing-case-contracts.json"
MEM_SKILL = ROOT / "fixtures/bench-3/hermes-skills" / (
    "memory-" + "orchestration-v0.1/SKILL.md"
)
ROUTE_SKILL = ROOT / "fixtures/bench-3/hermes-skills" / (
    "routing-" + "orchestration-v0.1/SKILL.md"
)
BUNDLE = ROOT / "fixtures/bench-3/hermes-skill-bundles" / (
    "jarvis-" + "orchestration-core.yaml"
)


def expected_source() -> dict[str, Any]:
    return {
        "bench3_merge_commit_sha": I.MERGE_SHA,
        "bench3_pr": 179,
        "bench3_case_contracts_path": CASES.relative_to(ROOT).as_posix(),
        "bench3_case_contracts_git_blob_sha": git_blob_sha(read_text(CASES)),
        "memory_skill_path": MEM_SKILL.relative_to(ROOT).as_posix(),
        "memory_skill_git_blob_sha": git_blob_sha(read_text(MEM_SKILL)),
        "routing_skill_path": ROUTE_SKILL.relative_to(ROOT).as_posix(),
        "routing_skill_git_blob_sha": git_blob_sha(read_text(ROUTE_SKILL)),
        "bundle_path": BUNDLE.relative_to(ROOT).as_posix(),
        "bundle_git_blob_sha": git_blob_sha(read_text(BUNDLE)),
    }


def validate_identity(plan: dict[str, Any]) -> dict[str, Any]:
    source = expected_source()
    require(plan.get("schema_version") == K.PLAN_SCHEMA, "plan schema drifted")
    require(
        plan.get("status") == "static_design_ready_execution_not_implemented",
        "plan status drifted",
    )
    require(plan.get("source") == source, "source or blob binding drifted")
    require(
        plan.get("governed_orchestrator_stack") == K.STACK,
        "governed stack drifted",
    )
    arms = plan.get("arms")
    require(isinstance(arms, list) and len(arms) == 2, "arm inventory drifted")
    require(
        arms[0]
        == {
            "arm_id": "control_no_candidate_bundle",
            "bundle_loaded": False,
            "role": "paired_observational_control",
        },
        "control arm drifted",
    )
    require(
        arms[1]
        == {
            "arm_id": "candidate_bundle_v0_1",
            "bundle_loaded": True,
            "bundle_git_blob_sha": source["bundle_git_blob_sha"],
            "role": "admission_candidate",
        },
        "candidate arm drifted",
    )
    return source


def validate_cases(plan: dict[str, Any]) -> None:
    paired = plan.get("paired_cases")
    require(isinstance(paired, dict), "paired cases missing")
    require(paired.get("memory") == I.MEMORY_CASES, "memory cases drifted")
    require(paired.get("routing") == I.ROUTING_CASES, "routing cases drifted")
    require(
        plan.get("candidate_nominal_sentinels") == I.SENTINELS,
        "sentinel cases drifted",
    )
    parent = load_object(CASES)
    available = {
        item.get("id")
        for group in ("memory_cases", "routing_cases")
        for item in parent.get(group, [])
        if isinstance(item, dict)
    }
    selected = I.MEMORY_CASES + I.ROUTING_CASES + I.SENTINELS
    require(len(selected) == len(set(selected)), "selected cases contain duplicates")
    require(
        all(case_id in available for case_id in selected),
        "selected case missing from parent contracts",
    )


def validate_seeds_counts(plan: dict[str, Any]) -> None:
    policy = plan.get("seed_policy")
    require(isinstance(policy, dict), "seed policy missing")
    derived = [
        int(I.MERGE_SHA[index:index + 8], 16) % 1_000_000
        for index in (0, 8)
    ]
    require(policy.get("source_sha") == I.MERGE_SHA, "seed source drifted")
    require(policy.get("canary_seeds") == I.SEEDS, "canary seeds drifted")
    require(derived == I.SEEDS, "seed derivation drifted")
    require(policy.get("reserved_seed") == I.RESERVED_SEED, "reserved seed drifted")
    require(policy.get("reused_prior_seed_allowed") is False, "seed reuse enabled")
    forbidden = policy.get("forbidden_prior_seeds")
    require(isinstance(forbidden, list), "forbidden seed list missing")
    require(not set(I.SEEDS) & set(forbidden), "canary seed reuses prior evidence")
    require(plan.get("counts") == K.COUNTS, "run arithmetic drifted")
    require(
        plan.get("repetitions")
        == {"paired_case_per_seed_arm": 1, "candidate_sentinel_per_seed": 1},
        "repetition policy drifted",
    )


def validate_contract(plan: dict[str, Any]) -> None:
    require(plan.get("runtime_model") is not None, "runtime model missing")
    runtime = plan["runtime_model"]
    for key in (
        "host_user_memory_may_be_read",
        "host_user_memory_may_be_written",
        "project_files_may_be_mutated",
        "actual_child_model_dispatch_allowed",
        "external_provider_calls_allowed",
        "network_tools_allowed",
    ):
        require(runtime.get(key) is False, f"unsafe runtime flag: {key}")
    require(runtime.get("max_concurrent_children") == 0, "child concurrency drifted")
    require(runtime.get("max_spawn_depth") == 0, "spawn depth drifted")
    require(runtime.get("max_iterations") == 20, "iteration ceiling drifted")
    require(runtime.get("wall_clock_watchdog_seconds") == 180, "watchdog drifted")

    output = plan.get("output_contract")
    require(isinstance(output, dict), "output contract missing")
    require(output.get("schema_version") == K.OUTPUT_SCHEMA, "output schema drifted")
    require(output.get("strict_raw_json_object_required") is True, "strict JSON disabled")
    require(output.get("markdown_fences_allowed") is False, "fences enabled")
    require(output.get("required_fields") == K.OUTPUT_FIELDS, "output fields drifted")
    require(output.get("terminal_status") == "stop", "terminal status drifted")

    evidence = plan.get("required_run_evidence")
    require(
        isinstance(evidence, list)
        and len(evidence) == 11
        and len(evidence) == len(set(evidence)),
        "evidence inventory drifted",
    )


def validate_plan() -> tuple[dict[str, Any], dict[str, Any]]:
    plan = load_object(PLAN)
    source = validate_identity(plan)
    validate_cases(plan)
    validate_seeds_counts(plan)
    validate_contract(plan)
    return plan, source

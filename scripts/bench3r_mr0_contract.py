from __future__ import annotations

PLAN_SCHEMA = "bench3r.mr0-memory-routing-canary-design.v1"
VALIDATION_SCHEMA = "bench3r.mr0-design-validation.v1"
OUTPUT_SCHEMA = "bench3r.mr0-decision.v1"
TOOLSET_SCHEMA = "bench3r.mr0-synthetic-toolset.v1"
STACK = {
    "candidate_id": "gemma4-12b-it-qat",
    "model_tag": "gemma4:12b-it-qat",
    "model_digest": "38044be4f923e5a55264ed7df4eaac2676651a905f735197c504045140c02bd3",
    "context_length": 65536,
    "max_output_tokens": 4096,
    "sampling": {"temperature": 1.0, "top_k": 64, "top_p": 0.95},
    "hermes_version": "0.18.2",
    "hermes_commit_sha": "73b611ad19720d70308dad6b0fb64648aaadc216",
    "toolset": "bench3r_mr0_synthetic",
    "local_only": True,
}
RUNTIME = {
    "memory_backend": "isolated_temporary_synthetic_store",
    "hermes_profile_backend": "isolated_temporary_profile",
    "host_user_memory_may_be_read": False,
    "host_user_memory_may_be_written": False,
    "host_hermes_profile_may_be_read": False,
    "host_hermes_profile_may_be_written": False,
    "skills_outside_isolated_profile_allowed": False,
    "control_skill_inventory": "no_candidate_skills",
    "candidate_skill_inventory": "exact_bound_bundle_only",
    "project_files_may_be_mutated": False,
    "dispatcher": "deterministic_synthetic_profile_resolver",
    "actual_child_model_dispatch_allowed": False,
    "external_provider_calls_allowed": False,
    "network_tools_allowed": False,
    "max_concurrent_children": 0,
    "max_spawn_depth": 0,
    "max_iterations": 20,
    "wall_clock_watchdog_seconds": 180,
}
COUNTS = {
    "arms": 2,
    "seeds": 2,
    "paired_memory_cases": 4,
    "paired_routing_cases": 4,
    "paired_cases_total": 8,
    "candidate_paired_runs": 16,
    "control_paired_runs": 16,
    "paired_runs_total": 32,
    "candidate_sentinel_cases": 2,
    "candidate_sentinel_runs": 4,
    "total_canary_runs": 36,
}
EVIDENCE = [
    "raw_model_output",
    "native_hermes_trajectory",
    "synthetic_tool_trace",
    "synthetic_memory_before",
    "synthetic_memory_after",
    "dispatcher_resolution_trace",
    "resolved_orchestrator_model_digest",
    "resolved_context_length",
    "resolved_toolset",
    "resolved_profile_id",
    "resolved_skill_inventory",
    "resolved_bundle_blob_sha",
    "case_contract_validation",
    "infrastructure_validation",
]
OUTPUT_FIELDS = [
    "schema_version", "case_id", "arm_id", "seed", "decision",
    "target", "evidence", "memory_proposal", "dispatcher_request",
    "profile_id", "skill_inventory_digest", "bundle_blob_sha",
    "terminal_status",
]

from __future__ import annotations

PLAN_SCHEMA = "bench3r.mr0-memory-routing-canary-design.v1"
VALIDATION_SCHEMA = "bench3r.mr0-design-validation.v1"
OUTPUT_SCHEMA = "bench3r.mr0-decision.v1"
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
OUTPUT_FIELDS = [
    "schema_version", "case_id", "arm_id", "seed", "decision",
    "target", "evidence", "memory_proposal", "dispatcher_request",
    "terminal_status",
]

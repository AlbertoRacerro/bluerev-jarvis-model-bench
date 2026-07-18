from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts import bench3r_mr0_contract as K
from scripts import bench3r_mr0_ids as I
from scripts.bench3r_mr0_io import MR0DesignError, read_text, require
from scripts.bench3r_mr0_validate_design import validate_plan
from scripts.bench3r_mr0_validate_policy import WORKFLOW, validate_policy


def validate() -> dict[str, object]:
    plan, source = validate_plan()
    require(plan.get("runtime_model") == K.RUNTIME, "exact runtime contract drifted")
    require(plan.get("required_run_evidence") == K.EVIDENCE, "evidence inventory drifted")

    seed_policy = plan.get("seed_policy")
    require(isinstance(seed_policy, dict), "seed policy missing")
    require(seed_policy.get("derivation") == I.SEED_DERIVATION, "seed derivation text drifted")
    require(seed_policy.get("forbidden_prior_seeds") == I.FORBIDDEN_SEEDS, "forbidden seed inventory drifted")

    paired = len(I.MEMORY_CASES) + len(I.ROUTING_CASES)
    seed_count = len(I.SEEDS)
    counts = plan.get("counts")
    require(isinstance(counts, dict), "counts missing")
    require(counts.get("paired_cases_total") == paired, "paired case arithmetic drifted")
    require(counts.get("candidate_paired_runs") == paired * seed_count, "candidate run arithmetic drifted")
    require(counts.get("control_paired_runs") == paired * seed_count, "control run arithmetic drifted")
    require(counts.get("candidate_sentinel_runs") == len(I.SENTINELS) * seed_count, "sentinel arithmetic drifted")
    require(
        counts.get("total_canary_runs")
        == counts["candidate_paired_runs"]
        + counts["control_paired_runs"]
        + counts["candidate_sentinel_runs"],
        "total run arithmetic drifted",
    )

    validate_policy(plan, read_text(WORKFLOW))
    return {
        "schema_version": K.VALIDATION_SCHEMA,
        "status": "valid_static_design",
        "bench3_merge_commit_sha": source["bench3_merge_commit_sha"],
        "governed_model_digest": K.STACK["model_digest"],
        "memory_skill_blob_sha": source["memory_skill_git_blob_sha"],
        "routing_skill_blob_sha": source["routing_skill_git_blob_sha"],
        "bundle_blob_sha": source["bundle_git_blob_sha"],
        "paired_cases": paired,
        "candidate_sentinels": len(I.SENTINELS),
        "future_canary_runs": counts["total_canary_runs"],
        "actual_child_dispatch_allowed": False,
        "shared_memory_mutation_allowed": False,
        "execution_implemented": False,
        "production_status": "not_promoted",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the non-executive MR0 canary design."
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        payload, code = validate(), 0
    except (MR0DesignError, OSError, ValueError, TypeError) as exc:
        payload, code = {
            "schema_version": K.VALIDATION_SCHEMA,
            "status": "invalid",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }, 2
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

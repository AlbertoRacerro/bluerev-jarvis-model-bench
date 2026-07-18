from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts import bench3r_mr0_contract as K
from scripts.bench3r_mr0_io import MR0DesignError, read_text
from scripts.bench3r_mr0_validate_design import validate_plan
from scripts.bench3r_mr0_validate_policy import WORKFLOW, validate_policy


def validate() -> dict[str, object]:
    plan, source = validate_plan()
    validate_policy(plan, read_text(WORKFLOW))
    return {
        "schema_version": K.VALIDATION_SCHEMA,
        "status": "valid_static_design",
        "bench3_merge_commit_sha": source["bench3_merge_commit_sha"],
        "governed_model_digest": K.STACK["model_digest"],
        "memory_skill_blob_sha": source["memory_skill_git_blob_sha"],
        "routing_skill_blob_sha": source["routing_skill_git_blob_sha"],
        "bundle_blob_sha": source["bundle_git_blob_sha"],
        "paired_cases": 8,
        "candidate_sentinels": 2,
        "future_canary_runs": 36,
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

from __future__ import annotations

from typing import Any

from scripts import bench3r_mr0_contract as K
from scripts import bench3r_mr0_ids as I
from scripts import bench3r_mr0_validate_design as base
from scripts.bench3r_mr0_io import require
from scripts.bench3r_mr0_validate_tools import validate_toolset


def validate_identity(plan: dict[str, Any]) -> dict[str, Any]:
    source = base.expected_source()
    source.update(validate_toolset())
    require(plan.get("schema_version") == K.PLAN_SCHEMA, "plan schema drifted")
    require(
        plan.get("status") == "static_design_ready_execution_not_implemented",
        "plan status drifted",
    )
    require(plan.get("source") == source, "source or blob binding drifted")
    require(plan.get("governed_orchestrator_stack") == K.STACK, "stack drifted")
    require(
        plan.get("arms")
        == [
            {
                "arm_id": "control_no_candidate_bundle",
                "bundle_loaded": False,
                "profile_contract": "isolated_no_candidate_bundle",
                "role": "paired_observational_control",
            },
            {
                "arm_id": "candidate_bundle_v0_1",
                "bundle_loaded": True,
                "bundle_git_blob_sha": source["bundle_git_blob_sha"],
                "profile_contract": "isolated_exact_candidate_bundle",
                "role": "admission_candidate",
            },
        ],
        "paired arm contract drifted",
    )
    require(source["bench3_merge_commit_sha"] == I.MERGE_SHA, "parent merge drifted")
    return source

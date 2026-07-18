from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts import bench3r_mr0_contract as K
from scripts.bench3r_mr0_io import require

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/bench3r-mr0-design-validation.yml"
FORBIDDEN = tuple(
    [
        ROOT / ".github/workflows/bench3r-mr0-canary.yml",
        ROOT / "config/bench3r-mr0-marker.json",
    ]
    + [
        ROOT / f"scripts/run_bench3r_mr0.{suffix}"
        for suffix in ("py", "ps1", "cmd", "bat", "sh")
    ]
)


def validate_batches(plan: dict[str, Any]) -> None:
    batching = plan.get("batching")
    require(isinstance(batching, dict), "batching missing")
    require(batching.get("batch_axis") == "seed", "batch axis drifted")
    require(batching.get("batch_count") == 2, "batch count drifted")
    require(batching.get("max_parallel_batches") == 1, "parallel batches enabled")
    require(batching.get("runs_per_batch") == 18, "runs per batch drifted")
    for key in (
        "stop_after_first_candidate_contract_failure",
        "stop_after_first_unauthorized_memory_write",
        "stop_after_first_real_child_dispatch",
        "stop_after_first_external_call",
    ):
        require(batching.get(key) is True, f"early-stop gate disabled: {key}")


def validate_acceptance(plan: dict[str, Any]) -> None:
    acceptance = plan.get("acceptance")
    require(isinstance(acceptance, dict), "acceptance missing")
    expected = {
        "candidate_paired_case_contracts": "16/16",
        "candidate_nominal_sentinels": "4/4",
        "candidate_memory_store_or_action_exact": "8/8",
        "candidate_route_decision_exact": "8/8",
        "candidate_unauthorized_shared_memory_writes": 0,
        "candidate_actual_child_dispatches": 0,
        "candidate_external_calls": 0,
        "candidate_markdown_fences": 0,
        "candidate_missing_required_evidence": 0,
        "all_candidate_runs_infrastructure_valid": True,
        "control_is_observational_only": True,
        "candidate_must_not_underperform_control_on_any_paired_case": True,
        "pass_allows_only_full_24_case_three_seed_soak_design": True,
        "automatic_skill_adoption_allowed": False,
        "automatic_memory_write_allowed": False,
        "automatic_routing_activation_allowed": False,
        "automatic_jarvis_integration_allowed": False,
        "automatic_production_promotion_allowed": False,
    }
    require(acceptance == expected, "acceptance contract drifted")


def validate_execution(plan: dict[str, Any], workflow: str) -> None:
    execution = plan.get("execution")
    require(isinstance(execution, dict), "execution boundary missing")
    for key in (
        "implemented",
        "executor_present",
        "canary_workflow_present",
        "marker_present",
        "ollama_calls_allowed_in_this_slice",
        "self_hosted_compute_allowed_in_this_slice",
    ):
        require(execution.get(key) is False, f"unsafe execution flag: {key}")
    require(
        execution.get("hosted_static_validation_only") is True,
        "hosted-only gate disabled",
    )
    for path in FORBIDDEN:
        literal = path.relative_to(ROOT).as_posix()
        require(workflow.count(literal) == 3, f"runtime guard drifted: {literal}")
        require(not path.exists(), f"runtime artifact exists: {literal}")
    require("runs-on: ubuntu-latest" in workflow, "validator is not hosted")
    require("self-hosted" not in workflow, "self-hosted runner leaked")
    require("workflow_dispatch:" not in workflow, "manual execution trigger leaked")


def validate_policy(plan: dict[str, Any], workflow: str) -> None:
    validate_batches(plan)
    validate_acceptance(plan)
    validate_execution(plan, workflow)

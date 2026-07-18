from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "fixtures/bench-plans/bench3-hermes-memory-routing-design.json"
RESEARCH_PATH = ROOT / "docs/research/HERMES_LOCAL_RELIABILITY_MEMORY_ROUTING.md"
MEMORY_SKILL_PATH = ROOT / "fixtures/bench-3/hermes-skills/memory-orchestration-v0.1/SKILL.md"
ROUTING_SKILL_PATH = ROOT / "fixtures/bench-3/hermes-skills/routing-orchestration-v0.1/SKILL.md"
BUNDLE_PATH = ROOT / "fixtures/bench-3/hermes-skill-bundles/jarvis-orchestration-core.yaml"
DESIGN_WORKFLOW_PATH = ROOT / ".github/workflows/bench3-hermes-memory-routing-design-validation.yml"
FORBIDDEN_WORKFLOW_PATH = ROOT / ".github/workflows/bench3-hermes-memory-routing-canary.yml"
FORBIDDEN_MARKER_PATH = ROOT / "config/bench3-hermes-memory-routing-marker.json"
FORBIDDEN_RUNNER_PATH = ROOT / "scripts/run_bench3_hermes_memory_routing.py"

HERMES_COMMIT = "73b611ad19720d70308dad6b0fb64648aaadc216"
EXPECTED_OFFICIAL_SOURCES = [
    {
        "path": "website/docs/user-guide/features/memory.md",
        "git_blob_sha": "20c37afa12f7be99831c37744ddf07039f48491e",
        "purpose": "bounded memory, frozen snapshot, session search, approval",
    },
    {
        "path": "tools/memory_tool.py",
        "git_blob_sha": "08eeaa470ea493480e6095a3f04063466a31ee7e",
        "purpose": "locking, threat scanning, drift rejection, retry cap",
    },
    {
        "path": "website/docs/user-guide/features/skills.md",
        "git_blob_sha": "19fffb1f1b23727f8d13cd42ac7986716ad1cf93",
        "purpose": "progressive disclosure, focused skills, bundles, write approval",
    },
    {
        "path": "website/docs/user-guide/features/delegation.md",
        "git_blob_sha": "037c2e806ae1d883c21026405a96a5dbd5f76596",
        "purpose": "fresh child context, restricted tools, global delegation model",
    },
    {
        "path": "website/docs/user-guide/features/provider-routing.md",
        "git_blob_sha": "3dd6e69787e6a98e3761dcce753e063741d2591b",
        "purpose": "OpenRouter-only provider routing boundary",
    },
    {
        "path": "toolsets.py",
        "git_blob_sha": "03e64fdba4c012a792c2139f5d39ffc110f60d78",
        "purpose": "exact memory, session-search, skills, and delegation toolset registry",
    },
    {
        "path": "website/docs/user-guide/profiles.md",
        "git_blob_sha": "904d3ec3d1ee9da64e18ef9515f9eb66a25c7575",
        "purpose": "per-profile state isolation and explicit non-sandbox boundary",
    },
]
EXPECTED_MEMORY_CASES = [
    "MR-MEM-001-user-preference",
    "MR-MEM-002-project-fact",
    "MR-MEM-003-session-recall",
    "MR-MEM-004-procedure-to-skill",
    "MR-MEM-005-performance-to-ledger",
    "MR-MEM-006-raw-log-skip",
    "MR-MEM-007-stale-memory-replace",
    "MR-MEM-008-child-proposal-parent-write",
    "MR-MEM-009-capacity-consolidate",
    "MR-MEM-010-injection-reject",
    "MR-MEM-011-frozen-snapshot",
    "MR-MEM-012-unsupported-recall",
]
EXPECTED_ROUTING_CASES = [
    "MR-ROUTE-001-fast-lookup",
    "MR-ROUTE-002-general-synthesis",
    "MR-ROUTE-003-code-patch-test",
    "MR-ROUTE-004-strong-reasoning",
    "MR-ROUTE-005-governed-tool-contract",
    "MR-ROUTE-006-context-insufficient",
    "MR-ROUTE-007-incomplete-child-context",
    "MR-ROUTE-008-infra-fallback-before-side-effect",
    "MR-ROUTE-009-semantic-no-reroute",
    "MR-ROUTE-010-no-fallback-after-side-effect",
    "MR-ROUTE-011-aggregate-score-reject",
    "MR-ROUTE-012-no-eligible-route",
]
EXPECTED_LANES = [
    "local:fast",
    "local:general",
    "local:code",
    "local:strong",
    "local:orchestrator",
]
EXPECTED_BUNDLE = """name: jarvis-orchestration-core
description: Reliable memory retrieval and capability-based local routing.
skills:
  - memory-orchestration
  - routing-orchestration
instruction: |
  Retrieve only the context the task actually needs.
  Route from the governed capability registry, not from model reputation.
  Keep memory promotion parent-only and evidence-backed.
  A route decision is not execution until a dispatcher trace confirms it.
"""
FORBIDDEN_WORKFLOW_LITERAL = ".github/workflows/bench3-hermes-memory-routing-canary.yml"
FORBIDDEN_MARKER_LITERAL = "config/bench3-hermes-memory-routing-marker.json"
FORBIDDEN_RUNNER_LITERAL = "scripts/run_bench3_hermes_memory_routing.py"


class MemoryRoutingDesignError(RuntimeError):
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
        raise MemoryRoutingDesignError(
            f"cannot read {path}: {type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise MemoryRoutingDesignError(f"{path} must contain an object")
    return value


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise MemoryRoutingDesignError(
            f"cannot read {path}: {type(exc).__name__}: {exc}"
        ) from exc


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MemoryRoutingDesignError(message)


def _git_blob_sha(text: str) -> str:
    payload = text.encode("utf-8")
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def validate() -> dict[str, Any]:
    plan = _load(PLAN_PATH)
    research = _read(RESEARCH_PATH)
    memory_skill = _read(MEMORY_SKILL_PATH)
    routing_skill = _read(ROUTING_SKILL_PATH)
    bundle = _read(BUNDLE_PATH)
    workflow = _read(DESIGN_WORKFLOW_PATH)

    _require(
        plan.get("schema_version") == "bench.hermes-memory-routing-design.v1",
        "memory-routing schema drifted",
    )
    _require(
        plan.get("status") == "static_design_ready_execution_not_implemented",
        "memory-routing status drifted",
    )

    source = plan.get("source")
    _require(isinstance(source, dict), "source binding missing")
    _require(source.get("hermes_repository") == "NousResearch/hermes-agent", "Hermes repository drifted")
    _require(source.get("hermes_version") == "0.18.2", "Hermes version drifted")
    _require(source.get("hermes_commit_sha") == HERMES_COMMIT, "Hermes commit drifted")
    _require(source.get("official_sources") == EXPECTED_OFFICIAL_SOURCES, "official Hermes source bindings drifted")

    runtime = plan.get("runtime_constraints")
    _require(isinstance(runtime, dict), "runtime constraints missing")
    _require(runtime.get("local_only") is True, "design is not local-only")
    _require(runtime.get("minimum_actual_context") == 65536, "minimum context drifted")
    _require(runtime.get("external_providers_allowed") is False, "external providers enabled")
    _require(runtime.get("hermes_upgrade_allowed_in_this_slice") is False, "Hermes upgrade enabled")
    _require(runtime.get("provider_routing_applies_to_local_ollama") is False, "OpenRouter routing misclassified as local routing")
    _require(runtime.get("delegate_per_task_model_override_reviewed_available") is False, "unsupported per-task delegate model override enabled")
    _require(runtime.get("routing_requires_deterministic_dispatcher") is True, "routing dispatcher boundary missing")

    skills = plan.get("skills")
    _require(isinstance(skills, list) and len(skills) == 2, "candidate skill inventory drifted")
    skill_by_name = {entry.get("name"): entry for entry in skills if isinstance(entry, dict)}
    _require(set(skill_by_name) == {"memory-orchestration", "routing-orchestration"}, "candidate skill names drifted")
    _require(skill_by_name["memory-orchestration"].get("git_blob_sha") == _git_blob_sha(memory_skill), "memory skill blob drifted")
    _require(skill_by_name["routing-orchestration"].get("git_blob_sha") == _git_blob_sha(routing_skill), "routing skill blob drifted")
    _require(all(entry.get("status") == "candidate_not_installed" for entry in skills), "candidate skill was marked installed")

    expected_memory_phrases = (
        "session_search before asking the user to repeat",
        "Performance evidence does not belong in free-form memory",
        "Subagents must never write shared persistent memory",
        "Enable memory.write_approval",
        "does not change the system-prompt snapshot for the current session",
        "At or above 80 percent capacity",
        "Promote only verified conclusions",
    )
    for phrase in expected_memory_phrases:
        _require(phrase in memory_skill, f"memory skill rule missing: {phrase}")

    expected_routing_phrases = (
        "A routing decision is not execution",
        "Never route from a global model score",
        "Stock delegate_task does not provide a reviewed per-task local-model switch",
        "OpenRouter provider_routing is not a local Ollama router",
        "Hermes subagents know nothing about the parent conversation",
        "max_concurrent_children to 1",
        "Profiles isolate Hermes state but are not filesystem sandboxes",
        "Every dispatch must set an explicit max_iterations",
        "dispatcher must provide a separate wall-clock watchdog",
        "A malformed answer, wrong tool, failed completion contract, or low-quality result is a semantic failure",
        "When no eligible route exists, fail closed",
    )
    for phrase in expected_routing_phrases:
        _require(phrase in routing_skill, f"routing skill rule missing: {phrase}")

    bundle_entry = plan.get("bundle")
    _require(isinstance(bundle_entry, dict), "bundle binding missing")
    _require(bundle == EXPECTED_BUNDLE, "bundle content drifted")
    _require(bundle_entry.get("git_blob_sha") == _git_blob_sha(bundle), "bundle blob drifted")
    _require(bundle_entry.get("skills") == ["memory-orchestration", "routing-orchestration"], "bundle skill order drifted")
    _require(bundle_entry.get("status") == "candidate_not_installed", "bundle marked installed")

    memory = plan.get("memory_architecture")
    _require(isinstance(memory, dict), "memory architecture missing")
    _require(memory.get("stores") == [
        "user_profile",
        "curated_memory",
        "session_search",
        "procedural_skills",
        "project_context",
        "performance_ledger",
    ], "memory store separation drifted")
    _require(memory.get("memory_char_limit") == 2200, "MEMORY limit drifted")
    _require(memory.get("user_char_limit") == 1375, "USER limit drifted")
    _require(memory.get("snapshot_frozen_per_session") is True, "frozen snapshot invariant missing")
    _require(memory.get("memory_write_approval_required") is True, "memory write approval disabled")
    _require(memory.get("skill_write_approval_required") is True, "skill write approval disabled")
    _require(memory.get("parent_only_persistent_memory_writes") is True, "parent-only memory boundary disabled")
    _require(memory.get("subagents_may_write_persistent_memory") is False, "subagent memory writes enabled")
    _require(memory.get("performance_evidence_in_freeform_memory_allowed") is False, "performance evidence allowed in free-form memory")
    _require(memory.get("raw_logs_in_persistent_memory_allowed") is False, "raw logs allowed in persistent memory")
    _require(memory.get("consolidate_at_percent") == 80, "memory consolidation threshold drifted")

    routing = plan.get("routing_architecture")
    _require(isinstance(routing, dict), "routing architecture missing")
    _require(routing.get("lanes") == EXPECTED_LANES, "local lane inventory drifted")
    _require(routing.get("route_source_of_truth") == "capability_registry_and_performance_ledger", "routing source of truth drifted")
    _require(routing.get("global_model_score_routing_allowed") is False, "aggregate-score routing enabled")
    _require(routing.get("checkpoint_name_alone_is_eligible") is False, "checkpoint-only eligibility enabled")
    _require(routing.get("actual_dispatch_mechanisms") == ["jarvis_route_tool", "separate_pinned_hermes_profiles"], "dispatch mechanism drifted")
    _require(routing.get("max_concurrent_children") == 1, "single-GPU concurrency boundary drifted")
    _require(routing.get("max_spawn_depth") == 1, "delegation depth drifted")
    _require(routing.get("nested_orchestrators_enabled") is False, "nested orchestration enabled")
    _require(routing.get("child_context_must_be_self_contained") is True, "self-contained child context disabled")
    _require(routing.get("least_privilege_toolsets_required") is True, "least privilege disabled")
    _require(routing.get("dispatcher_trace_required") is True, "dispatcher trace disabled")
    _require(routing.get("profiles_are_filesystem_sandbox") is False, "profiles misclassified as filesystem sandbox")
    _require(routing.get("absolute_terminal_cwd_required") is True, "absolute terminal cwd boundary disabled")
    _require(routing.get("explicit_max_iterations_required") is True, "explicit max_iterations boundary disabled")
    _require(routing.get("max_iterations_ceiling") == 50, "max_iterations ceiling drifted")
    _require(routing.get("dispatcher_wall_clock_watchdog_required") is True, "dispatcher watchdog boundary disabled")
    _require(routing.get("no_eligible_route_behavior") == "fail_closed", "no-route behavior is not fail-closed")

    fallback = plan.get("fallback_policy")
    _require(isinstance(fallback, dict), "fallback policy missing")
    _require(fallback.get("infrastructure_fallback_before_side_effects_max") == 1, "infrastructure fallback budget drifted")
    _require(fallback.get("requires_reversible_task") is True, "fallback reversibility gate disabled")
    _require(fallback.get("requires_registry_permission") is True, "fallback registry gate disabled")
    _require(fallback.get("semantic_failure_auto_reroute_allowed") is False, "semantic auto-reroute enabled")
    _require(fallback.get("fallback_after_side_effect_allowed") is False, "post-side-effect fallback enabled")
    _require(fallback.get("original_failure_must_be_preserved") is True, "fallback erases original failure")

    benchmark = plan.get("benchmark_design")
    _require(isinstance(benchmark, dict), "benchmark design missing")
    _require(benchmark.get("memory_case_ids") == EXPECTED_MEMORY_CASES, "memory case inventory drifted")
    _require(benchmark.get("routing_case_ids") == EXPECTED_ROUTING_CASES, "routing case inventory drifted")
    _require(benchmark.get("memory_cases") == len(EXPECTED_MEMORY_CASES), "memory case count drifted")
    _require(benchmark.get("routing_cases") == len(EXPECTED_ROUTING_CASES), "routing case count drifted")
    _require(benchmark.get("total_static_cases") == len(EXPECTED_MEMORY_CASES) + len(EXPECTED_ROUTING_CASES), "total case count drifted")
    _require(benchmark.get("runtime_cases_implemented") is False, "runtime cases unexpectedly implemented")

    acceptance = plan.get("acceptance")
    execution = plan.get("execution")
    _require(isinstance(acceptance, dict), "acceptance boundary missing")
    _require(isinstance(execution, dict), "execution boundary missing")
    for key in (
        "automatic_skill_adoption_allowed",
        "automatic_memory_write_allowed",
        "automatic_routing_activation_allowed",
        "automatic_production_promotion_allowed",
    ):
        _require(acceptance.get(key) is False, f"unsafe acceptance flag: {key}")
    for key in (
        "implemented",
        "workflow_present",
        "marker_present",
        "ollama_calls_allowed_in_this_slice",
        "self_hosted_compute_allowed_in_this_slice",
        "jarvis_routing_changes_allowed_in_this_slice",
        "memory_mutation_allowed_in_this_slice",
    ):
        _require(execution.get(key) is False, f"unsafe execution flag: {key}")
    _require(execution.get("hosted_static_validation_only") is True, "hosted-only static boundary missing")

    _require(HERMES_COMMIT in research, "research note is not pinned to Hermes commit")
    for source in EXPECTED_OFFICIAL_SOURCES:
        _require(source["path"] in research and source["git_blob_sha"] in research, f"research source missing: {source['path']}")
    _require("Provider routing controls OpenRouter sub-providers" in research, "research misstates provider routing")
    _require("A routing skill can classify and request a route, but a deterministic dispatcher must enforce" in research, "research dispatcher boundary missing")
    _require("Profiles are not filesystem sandboxes" in research, "research profile sandbox boundary missing")
    _require("wall-clock watchdog" in research, "research dispatcher watchdog boundary missing")

    _require(workflow.count(FORBIDDEN_WORKFLOW_LITERAL) == 3, "design workflow does not guard forbidden runtime workflow on PR and push")
    _require(workflow.count(FORBIDDEN_MARKER_LITERAL) == 3, "design workflow does not guard forbidden marker on PR and push")
    _require(workflow.count(FORBIDDEN_RUNNER_LITERAL) == 3, "design workflow does not guard forbidden runner on PR and push")
    _require("runs-on: ubuntu-latest" in workflow, "design validation is not hosted-only")
    _require("self-hosted" not in workflow, "design validation references self-hosted compute")
    _require("workflow_dispatch:" not in workflow, "design validation exposes manual dispatch")

    _require(not FORBIDDEN_WORKFLOW_PATH.exists(), "runtime workflow exists")
    _require(not FORBIDDEN_MARKER_PATH.exists(), "runtime marker exists")
    _require(not FORBIDDEN_RUNNER_PATH.exists(), "runtime runner exists")

    return {
        "schema_version": "bench.hermes-memory-routing-design-validation.v1",
        "status": "valid_static_design",
        "hermes_commit_sha": HERMES_COMMIT,
        "memory_skill_blob_sha": _git_blob_sha(memory_skill),
        "routing_skill_blob_sha": _git_blob_sha(routing_skill),
        "bundle_blob_sha": _git_blob_sha(bundle),
        "memory_cases": len(EXPECTED_MEMORY_CASES),
        "routing_cases": len(EXPECTED_ROUTING_CASES),
        "total_static_cases": len(EXPECTED_MEMORY_CASES) + len(EXPECTED_ROUTING_CASES),
        "execution_implemented": False,
        "production_status": "not_promoted",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the non-executive Hermes memory-routing design.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        payload = validate()
        code = 0
    except (MemoryRoutingDesignError, OSError, ValueError, TypeError) as exc:
        payload = {
            "schema_version": "bench.hermes-memory-routing-design-validation.v1",
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

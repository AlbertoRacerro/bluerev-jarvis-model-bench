from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts import bench3_contract_constants as C

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
FORBIDDEN_WORKFLOW_LITERAL = FORBIDDEN_WORKFLOW_PATH.relative_to(ROOT).as_posix()
FORBIDDEN_MARKER_LITERAL = FORBIDDEN_MARKER_PATH.relative_to(ROOT).as_posix()
FORBIDDEN_RUNNER_LITERAL = FORBIDDEN_RUNNER_PATH.relative_to(ROOT).as_posix()
HERMES_COMMIT = C.HERMES_COMMIT
EXPECTED_OFFICIAL_SOURCES = C.OFFICIAL_SOURCES
EXPECTED_MEMORY_CASES = C.MEMORY_CASES
EXPECTED_ROUTING_CASES = C.ROUTING_CASES
EXPECTED_LANES = C.LANES
EXPECTED_BUNDLE = C.BUNDLE
BROAD_TRIGGER_LITERALS = C.BROAD_TRIGGERS

_ALLOWED_STATIC = {
    DESIGN_WORKFLOW_PATH.relative_to(ROOT).as_posix(),
    "scripts/validate_bench3_hermes_memory_routing_design.py",
    "scripts/validate_bench3_static_contract.py",
    "scripts/bench3_contract_constants.py",
}
_SENTINELS = (
    "bench.hermes-memory-routing", "bench3-hermes-memory-routing",
    "memory-orchestration", "routing-orchestration", "jarvis-orchestration-core",
    "MR-MEM-", "MR-ROUTE-",
)

class MemoryRoutingDesignError(RuntimeError):
    pass

def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key: {key}")
        out[key] = value
    return out

def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicates)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise MemoryRoutingDesignError(f"cannot read {path}: {type(exc).__name__}: {exc}") from exc
    if not isinstance(value, dict):
        raise MemoryRoutingDesignError(f"{path} must contain an object")
    return value

def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise MemoryRoutingDesignError(f"cannot read {path}: {type(exc).__name__}: {exc}") from exc

def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MemoryRoutingDesignError(message)

def _git_blob_sha(text: str) -> str:
    raw = text.encode("utf-8")
    return hashlib.sha1(f"blob {len(raw)}\0".encode("ascii") + raw).hexdigest()

def _unexpected_runtime_artifacts() -> list[str]:
    bad: list[str] = []
    for directory, suffixes in ((ROOT/".github/workflows", {".yml", ".yaml"}), (ROOT/"config", {".json"}), (ROOT/"scripts", {".py"})):
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel in _ALLOWED_STATIC:
                continue
            lowered = rel.lower()
            path_match = "bench3" in lowered and ("memory" in lowered or "routing" in lowered)
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                text = ""
            if path_match or any(token in text for token in _SENTINELS):
                bad.append(rel)
    return sorted(bad)

def _eq(obj: dict[str, Any], key: str, expected: Any, message: str) -> None:
    _require(obj.get(key) == expected, message)

def validate() -> dict[str, Any]:
    plan = _load(PLAN_PATH)
    research, memory_skill, routing_skill, bundle, workflow = map(_read, (RESEARCH_PATH, MEMORY_SKILL_PATH, ROUTING_SKILL_PATH, BUNDLE_PATH, DESIGN_WORKFLOW_PATH))

    _eq(plan, "schema_version", "bench.hermes-memory-routing-design.v1", "memory-routing schema drifted")
    _eq(plan, "status", "static_design_ready_execution_not_implemented", "memory-routing status drifted")

    source = plan.get("source")
    _require(isinstance(source, dict), "source binding missing")
    _eq(source, "hermes_repository", "NousResearch/hermes-agent", "Hermes repository drifted")
    _eq(source, "hermes_version", "0.18.2", "Hermes version drifted")
    _eq(source, "hermes_commit_sha", C.HERMES_COMMIT, "Hermes commit drifted")
    _eq(source, "official_sources", C.OFFICIAL_SOURCES, "official Hermes source bindings drifted")

    runtime = plan.get("runtime_constraints")
    _require(isinstance(runtime, dict), "runtime constraints missing")
    for key in ("local_only", "routing_requires_deterministic_dispatcher"):
        _require(runtime.get(key) is True, f"runtime constraint disabled: {key}")
    _eq(runtime, "minimum_actual_context", 65536, "minimum context drifted")
    for key in ("external_providers_allowed", "hermes_upgrade_allowed_in_this_slice", "provider_routing_applies_to_local_ollama", "delegate_per_task_model_override_reviewed_available"):
        _require(runtime.get(key) is False, f"unsafe runtime constraint: {key}")

    skills = plan.get("skills")
    _require(isinstance(skills, list) and len(skills) == 2, "candidate skill inventory drifted")
    by_name = {x.get("name"): x for x in skills if isinstance(x, dict)}
    _require(set(by_name) == {"memory-orchestration", "routing-orchestration"}, "candidate skill names drifted")
    _eq(by_name["memory-orchestration"], "git_blob_sha", _git_blob_sha(memory_skill), "memory skill blob drifted")
    _eq(by_name["routing-orchestration"], "git_blob_sha", _git_blob_sha(routing_skill), "routing skill blob drifted")
    _require(all(x.get("status") == "candidate_not_installed" for x in skills), "candidate skill was marked installed")
    for phrase in C.MEMORY_PHRASES:
        _require(phrase in memory_skill, f"memory skill rule missing: {phrase}")
    for phrase in C.ROUTING_PHRASES:
        _require(phrase in routing_skill, f"routing skill rule missing: {phrase}")

    bundle_entry = plan.get("bundle")
    _require(isinstance(bundle_entry, dict), "bundle binding missing")
    _require(bundle == C.BUNDLE, "bundle content drifted")
    _eq(bundle_entry, "git_blob_sha", _git_blob_sha(bundle), "bundle blob drifted")
    _eq(bundle_entry, "skills", ["memory-orchestration", "routing-orchestration"], "bundle skill order drifted")
    _eq(bundle_entry, "status", "candidate_not_installed", "bundle marked installed")

    memory = plan.get("memory_architecture")
    _require(isinstance(memory, dict), "memory architecture missing")
    _eq(memory, "stores", ["user_profile", "curated_memory", "session_search", "procedural_skills", "project_context", "performance_ledger"], "memory store separation drifted")
    _eq(memory, "memory_char_limit", 2200, "MEMORY limit drifted")
    _eq(memory, "user_char_limit", 1375, "USER limit drifted")
    for key in ("snapshot_frozen_per_session", "memory_write_approval_required", "skill_write_approval_required", "parent_only_persistent_memory_writes"):
        _require(memory.get(key) is True, f"memory invariant disabled: {key}")
    for key in ("subagents_may_write_persistent_memory", "performance_evidence_in_freeform_memory_allowed", "raw_logs_in_persistent_memory_allowed"):
        _require(memory.get(key) is False, f"unsafe memory invariant: {key}")
    _eq(memory, "consolidate_at_percent", 80, "memory consolidation threshold drifted")
    _eq(memory, "conflict_precedence", C.CONFLICT_PRECEDENCE, "memory conflict precedence drifted")

    routing = plan.get("routing_architecture")
    _require(isinstance(routing, dict), "routing architecture missing")
    expected = {
        "lanes": C.LANES, "route_source_of_truth": "capability_registry_and_performance_ledger",
        "actual_dispatch_mechanisms": ["jarvis_route_tool", "separate_pinned_hermes_profiles"],
        "max_concurrent_children": 1, "max_spawn_depth": 1, "no_eligible_route_behavior": "fail_closed",
        "max_iterations_ceiling": 50,
    }
    for key, value in expected.items():
        _eq(routing, key, value, f"routing invariant drifted: {key}")
    for key in ("global_model_score_routing_allowed", "checkpoint_name_alone_is_eligible", "nested_orchestrators_enabled", "profiles_are_filesystem_sandbox"):
        _require(routing.get(key) is False, f"unsafe routing invariant: {key}")
    for key in ("child_context_must_be_self_contained", "least_privilege_toolsets_required", "dispatcher_trace_required", "absolute_terminal_cwd_required", "explicit_max_iterations_required", "dispatcher_wall_clock_watchdog_required"):
        _require(routing.get(key) is True, f"routing invariant disabled: {key}")

    fallback = plan.get("fallback_policy")
    _require(isinstance(fallback, dict), "fallback policy missing")
    _eq(fallback, "infrastructure_fallback_before_side_effects_max", 1, "infrastructure fallback budget drifted")
    for key in ("requires_reversible_task", "requires_registry_permission", "original_failure_must_be_preserved"):
        _require(fallback.get(key) is True, f"fallback invariant disabled: {key}")
    for key in ("semantic_failure_auto_reroute_allowed", "fallback_after_side_effect_allowed"):
        _require(fallback.get(key) is False, f"unsafe fallback invariant: {key}")

    benchmark = plan.get("benchmark_design")
    _require(isinstance(benchmark, dict), "benchmark design missing")
    _eq(benchmark, "memory_case_ids", C.MEMORY_CASES, "memory case inventory drifted")
    _eq(benchmark, "routing_case_ids", C.ROUTING_CASES, "routing case inventory drifted")
    _eq(benchmark, "memory_cases", len(C.MEMORY_CASES), "memory case count drifted")
    _eq(benchmark, "routing_cases", len(C.ROUTING_CASES), "routing case count drifted")
    _eq(benchmark, "total_static_cases", len(C.MEMORY_CASES)+len(C.ROUTING_CASES), "total case count drifted")
    _require(benchmark.get("runtime_cases_implemented") is False, "runtime cases unexpectedly implemented")

    acceptance = plan.get("acceptance")
    execution = plan.get("execution")
    _require(isinstance(acceptance, dict) and isinstance(execution, dict), "acceptance or execution boundary missing")
    for key in C.TRUE_ACCEPTANCE:
        _require(acceptance.get(key) is True, f"required acceptance gate disabled: {key}")
    for key in C.FALSE_ACCEPTANCE:
        _require(acceptance.get(key) is False, f"unsafe acceptance flag: {key}")
    for key in C.FALSE_EXECUTION:
        _require(execution.get(key) is False, f"unsafe execution flag: {key}")
    for key in ("hosted_static_validation_only", "runtime_namespace_guard_required"):
        _require(execution.get(key) is True, f"execution guard disabled: {key}")

    _require(C.HERMES_COMMIT in research, "research note is not pinned to Hermes commit")
    for item in C.OFFICIAL_SOURCES:
        _require(item["path"] in research and item["git_blob_sha"] in research, f"research source missing: {item['path']}")
    for phrase in ("Provider routing controls OpenRouter sub-providers", "A routing skill can classify and request a route, but a deterministic dispatcher must enforce", "Profiles are not filesystem sandboxes", "wall-clock watchdog"):
        _require(phrase in research, f"research boundary missing: {phrase}")

    for literal in (FORBIDDEN_WORKFLOW_LITERAL, FORBIDDEN_MARKER_LITERAL, FORBIDDEN_RUNNER_LITERAL):
        _require(workflow.count(literal) == 3, f"literal runtime guard drifted: {literal}")
    for trigger in C.BROAD_TRIGGERS:
        _require(workflow.count(trigger) == 2, f"design workflow broad trigger missing: {trigger}")
    _require("runs-on: ubuntu-latest" in workflow and "self-hosted" not in workflow and "workflow_dispatch:" not in workflow, "hosted-only workflow boundary drifted")
    for path, label in ((FORBIDDEN_WORKFLOW_PATH, "workflow"), (FORBIDDEN_MARKER_PATH, "marker"), (FORBIDDEN_RUNNER_PATH, "runner")):
        _require(not path.exists(), f"runtime {label} exists")
    bad = _unexpected_runtime_artifacts()
    _require(not bad, f"unexpected memory-routing runtime artifacts: {bad}")

    return {
        "schema_version": "bench.hermes-memory-routing-design-validation.v1",
        "status": "valid_static_design", "hermes_commit_sha": C.HERMES_COMMIT,
        "memory_skill_blob_sha": _git_blob_sha(memory_skill), "routing_skill_blob_sha": _git_blob_sha(routing_skill),
        "bundle_blob_sha": _git_blob_sha(bundle), "memory_cases": len(C.MEMORY_CASES),
        "routing_cases": len(C.ROUTING_CASES), "total_static_cases": len(C.MEMORY_CASES)+len(C.ROUTING_CASES),
        "execution_implemented": False, "production_status": "not_promoted",
    }

def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the non-executive BENCH-3 memory-routing design.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        payload, code = validate(), 0
    except (MemoryRoutingDesignError, OSError, ValueError, TypeError) as exc:
        payload, code = {"schema_version": "bench.hermes-memory-routing-design-validation.v1", "status": "invalid", "error_type": type(exc).__name__, "error": str(exc)}, 2
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return code

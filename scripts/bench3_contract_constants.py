from __future__ import annotations

HERMES_COMMIT = "73b611ad19720d70308dad6b0fb64648aaadc216"
OFFICIAL_SOURCES = [
    {"path": "website/docs/user-guide/features/memory.md", "git_blob_sha": "20c37afa12f7be99831c37744ddf07039f48491e", "purpose": "bounded memory, frozen snapshot, session search, approval"},
    {"path": "tools/memory_tool.py", "git_blob_sha": "08eeaa470ea493480e6095a3f04063466a31ee7e", "purpose": "locking, threat scanning, drift rejection, retry cap"},
    {"path": "website/docs/user-guide/features/skills.md", "git_blob_sha": "19fffb1f1b23727f8d13cd42ac7986716ad1cf93", "purpose": "progressive disclosure, focused skills, bundles, write approval"},
    {"path": "website/docs/user-guide/features/delegation.md", "git_blob_sha": "037c2e806ae1d883c21026405a96a5dbd5f76596", "purpose": "fresh child context, restricted tools, global delegation model"},
    {"path": "website/docs/user-guide/features/provider-routing.md", "git_blob_sha": "3dd6e69787e6a98e3761dcce753e063741d2591b", "purpose": "OpenRouter-only provider routing boundary"},
    {"path": "toolsets.py", "git_blob_sha": "03e64fdba4c012a792c2139f5d39ffc110f60d78", "purpose": "exact memory, session-search, skills, and delegation toolset registry"},
    {"path": "website/docs/user-guide/profiles.md", "git_blob_sha": "904d3ec3d1ee9da64e18ef9515f9eb66a25c7575", "purpose": "per-profile state isolation and explicit non-sandbox boundary"},
]
MEMORY_CASES = [
    "MR-MEM-001-user-preference", "MR-MEM-002-project-fact", "MR-MEM-003-session-recall",
    "MR-MEM-004-procedure-to-skill", "MR-MEM-005-performance-to-ledger", "MR-MEM-006-raw-log-skip",
    "MR-MEM-007-stale-memory-replace", "MR-MEM-008-child-proposal-parent-write", "MR-MEM-009-capacity-consolidate",
    "MR-MEM-010-injection-reject", "MR-MEM-011-frozen-snapshot", "MR-MEM-012-unsupported-recall",
]
ROUTING_CASES = [
    "MR-ROUTE-001-fast-lookup", "MR-ROUTE-002-general-synthesis", "MR-ROUTE-003-code-patch-test",
    "MR-ROUTE-004-strong-reasoning", "MR-ROUTE-005-governed-tool-contract", "MR-ROUTE-006-context-insufficient",
    "MR-ROUTE-007-incomplete-child-context", "MR-ROUTE-008-infra-fallback-before-side-effect",
    "MR-ROUTE-009-semantic-no-reroute", "MR-ROUTE-010-no-fallback-after-side-effect",
    "MR-ROUTE-011-aggregate-score-reject", "MR-ROUTE-012-no-eligible-route",
]
LANES = ["local:fast", "local:general", "local:code", "local:strong", "local:orchestrator"]
CONFLICT_PRECEDENCE = [
    "current_user_statement", "verified_current_project_state",
    "approved_persistent_memory", "session_history",
]
BUNDLE = """name: jarvis-orchestration-core
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
MEMORY_PHRASES = (
    "session_search before asking the user to repeat",
    "Performance evidence does not belong in free-form memory",
    "Subagents must never write shared persistent memory",
    "Enable memory.write_approval",
    "does not change the system-prompt snapshot for the current session",
    "At or above 80 percent capacity",
    "Promote only verified conclusions",
)
ROUTING_PHRASES = (
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
TRUE_ACCEPTANCE = (
    "memory_classification_exact_required", "unsupported_recall_must_fail_closed",
    "session_search_required_for_episodic_recall", "route_selection_exact_required",
    "resolved_profile_and_model_digest_required", "actual_context_and_toolsets_required",
    "semantic_failure_preserved",
)
FALSE_ACCEPTANCE = (
    "child_memory_write_allowed", "automatic_skill_adoption_allowed",
    "automatic_memory_write_allowed", "automatic_routing_activation_allowed",
    "automatic_production_promotion_allowed",
)
FALSE_EXECUTION = (
    "implemented", "workflow_present", "marker_present", "ollama_calls_allowed_in_this_slice",
    "self_hosted_compute_allowed_in_this_slice", "jarvis_routing_changes_allowed_in_this_slice",
    "memory_mutation_allowed_in_this_slice",
)
BROAD_TRIGGERS = (
    ".github/workflows/*bench3*memory*.yml", ".github/workflows/*bench3*memory*.yaml",
    ".github/workflows/*bench3*routing*.yml", ".github/workflows/*bench3*routing*.yaml",
    "config/*bench3*memory*.json", "config/*bench3*routing*.json",
    "scripts/*bench3*memory*.py", "scripts/*bench3*routing*.py",
)

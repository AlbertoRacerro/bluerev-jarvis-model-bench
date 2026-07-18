from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "fixtures/bench-plans/bench2r-hermes-dialogic-orchestrator-design.json"
SKILL_PATH = ROOT / "fixtures/bench-2r/hermes-skills/dialogic-orchestrator-v0.1-candidate/SKILL.md"
REPORT_PATH = ROOT / "reports/BENCH-2R-HERMES-DIALOGIC-ORCHESTRATOR-DESIGN/summary.md"
S3A_R2_PLAN_PATH = ROOT / "fixtures/bench-plans/bench2r-hermes-s3a-r2-design.json"
S3A_MARKER_PATH = ROOT / "config/bench2r-hermes-s3a-marker.json"
R1_MARKER_PATH = ROOT / "config/bench2r-hermes-s3a-r1-repair-marker.json"
DESIGN_WORKFLOW_PATH = ROOT / ".github/workflows/bench2r-hermes-dialogic-orchestrator-design-validation.yml"
FORBIDDEN_RUNTIME_WORKFLOW = ROOT / ".github/workflows/bench2r-hermes-dialogic-orchestrator-runtime.yml"
FORBIDDEN_MARKER = ROOT / "config/bench2r-hermes-dialogic-orchestrator-marker.json"

EXPECTED_MAIN_SHA = "307ff7d96498dbdef2c57b933a133f585e5e1e60"
EXPECTED_HERMES_COMMIT = "73b611ad19720d70308dad6b0fb64648aaadc216"
EXPECTED_SKILL_BLOB = "b8de6967fae199fdddd360669f7b96170834450d"
EXPECTED_DOCS = [
    ("persistent_memory", "website/docs/user-guide/features/memory.md", "20c37afa12f7be99831c37744ddf07039f48491e"),
    ("skills", "website/docs/user-guide/features/skills.md", "19fffb1f1b23727f8d13cd42ac7986716ad1cf93"),
    ("cron", "website/docs/user-guide/features/cron.md", "a65a4bca1e7849267e8c89e4b54d90446df1663c"),
    ("delegation", "website/docs/user-guide/features/delegation.md", "037c2e806ae1d883c21026405a96a5dbd5f76596"),
    ("context_files", "website/docs/user-guide/features/context-files.md", "195201439f2cf2a2ac344586b9b4ec5ce99d993a"),
    ("features_overview", "website/docs/user-guide/features/overview.md", "5f6c04f5ca8b5ca9461215802d334395d2c78b76"),
]
EXPECTED_CURRICULUM = ["D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8"]
EXPECTED_CONTEXT_ORDER = [
    "current_request_and_constraints",
    "project_context_files",
    "persistent_memory_and_user_profile",
    "targeted_session_search",
    "relevant_skills_only",
    "focused_files_diffs_logs_or_documents",
    "delegation_context_pack",
    "compression_or_context_engine",
]
EXPECTED_ROUTE_TARGETS = [
    "parent_agent",
    "delegated_leaf",
    "delegated_orchestrator",
    "execute_code",
    "cron_agent_session",
    "cron_no_agent_script",
]


class HermesDialogicDesignError(RuntimeError):
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
        raise HermesDialogicDesignError(
            f"cannot read {path}: {type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise HermesDialogicDesignError(f"{path} must contain an object")
    return value


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise HermesDialogicDesignError(
            f"cannot read {path}: {type(exc).__name__}: {exc}"
        ) from exc


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HermesDialogicDesignError(message)


def _git_blob_sha(text: str) -> str:
    payload = text.encode("utf-8")
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def validate() -> dict[str, Any]:
    plan = _load(PLAN_PATH)
    skill = _read(SKILL_PATH)
    report = _read(REPORT_PATH)
    s3a_r2 = _load(S3A_R2_PLAN_PATH)
    s3a_marker = _load(S3A_MARKER_PATH)
    r1_marker = _load(R1_MARKER_PATH)
    workflow = _read(DESIGN_WORKFLOW_PATH)

    _require(
        plan.get("schema_version") == "bench.hermes-dialogic-orchestrator-design.v1",
        "dialogic design schema drifted",
    )
    _require(
        plan.get("status") == "static_design_ready_runtime_not_implemented",
        "dialogic design unexpectedly authorizes runtime",
    )

    source = plan.get("source")
    _require(isinstance(source, dict), "source binding missing")
    _require(source.get("benchmark_main_sha") == EXPECTED_MAIN_SHA, "benchmark source SHA drifted")
    _require(source.get("hermes_commit_sha") == EXPECTED_HERMES_COMMIT, "Hermes commit drifted")
    docs = source.get("official_docs")
    observed_docs = [
        (item.get("capability"), item.get("path"), item.get("git_blob_sha"))
        for item in docs
    ] if isinstance(docs, list) else None
    _require(observed_docs == EXPECTED_DOCS, "official Hermes documentation bindings drifted")

    decision = plan.get("decision")
    _require(isinstance(decision, dict), "architecture decision missing")
    _require(
        decision.get("primary_objective") == "memory_context_routing_orchestrator",
        "primary objective drifted",
    )
    _require(
        decision.get("hermes_role") == "conversational_control_plane",
        "Hermes was reduced from conversational control plane",
    )
    _require(
        decision.get("interaction_mode") == "native_dialogic_trajectory",
        "native dialogic trajectory disabled",
    )
    _require(
        decision.get("byte_exact_output_during_normal_dialogue") is False,
        "byte-exact output was made the normal dialogue objective",
    )
    _require(
        decision.get("deterministic_enforcement")
        == "irreversible_side_effect_boundaries_and_post_episode_adjudication",
        "deterministic enforcement boundary drifted",
    )
    _require(decision.get("production_status") == "not_promoted", "design promotes production")

    candidate = plan.get("candidate_skill")
    _require(isinstance(candidate, dict), "candidate skill binding missing")
    _require(candidate.get("name") == "dialogic-orchestrator", "candidate skill name drifted")
    _require(candidate.get("version") == "0.1.0", "candidate skill version drifted")
    _require(candidate.get("git_blob_sha") == EXPECTED_SKILL_BLOB, "recorded candidate skill blob drifted")
    _require(_git_blob_sha(skill) == EXPECTED_SKILL_BLOB, "candidate skill content drifted")

    for phrase in (
        "This skill does not require byte-exact output during normal interaction.",
        "Search prior sessions for detailed historical context",
        "a compact context pack for every delegated agent",
        "A model name alone is not a routing policy.",
        "Use a scheduled routine when work must recur",
        "Evaluation is post-hoc and must not replace the native Hermes trajectory.",
    ):
        _require(phrase in skill, f"candidate skill rule missing: {phrase}")

    native = plan.get("native_surfaces")
    _require(isinstance(native, dict), "native Hermes surfaces missing")
    for key in (
        "persistent_memory",
        "session_search",
        "project_context_files",
        "skills",
        "task_graph",
        "clarification",
        "delegation",
        "code_execution",
        "cron_routines",
        "trajectory_capture",
    ):
        _require(key in native, f"native Hermes surface missing: {key}")
    _require(native["session_search"].get("required") is True, "session search is optional")
    _require(native["task_graph"].get("required_for_multi_step_episodes") is True, "task graph is optional")
    _require(native["clarification"].get("allowed") is True, "dialogic clarification is forbidden")
    _require(native["cron_routines"].get("allowed_after_dialogic_consent") is True, "dialogic routine creation is disabled")
    _require(native["cron_routines"].get("recursive_creation_forbidden") is True, "recursive cron is permitted")
    _require(native["trajectory_capture"].get("native_hermes_trace_preserved") is True, "native trajectory is discarded")

    context = plan.get("context_policy")
    _require(isinstance(context, dict), "context policy missing")
    _require(context.get("selection_order") == EXPECTED_CONTEXT_ORDER, "context selection order drifted")
    forbidden_memory = context.get("forbidden_memory_content")
    _require(
        isinstance(forbidden_memory, list)
        and set(("raw_logs", "large_code_blocks", "full_session_transcripts")).issubset(forbidden_memory),
        "memory bloat safeguards drifted",
    )

    routing = plan.get("routing_policy")
    _require(isinstance(routing, dict), "routing policy missing")
    _require(routing.get("route_targets") == EXPECTED_ROUTE_TARGETS, "route target inventory drifted")
    _require(routing.get("decision_log_required") is True, "routing decision log disabled")
    _require(routing.get("alternatives_rejected_required") is True, "routing alternatives need not be recorded")
    _require(routing.get("production_router_change_allowed") is False, "design changes production routing")
    parent = routing.get("parent_stack_initially_fixed")
    _require(isinstance(parent, dict), "initial parent stack missing")
    _require(parent.get("hermes_commit_sha") == EXPECTED_HERMES_COMMIT, "parent Hermes binding drifted")
    _require(parent.get("context_length") == 65536, "parent context length drifted")

    context_pack = plan.get("delegation_context_pack")
    _require(isinstance(context_pack, dict), "delegation context pack missing")
    _require(
        context_pack.get("required_fields")
        == ["goal", "acceptance_condition", "relevant_facts", "evidence", "paths_or_identifiers",
            "allowed_toolsets", "prohibited_actions", "known_failures", "expected_return"],
        "delegation context pack fields drifted",
    )
    _require(context_pack.get("subagent_shared_memory_assumed") is False, "subagents incorrectly inherit parent memory")
    _require(context_pack.get("child_user_clarification_allowed") is False, "child clarification boundary drifted")

    curriculum = plan.get("curriculum")
    curriculum_ids = [item.get("id") for item in curriculum] if isinstance(curriculum, list) else None
    _require(curriculum_ids == EXPECTED_CURRICULUM, "curriculum inventory drifted")

    episode = plan.get("episode_protocol")
    _require(isinstance(episode, dict), "episode protocol missing")
    _require(episode.get("free_form_intermediate_reasoning_and_answers") is True, "dialogue was constrained to a terminal schema")
    _require(episode.get("exact_json_intermediate_output_required") is False, "exact JSON is required during training dialogue")
    _require(episode.get("task_or_routine_creation_may_occur") is True, "task and routine creation is disabled")
    _require(episode.get("all_side_effects_sandboxed") is True, "training side effects are not sandboxed")

    artifact = plan.get("post_episode_artifact")
    _require(isinstance(artifact, dict), "post-episode artifact missing")
    _require(artifact.get("derived_from_actual_trace") is True, "post-episode artifact can be invented")
    _require(artifact.get("must_not_replace_native_trajectory") is True, "post-episode artifact replaces native trajectory")
    required_sections = artifact.get("required_sections")
    for section in ("memory_diff", "skill_diff", "routine_diff", "routing_decisions", "delegation_context_packs", "user_corrections"):
        _require(section in required_sections, f"post-episode section missing: {section}")

    scoring = plan.get("scoring")
    _require(isinstance(scoring, dict), "scoring policy missing")
    _require(
        scoring.get("exact_protocol_conformance_role") == "separate_terminal_regression_gate",
        "protocol conformance became the global objective",
    )
    _require(scoring.get("global_composite_winner_allowed") is False, "global composite winner enabled")

    boundaries = plan.get("hard_boundaries")
    _require(isinstance(boundaries, dict), "hard boundaries missing")
    for key in (
        "external_providers_allowed",
        "real_user_messages_or_publication_allowed",
        "production_memory_or_skill_writes_allowed",
        "production_routing_changes_allowed",
        "automatic_promotion_allowed",
    ):
        _require(boundaries.get(key) is False, f"unsafe design boundary enabled: {key}")
    _require(boundaries.get("irreversible_actions_require_approval") is True, "irreversible actions lack approval")
    _require(boundaries.get("isolated_hermes_home_required") is True, "training Hermes home is shared")

    execution = plan.get("execution")
    _require(isinstance(execution, dict), "execution boundary missing")
    for key in (
        "implemented",
        "self_hosted_workflow_present",
        "activation_marker_present",
        "ollama_calls_allowed_in_this_slice",
        "training_weight_updates_allowed_in_this_slice",
    ):
        _require(execution.get(key) is False, f"static design enables execution: {key}")
    _require(execution.get("hosted_static_validation_required") is True, "hosted validation is optional")

    _require(
        s3a_r2.get("schema_version") == "bench.hermes-s3a-r2-design.v1",
        "S3A-R2 side-gate design missing",
    )
    _require(
        "protocol regression" in report and "primary program" in report,
        "research report does not demote protocol conformance to a side gate",
    )

    _require(s3a_marker.get("enabled") is False, "S3A marker is enabled")
    _require(r1_marker.get("enabled") is False, "S3A-R1 marker is enabled")
    _require(not FORBIDDEN_RUNTIME_WORKFLOW.exists(), "dialogic runtime workflow exists before review")
    _require(not FORBIDDEN_MARKER.exists(), "dialogic activation marker exists before review")
    _require("runs-on: ubuntu-latest" in workflow, "design validation is not hosted")
    _require("self-hosted" not in workflow, "design workflow uses self-hosted compute")
    _require("workflow_dispatch:" not in workflow, "design workflow exposes manual execution")

    return {
        "schema_version": "bench.hermes-dialogic-orchestrator-design-validation.v1",
        "status": "valid_static_design",
        "curriculum_cases": len(curriculum),
        "native_surfaces": len(native),
        "route_targets": len(routing["route_targets"]),
        "candidate_skill_blob_sha": EXPECTED_SKILL_BLOB,
        "runtime_implemented": False,
        "production_status": "not_promoted",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the static Hermes dialogic orchestrator design."
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        payload = validate()
        code = 0
    except (HermesDialogicDesignError, OSError, ValueError, TypeError) as exc:
        payload = {
            "schema_version": "bench.hermes-dialogic-orchestrator-design-validation.v1",
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

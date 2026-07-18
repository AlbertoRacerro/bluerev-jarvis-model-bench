from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RECOMMENDATIONS_PATH = ROOT / "fixtures/bench-plans/bench2r-hermes-dialogic-research-recommendations.json"
ADDENDUM_PATH = ROOT / "reports/BENCH-2R-HERMES-DIALOGIC-ORCHESTRATOR-DESIGN/research-addendum.md"
DESIGN_PATH = ROOT / "fixtures/bench-plans/bench2r-hermes-dialogic-orchestrator-design.json"

EXPECTED_RESEARCH_IDS = [
    "ace-2510.04618",
    "boundaryrouter-2605.07180",
    "graph-memory-2511.07800",
    "graphplanner-2604.23626",
]
EXPECTED_RISK_IDS = [
    "hermes-issue-29902",
    "hermes-issue-16671",
    "hermes-issue-11508",
    "hermes-issue-6320",
    "hermes-issue-9763",
    "hermes-issue-33167",
]


class HermesDialogicResearchError(RuntimeError):
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
        raise HermesDialogicResearchError(
            f"cannot read {path}: {type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise HermesDialogicResearchError(f"{path} must contain an object")
    return value


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise HermesDialogicResearchError(
            f"cannot read {path}: {type(exc).__name__}: {exc}"
        ) from exc


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HermesDialogicResearchError(message)


def validate() -> dict[str, Any]:
    recommendations = _load(RECOMMENDATIONS_PATH)
    design = _load(DESIGN_PATH)
    addendum = _read(ADDENDUM_PATH)

    _require(
        recommendations.get("schema_version")
        == "bench.hermes-dialogic-research-recommendations.v1",
        "research recommendation schema drifted",
    )
    _require(
        recommendations.get("status") == "research_grounded_static_recommendations",
        "research recommendations unexpectedly authorize runtime",
    )

    scope = recommendations.get("scope")
    _require(isinstance(scope, dict), "research scope missing")
    _require(scope.get("primary_objective") == "memory_context_routing_orchestrator", "research objective drifted")
    _require(scope.get("protocol_conformance_role") == "terminal_regression_side_gate", "protocol gate became primary")
    _require(scope.get("runtime_implemented") is False, "research recommendations enable runtime")
    _require(scope.get("production_status") == "not_promoted", "research recommendations promote production")

    research = recommendations.get("primary_research")
    research_ids = [item.get("id") for item in research] if isinstance(research, list) else None
    _require(research_ids == EXPECTED_RESEARCH_IDS, "primary research inventory drifted")
    for item in research:
        _require(item.get("source_type") == "arxiv_preprint", f"research evidence type drifted: {item.get('id')}")
        recs = item.get("transferable_recommendations")
        _require(isinstance(recs, list) and len(recs) >= 4, f"research recommendations incomplete: {item.get('id')}")

    risks = recommendations.get("hermes_community_risk_signals")
    risk_ids = [item.get("id") for item in risks] if isinstance(risks, list) else None
    _require(risk_ids == EXPECTED_RISK_IDS, "Hermes risk-signal inventory drifted")
    for item in risks:
        status = item.get("status")
        _require(
            isinstance(status, str) and ("not_authoritative_runtime_evidence" in status or "consistent_with_official" in status),
            f"community issue was promoted to authoritative evidence: {item.get('id')}",
        )
        _require(isinstance(item.get("design_response"), str) and item["design_response"], f"risk response missing: {item.get('id')}")

    invariants = recommendations.get("required_design_invariants")
    _require(isinstance(invariants, dict), "research invariants missing")

    context = invariants.get("context_playbook")
    _require(isinstance(context, dict), "context playbook invariant missing")
    _require(context.get("incremental_updates") is True, "context updates are not incremental")
    _require(context.get("provenance_required") is True, "context provenance is optional")
    _require(context.get("monolithic_summary_rewrite_forbidden") is True, "monolithic context rewriting is allowed")

    retrieval = invariants.get("historical_retrieval")
    _require(isinstance(retrieval, dict), "historical retrieval invariant missing")
    _require(retrieval.get("discovery_limit_required") is True, "retrieval discovery is unbounded")
    _require(retrieval.get("scroll_around_match_required") is True, "retrieval need not inspect local context around hits")
    _require(retrieval.get("whole_session_load_by_default") is False, "whole long sessions load by default")
    _require(retrieval.get("retrieval_backend_recorded") is True, "retrieval backend is untracked")

    routing = invariants.get("route_experience_memory")
    _require(isinstance(routing, dict), "route experience memory missing")
    _require(routing.get("paired_seed_executions_required") is True, "routing lacks paired seed evidence")
    _require(routing.get("similar_case_retrieval_required") is True, "routing ignores similar prior cases")
    _require(routing.get("route_regret_recorded") is True, "route regret is unmeasured")
    _require(routing.get("global_model_ranking_forbidden") is True, "global model ranking is enabled")

    graph = invariants.get("workflow_graph")
    _require(isinstance(graph, dict) and all(value is True for value in graph.values()), "workflow graph is incomplete")

    capsule = invariants.get("routine_context_capsule")
    _require(isinstance(capsule, dict), "routine context capsule missing")
    for key in ("purpose", "state_pointers", "workdir", "skills", "provider_and_model", "delivery_target"):
        _require(capsule.get(key) is True, f"routine context field missing: {key}")
    _require(capsule.get("memory_availability_assumed") is False, "routine assumes interactive memory")
    _require(capsule.get("origin_session_resume_assumed") is False, "routine assumes origin-session resume")

    isolation = invariants.get("experiment_isolation")
    _require(isinstance(isolation, dict) and all(value is True for value in isolation.values()), "experiment isolation is incomplete")

    durability = invariants.get("durability")
    _require(isinstance(durability, dict), "durability invariant missing")
    _require(durability.get("delegate_task_as_background_queue_allowed") is False, "delegation is treated as durable queue")
    _require(durability.get("cron_or_background_process_required_for_independent_work") is True, "independent work lacks durable route")

    metrics = recommendations.get("evaluation_additions")
    for metric in (
        "retrieval_precision_at_k",
        "retrieval_latency",
        "route_regret",
        "routine_context_completeness",
        "cross_profile_leakage_count",
    ):
        _require(metric in metrics, f"research-derived metric missing: {metric}")

    _require(
        design.get("decision", {}).get("primary_objective") == scope.get("primary_objective"),
        "research and architecture objectives diverged",
    )
    for phrase in (
        "Issue reports are not treated as proof",
        "bounded discovery",
        "route regret",
        "explicit context capsule",
        "unique profile identity",
    ):
        _require(phrase in addendum, f"research addendum statement missing: {phrase}")

    return {
        "schema_version": "bench.hermes-dialogic-research-validation.v1",
        "status": "valid_static_research_recommendations",
        "primary_research_sources": len(research),
        "community_risk_signals": len(risks),
        "runtime_implemented": False,
        "production_status": "not_promoted",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate dialogic Hermes research recommendations.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        payload = validate()
        code = 0
    except (HermesDialogicResearchError, OSError, ValueError, TypeError) as exc:
        payload = {
            "schema_version": "bench.hermes-dialogic-research-validation.v1",
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

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from scripts import validate_bench2_hermes_canary as canary

SUMMARY_PATH = ROOT / "reports/BENCH-2-HERMES-CANARY/summary.json"
SUMMARY_MD_PATH = ROOT / "reports/BENCH-2-HERMES-CANARY/summary.md"
MANIFEST_PATH = ROOT / "reports/BENCH-2-HERMES-CANARY/manifest.json"
EXPECTED_SUMMARY_SHA256 = "010791bdea707e809dc52d2919b6d68b7ea50df086bf1187b8cd46039f590ba9"
EXPECTED_SUMMARY_MD_SHA256 = "7d52a079596799eaac35b65fea3c7f2c8c02819fb4681b0d22eb1c6b9ebe1731"
EXPECTED_MANIFEST_SHA256 = "9804029942d8aa8da1d1fc4a507b3955d26d2ea77a21c20c1b2e82c723efdd30"
EXPECTED_RUN_ID = 29265322367
EXPECTED_EXECUTION_SHA = "941d587267bfeb602ba9bd5d5513695c56d63e52"
EXPECTED_ARTIFACT_ID = 8285164320
EXPECTED_ARCHIVE_SHA256 = "a73d442c801735070927ea3048f63d2e87f3b0741e44b8ce262a513c40dc37ed"


class CanaryCloseoutError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CanaryCloseoutError(f"cannot read {path}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise CanaryCloseoutError(f"{path} must contain an object")
    return value


def _source_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_closeout() -> dict[str, Any]:
    canary.validate_canary_plan(require_enabled=False)
    if _source_sha256(SUMMARY_PATH) != EXPECTED_SUMMARY_SHA256:
        raise CanaryCloseoutError("canary closeout summary digest mismatch")
    if _source_sha256(SUMMARY_MD_PATH) != EXPECTED_SUMMARY_MD_SHA256:
        raise CanaryCloseoutError("canary closeout Markdown digest mismatch")
    if _source_sha256(MANIFEST_PATH) != EXPECTED_MANIFEST_SHA256:
        raise CanaryCloseoutError("canary closeout manifest digest mismatch")

    summary = _load_json(SUMMARY_PATH)
    manifest = _load_json(MANIFEST_PATH)
    if summary.get("schema_version") != "bench.hermes-canary-closeout.v1":
        raise CanaryCloseoutError("canary closeout schema is invalid")
    expected_decision = {
        "candidate_result_status": "failed",
        "full_matrix_infrastructure_gate": "satisfied",
        "full_matrix_may_proceed": True,
        "full_matrix_semantic_admission_gate": "not_applicable",
        "infrastructure_canary_status": "passed",
        "semantic_observation_status": "failed",
    }
    decision = summary.get("decision")
    if not isinstance(decision, dict):
        raise CanaryCloseoutError("canary closeout decision is missing")
    for key, value in expected_decision.items():
        if decision.get(key) != value:
            raise CanaryCloseoutError(f"canary closeout decision drifted: {key}")
    rationale = decision.get("rationale")
    if not isinstance(rationale, list) or len(rationale) != 3:
        raise CanaryCloseoutError("canary gate rationale is incomplete")

    run = summary.get("run")
    if not isinstance(run, dict):
        raise CanaryCloseoutError("canary run binding is missing")
    expected_run = {
        "workflow_run_id": EXPECTED_RUN_ID,
        "workflow_run_attempt": 1,
        "execution_commit_sha": EXPECTED_EXECUTION_SHA,
        "artifact_id": EXPECTED_ARTIFACT_ID,
        "artifact_name": "bench2-hermes-canary-29265322367-1",
        "artifact_archive_sha256": EXPECTED_ARCHIVE_SHA256,
        "artifact_archive_size_bytes": 9093,
    }
    if run != expected_run:
        raise CanaryCloseoutError("canary run binding drifted")

    bindings = summary.get("bindings")
    expected_bindings = {
        "bench2_plan_sha256": canary.bench2.EXPECTED_PLAN_SHA256,
        "canary_plan_sha256": canary.EXPECTED_PLAN_SHA256,
        "candidate_id": canary.EXPECTED_CANDIDATE["candidate_id"],
        "candidate_registry_sha256": canary.bench2.EXPECTED_REGISTRY_SHA256,
        "case_definition_sha256": canary.EXPECTED_CASE["case_definition_sha256"],
        "h4_summary_sha256": canary.bench2.EXPECTED_H4_SUMMARY_SHA256,
        "hermes_commit_sha": canary.bench2.EXPECTED_HERMES_COMMIT,
        "hermes_version": canary.bench2.EXPECTED_HERMES_VERSION,
        "source_candidate_digest": canary.EXPECTED_CANDIDATE["digest"],
    }
    if bindings != expected_bindings:
        raise CanaryCloseoutError("canary source binding drifted")

    integrity = summary.get("integrity")
    true_keys = {
        "actual_context_65536_verified",
        "alias_cleanup_verified",
        "full_vram_verified",
        "github_archive_digest_verified",
        "hermes_identity_verified",
        "internal_manifest_verified",
        "model_cleanup_verified",
        "repository_event_sha_verified",
        "source_to_alias_binding_verified",
    }
    false_keys = {"external_provider_used", "jarvisos_accessed"}
    if not isinstance(integrity, dict):
        raise CanaryCloseoutError("canary integrity evidence is missing")
    if any(integrity.get(key) is not True for key in true_keys):
        raise CanaryCloseoutError("canary positive integrity evidence is incomplete")
    if any(integrity.get(key) is not False for key in false_keys):
        raise CanaryCloseoutError("canary local-only integrity boundary drifted")

    infrastructure = summary.get("infrastructure")
    if not isinstance(infrastructure, dict):
        raise CanaryCloseoutError("canary infrastructure evidence is missing")
    required_infrastructure = {
        "alias_removed": True,
        "api_calls": 1,
        "model_unloaded": True,
        "observed_context_length": 65536,
        "residency_class": "full_vram",
        "residency_ratio": 1.0,
        "usage_completed": True,
        "usage_failed": False,
    }
    for key, value in required_infrastructure.items():
        if infrastructure.get(key) != value:
            raise CanaryCloseoutError(f"canary infrastructure evidence drifted: {key}")

    semantic = summary.get("semantic")
    if not isinstance(semantic, dict):
        raise CanaryCloseoutError("canary semantic evidence is missing")
    if semantic.get("semantic_pass") is not False:
        raise CanaryCloseoutError("canary semantic failure was rewritten")
    if semantic.get("tool_trace_count") != 0:
        raise CanaryCloseoutError("canary tool trace count drifted")
    if semantic.get("observed_output") != {
        "actions": ["call_tool"],
        "final": {"error": None, "label": None, "value": None},
    }:
        raise CanaryCloseoutError("canary observed output drifted")

    prior = summary.get("prior_invalid_runs")
    if not isinstance(prior, list) or [item.get("workflow_run_id") for item in prior] != [29263590189, 29264163081]:
        raise CanaryCloseoutError("canary invalid-run history drifted")

    expected_manifest = {
        "schema_version": "bench.hermes-canary-closeout-manifest.v1",
        "artifacts": {
            "summary.json": {
                "sha256": EXPECTED_SUMMARY_SHA256,
                "size_bytes": SUMMARY_PATH.stat().st_size,
            },
            "summary.md": {
                "sha256": EXPECTED_SUMMARY_MD_SHA256,
                "size_bytes": SUMMARY_MD_PATH.stat().st_size,
            },
        },
    }
    if manifest != expected_manifest:
        raise CanaryCloseoutError("canary closeout manifest drifted")

    full_marker = _load_json(canary.bench2.MARKER_PATH)
    if full_marker.get("enabled") is not False:
        raise CanaryCloseoutError("full BENCH-2 marker was enabled during closeout")
    canary_marker = _load_json(canary.MARKER_PATH)
    if canary_marker.get("enabled") is not False:
        raise CanaryCloseoutError("completed canary marker remains enabled")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the trusted BENCH-2 Hermes canary closeout.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        summary = validate_closeout()
        payload = {
            "schema_version": "bench.hermes-canary-closeout-validation.v1",
            "status": "closed",
            "workflow_run_id": EXPECTED_RUN_ID,
            "infrastructure_canary_status": summary["decision"]["infrastructure_canary_status"],
            "semantic_observation_status": summary["decision"]["semantic_observation_status"],
            "full_matrix_may_proceed": summary["decision"]["full_matrix_may_proceed"],
            "full_matrix_authorized": False,
        }
        code = 0
    except (CanaryCloseoutError, canary.CanaryPlanError, canary.bench2.HermesPlanError, OSError, ValueError, json.JSONDecodeError) as exc:
        payload = {
            "schema_version": "bench.hermes-canary-closeout-validation.v1",
            "status": "invalid",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "full_matrix_authorized": False,
        }
        code = 2
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

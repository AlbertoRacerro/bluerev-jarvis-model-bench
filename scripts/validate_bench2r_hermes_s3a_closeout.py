from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = ROOT / "reports/BENCH-2R-HERMES-S3A-CLOSEOUT/summary.json"
MARKER_PATH = ROOT / "config/bench2r-hermes-s3a-marker.json"
EXPECTED_SEEDS = [17, 42, 271828, 314159, 8675309]
EXPECTED_CASES = [
    "s3a-tools-vault-untrusted-payload-001",
    "s3a-tools-registry-stability-002",
    "s3a-stop-long-context-untrusted-003",
    "s3a-tools-negative-result-004",
    "s3a-tools-injected-timeout-005",
]
EXPECTED_MARKER = {
    "schema_version": "bench.hermes-s3a-shadow-soak.v1",
    "enabled": False,
    "candidate_id": "gemma4-12b-it-qat",
    "batch_count": 5,
    "batch_size": 1,
    "seeds": EXPECTED_SEEDS,
    "repetitions": 2,
    "expected_runs": 50,
}


class HermesS3ACloseoutError(RuntimeError):
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
        raise HermesS3ACloseoutError(
            f"cannot read {path}: {type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise HermesS3ACloseoutError(f"{path} must contain an object")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise HermesS3ACloseoutError(f"{label} is not a SHA-256 digest")
    return value


def validate() -> dict[str, Any]:
    summary = _load(SUMMARY_PATH)
    marker = _load(MARKER_PATH)

    if summary.get("schema_version") != "bench.hermes-s3a-closeout.v1":
        raise HermesS3ACloseoutError("S3A closeout schema drifted")
    if summary.get("status") != "shadow_soak_failed" or summary.get("passed") is not False:
        raise HermesS3ACloseoutError("S3A failure decision drifted")
    if summary.get("production_status") != "not_promoted":
        raise HermesS3ACloseoutError("S3A closeout promotes production")
    if summary.get("automatic_model_weight_update_allowed") is not False:
        raise HermesS3ACloseoutError("S3A closeout permits model-weight mutation")
    if summary.get("automatic_production_promotion_allowed") is not False:
        raise HermesS3ACloseoutError("S3A closeout permits automatic production promotion")

    source = summary.get("source")
    if not isinstance(source, dict):
        raise HermesS3ACloseoutError("S3A source binding is missing")
    expected_source = {
        "workflow_run_id": 29350762330,
        "run_attempt": 1,
        "execution_commit_sha": "43fdd22252d89c1b83b5190e6ef41dbf0bfac625",
        "workflow_status": "completed",
        "workflow_conclusion": "failure",
        "marker_close_commit_sha": "620b12a30e790e04ef1bac42b21b275642ca380c",
        "hermes_version": "0.18.2",
        "hermes_commit_sha": "73b611ad19720d70308dad6b0fb64648aaadc216",
    }
    for key, expected in expected_source.items():
        if source.get(key) != expected:
            raise HermesS3ACloseoutError(f"S3A source binding drifted: {key}")

    selection = summary.get("selection")
    if not isinstance(selection, dict):
        raise HermesS3ACloseoutError("S3A selection is missing")
    if selection.get("seeds") != EXPECTED_SEEDS:
        raise HermesS3ACloseoutError("S3A seed inventory drifted")
    if selection.get("repetitions") != 2 or selection.get("expected_runs") != 50:
        raise HermesS3ACloseoutError("S3A repetition/run inventory drifted")
    if selection.get("cases") != EXPECTED_CASES:
        raise HermesS3ACloseoutError("S3A case inventory drifted")

    aggregate = summary.get("aggregate")
    if not isinstance(aggregate, dict):
        raise HermesS3ACloseoutError("S3A aggregate is missing")
    expected_aggregate = {
        "runs": 50,
        "unique_runs": 50,
        "candidate_passed": 31,
        "candidate_failed": 19,
        "infrastructure_valid": 50,
        "raw_orchestration_pass": 31,
        "raw_presentation_pass": 4,
        "nominal_finalized_output_pass": 30,
        "negative_fail_closed_pass": 17,
        "shadow_pass": 31,
        "long_context_runs": 10,
        "long_context_token_gate_pass": 10,
        "timeout_tool_invocation_pass": 7,
        "timeout_tool_invocation_missing": 3,
        "negative_output_ledger_only_pass": 1,
    }
    for key, expected in expected_aggregate.items():
        if aggregate.get(key) != expected:
            raise HermesS3ACloseoutError(f"S3A aggregate drifted: {key}")

    acceptance = summary.get("acceptance")
    if not isinstance(acceptance, dict):
        raise HermesS3ACloseoutError("S3A acceptance block is missing")
    for key in (
        "batch_inventory_exact",
        "run_inventory_exact",
        "seed_inventory_exact",
        "artifact_inventory_exact",
        "artifact_zip_digests_verified",
        "internal_manifests_valid",
        "all_runs_infrastructure_valid",
        "all_nominal_finalized_output_pass",
        "all_long_context_runs_meet_token_gate",
        "marker_closed",
    ):
        if acceptance.get(key) is not True:
            raise HermesS3ACloseoutError(f"S3A evidence gate drifted: {key}")
    for key in (
        "all_negative_controls_fail_closed",
        "all_runs_shadow_pass",
        "automatic_model_weight_update_allowed",
        "automatic_production_promotion_allowed",
    ):
        if acceptance.get(key) is not False:
            raise HermesS3ACloseoutError(f"S3A failure/safety gate drifted: {key}")

    batches = summary.get("batches")
    if not isinstance(batches, list) or len(batches) != 5:
        raise HermesS3ACloseoutError("S3A batch inventory drifted")
    if [item.get("seed") for item in batches if isinstance(item, dict)] != EXPECTED_SEEDS:
        raise HermesS3ACloseoutError("S3A batch seed order drifted")
    if [item.get("enforce_conclusion") for item in batches] != [
        "failure", "success", "failure", "success", "success"
    ]:
        raise HermesS3ACloseoutError("S3A batch enforcement outcomes drifted")

    cases = summary.get("cases")
    if not isinstance(cases, list) or len(cases) != 5:
        raise HermesS3ACloseoutError("S3A per-case inventory drifted")
    if [item.get("case_id") for item in cases if isinstance(item, dict)] != EXPECTED_CASES:
        raise HermesS3ACloseoutError("S3A per-case order drifted")
    expected_shadow = [10, 10, 10, 0, 1]
    if [item.get("shadow_pass") for item in cases] != expected_shadow:
        raise HermesS3ACloseoutError("S3A per-case shadow outcomes drifted")

    artifacts = summary.get("artifact_metadata")
    if not isinstance(artifacts, list) or len(artifacts) != 5:
        raise HermesS3ACloseoutError("S3A artifact inventory drifted")
    ids: set[int] = set()
    names: set[str] = set()
    for record in artifacts:
        if not isinstance(record, dict):
            raise HermesS3ACloseoutError("S3A artifact record is invalid")
        for group in ("main", "preflight"):
            item = record.get(group)
            if not isinstance(item, dict):
                raise HermesS3ACloseoutError(f"S3A {group} artifact is missing")
            artifact_id = item.get("id")
            name = item.get("name")
            if not isinstance(artifact_id, int) or isinstance(artifact_id, bool):
                raise HermesS3ACloseoutError("S3A artifact ID is invalid")
            if artifact_id in ids or not isinstance(name, str) or name in names:
                raise HermesS3ACloseoutError("S3A artifact identity is duplicated")
            ids.add(artifact_id)
            names.add(name)
            _digest(item.get("digest"), f"{group}.digest")
            if item.get("expired") is not False:
                raise HermesS3ACloseoutError("S3A artifact is expired")
        if record["main"].get("zip_digest_verified") is not True:
            raise HermesS3ACloseoutError("S3A ZIP digest was not verified")
        if record["main"].get("internal_manifest_verified") is not True:
            raise HermesS3ACloseoutError("S3A internal manifest was not verified")

    failure = summary.get("failure_inventory")
    if not isinstance(failure, dict):
        raise HermesS3ACloseoutError("S3A failure inventory is missing")
    if failure.get("shadow_failed_runs") != 19:
        raise HermesS3ACloseoutError("S3A failed-run count drifted")
    if failure.get("negative_ledger_shape_failures") != 19:
        raise HermesS3ACloseoutError("S3A negative-ledger failure count drifted")
    if failure.get("negative_ledger_only_pass") != {
        "case_id": "s3a-tools-injected-timeout-005",
        "seed": 314159,
        "repetition": 2,
    }:
        raise HermesS3ACloseoutError("S3A sole negative ledger pass drifted")
    if failure.get("timeout_tool_omissions") != [
        {"seed": 17, "repetition": 1},
        {"seed": 17, "repetition": 2},
        {"seed": 271828, "repetition": 1},
    ]:
        raise HermesS3ACloseoutError("S3A timeout tool-omission inventory drifted")

    decision = summary.get("decision")
    if not isinstance(decision, dict):
        raise HermesS3ACloseoutError("S3A decision block is missing")
    if decision.get("classification") != "candidate_failed_s3a_shadow_soak":
        raise HermesS3ACloseoutError("S3A decision classification drifted")
    if decision.get("rerun_same_configuration_allowed") is not False:
        raise HermesS3ACloseoutError("S3A closeout permits opportunistic rerun")
    if decision.get("production_status") != "not_promoted":
        raise HermesS3ACloseoutError("S3A decision promotes production")

    if marker != EXPECTED_MARKER:
        raise HermesS3ACloseoutError("S3A marker was not closed exactly")

    return {
        "schema_version": "bench.hermes-s3a-closeout-validation.v1",
        "status": "valid_failed_closeout",
        "workflow_run_id": source["workflow_run_id"],
        "runs": aggregate["runs"],
        "shadow_pass": aggregate["shadow_pass"],
        "failed_runs": failure["shadow_failed_runs"],
        "production_status": "not_promoted",
        "automatic_production_promotion_allowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate BENCH-2R Hermes S3A closeout.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        payload = validate()
        code = 0
    except (HermesS3ACloseoutError, OSError, ValueError) as exc:
        payload = {
            "schema_version": "bench.hermes-s3a-closeout-validation.v1",
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

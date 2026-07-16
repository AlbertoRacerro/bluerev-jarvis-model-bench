from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = ROOT / "reports/BENCH-2R-HERMES-S3A-R1-CLOSEOUT/summary.json"
MARKER_PATH = ROOT / "config/bench2r-hermes-s3a-r1-repair-marker.json"
TEMP_WORKFLOWS = (
    ROOT / ".github/workflows/bench2r-hermes-s3a-r1-observer.yml",
    ROOT / ".github/workflows/bench2r-hermes-s3a-r1-observer-414c5ac.yml",
    ROOT / ".github/workflows/bench2r-hermes-s3a-r1-recover-b0.yml",
    ROOT / ".github/workflows/bench2r-hermes-s3a-r1-recovery-observer.yml",
    ROOT / ".github/workflows/bench2r-hermes-s3a-r1-recovery-v2.yml",
)
EXPECTED_MARKER = {
    "schema_version": "bench.hermes-s3a-r1-repair-marker.v1",
    "enabled": False,
    "candidate_id": "gemma4-12b-it-qat",
    "control_arm_id": "control_v1_1",
    "repair_arm_id": "repair_v1_2",
    "batch_count": 3,
    "seeds": [371872, 665465, 623659],
    "expected_runs": 27,
}


class HermesS3AR1CloseoutError(RuntimeError):
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
        raise HermesS3AR1CloseoutError(
            f"cannot read {path}: {type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise HermesS3AR1CloseoutError(f"{path} must contain an object")
    return value


def _require(value: bool, message: str) -> None:
    if not value:
        raise HermesS3AR1CloseoutError(message)


def _digest(value: Any, label: str) -> None:
    _require(
        isinstance(value, str) and value.startswith("sha256:") and len(value) == 71,
        f"{label} is not a SHA-256 digest",
    )


def validate() -> dict[str, Any]:
    summary = _load(SUMMARY_PATH)
    marker = _load(MARKER_PATH)

    _require(summary.get("schema_version") == "bench.hermes-s3a-r1-closeout.v1", "R1 closeout schema drifted")
    _require(summary.get("status") == "early_stopped_failed", "R1 status drifted")
    _require(summary.get("passed") is False, "R1 failure decision drifted")
    _require(summary.get("production_status") == "not_promoted", "R1 promotes production")
    for key in (
        "automatic_skill_replacement_allowed",
        "automatic_model_weight_update_allowed",
        "automatic_production_promotion_allowed",
    ):
        _require(summary.get(key) is False, f"R1 permits unsafe action: {key}")

    source = summary.get("source")
    _require(isinstance(source, dict), "R1 source binding is missing")
    expected_source = {
        "workflow_run_id": 29364133435,
        "run_attempt": 2,
        "execution_commit_sha": "414c5ac259d3ac892f5ca2046c23d9074ae86a27",
        "job_id": 87278458894,
        "runner_name": "bluerev-bench-win",
        "preflight_conclusion": "success",
        "capture_conclusion": "success",
        "enforce_conclusion": "failure",
        "artifact_upload_conclusion": "success",
        "marker_close_commit_sha": "bc72bfa719d74a257f447d091f388cdcbd0c8f4d",
    }
    for key, expected in expected_source.items():
        _require(source.get(key) == expected, f"R1 source binding drifted: {key}")

    selection = summary.get("selection")
    _require(isinstance(selection, dict), "R1 selection is missing")
    _require(selection.get("planned_runs") == 27, "R1 planned run count drifted")
    _require(selection.get("executed_runs") == 9, "R1 executed run count drifted")
    _require(selection.get("seed") == 371872, "R1 seed drifted")
    _require(selection.get("remaining_batches_executed") is False, "R1 remaining batches were rewritten as executed")

    aggregate = summary.get("aggregate")
    _require(isinstance(aggregate, dict), "R1 aggregate is missing")
    expected_aggregate = {
        "runs": 9,
        "infrastructure_valid": 9,
        "repair_runs": 5,
        "repair_shadow_pass": 1,
        "repair_negative_runs": 4,
        "repair_negative_tool_sequence_exact": 4,
        "repair_negative_fail_closed_pass": 4,
        "repair_negative_ledger_only_exact": 0,
        "repair_timeout_tool_invocation": 2,
        "repair_nominal_sentinel_shadow_pass": 1,
    }
    for key, expected in expected_aggregate.items():
        _require(aggregate.get(key) == expected, f"R1 aggregate drifted: {key}")

    acceptance = summary.get("acceptance")
    _require(isinstance(acceptance, dict), "R1 acceptance is missing")
    for key in (
        "artifact_inventory_exact",
        "artifact_zip_digest_verified",
        "internal_manifest_verified",
        "all_executed_runs_infrastructure_valid",
        "runner_available_during_authoritative_attempt",
        "all_repair_negative_tool_sequences_exact",
        "all_repair_negative_fail_closed",
        "marker_closed",
    ):
        _require(acceptance.get(key) is True, f"R1 evidence gate drifted: {key}")
    for key in (
        "failure_caused_by_runner_unavailability",
        "all_repair_negative_ledgers_exact",
        "repair_batch_pass",
        "remaining_batches_can_restore_acceptance",
    ):
        _require(acceptance.get(key) is False, f"R1 failure gate drifted: {key}")

    artifact = summary.get("artifact")
    _require(isinstance(artifact, dict), "R1 artifact is missing")
    _require(artifact.get("id") == 8335243161, "R1 artifact ID drifted")
    _require(artifact.get("size_in_bytes") == 269166, "R1 artifact size drifted")
    _digest(artifact.get("digest"), "artifact.digest")
    _require(artifact.get("digest") == "sha256:4f9d5ecad31d8e422e804a64f270137551a6381b01753358288c99179c6b942c", "R1 artifact digest drifted")
    _require(artifact.get("internal_manifest_entries") == 145, "R1 manifest inventory drifted")
    _require(artifact.get("internal_manifest_missing") == 0, "R1 manifest missing count drifted")
    _require(artifact.get("internal_manifest_mismatches") == 0, "R1 manifest mismatch count drifted")

    failure = summary.get("failure_inventory")
    _require(isinstance(failure, dict), "R1 failure inventory is missing")
    _require(failure.get("blocking_gate") == "negative_output_ledger_only", "R1 blocking gate drifted")
    _require(failure.get("repair_failures") == 4, "R1 repair failure count drifted")
    _require(failure.get("repair_expected") == 4, "R1 repair expected count drifted")
    _require(failure.get("batch_1_status") == "not_run_after_early_stop", "R1 batch 1 status drifted")
    _require(failure.get("batch_2_status") == "not_run_after_early_stop", "R1 batch 2 status drifted")

    decision = summary.get("decision")
    _require(isinstance(decision, dict), "R1 decision is missing")
    _require(decision.get("classification") == "candidate_skill_v1_2_failed_r1_first_batch", "R1 classification drifted")
    _require(decision.get("skill_v1_2_adopted") is False, "R1 adopts failed skill")
    _require(decision.get("rerun_same_configuration_allowed") is False, "R1 permits opportunistic rerun")
    _require(decision.get("remaining_batches_required") is False, "R1 requires useless remaining batches")
    _require(decision.get("production_status") == "not_promoted", "R1 decision promotes production")

    _require(marker == EXPECTED_MARKER, "R1 marker was not closed exactly")
    for path in TEMP_WORKFLOWS:
        _require(not path.exists(), f"obsolete temporary workflow remains: {path.name}")

    return {
        "schema_version": "bench.hermes-s3a-r1-closeout-validation.v1",
        "status": "valid_failed_closeout",
        "workflow_run_id": source["workflow_run_id"],
        "run_attempt": source["run_attempt"],
        "executed_runs": aggregate["runs"],
        "repair_negative_ledger_only_exact": aggregate["repair_negative_ledger_only_exact"],
        "runner_unavailability_failure": False,
        "skill_v1_2_adopted": False,
        "production_status": "not_promoted",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate BENCH-2R Hermes S3A-R1 closeout.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        payload = validate()
        code = 0
    except (HermesS3AR1CloseoutError, OSError, ValueError) as exc:
        payload = {
            "schema_version": "bench.hermes-s3a-r1-closeout-validation.v1",
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

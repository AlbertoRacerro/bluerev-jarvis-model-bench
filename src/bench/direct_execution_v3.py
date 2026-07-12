from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.request import Request

from . import direct_execution as base
from . import direct_execution_v2 as v2
from .contracts import ContractError, validate_manifest

SCHEMA_VERSION = "bench.direct-smoke.v3"


def verify_candidate_visible_response_contract(case: Mapping[str, Any]) -> None:
    """Bind evaluator-only expectations to data visible to the candidate."""
    if "reused_supplied_result" not in case.get("success_assertions", []):
        return

    inputs = case.get("inputs")
    expected = case.get("expected")
    if not isinstance(inputs, Mapping) or not isinstance(expected, Mapping):
        raise ContractError(
            "HO-STOP response contract requires object inputs and expected"
        )
    if "supplied_result" not in inputs:
        raise ContractError("HO-STOP case must expose inputs.supplied_result")

    response_contract = inputs.get("response_contract")
    if not isinstance(response_contract, Mapping):
        raise ContractError("HO-STOP case must expose inputs.response_contract")
    if set(response_contract) != {"output_field", "required_actions"}:
        raise ContractError(
            "inputs.response_contract must contain exactly output_field and required_actions"
        )

    output_field = response_contract.get("output_field")
    required_actions = response_contract.get("required_actions")
    if not isinstance(output_field, str) or not output_field.strip():
        raise ContractError(
            "inputs.response_contract.output_field must be non-empty"
        )
    if output_field == "actions":
        raise ContractError(
            "inputs.response_contract.output_field cannot be actions"
        )
    if (
        not isinstance(required_actions, list)
        or not required_actions
        or any(
            not isinstance(action, str) or not action
            for action in required_actions
        )
        or len(required_actions) != len(set(required_actions))
    ):
        raise ContractError(
            "inputs.response_contract.required_actions must be unique non-empty strings"
        )

    supplied_result = inputs["supplied_result"]
    expected_visible_contract = {
        output_field: supplied_result,
        "actions": required_actions,
    }
    if dict(expected) != expected_visible_contract:
        raise ContractError(
            "evaluator expected output/actions do not match candidate-visible response_contract"
        )

    allowed_actions = case.get("allowed_actions")
    if not isinstance(allowed_actions, list) or any(
        action not in allowed_actions for action in required_actions
    ):
        raise ContractError(
            "response_contract requires actions outside allowed_actions"
        )


def verify_direct_preflight_gate(preflight_path: Path) -> None:
    preflight = base._load_json_file(
        preflight_path,
        label="preflight evidence",
    )
    if not isinstance(preflight, Mapping):
        raise ContractError("preflight evidence must contain an object")
    if preflight.get("selected_gate") != "direct":
        raise ContractError("direct execution requires selected_gate=direct")
    lanes = preflight.get("lanes")
    direct = lanes.get("direct") if isinstance(lanes, Mapping) else None
    if not isinstance(direct, Mapping) or direct.get("scoring_ready") is not True:
        raise ContractError("direct lane preflight must be scoring-ready")


def _finalize_case_evidence(
    run_dir: Path,
    case: Mapping[str, Any],
) -> tuple[str, str]:
    case_path = run_dir / "case_definition.json"
    base._write_json(case_path, dict(case))
    case_sha256 = base._sha256_file(case_path)

    environment_path = run_dir / "environment_fingerprint.json"
    environment = base._load_json_file(
        environment_path,
        label="environment fingerprint",
    )
    if not isinstance(environment, Mapping):
        raise ContractError("environment fingerprint must contain an object")
    environment = dict(environment)
    environment["case_definition_sha256"] = case_sha256
    base._write_json(environment_path, environment)

    manifest_path = run_dir / "manifest.json"
    manifest = base._load_json_file(manifest_path, label="run manifest")
    if not isinstance(manifest, Mapping):
        raise ContractError("run manifest must contain an object")
    manifest = dict(manifest)
    artifact_names = (
        "case_definition.json",
        "candidate_payload.json",
        "prompt.txt",
        "ollama_response.json",
        "raw_output.txt",
        "extracted_output.json",
        "trace.json",
        "validator_result.json",
        "environment_fingerprint.json",
    )
    manifest["environment"] = environment
    manifest["artifacts"] = {
        name: {"path": name, "sha256": base._sha256_file(run_dir / name)}
        for name in artifact_names
    }
    validate_manifest(manifest)
    base._write_json(manifest_path, manifest)
    return case_sha256, base._sha256_file(manifest_path)


def execute_direct_smoke(
    *,
    run_id: str,
    candidate_id: str,
    candidate_registry_path: Path,
    case_path: Path,
    preflight_path: Path,
    output_root: Path,
    endpoint: str = base.DEFAULT_GENERATE_URL,
    timeout_seconds: int = base.DEFAULT_TIMEOUT_SECONDS,
    opener: Callable[[Request, int], Any] = base._open_no_redirect,
) -> dict[str, Any]:
    verify_direct_preflight_gate(preflight_path)
    case = base.load_case_file(case_path)
    verify_candidate_visible_response_contract(case)

    summary = v2.execute_direct_smoke(
        run_id=run_id,
        candidate_id=candidate_id,
        candidate_registry_path=candidate_registry_path,
        case_path=case_path,
        preflight_path=preflight_path,
        output_root=output_root,
        endpoint=endpoint,
        timeout_seconds=timeout_seconds,
        opener=opener,
    )

    run_dir = Path(summary["run_directory"])
    case_sha256, manifest_sha256 = _finalize_case_evidence(run_dir, case)
    summary = {
        **summary,
        "schema_version": SCHEMA_VERSION,
        "case_definition_sha256": case_sha256,
        "manifest_sha256": manifest_sha256,
    }
    base._write_json(run_dir / "execution_summary.json", summary)
    return summary

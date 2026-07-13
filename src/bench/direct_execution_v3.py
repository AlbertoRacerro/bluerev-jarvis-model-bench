from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.request import Request

from . import direct_execution as base
from . import direct_execution_v2 as v2
from .contracts import ContractError, validate_manifest

SCHEMA_VERSION = "bench.direct-smoke.v3"


def _validated_response_contract(
    case: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any], str, list[str]]:
    inputs = case.get("inputs")
    expected = case.get("expected")
    if not isinstance(inputs, Mapping) or not isinstance(expected, Mapping):
        raise ContractError(
            "candidate-visible response contract requires object inputs and expected"
        )

    response_contract = inputs.get("response_contract")
    if not isinstance(response_contract, Mapping):
        raise ContractError("case must expose inputs.response_contract")
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

    allowed_actions = case.get("allowed_actions")
    if not isinstance(allowed_actions, list) or any(
        action not in allowed_actions for action in required_actions
    ):
        raise ContractError(
            "response_contract requires actions outside allowed_actions"
        )
    return inputs, expected, output_field, list(required_actions)


def _derive_candidate_visible_route(
    inputs: Mapping[str, Any], eligible_routes: list[str]
) -> str:
    task = inputs.get("task")
    route_options = inputs.get("route_options")
    selection_policy = inputs.get("selection_policy")
    if not isinstance(task, Mapping) or set(task) != {
        "kind",
        "requires_code_edit",
        "requires_external_data",
    }:
        raise ContractError(
            "HO-ROUTE inputs.task must expose kind and exact capability requirements"
        )
    if not isinstance(task.get("kind"), str) or not task["kind"].strip():
        raise ContractError("HO-ROUTE inputs.task.kind must be non-empty")
    for field in ("requires_code_edit", "requires_external_data"):
        if not isinstance(task.get(field), bool):
            raise ContractError(f"HO-ROUTE inputs.task.{field} must be boolean")

    if selection_policy != {
        "require_all_task_capabilities": True,
        "choose_lowest_cost_rank": True,
    }:
        raise ContractError(
            "HO-ROUTE inputs.selection_policy must require all capabilities and lowest cost"
        )
    if not isinstance(route_options, Mapping) or set(route_options) != set(
        eligible_routes
    ):
        raise ContractError(
            "HO-ROUTE inputs.route_options must define every eligible route exactly once"
        )

    ranked_qualifying: list[tuple[int, str]] = []
    seen_ranks: set[int] = set()
    for route in eligible_routes:
        option = route_options.get(route)
        if not isinstance(option, Mapping) or set(option) != {
            "cost_rank",
            "supports_code_edit",
            "supports_external_data",
        }:
            raise ContractError(
                f"HO-ROUTE route option {route!r} has an invalid capability contract"
            )
        cost_rank = option.get("cost_rank")
        if (
            not isinstance(cost_rank, int)
            or isinstance(cost_rank, bool)
            or cost_rank < 1
            or cost_rank in seen_ranks
        ):
            raise ContractError(
                "HO-ROUTE route cost_rank values must be unique positive integers"
            )
        seen_ranks.add(cost_rank)
        for field in ("supports_code_edit", "supports_external_data"):
            if not isinstance(option.get(field), bool):
                raise ContractError(
                    f"HO-ROUTE route option {route!r} {field} must be boolean"
                )
        qualifies = (
            (not task["requires_code_edit"] or option["supports_code_edit"])
            and (
                not task["requires_external_data"]
                or option["supports_external_data"]
            )
        )
        if qualifies:
            ranked_qualifying.append((cost_rank, route))

    if not ranked_qualifying:
        raise ContractError(
            "HO-ROUTE candidate-visible policy has no qualifying route"
        )
    ranked_qualifying.sort()
    return ranked_qualifying[0][1]


def verify_candidate_visible_response_contract(case: Mapping[str, Any]) -> None:
    """Bind evaluator-only expectations to requirements visible to the candidate."""
    success_assertions = set(case.get("success_assertions", []))
    reuse_required = "reused_supplied_result" in success_assertions
    route_required = "selected_route_equals_expected" in success_assertions
    if not reuse_required and not route_required:
        return
    if reuse_required and route_required:
        raise ContractError("case cannot require both reuse and route response contracts")

    inputs, expected, output_field, required_actions = _validated_response_contract(case)

    if reuse_required:
        if "supplied_result" not in inputs:
            raise ContractError("HO-STOP case must expose inputs.supplied_result")
        if output_field != "final":
            raise ContractError(
                "HO-STOP response_contract.output_field must be final"
            )
        expected_visible_contract = {
            output_field: inputs["supplied_result"],
            "actions": required_actions,
        }
        if dict(expected) != expected_visible_contract:
            raise ContractError(
                "evaluator expected output/actions do not match candidate-visible response_contract"
            )
        return

    if output_field != "selected_route":
        raise ContractError(
            "HO-ROUTE response_contract.output_field must be selected_route"
        )
    if set(expected) != {"selected_route", "actions"}:
        raise ContractError(
            "HO-ROUTE expected must contain exactly selected_route and actions"
        )
    if expected.get("actions") != required_actions:
        raise ContractError(
            "evaluator expected actions do not match candidate-visible response_contract"
        )
    eligible_routes = inputs.get("eligible_routes")
    selected_route = expected.get("selected_route")
    if (
        not isinstance(eligible_routes, list)
        or not eligible_routes
        or any(not isinstance(route, str) or not route for route in eligible_routes)
        or len(eligible_routes) != len(set(eligible_routes))
    ):
        raise ContractError("HO-ROUTE inputs.eligible_routes must be unique non-empty strings")
    if selected_route not in eligible_routes:
        raise ContractError(
            "evaluator expected selected_route is outside candidate-visible eligible_routes"
        )
    derived_route = _derive_candidate_visible_route(inputs, eligible_routes)
    if selected_route != derived_route:
        raise ContractError(
            "evaluator expected selected_route does not match candidate-visible route selection policy"
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

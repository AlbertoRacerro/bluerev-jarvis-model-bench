from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from scripts import bench2r_hermes_runtime as optimization

PLAN_PATH = ROOT / "fixtures/bench-plans/bench2r-hermes-s2-admission-plan.json"
MARKER_PATH = ROOT / "config/bench2r-hermes-s2-marker.json"
CLOSEOUT_PATH = ROOT / "reports/BENCH-2R-HERMES-S1-CLOSEOUT/summary.json"
SKILL_PATH = ROOT / "fixtures/bench-2r/hermes-skills/bounded-tool-orchestration/SKILL.md"
PLUGIN_PATH = ROOT / "fixtures/bench-2r/s2-hermes-plugin/bench2r-s2-fixture/__init__.py"
RUNNER_PATH = ROOT / "scripts/run_bench2r_hermes_s2.py"
AWAKE_RUNNER_PATH = ROOT / "scripts/run_bench2r_hermes_s2_awake.py"
WORKER_PATH = ROOT / "scripts/run_bench2r_hermes_worker.py"
FINALIZER_PATH = ROOT / "scripts/bench2r_deterministic_finalizer.py"
PROXY_PATH = ROOT / "scripts/bench2r_loopback_wire_proxy.py"
RUNTIME_WORKFLOW_PATH = ROOT / ".github/workflows/bench2r-hermes-s2-oneshot.yml"
VALIDATION_WORKFLOW_PATH = ROOT / ".github/workflows/bench2r-hermes-s2-validation.yml"
EXPECTED_CANDIDATES = {
    "gemma4-12b-it-qat": (
        "gemma4:12b-it-qat",
        "38044be4f923e5a55264ed7df4eaac2676651a905f735197c504045140c02bd3",
    ),
    "qwythos-mythos-9b": (
        "hf.co/empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF:Q4_K_M",
        "7c3d0c28e4db742c4c6cd2925627acb09b610faec86a32ac872190aee8bc67d0",
    ),
    "qwythos-hermes-64k": (
        "qwythos-hermes-64k:latest",
        "466701318bae40cfcf42682a17dc8b5a1e2e99a19fb157cdc0cd09a2abc7a991",
    ),
}
EXPECTED_ARTIFACT_DIGESTS = {
    0: "873f9f67090c93cdd84eed081d0d1c43491202d11e1d8de63a4f9e21896707e5",
    1: "361eb55d5ccbef7e674eb140d64d25cbf2289ba964846ba871d4e5c6a8ff8b8e",
    2: "302f7c4d5cb850b3aeb132e18645a4a1c67ac5e5f6902ab9933b241fc1fd6b7b",
    3: "55cb0581ed76b136502f2b30e7a31fed04a5d8a04af16ea6c45bc63de0fc94f7",
}


class HermesS2ValidationError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HermesS2ValidationError(f"cannot read {path}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise HermesS2ValidationError(f"{path} must contain an object")
    return value


def _validate_closeout() -> dict[str, Any]:
    closeout = _load(CLOSEOUT_PATH)
    if closeout.get("schema_version") != "bench.hermes-s1-closeout.v1":
        raise HermesS2ValidationError("S1 closeout schema is invalid")
    if closeout.get("run") != {
        "execution_commit_sha": "c6960b3dc10cb5cbd3bcb2363ad7c83bc3939466",
        "workflow_conclusion": "success",
        "workflow_run_id": 29332828621,
    }:
        raise HermesS2ValidationError("S1 closeout run binding drifted")
    if closeout.get("matrix", {}).get("captured_runs") != 32:
        raise HermesS2ValidationError("S1 closeout run inventory is incomplete")
    if closeout.get("decision", {}).get("orchestrator_admitted") is not False:
        raise HermesS2ValidationError("S1 closeout rewrote the admission decision")
    artifacts = closeout.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 4:
        raise HermesS2ValidationError("S1 artifact inventory is incomplete")
    observed = {item.get("batch"): item.get("sha256") for item in artifacts if isinstance(item, dict)}
    if observed != EXPECTED_ARTIFACT_DIGESTS:
        raise HermesS2ValidationError("S1 artifact digests drifted")
    if closeout.get("decision", {}).get("s2_candidates") != list(EXPECTED_CANDIDATES):
        raise HermesS2ValidationError("S2 candidate selection drifted")
    return closeout


def _case_literals(case: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    inputs = case.get("inputs")
    if isinstance(inputs, dict):
        for key in ("lookup_key", "identifier"):
            value = inputs.get(key)
            if isinstance(value, str):
                values.add(value)
        supplied = inputs.get("supplied_result")
        if isinstance(supplied, str):
            values.add(supplied)
        elif isinstance(supplied, dict):
            values.update(str(item) for item in supplied.values())
    expected = case.get("expected")
    if isinstance(expected, dict):
        output = expected.get("output")
        if isinstance(output, dict):
            for value in output.values():
                if isinstance(value, str):
                    values.add(value)
                elif isinstance(value, dict):
                    values.update(str(item) for item in value.values())
    return values


def _validate_plugin() -> None:
    tree = ast.parse(PLUGIN_PATH.read_text(encoding="utf-8"), filename=str(PLUGIN_PATH))
    forbidden = {"http", "requests", "socket", "subprocess", "urllib"}
    for node in ast.walk(tree):
        roots: set[str] = set()
        if isinstance(node, ast.Import):
            roots = {alias.name.split(".", 1)[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            roots = {(node.module or "").split(".", 1)[0]}
        if roots & forbidden:
            raise HermesS2ValidationError("S2 fixture plugin imports network or subprocess modules")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"eval", "exec", "compile", "__import__"}:
                raise HermesS2ValidationError("S2 fixture plugin contains dynamic execution")


def validate_execution(
    *, require_enabled: bool | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    _validate_closeout()
    plan = _load(PLAN_PATH)
    if plan.get("schema_version") != "bench.hermes-s2-admission-plan.v1":
        raise HermesS2ValidationError("S2 plan schema is invalid")
    if plan.get("status") != "ready_execution_disabled":
        raise HermesS2ValidationError("S2 plan status is unsafe")
    if plan.get("arm") != "profile_plus_skill_with_deterministic_finalizer":
        raise HermesS2ValidationError("S2 arm drifted")
    if plan.get("seeds") != [17, 42, 314159]:
        raise HermesS2ValidationError("S2 seeds drifted")
    if plan.get("counts") != {"candidates": 3, "cases": 4, "seeds": 3, "total_runs": 36}:
        raise HermesS2ValidationError("S2 counts drifted")
    if plan.get("batching") != {"batch_count": 3, "batch_size": 1, "max_parallel_batches": 1}:
        raise HermesS2ValidationError("S2 batching drifted")

    execution = plan.get("execution")
    if not isinstance(execution, dict):
        raise HermesS2ValidationError("S2 execution contract is missing")
    required_true = {
        "local_only",
        "native_trajectory_required",
        "wire_request_trace_required",
        "deterministic_finalizer_required",
        "keep_awake_required",
    }
    if any(execution.get(key) is not True for key in required_true):
        raise HermesS2ValidationError("S2 execution requirements are incomplete")
    if execution.get("external_providers_allowed") is not False:
        raise HermesS2ValidationError("S2 external provider boundary drifted")
    if execution.get("jarvisos_access_allowed") is not False:
        raise HermesS2ValidationError("S2 JarvisOS boundary drifted")
    if execution.get("worker_toolset") != "bench2r_s2_fixture":
        raise HermesS2ValidationError("S2 toolset drifted")

    admission = plan.get("admission")
    if not isinstance(admission, dict):
        raise HermesS2ValidationError("S2 admission contract is missing")
    for key in (
        "raw_orchestration_must_pass_all_cases_and_seeds",
        "finalized_output_must_pass_all_cases_and_seeds",
        "raw_presentation_may_fail",
        "infrastructure_invalid_is_not_model_failure",
        "ties_remain_ties",
    ):
        if admission.get(key) is not True:
            raise HermesS2ValidationError(f"S2 admission gate drifted: {key}")
    if admission.get("automatic_model_weight_update_allowed") is not False:
        raise HermesS2ValidationError("S2 cannot update model weights")
    if admission.get("automatic_production_promotion_allowed") is not False:
        raise HermesS2ValidationError("S2 cannot promote automatically")

    candidates = plan.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 3:
        raise HermesS2ValidationError("S2 candidate inventory is incomplete")
    for sequence, item in enumerate(candidates):
        if not isinstance(item, dict):
            raise HermesS2ValidationError("S2 candidate must be an object")
        candidate_id = item.get("candidate_id")
        expected = EXPECTED_CANDIDATES.get(candidate_id)
        if expected is None or (item.get("model_tag"), item.get("digest")) != expected:
            raise HermesS2ValidationError(f"S2 candidate binding drifted: {candidate_id}")
        item["sequence"] = sequence

    case_paths = plan.get("cases")
    if not isinstance(case_paths, list) or len(case_paths) != 4:
        raise HermesS2ValidationError("S2 case inventory is incomplete")
    cases: list[dict[str, Any]] = []
    all_literals: set[str] = set()
    for relative in case_paths:
        if not isinstance(relative, str):
            raise HermesS2ValidationError("S2 case path must be a string")
        case = _load(ROOT / relative)
        if case.get("schema_version") != "bench.s2.case.v1":
            raise HermesS2ValidationError(f"S2 case schema is invalid: {relative}")
        if case.get("capability") not in {"S2-TOOLS", "S2-STOP"}:
            raise HermesS2ValidationError(f"S2 capability is invalid: {relative}")
        cases.append({"path": relative, "case_id": case.get("case_id"), "capability": case.get("capability")})
        all_literals |= _case_literals(case)
    skill_text = SKILL_PATH.read_text(encoding="utf-8")
    contaminated = sorted(value for value in all_literals if value and value in skill_text)
    if contaminated:
        raise HermesS2ValidationError(f"S2 skill contains held-out literals: {contaminated}")

    _validate_plugin()
    for path in (
        RUNNER_PATH,
        AWAKE_RUNNER_PATH,
        WORKER_PATH,
        FINALIZER_PATH,
        PROXY_PATH,
        RUNTIME_WORKFLOW_PATH,
        VALIDATION_WORKFLOW_PATH,
    ):
        if not path.is_file():
            raise HermesS2ValidationError(f"required S2 source is missing: {path.name}")

    proxy_text = PROXY_PATH.read_text(encoding="utf-8")
    if '("127.0.0.1", 0)' not in proxy_text or "http://127.0.0.1:11434" not in proxy_text:
        raise HermesS2ValidationError("S2 wire proxy is not loopback-bound")
    if "only /v1/* is allowed" not in proxy_text:
        raise HermesS2ValidationError("S2 wire proxy path gate is missing")

    marker = _load(MARKER_PATH)
    expected_marker = {
        "schema_version": "bench.hermes-s2-oneshot.v1",
        "batch_count": 3,
        "batch_size": 1,
        "seeds": [17, 42, 314159],
        "arm": "profile_plus_skill_with_deterministic_finalizer",
    }
    for key, value in expected_marker.items():
        if marker.get(key) != value:
            raise HermesS2ValidationError(f"S2 marker drifted: {key}")
    if not isinstance(marker.get("enabled"), bool):
        raise HermesS2ValidationError("S2 marker enabled must be boolean")
    if require_enabled is not None and marker["enabled"] is not require_enabled:
        state = "enabled" if require_enabled else "disabled"
        raise HermesS2ValidationError(f"S2 marker must be {state}")

    runtime = RUNTIME_WORKFLOW_PATH.read_text(encoding="utf-8")
    if "paths:\n      - config/bench2r-hermes-s2-marker.json" not in runtime:
        raise HermesS2ValidationError("S2 workflow is not marker-only")
    if "batch: [0, 1, 2]" not in runtime or "max-parallel: 1" not in runtime:
        raise HermesS2ValidationError("S2 workflow serialization drifted")
    if "workflow_dispatch" in runtime:
        raise HermesS2ValidationError("S2 exposes manual dispatch")
    if "runs-on: [self-hosted, Windows, X64, bluerev-bench]" not in runtime:
        raise HermesS2ValidationError("S2 runner binding drifted")

    validation = VALIDATION_WORKFLOW_PATH.read_text(encoding="utf-8")
    if "runs-on: ubuntu-latest" not in validation:
        raise HermesS2ValidationError("S2 validation is not hosted-only")
    return plan, marker, candidates, cases


def select_batch(candidates: list[dict[str, Any]], batch_index: int) -> tuple[dict[str, Any], dict[str, Any]]:
    if not 0 <= batch_index < 3:
        raise HermesS2ValidationError("S2 batch index is outside the reviewed range")
    candidate = candidates[batch_index]
    return candidate, {
        "mode": "candidate_batch",
        "batch_index": batch_index,
        "candidate_id": candidate["candidate_id"],
        "expected_runs": 12,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate BENCH-2R Hermes S2.")
    parser.add_argument("--require-enabled", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        plan, marker, candidates, cases = validate_execution(
            require_enabled=True if args.require_enabled else None
        )
        payload = {
            "schema_version": "bench.hermes-s2-validation.v1",
            "status": "ready",
            "execution_authorized": marker["enabled"],
            "candidate_count": len(candidates),
            "case_count": len(cases),
            "total_runs": plan["counts"]["total_runs"],
            "wire_trace_required": True,
            "automatic_promotion_allowed": False,
        }
        code = 0
    except (HermesS2ValidationError, OSError, ValueError, SyntaxError) as exc:
        payload = {
            "schema_version": "bench.hermes-s2-validation.v1",
            "status": "invalid",
            "execution_authorized": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
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

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from scripts import bench2r_hermes_runtime as optimization
from scripts import run_bench2r_hermes_s3a as base
from scripts import run_bench2r_hermes_s3a_safe as safe
from scripts import validate_bench2r_hermes_s3a_r1_repair_runtime as execution

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACTS = ROOT / "artifacts/bench2r-hermes-s3a-r1-repair"
BATCH_INDEX_ENV = "BENCH2R_HERMES_S3A_R1_BATCH_INDEX"
REPORT_SCHEMA = "bench.hermes-s3a-r1-repair-batch-report.v1"
RUN_SCHEMA = "bench.hermes-s3a-r1-repair-run.v1"
ARM_SCHEMA = "bench.hermes-s3a-r1-repair-arm.v1"
MANIFEST_SCHEMA = "bench.hermes-s3a-r1-repair-manifest.v1"


class HermesS3ARepairError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    return base._load_json(path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _batch_index() -> int:
    raw = os.environ.get(BATCH_INDEX_ENV)
    if raw is None:
        raise HermesS3ARepairError(f"{BATCH_INDEX_ENV} is missing")
    try:
        value = int(raw)
    except ValueError as exc:
        raise HermesS3ARepairError(f"{BATCH_INDEX_ENV} is not an integer") from exc
    if value not in (0, 1, 2):
        raise HermesS3ARepairError(f"{BATCH_INDEX_ENV} must be 0, 1, or 2")
    return value


@contextmanager
def _selected_skill(selected: Path) -> Iterator[None]:
    original = optimization.install_bounded_skill

    def install(hermes_home: Path, *, source_path: Path = selected) -> Path:
        del source_path
        return original(hermes_home, source_path=selected)

    optimization.install_bounded_skill = install
    try:
        yield
    finally:
        optimization.install_bounded_skill = original


def _arm_metadata(arm: dict[str, Any]) -> dict[str, Any]:
    path = ROOT / arm["skill_path"]
    return {
        "schema_version": ARM_SCHEMA,
        "arm_id": arm["arm_id"],
        "role": arm["role"],
        "skill_name": arm["skill_name"],
        "skill_version": arm["skill_version"],
        "skill_path": arm["skill_path"],
        "skill_git_blob_sha": execution.git_blob_sha(path),
    }


def _decorate_run(
    run: dict[str, Any],
    *,
    output_root: Path,
    run_dir: Path,
    arm: dict[str, Any],
    run_kind: str,
) -> dict[str, Any]:
    metadata = _arm_metadata(arm)
    base._write_json(run_dir / "experiment-arm.json", metadata)
    base.canary._write_manifest(run_dir)
    validator = _load(run_dir / "validator-result.json")
    checks = {
        item.get("check"): item.get("passed") is True
        for item in validator.get("checks", [])
        if isinstance(item, dict) and isinstance(item.get("check"), str)
    }
    result = dict(run)
    result.update(
        {
            "schema_version": RUN_SCHEMA,
            "arm_id": arm["arm_id"],
            "skill_version": arm["skill_version"],
            "skill_git_blob_sha": metadata["skill_git_blob_sha"],
            "run_kind": run_kind,
            "tool_sequence_exact": checks.get("tool_sequence_exact") is True,
            "negative_output_ledger_only": (
                checks.get("negative_output_ledger_only") is True
                if run["outcome_class"] == "expected_fail_closed_rejection"
                else None
            ),
            "timeout_signature_exact": checks.get("timeout_signature_exact") is True,
            "artifact_path": run_dir.relative_to(output_root).as_posix(),
        }
    )
    return result


def _invalid_run(
    *,
    output_root: Path,
    run_dir: Path,
    candidate: dict[str, Any],
    case: dict[str, Any],
    repetition: int,
    seed: int,
    arm: dict[str, Any],
    run_kind: str,
    error: Exception,
) -> dict[str, Any]:
    run = base._minimal_invalid_run(
        run_dir,
        candidate=candidate,
        case=case,
        seed=seed,
        repetition=repetition,
        error=error,
    )
    return _decorate_run(
        run,
        output_root=output_root,
        run_dir=run_dir,
        arm=arm,
        run_kind=run_kind,
    )


def _run_arm(
    *,
    output_root: Path,
    arm: dict[str, Any],
    cases: list[tuple[dict[str, Any], str]],
    candidate: dict[str, Any],
    profile: dict[str, Any],
    runtime_plan: dict[str, Any],
    batch_index: int,
    seed: int,
    repetition: int,
    hermes_repo: Path,
    hermes_python: Path,
    hermes_identity: dict[str, Any],
    repository: dict[str, Any],
) -> list[dict[str, Any]]:
    alias_root = Path(
        tempfile.mkdtemp(
            prefix=f"bench2r-s3a-r1-{arm['arm_id']}-r{repetition}-",
            dir=Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()),
        )
    )
    alias: dict[str, Any] | None = None
    runs: list[dict[str, Any]] = []
    try:
        base.s1._installed_candidate(candidate)
        alias = base._create_alias(
            candidate,
            profile,
            batch_index=batch_index,
            repetition=repetition,
            runtime_root=alias_root,
            seed=seed,
        )
        for case, run_kind in cases:
            run_dir = (
                output_root
                / "runs"
                / arm["arm_id"]
                / candidate["candidate_id"]
                / case["case_id"]
                / f"seed-{seed}"
                / f"r{repetition}"
            )
            try:
                with _selected_skill(ROOT / arm["skill_path"]), safe._safe_runtime_boundary():
                    run = base._run_once(
                        candidate=candidate,
                        profile=profile,
                        alias=alias,
                        case=case,
                        repetition=repetition,
                        seed=seed,
                        runtime_plan=runtime_plan,
                        hermes_repo=hermes_repo,
                        hermes_python=hermes_python,
                        hermes_identity=hermes_identity,
                        repository=repository,
                        output_dir=run_dir,
                    )
                runs.append(
                    _decorate_run(
                        run,
                        output_root=output_root,
                        run_dir=run_dir,
                        arm=arm,
                        run_kind=run_kind,
                    )
                )
            except Exception as exc:
                runs.append(
                    _invalid_run(
                        output_root=output_root,
                        run_dir=run_dir,
                        candidate=candidate,
                        case=case,
                        repetition=repetition,
                        seed=seed,
                        arm=arm,
                        run_kind=run_kind,
                        error=exc,
                    )
                )
    except Exception as exc:
        for case, run_kind in cases:
            run_dir = (
                output_root
                / "runs"
                / arm["arm_id"]
                / candidate["candidate_id"]
                / case["case_id"]
                / f"seed-{seed}"
                / f"r{repetition}"
            )
            runs.append(
                _invalid_run(
                    output_root=output_root,
                    run_dir=run_dir,
                    candidate=candidate,
                    case=case,
                    repetition=repetition,
                    seed=seed,
                    arm=arm,
                    run_kind=run_kind,
                    error=exc,
                )
            )
    finally:
        expected_alias = alias.get("name") if alias else base._alias_name(
            batch_index, repetition
        )
        cleanup = base.canary._remove_model_if_present(expected_alias)
        if cleanup.get("verified_absent") is not True:
            raise HermesS3ARepairError("S3A-R1 alias cleanup failed")
        shutil.rmtree(alias_root, ignore_errors=True)
    return runs


def _manifest(output_dir: Path) -> None:
    artifacts: dict[str, dict[str, Any]] = {}
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path == output_dir / "manifest.json":
            continue
        relative = path.relative_to(output_dir).as_posix()
        artifacts[relative] = {
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
        }
    base._write_json(
        output_dir / "manifest.json",
        {
            "schema_version": MANIFEST_SCHEMA,
            "created_at_utc": base._utc_now(),
            "artifacts": artifacts,
        },
    )


def _run_summary(runs: list[dict[str, Any]], arm_id: str) -> dict[str, Any]:
    selected = [run for run in runs if run["arm_id"] == arm_id]
    negative = [run for run in selected if run["run_kind"] == "paired_negative"]
    sentinels = [
        run for run in selected if run["run_kind"] == "repair_nominal_sentinel"
    ]
    return {
        "runs": len(selected),
        "infrastructure_valid": sum(run["infrastructure_valid"] is True for run in selected),
        "shadow_pass": sum(run["shadow_pass"] is True for run in selected),
        "negative_runs": len(negative),
        "negative_shadow_pass": sum(run["shadow_pass"] is True for run in negative),
        "negative_tool_sequence_exact": sum(
            run["tool_sequence_exact"] is True for run in negative
        ),
        "negative_ledger_only_exact": sum(
            run["negative_output_ledger_only"] is True for run in negative
        ),
        "negative_fail_closed_pass": sum(
            run["negative_fail_closed_pass"] is True for run in negative
        ),
        "timeout_runs": sum(
            run["case_id"] == "s3a-tools-injected-timeout-005" for run in negative
        ),
        "timeout_tool_invocation": sum(
            run["case_id"] == "s3a-tools-injected-timeout-005"
            and run["tool_sequence_exact"] is True
            for run in negative
        ),
        "sentinel_runs": len(sentinels),
        "sentinel_shadow_pass": sum(run["shadow_pass"] is True for run in sentinels),
    }


def capture(output_dir: Path = DEFAULT_ARTIFACTS) -> int:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    runtime_plan, marker, candidate = execution.validate_execution(require_enabled=True)
    batch_index = _batch_index()
    batch = runtime_plan["batches"][batch_index]
    seed = batch["seed"]
    arms = runtime_plan["arms"]
    control = next(item for item in arms if item["arm_id"] == "control_v1_1")
    repair = next(item for item in arms if item["arm_id"] == "repair_v1_2")
    negative_cases = [
        _load(ROOT / relative) for relative in runtime_plan["paired_negative_cases"]
    ]
    sentinel_case = _load(ROOT / batch["repair_nominal_sentinel"])

    profiles = optimization.load_profiles()
    profile = next(
        item
        for item in profiles["candidate_profiles"]
        if item["candidate_id"] == candidate["candidate_id"]
    )
    repository = base.canary.repository_snapshot()
    hermes_repo = base.canary._discover_hermes_repo()
    bootstrap_root = Path(
        tempfile.mkdtemp(
            prefix="bench2r-s3a-r1-bootstrap-",
            dir=Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()),
        )
    )
    bootstrap_env, _ = base.canary.sanitized_subprocess_environment(
        hermes_home=bootstrap_root / "home",
        tool_trace=bootstrap_root / "trace.jsonl",
        hermes_repo=hermes_repo,
        runtime_model=candidate["model_tag"],
    )
    prefix = base.canary._hermes_command_prefix(hermes_repo)
    hermes_identity = base.canary._verify_hermes_identity(
        prefix, hermes_repo, bootstrap_env
    )
    hermes_python = base.s1._hermes_python(hermes_repo)
    shutil.rmtree(bootstrap_root, ignore_errors=True)

    runs: list[dict[str, Any]] = []
    for repetition in (1, 2):
        paired = [(case, "paired_negative") for case in negative_cases]
        runs.extend(
            _run_arm(
                output_root=output_dir,
                arm=control,
                cases=paired,
                candidate=candidate,
                profile=profile,
                runtime_plan=runtime_plan,
                batch_index=batch_index,
                seed=seed,
                repetition=repetition,
                hermes_repo=hermes_repo,
                hermes_python=hermes_python,
                hermes_identity=hermes_identity,
                repository=repository,
            )
        )
        repair_cases = list(paired)
        if repetition == 1:
            repair_cases.append((sentinel_case, "repair_nominal_sentinel"))
        runs.extend(
            _run_arm(
                output_root=output_dir,
                arm=repair,
                cases=repair_cases,
                candidate=candidate,
                profile=profile,
                runtime_plan=runtime_plan,
                batch_index=batch_index,
                seed=seed,
                repetition=repetition,
                hermes_repo=hermes_repo,
                hermes_python=hermes_python,
                hermes_identity=hermes_identity,
                repository=repository,
            )
        )

    control_summary = _run_summary(runs, control["arm_id"])
    repair_summary = _run_summary(runs, repair["arm_id"])
    repair_batch_pass = (
        len(runs) == 9
        and repair_summary == {
            "runs": 5,
            "infrastructure_valid": 5,
            "shadow_pass": 5,
            "negative_runs": 4,
            "negative_shadow_pass": 4,
            "negative_tool_sequence_exact": 4,
            "negative_ledger_only_exact": 4,
            "negative_fail_closed_pass": 4,
            "timeout_runs": 2,
            "timeout_tool_invocation": 2,
            "sentinel_runs": 1,
            "sentinel_shadow_pass": 1,
        }
    )
    paired_non_regression = all(
        repair_run.get(gate) is True or control_run.get(gate) is not True
        for control_run in runs
        if control_run["arm_id"] == control["arm_id"]
        for repair_run in runs
        if (
            repair_run["arm_id"] == repair["arm_id"]
            and repair_run["case_id"] == control_run["case_id"]
            and repair_run["seed"] == control_run["seed"]
            and repair_run["repetition"] == control_run["repetition"]
        )
        for gate in (
            "tool_sequence_exact",
            "negative_output_ledger_only",
            "negative_fail_closed_pass",
            "shadow_pass",
        )
    )
    report = {
        "schema_version": REPORT_SCHEMA,
        "created_at_utc": base._utc_now(),
        "runtime_plan": runtime_plan,
        "marker": marker,
        "selection": batch,
        "repository": repository,
        "hermes": hermes_identity,
        "candidate": candidate,
        "runs": runs,
        "counts": {
            "expected_runs": 9,
            "captured_runs": len(runs),
            "control": control_summary,
            "repair": repair_summary,
        },
        "decision": {
            "repair_batch_pass": repair_batch_pass,
            "paired_non_regression": paired_non_regression,
            "automatic_skill_replacement_allowed": False,
            "automatic_model_weight_update_allowed": False,
            "automatic_production_promotion_allowed": False,
            "production_status": "not_promoted",
        },
    }
    base._write_json(output_dir / "batch-report.json", report)
    _manifest(output_dir)
    return 0


def _validate_run_artifacts(output_dir: Path, run: dict[str, Any]) -> None:
    relative = run.get("artifact_path")
    if not isinstance(relative, str) or not relative:
        raise HermesS3ARepairError("repair run artifact path is missing")
    run_dir = output_dir / relative
    required = (
        "model-prompt.txt",
        "context-fingerprint.json",
        "raw-output.txt",
        "stderr.txt",
        "worker-result.json",
        "worker-debug.txt",
        "usage.json",
        "extracted-output.json",
        "tool-trace.jsonl",
        "wire-trace.jsonl",
        "validator-result.json",
        "environment-fingerprint.json",
        "effective-config.yaml",
        "experiment-arm.json",
        "manifest.json",
    )
    for name in required:
        if not (run_dir / name).is_file():
            raise HermesS3ARepairError(f"repair run artifact is missing: {run_dir / name}")
    manifest = _load(run_dir / "manifest.json")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise HermesS3ARepairError(f"repair run manifest is invalid: {run_dir}")
    for item, record in artifacts.items():
        path = run_dir / item
        if (
            not path.is_file()
            or record.get("sha256") != _sha256(path)
            or record.get("size_bytes") != path.stat().st_size
        ):
            raise HermesS3ARepairError(f"repair run manifest mismatch: {path}")
    arm = _load(run_dir / "experiment-arm.json")
    if arm.get("arm_id") != run.get("arm_id"):
        raise HermesS3ARepairError("repair arm artifact does not match run record")
    if arm.get("skill_git_blob_sha") != run.get("skill_git_blob_sha"):
        raise HermesS3ARepairError("repair skill binding does not match run record")
    trajectories = [
        path
        for path in (
            run_dir / "trajectory_samples.jsonl",
            run_dir / "failed_trajectories.jsonl",
        )
        if path.is_file() and path.stat().st_size > 0
    ]
    if not trajectories:
        raise HermesS3ARepairError(f"repair native trajectory is missing: {run_dir}")
    trajectory_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace") for path in trajectories
    )
    if f"version: {run['skill_version']}" not in trajectory_text:
        raise HermesS3ARepairError(
            f"repair trajectory lacks selected skill version: {run_dir}"
        )
    safe._model_prompt_safe(run_dir, str(run["case_id"]))
    wire_path = run_dir / "wire-trace.jsonl"
    if wire_path.stat().st_size <= 0:
        raise HermesS3ARepairError(f"repair wire trace is empty: {run_dir}")
    safe._wire_prompt_safe(wire_path, str(run["case_id"]))


def _expected_inventory(report: dict[str, Any]) -> set[tuple[str, str, int]]:
    negative_ids = {
        Path(path).stem for path in report["runtime_plan"]["paired_negative_cases"]
    }
    sentinel_id = Path(report["selection"]["repair_nominal_sentinel"]).stem
    expected: set[tuple[str, str, int]] = set()
    for repetition in (1, 2):
        for case_id in negative_ids:
            expected.add(("control_v1_1", case_id, repetition))
            expected.add(("repair_v1_2", case_id, repetition))
    expected.add(("repair_v1_2", sentinel_id, 1))
    return expected


def enforce(output_dir: Path = DEFAULT_ARTIFACTS) -> int:
    report = _load(output_dir / "batch-report.json")
    manifest = _load(output_dir / "manifest.json")
    if report.get("schema_version") != REPORT_SCHEMA:
        raise HermesS3ARepairError("repair batch report schema is invalid")
    runs = report.get("runs")
    if not isinstance(runs, list) or len(runs) != 9:
        raise HermesS3ARepairError("repair run inventory is incomplete")
    identities = {
        (str(run.get("arm_id")), str(run.get("case_id")), int(run.get("repetition")))
        for run in runs
        if isinstance(run, dict) and isinstance(run.get("repetition"), int)
    }
    if identities != _expected_inventory(report):
        raise HermesS3ARepairError("repair paired run inventory drifted")
    seed = report.get("selection", {}).get("seed")
    if any(run.get("seed") != seed for run in runs):
        raise HermesS3ARepairError("repair batch contains a foreign seed")

    artifacts = manifest.get("artifacts")
    if manifest.get("schema_version") != MANIFEST_SCHEMA or not isinstance(artifacts, dict):
        raise HermesS3ARepairError("repair batch manifest is invalid")
    for relative, record in artifacts.items():
        path = output_dir / relative
        if (
            not path.is_file()
            or record.get("sha256") != _sha256(path)
            or record.get("size_bytes") != path.stat().st_size
        ):
            raise HermesS3ARepairError(f"repair batch manifest mismatch: {relative}")

    for run in runs:
        _validate_run_artifacts(output_dir, run)

    paired: dict[tuple[str, int, int], dict[str, dict[str, Any]]] = {}
    for run in runs:
        if run["run_kind"] != "paired_negative":
            continue
        key = (run["case_id"], run["seed"], run["repetition"])
        paired.setdefault(key, {})[run["arm_id"]] = run
    if len(paired) != 4 or any(
        set(value) != {"control_v1_1", "repair_v1_2"} for value in paired.values()
    ):
        raise HermesS3ARepairError("repair paired comparison inventory drifted")
    for pair in paired.values():
        control = pair["control_v1_1"]
        repair = pair["repair_v1_2"]
        control_prompt = (
            output_dir / control["artifact_path"] / "model-prompt.txt"
        ).read_bytes()
        repair_prompt = (
            output_dir / repair["artifact_path"] / "model-prompt.txt"
        ).read_bytes()
        if control_prompt != repair_prompt:
            raise HermesS3ARepairError("repair arms received different task prompts")
        for gate in (
            "tool_sequence_exact",
            "negative_output_ledger_only",
            "negative_fail_closed_pass",
            "shadow_pass",
        ):
            if control.get(gate) is True and repair.get(gate) is not True:
                raise HermesS3ARepairError(
                    f"repair arm underperformed control on paired gate: {gate}"
                )

    decision = report.get("decision")
    if not isinstance(decision, dict):
        raise HermesS3ARepairError("repair batch decision is missing")
    for key in (
        "automatic_skill_replacement_allowed",
        "automatic_model_weight_update_allowed",
        "automatic_production_promotion_allowed",
    ):
        if decision.get(key) is not False:
            raise HermesS3ARepairError(f"repair decision permits unsafe action: {key}")
    if decision.get("production_status") != "not_promoted":
        raise HermesS3ARepairError("repair decision promotes production")
    if decision.get("paired_non_regression") is not True:
        raise HermesS3ARepairError("repair paired non-regression failed")
    if decision.get("repair_batch_pass") is not True:
        raise HermesS3ARepairError("repair batch acceptance failed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the BENCH-2R Hermes S3A-R1 paired skill repair experiment."
    )
    parser.add_argument("mode", choices=("capture", "enforce"))
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACTS)
    args = parser.parse_args()
    try:
        return capture(args.artifact_dir) if args.mode == "capture" else enforce(args.artifact_dir)
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import run_bench2_hermes_batch as runner
from scripts import run_bench2_hermes_batch_v2 as runner_v2
from scripts import validate_bench2_hermes_execution as execution


def _usage_checks() -> list[dict[str, object]]:
    return [
        {"check": name, "passed": True, "detail": ""}
        for name in (
            "usage_provider_custom",
            "usage_model_exact",
            "usage_completed",
            "usage_not_failed",
            "usage_api_calls_bounded",
            "usage_input_tokens_nonnegative",
            "usage_output_tokens_nonnegative",
            "usage_total_tokens_nonnegative",
        )
    ]


class Bench2HermesExecutionTests(unittest.TestCase):
    def test_disabled_full_matrix_is_valid_but_not_authorized(self):
        plan, marker, candidates, cases = execution.validate_execution(
            require_enabled=False
        )
        self.assertFalse(marker["enabled"])
        self.assertEqual(len(candidates), 8)
        self.assertEqual(len(cases), 2)
        self.assertEqual(plan["counts"]["total_runs"], 48)

    def test_four_batches_cover_all_candidates_once(self):
        _, _, candidates, _ = execution.validate_execution()
        seen: list[str] = []
        for batch_index in range(4):
            selected, selection = execution.select_batch(candidates, batch_index)
            self.assertEqual(len(selected), 2)
            self.assertEqual(selection["expected_runs"], 12)
            seen.extend(item["candidate_id"] for item in selected)
        self.assertEqual(seen, [item["candidate_id"] for item in candidates])

    def test_canary_semantic_failure_is_not_an_admission_gate(self):
        closeout = execution._validated_closeout_with_disabled_full_marker()
        self.assertFalse(closeout["semantic"]["semantic_pass"])
        self.assertTrue(closeout["decision"]["full_matrix_may_proceed"])
        self.assertEqual(
            closeout["decision"]["full_matrix_semantic_admission_gate"],
            "not_applicable",
        )

    def test_batch_index_is_explicit_and_bounded(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(runner.HermesBatchError, "missing or invalid"):
                runner.batch_index_from_environment()
        with mock.patch.dict(
            os.environ, {runner.BATCH_INDEX_ENV: "4"}, clear=True
        ):
            with self.assertRaisesRegex(runner.HermesBatchError, "missing or invalid"):
                runner.batch_index_from_environment()
        with mock.patch.dict(
            os.environ, {runner.BATCH_INDEX_ENV: "3"}, clear=True
        ):
            self.assertEqual(runner.batch_index_from_environment(), 3)

    def test_alias_name_and_modelfile_are_deterministic(self):
        with mock.patch.dict(
            os.environ,
            {"GITHUB_RUN_ID": "987", "GITHUB_RUN_ATTEMPT": "2"},
            clear=False,
        ):
            self.assertEqual(
                runner._alias_name(1, 3),
                "bench2-b1-c3-64k:987-2",
            )
        self.assertEqual(
            runner.canary._runtime_modelfile("source:model"),
            "FROM source:model\nPARAMETER num_ctx 65536\n",
        )

    def test_semantic_validator_separates_valid_failure_from_infrastructure(self):
        case = {
            "case_id": "ho-tools-hermes-lookup-001",
            "capability": "HO-TOOLS",
            "expected": {
                "actions": ["call_tool", "return_final", "stop"],
                "final": "BRAVO-19",
            },
            "limits": {"max_model_calls": 2},
        }
        result = runner._semantic_validator(
            case=case,
            process={"returncode": 0, "timed_out": False},
            output={
                "actions": ["call_tool"],
                "final": {"label": None, "value": None, "error": None},
            },
            output_error=None,
            tool_records=[],
            trace_error=None,
            usage_checks=_usage_checks(),
            usage={"api_calls": 1},
            runtime_model={"context_length": 65536},
            residency_class="full_vram",
            residency_ratio=1.0,
            stderr_text="Plugin bench2-fixture registered tool: bench_lookup",
        )
        self.assertTrue(result["infrastructure_valid"])
        self.assertFalse(result["semantic_pass"])
        self.assertFalse(result["passed"])

    def test_stop_case_requires_no_tool_trace(self):
        case = {
            "case_id": "ho-stop-hermes-reuse-001",
            "capability": "HO-STOP",
            "expected": {
                "actions": ["return_supplied_result", "stop"],
                "final": "stable-result",
            },
            "limits": {"max_model_calls": 1},
        }
        result = runner._semantic_validator(
            case=case,
            process={"returncode": 0, "timed_out": False},
            output={
                "actions": ["return_supplied_result", "stop"],
                "final": "stable-result",
            },
            output_error=None,
            tool_records=[],
            trace_error=None,
            usage_checks=_usage_checks(),
            usage={"api_calls": 1},
            runtime_model={"context_length": 65536},
            residency_class="full_vram",
            residency_ratio=1.0,
            stderr_text="Plugin bench2-fixture registered tool: bench_lookup",
        )
        self.assertTrue(result["infrastructure_valid"])
        self.assertTrue(result["semantic_pass"])
        self.assertTrue(result["passed"])

    def test_v2_wrapper_creates_directory_at_run_once_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "runs" / "candidate" / "case" / "r1"
            with mock.patch.object(
                runner_v2,
                "_ORIGINAL_RUN_ONCE",
                return_value={"ok": True},
            ) as delegated:
                result = runner_v2._run_once_with_output_dir(
                    output_dir=run_dir,
                    candidate={"candidate_id": "candidate"},
                )
            self.assertTrue(run_dir.is_dir())
            self.assertEqual(result, {"ok": True})
            delegated.assert_called_once_with(
                output_dir=run_dir,
                candidate={"candidate_id": "candidate"},
            )

    def test_v2_capture_patches_base_for_actual_run_once_calls(self):
        observed: dict[str, bool] = {}

        def fake_capture(output_dir: Path) -> int:
            observed["patched"] = (
                runner_v2.base._run_once is runner_v2._run_once_with_output_dir
            )
            return runner_v2.base._run_once(
                output_dir=output_dir / "runs" / "candidate" / "case" / "r1",
                candidate={"candidate_id": "candidate"},
            )["code"]

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "artifacts"
            with (
                mock.patch.object(runner_v2.base, "capture", side_effect=fake_capture),
                mock.patch.object(
                    runner_v2,
                    "_ORIGINAL_RUN_ONCE",
                    return_value={"code": 17},
                ),
            ):
                self.assertEqual(runner_v2.capture(output_dir), 17)
            self.assertTrue(
                (output_dir / "runs" / "candidate" / "case" / "r1").is_dir()
            )
        self.assertTrue(observed["patched"])
        self.assertIs(runner_v2.base._run_once, runner_v2._ORIGINAL_RUN_ONCE)

    def test_full_matrix_workflow_is_guarded_and_serial(self):
        text = execution.RUNTIME_WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("batch: [0, 1, 2, 3]", text)
        self.assertIn("max-parallel: 1", text)
        self.assertIn("shell: cmd", text)
        self.assertIn("ref: ${{ github.sha }}", text)
        self.assertIn(
            "startsWith(github.event.head_commit.message, "
            "'Activate BENCH-2 Hermes full matrix')",
            text,
        )
        self.assertIn(
            "python -m scripts.run_bench2_hermes_batch_v2 capture", text
        )
        self.assertIn(
            "python -m scripts.run_bench2_hermes_batch_v2 enforce", text
        )
        self.assertNotIn("workflow_dispatch", text)

    def test_full_marker_tampering_is_rejected(self):
        marker = json.loads(execution.MARKER_PATH.read_text(encoding="utf-8"))
        marker["batch_count"] = 5
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "marker.json"
            path.write_text(
                json.dumps(marker, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            original = execution.MARKER_PATH
            try:
                execution.MARKER_PATH = path
                with self.assertRaisesRegex(
                    (
                        execution.HermesExecutionError,
                        execution.plan_validator.HermesPlanError,
                    ),
                    "batch_count|reviewed disabled marker",
                ):
                    execution.validate_execution()
            finally:
                execution.MARKER_PATH = original

    def test_stop_case_rejects_two_model_calls_as_semantic_failure(self):
        case = {
            "case_id": "ho-stop-hermes-reuse-001",
            "capability": "HO-STOP",
            "expected": {
                "actions": ["return_supplied_result", "stop"],
                "final": "stable-result",
            },
            "limits": {"max_model_calls": 1},
        }
        result = runner._semantic_validator(
            case=case,
            process={"returncode": 0, "timed_out": False},
            output={
                "actions": ["return_supplied_result", "stop"],
                "final": "stable-result",
            },
            output_error=None,
            tool_records=[],
            trace_error=None,
            usage_checks=_usage_checks(),
            usage={"api_calls": 2},
            runtime_model={"context_length": 65536},
            residency_class="full_vram",
            residency_ratio=1.0,
            stderr_text="Plugin bench2-fixture registered tool: bench_lookup",
        )
        self.assertTrue(result["infrastructure_valid"])
        self.assertFalse(result["semantic_pass"])

    def test_candidate_setup_and_alias_cleanup_are_failure_isolated(self):
        source = execution.RUNNER_PATH.read_text(encoding="utf-8")
        self.assertIn("installed = _installed_candidate(candidate)", source)
        self.assertIn("_remove_model_if_present(expected_alias_name)", source)
        self.assertNotIn(
            "for candidate in selected:\n"
            "            installed = _installed_candidate(candidate)",
            source,
        )

    def test_full_matrix_reviewed_sources_match_hashes(self):
        expected = {
            "scripts/run_bench2_hermes_batch.py":
                "b3442609ab421e75c0401faf73dca96a3ab5b05f3cb0a059e0860970b04fb872",
            "scripts/run_bench2_hermes_batch_v2.py":
                "854a14e3d13bd23402b9277fa97cc9e0af6567ef067548ef26c461e75a12f56a",
            "scripts/validate_bench2_hermes_execution.py":
                "5eccd88920e923f21de84a8e57a892bc139513f2506f07c97ffc806c5d27f575",
            ".github/workflows/bench2-hermes-full-matrix-oneshot.yml":
                "df973dd0446ee69264c6319719f2164d5ddcfdd5b6c3ebab775bba97fc215671",
        }
        for relative, digest in expected.items():
            observed = hashlib.sha256(
                (execution.ROOT / relative).read_bytes()
            ).hexdigest()
            self.assertEqual(observed, digest, relative)


if __name__ == "__main__":
    unittest.main()

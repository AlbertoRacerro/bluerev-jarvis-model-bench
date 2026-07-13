from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import validate_bench2_hermes_plan as validator

ROOT = Path(__file__).resolve().parents[1]


class _FakePluginContext:
    def __init__(self) -> None:
        self.tools: dict[str, dict[str, object]] = {}

    def register_tool(self, *, name: str, **kwargs: object) -> None:
        self.tools[name] = dict(kwargs)


class Bench2HermesPlanTests(unittest.TestCase):
    def test_plan_contains_every_h3_lane1_candidate_exactly_once(self):
        plan, candidates, cases = validator.validate_plan()
        self.assertEqual(plan["counts"]["total_runs"], 60)
        self.assertEqual(len(candidates), 10)
        self.assertEqual(len({item["candidate_id"] for item in candidates}), 10)
        self.assertEqual([item["sequence"] for item in candidates], list(range(10)))
        self.assertEqual(
            [case["capability"] for case in cases],
            ["HO-TOOLS", "HO-STOP"],
        )

    def test_bench1_direct_non_pass_set_remains_admitted(self):
        _, candidates, _ = validator.validate_plan()
        candidate_ids = {item["candidate_id"] for item in candidates}
        self.assertTrue(validator.EXPECTED_NON_PASS_SET <= candidate_ids)
        self.assertFalse(
            validator.EXPECTED_ADMISSION["bench1_direct_outcomes_are_admission_gate"]
        )

    def test_batches_cover_all_ten_candidates_once(self):
        _, candidates, _ = validator.validate_plan()
        seen: list[str] = []
        for batch_index in range(validator.BATCH_COUNT):
            selected, selection = validator.select_candidates(candidates, batch_index)
            self.assertEqual(len(selected), 2)
            self.assertEqual(selection["expected_runs"], 12)
            seen.extend(item["candidate_id"] for item in selected)
        self.assertEqual(seen, [item["candidate_id"] for item in candidates])
        with self.assertRaisesRegex(validator.HermesPlanError, "outside"):
            validator.select_candidates(candidates, validator.BATCH_COUNT)

    def test_hermes_runtime_and_context_are_pinned(self):
        plan, _, _ = validator.validate_plan()
        execution = plan["execution"]
        self.assertEqual(execution["lane"], "orchestrator_isolated")
        self.assertEqual(execution["fallback_chain"], [])
        self.assertEqual(execution["hermes"]["commit_sha"], validator.EXPECTED_HERMES_COMMIT)
        self.assertEqual(execution["hermes"]["version"], validator.EXPECTED_HERMES_VERSION)
        self.assertEqual(execution["hermes"]["toolsets"], ["bench2_fixture"])
        self.assertTrue(execution["hermes"]["isolated_home_per_run"])
        self.assertTrue(execution["hermes"]["isolated_workdir_per_run"])
        self.assertEqual(execution["context"]["required_num_ctx"], 32768)
        self.assertTrue(execution["context"]["runtime_observation_required"])
        self.assertEqual(
            execution["context"]["mismatch_classification"],
            "invalid_infrastructure",
        )

    def test_execution_marker_is_deliberately_disabled(self):
        marker = json.loads(validator.MARKER_PATH.read_text(encoding="utf-8"))
        self.assertFalse(marker["enabled"])
        self.assertEqual(marker["plan_sha256"], validator.EXPECTED_PLAN_SHA256)
        validator.validate_plan()

    def test_plan_tampering_is_rejected_before_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            plan = json.loads(validator.PLAN_PATH.read_text(encoding="utf-8"))
            plan["admission_policy"]["bench1_direct_outcomes_are_admission_gate"] = True
            path.write_text(
                json.dumps(plan, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(validator.HermesPlanError, "digest mismatch"):
                validator.validate_plan(plan_path=path)

    def test_fixture_plugin_is_read_only_and_emits_deterministic_trace(self):
        plugin_path = (
            ROOT
            / "fixtures"
            / "bench-2"
            / "hermes-plugin"
            / "bench2-fixture"
            / "__init__.py"
        )
        validator._validate_plugin_source(plugin_path)
        spec = importlib.util.spec_from_file_location("bench2_fixture_test", plugin_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        context = _FakePluginContext()
        module.register(context)
        self.assertEqual(set(context.tools), {"bench_lookup", "bench_distractor"})

        with tempfile.TemporaryDirectory() as directory:
            trace_path = Path(directory) / "trace.jsonl"
            with mock.patch.dict(
                os.environ,
                {"BENCH2_TOOL_TRACE_PATH": str(trace_path)},
                clear=False,
            ):
                lookup = context.tools["bench_lookup"]["handler"]
                result = json.loads(lookup({"key": "alpha-7"}))
            self.assertEqual(
                result,
                {"key": "alpha-7", "ok": True, "value": "BRAVO-19"},
            )
            records = [
                json.loads(line)
                for line in trace_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["tool_name"], "bench_lookup")
            self.assertEqual(records[0]["arguments"], {"key": "alpha-7"})

    def test_branch_validation_cannot_execute_hermes_or_models(self):
        workflow = (
            ROOT / ".github" / "workflows" / "bench2-hermes-plan-validation.yml"
        ).read_text(encoding="utf-8")
        lowered = workflow.lower()
        self.assertIn("runs-on: ubuntu-latest", workflow)
        self.assertNotIn("self-hosted", lowered)
        self.assertNotIn("workflow_dispatch", lowered)
        self.assertNotIn("ollama", lowered)
        self.assertNotIn("hermes -z", lowered)
        self.assertNotIn("bench2-hermes-orchestrator-oneshot.json", workflow)
        self.assertIn("validate_bench2_hermes_plan.py", workflow)


if __name__ == "__main__":
    unittest.main()

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
    def test_plan_contains_exactly_the_h4_qualified_candidates(self):
        plan, candidates, cases = validator.validate_plan()
        self.assertEqual(plan["counts"]["total_runs"], 48)
        self.assertEqual(len(candidates), 8)
        self.assertEqual(len({item["candidate_id"] for item in candidates}), 8)
        self.assertEqual([item["sequence"] for item in candidates], list(range(8)))
        self.assertEqual([case["capability"] for case in cases], ["HO-TOOLS", "HO-STOP"])

    def test_all_ten_were_attempted_but_only_infrastructure_eligible_enter(self):
        plan, candidates, _ = validator.validate_plan()
        candidate_ids = {item["candidate_id"] for item in candidates}
        self.assertTrue(plan["admission_policy"]["all_h3_lane1_candidates_h4_attempted"])
        self.assertFalse(plan["admission_policy"]["bench1_direct_outcomes_are_admission_gate"])
        self.assertTrue(validator.EXPECTED_ELIGIBLE_NON_PASS_SET <= candidate_ids)
        self.assertEqual(
            {item["candidate_id"]: item["h4_status"] for item in plan["excluded_after_h4"]},
            validator.EXPECTED_EXCLUDED,
        )
        self.assertFalse(candidate_ids & set(validator.EXPECTED_EXCLUDED))

    def test_batches_cover_all_eight_candidates_once(self):
        _, candidates, _ = validator.validate_plan()
        seen: list[str] = []
        for batch_index in range(validator.BATCH_COUNT):
            selected, selection = validator.select_candidates(candidates, batch_index)
            self.assertEqual(len(selected), 2)
            self.assertEqual(selection["expected_runs"], 12)
            self.assertEqual(selection["total_candidates"], 8)
            seen.extend(item["candidate_id"] for item in selected)
        self.assertEqual(seen, [item["candidate_id"] for item in candidates])
        with self.assertRaisesRegex(validator.HermesPlanError, "outside"):
            validator.select_candidates(candidates, validator.BATCH_COUNT)

    def test_h4_closeout_and_hermes_runtime_are_pinned(self):
        plan, _, _ = validator.validate_plan()
        self.assertEqual(plan["execution"]["context"]["required_num_ctx"], 65536)
        self.assertEqual(plan["execution"]["fallback_chain"], [])
        self.assertEqual(
            plan["execution"]["hermes"]["commit_sha"],
            validator.EXPECTED_HERMES_COMMIT,
        )
        self.assertEqual(
            plan["source"]["h4_summary_sha256"],
            validator.EXPECTED_H4_SUMMARY_SHA256,
        )
        self.assertEqual(
            plan["source"]["h4_workflow_run_id"],
            validator.EXPECTED_H4_RUN_ID,
        )

    def test_execution_marker_is_deliberately_disabled(self):
        marker = json.loads(validator.MARKER_PATH.read_text(encoding="utf-8"))
        self.assertFalse(marker["enabled"])
        self.assertEqual(marker["batch_count"], 4)
        self.assertEqual(marker["plan_sha256"], validator.EXPECTED_PLAN_SHA256)
        validator.validate_plan()

    def test_plan_tampering_is_rejected_before_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            plan = json.loads(validator.PLAN_PATH.read_text(encoding="utf-8"))
            plan["admission_policy"]["bench1_direct_outcomes_are_admission_gate"] = True
            path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(validator.HermesPlanError, "digest mismatch"):
                validator.validate_plan(plan_path=path)

    def test_fixture_plugin_is_read_only_and_emits_deterministic_trace(self):
        plugin_path = ROOT / "fixtures/bench-2/hermes-plugin/bench2-fixture/__init__.py"
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
            with mock.patch.dict(os.environ, {"BENCH2_TOOL_TRACE_PATH": str(trace_path)}, clear=False):
                result = json.loads(context.tools["bench_lookup"]["handler"]({"key": "alpha-7"}))
            self.assertEqual(result, {"key": "alpha-7", "ok": True, "value": "BRAVO-19"})
            records = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["tool_name"], "bench_lookup")

    def test_branch_validation_cannot_execute_hermes_or_models(self):
        workflow = (ROOT / ".github/workflows/bench2-hermes-plan-validation.yml").read_text(encoding="utf-8")
        lowered = workflow.lower()
        self.assertIn("runs-on: ubuntu-latest", workflow)
        self.assertNotIn("self-hosted", lowered)
        self.assertNotIn("workflow_dispatch", lowered)
        self.assertNotIn("ollama", lowered)
        self.assertNotIn("hermes -z", lowered)
        self.assertIn("validate_bench2_hermes_plan.py", workflow)


if __name__ == "__main__":
    unittest.main()

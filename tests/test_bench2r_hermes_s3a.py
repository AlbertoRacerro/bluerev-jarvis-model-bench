from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import validate_bench2r_hermes_s3a as validator


class HermesS3ADesignTests(unittest.TestCase):
    def _temporary_json(self, value: dict) -> tuple[tempfile.TemporaryDirectory, Path]:
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "value.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return directory, path

    def test_reviewed_historical_design_validates_with_live_workflow_masked(self):
        sentinel = validator.ROOT / ".bench2r-s3a-test-no-runtime-workflow"
        with mock.patch.object(validator, "RUNTIME_WORKFLOW_PATH", sentinel):
            payload = validator.validate()
        self.assertEqual(payload["status"], "ready_design_execution_disabled")
        self.assertEqual(payload["candidate_id"], "gemma4-12b-it-qat")
        self.assertEqual(payload["total_runs"], 50)
        self.assertEqual(payload["nominal_runs"], 30)
        self.assertEqual(payload["negative_control_runs"], 20)
        self.assertFalse(payload["marker_enabled"])
        self.assertFalse(payload["runtime_implemented"])
        self.assertFalse(payload["production_promoted"])
        self.assertFalse(payload["latency_threshold_defined"])
        self.assertFalse(payload["multi_tool_in_scope"])

    def test_enabled_marker_is_rejected(self):
        marker = validator._load(validator.MARKER_PATH)
        marker["enabled"] = True
        directory, path = self._temporary_json(marker)
        self.addCleanup(directory.cleanup)
        with mock.patch.object(validator, "MARKER_PATH", path):
            with self.assertRaisesRegex(validator.HermesS3AValidationError, "marker drifted"):
                validator._validate_marker()

    def test_production_promoted_stack_is_rejected(self):
        stack = validator._load(validator.STACK_PATH)
        stack["promotion"]["production_promoted"] = True
        directory, path = self._temporary_json(stack)
        self.addCleanup(directory.cleanup)
        plan = validator._load(validator.PLAN_PATH)
        with mock.patch.object(validator, "STACK_PATH", path):
            with self.assertRaisesRegex(validator.HermesS3AValidationError, "production promotion"):
                validator._validate_stack(plan)

    def test_run_count_drift_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["counts"]["total_runs"] = 49
        with self.assertRaisesRegex(validator.HermesS3AValidationError, "run counts drifted"):
            validator._validate_plan(plan)

    def test_held_out_tool_value_in_model_payload_is_rejected(self):
        case = validator._load(validator.CASE_PATHS[0])
        case["prompt"] += " Return KAPPA-73 without consulting the tool."
        directory, path = self._temporary_json(case)
        self.addCleanup(directory.cleanup)
        with self.assertRaisesRegex(validator.HermesS3AValidationError, "held-out result leaked"):
            validator._validate_case(path, validator.EXPECTED_CASES[0])

    def test_historical_design_rejects_unmasked_runtime_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bench2r-hermes-s3a-oneshot.yml"
            path.write_text("name: forbidden runtime\n", encoding="utf-8")
            with mock.patch.object(validator, "RUNTIME_WORKFLOW_PATH", path):
                with self.assertRaisesRegex(validator.HermesS3AValidationError, "runtime workflow exists"):
                    validator._validate_no_contamination()

    def test_multi_tool_expansion_is_not_silently_admitted(self):
        plan = copy.deepcopy(validator._load(validator.PLAN_PATH))
        plan["scope_exclusions"]["multi_tool_chains"] = "included"
        self.assertFalse(plan["execution"]["implemented"])
        reviewed = validator._load(validator.PLAN_PATH)
        self.assertIn("finalizer v2", reviewed["scope_exclusions"]["multi_tool_chains"])


if __name__ == "__main__":
    unittest.main()

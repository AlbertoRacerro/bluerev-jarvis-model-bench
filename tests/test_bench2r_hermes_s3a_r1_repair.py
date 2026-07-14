from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import validate_bench2r_hermes_s3a_r1_repair as validator


class HermesS3ARepairDesignTests(unittest.TestCase):
    def _temporary_text(self, text: str, name: str = "value.txt") -> tuple[tempfile.TemporaryDirectory, Path]:
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / name
        path.write_text(text, encoding="utf-8")
        return directory, path

    def _temporary_json(self, value: dict) -> tuple[tempfile.TemporaryDirectory, Path]:
        return self._temporary_text(json.dumps(value, indent=2) + "\n", "value.json")

    @staticmethod
    def _blob_sha(path: Path) -> str:
        data = path.read_bytes()
        return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()

    def test_repair_design_validates_with_execution_absent(self):
        payload = validator.validate()
        self.assertEqual(payload["status"], "design_valid_execution_absent")
        self.assertEqual(payload["candidate_id"], "gemma4-12b-it-qat")
        self.assertEqual(payload["arms"], 2)
        self.assertEqual(payload["derived_seeds"], [371872, 665465, 623659])
        self.assertEqual(payload["planned_runs"], 27)
        self.assertFalse(payload["execution_implemented"])
        self.assertFalse(payload["automatic_skill_replacement_allowed"])
        self.assertFalse(payload["automatic_production_promotion_allowed"])

    def test_seed_derivation_is_bound_to_closeout_merge_sha(self):
        self.assertEqual(
            validator._derived_seeds(validator.EXPECTED_CLOSEOUT_MERGE_SHA),
            validator.EXPECTED_SEEDS,
        )
        self.assertFalse(
            set(validator.EXPECTED_SEEDS) & {17, 42, 271828, 314159, 8675309}
        )

    def test_closeout_cannot_be_reclassified_as_pass(self):
        closeout = validator._load(validator.CLOSEOUT_PATH)
        closeout["status"] = "shadow_soak_passed_requires_human_review"
        closeout["passed"] = True
        directory, path = self._temporary_json(closeout)
        self.addCleanup(directory.cleanup)
        with mock.patch.object(validator, "CLOSEOUT_PATH", path), mock.patch.object(
            validator, "EXPECTED_CLOSEOUT_BLOB_SHA", self._blob_sha(path)
        ):
            with self.assertRaisesRegex(
                validator.HermesS3ARepairDesignError,
                "not an immutable failure",
            ):
                validator.validate()

    def test_enabled_s3a_marker_is_rejected(self):
        marker = validator._load(validator.MARKER_PATH)
        marker["enabled"] = True
        directory, path = self._temporary_json(marker)
        self.addCleanup(directory.cleanup)
        with mock.patch.object(validator, "MARKER_PATH", path):
            with self.assertRaisesRegex(
                validator.HermesS3ARepairDesignError,
                "marker is not closed exactly",
            ):
                validator.validate()

    def test_repair_count_drift_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["counts"]["total_runs"] = 26
        directory, path = self._temporary_json(plan)
        self.addCleanup(directory.cleanup)
        with mock.patch.object(validator, "PLAN_PATH", path):
            with self.assertRaisesRegex(
                validator.HermesS3ARepairDesignError,
                "run counts drifted",
            ):
                validator.validate()

    def test_case_prompt_changes_cannot_be_allowed(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["scope_exclusions"]["case_prompt_changes"] = "allowed"
        directory, path = self._temporary_json(plan)
        self.addCleanup(directory.cleanup)
        with mock.patch.object(validator, "PLAN_PATH", path):
            with self.assertRaisesRegex(
                validator.HermesS3ARepairDesignError,
                "scope exclusions drifted",
            ):
                validator.validate()

    def test_repair_skill_must_require_real_tool_response(self):
        source = validator.REPAIR_SKILL_PATH.read_text(encoding="utf-8")
        source = source.replace(
            "Do not emit a final answer until the required tool response count has been observed.",
            "A final answer may be emitted immediately.",
        )
        directory, path = self._temporary_text(source, "SKILL.md")
        self.addCleanup(directory.cleanup)
        with mock.patch.object(validator, "REPAIR_SKILL_PATH", path), mock.patch.object(
            validator, "EXPECTED_REPAIR_SKILL_SHA", self._blob_sha(path)
        ):
            with self.assertRaisesRegex(
                validator.HermesS3ARepairDesignError,
                "repair skill rules are missing",
            ):
                validator.validate()

    def test_repair_skill_cannot_contain_benchmark_literals(self):
        source = validator.REPAIR_SKILL_PATH.read_text(encoding="utf-8") + "\nmissing-404\n"
        directory, path = self._temporary_text(source, "SKILL.md")
        self.addCleanup(directory.cleanup)
        with mock.patch.object(validator, "REPAIR_SKILL_PATH", path), mock.patch.object(
            validator, "EXPECTED_REPAIR_SKILL_SHA", self._blob_sha(path)
        ):
            with self.assertRaisesRegex(
                validator.HermesS3ARepairDesignError,
                "benchmark-specific literals",
            ):
                validator.validate()

    def test_control_skill_mutation_is_rejected(self):
        source = validator.CONTROL_SKILL_PATH.read_text(encoding="utf-8") + "\nmutation\n"
        directory, path = self._temporary_text(source, "SKILL.md")
        self.addCleanup(directory.cleanup)
        with mock.patch.object(validator, "CONTROL_SKILL_PATH", path):
            with self.assertRaisesRegex(
                validator.HermesS3ARepairDesignError,
                "control skill v1.1 drifted",
            ):
                validator.validate()

    def test_design_slice_rejects_execution_workflow(self):
        directory, path = self._temporary_text("name: forbidden\n", "workflow.yml")
        self.addCleanup(directory.cleanup)
        with mock.patch.object(validator, "WORKFLOW_PATH", path):
            with self.assertRaisesRegex(
                validator.HermesS3ARepairDesignError,
                "contains an execution runner or workflow",
            ):
                validator.validate()


if __name__ == "__main__":
    unittest.main()

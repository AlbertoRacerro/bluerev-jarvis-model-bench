from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import bench2r_hermes_runtime as optimization
from scripts import run_bench2r_hermes_s3a_r1_repair as repair
from scripts import validate_bench2r_hermes_s3a_r1_repair_runtime as validator


class HermesS3ARepairRuntimeTests(unittest.TestCase):
    def _marker_load_patch(self, marker: dict):
        original = validator._load

        def load(path: Path):
            if path == validator.MARKER_PATH:
                return marker
            return original(path)

        return mock.patch.object(validator, "_load", side_effect=load)

    def test_reviewed_workflow_validates_while_marker_remains_disabled(self):
        plan, marker, candidate = validator.validate_execution(require_enabled=False)
        self.assertFalse(marker["enabled"])
        self.assertEqual(candidate["candidate_id"], "gemma4-12b-it-qat")
        self.assertEqual(len(plan["arms"]), 2)
        self.assertEqual(len(plan["batches"]), 3)
        self.assertEqual(plan["counts"]["total_runs"], 27)
        self.assertTrue(validator.WORKFLOW_PATH.is_file())
        self.assertFalse(plan["decision"]["automatic_skill_replacement_allowed"])
        self.assertFalse(plan["decision"]["automatic_production_promotion_allowed"])

    def test_enabled_marker_validates_only_with_reviewed_workflow(self):
        marker = validator._load(validator.MARKER_PATH)
        marker["enabled"] = True
        with self._marker_load_patch(marker):
            plan, observed, candidate = validator.validate_execution(
                require_enabled=True
            )
        self.assertTrue(observed["enabled"])
        self.assertEqual(candidate["candidate_id"], "gemma4-12b-it-qat")
        self.assertEqual(plan["counts"]["total_runs"], 27)

    def test_marker_seed_drift_is_rejected(self):
        marker = validator._load(validator.MARKER_PATH)
        marker["seeds"] = [1, 2, 3]
        with self._marker_load_patch(marker):
            with self.assertRaisesRegex(
                validator.HermesS3ARepairRuntimeError,
                "repair marker drifted",
            ):
                validator.validate_execution(require_enabled=False)

    def test_selected_skill_installer_uses_requested_source_and_restores(self):
        observed: list[Path] = []
        original = optimization.install_bounded_skill

        def fake_install(hermes_home: Path, *, source_path: Path) -> Path:
            observed.append(source_path)
            return hermes_home / "skills" / "bounded-tool-orchestration" / "SKILL.md"

        selected = Path("candidate/SKILL.md")
        with mock.patch.object(optimization, "install_bounded_skill", fake_install):
            patched_original = optimization.install_bounded_skill
            with repair._selected_skill(selected):
                target = optimization.install_bounded_skill(Path("home"))
                self.assertEqual(
                    target,
                    Path("home/skills/bounded-tool-orchestration/SKILL.md"),
                )
                self.assertEqual(observed, [selected])
            self.assertIs(optimization.install_bounded_skill, patched_original)
        self.assertIs(optimization.install_bounded_skill, original)

    def test_selected_skill_restores_after_exception(self):
        original = optimization.install_bounded_skill
        selected = Path("candidate/SKILL.md")
        with self.assertRaisesRegex(RuntimeError, "boom"):
            with repair._selected_skill(selected):
                self.assertIsNot(optimization.install_bounded_skill, original)
                raise RuntimeError("boom")
        self.assertIs(optimization.install_bounded_skill, original)

    def test_batch_index_accepts_only_reviewed_matrix(self):
        for raw, expected in (("0", 0), ("1", 1), ("2", 2)):
            with self.subTest(raw=raw), mock.patch.dict(
                os.environ,
                {repair.BATCH_INDEX_ENV: raw},
                clear=False,
            ):
                self.assertEqual(repair._batch_index(), expected)
        for raw in ("-1", "3", "x"):
            with self.subTest(raw=raw), mock.patch.dict(
                os.environ,
                {repair.BATCH_INDEX_ENV: raw},
                clear=False,
            ):
                with self.assertRaises(repair.HermesS3ARepairError):
                    repair._batch_index()
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                repair.HermesS3ARepairError,
                "is missing",
            ):
                repair._batch_index()

    def test_run_summary_separates_negative_and_sentinel_gates(self):
        negative_pass = {
            "arm_id": "repair_v1_2",
            "run_kind": "paired_negative",
            "case_id": "s3a-tools-injected-timeout-005",
            "infrastructure_valid": True,
            "shadow_pass": True,
            "tool_sequence_exact": True,
            "negative_output_ledger_only": True,
            "negative_fail_closed_pass": True,
        }
        negative_fail = {
            **negative_pass,
            "case_id": "s3a-tools-negative-result-004",
            "shadow_pass": False,
            "negative_output_ledger_only": False,
        }
        sentinel = {
            "arm_id": "repair_v1_2",
            "run_kind": "repair_nominal_sentinel",
            "case_id": "s3a-tools-vault-untrusted-payload-001",
            "infrastructure_valid": True,
            "shadow_pass": True,
            "tool_sequence_exact": True,
            "negative_output_ledger_only": None,
            "negative_fail_closed_pass": False,
        }
        summary = repair._run_summary(
            [negative_pass, negative_fail, sentinel],
            "repair_v1_2",
        )
        self.assertEqual(summary["runs"], 3)
        self.assertEqual(summary["infrastructure_valid"], 3)
        self.assertEqual(summary["shadow_pass"], 2)
        self.assertEqual(summary["negative_runs"], 2)
        self.assertEqual(summary["negative_shadow_pass"], 1)
        self.assertEqual(summary["negative_tool_sequence_exact"], 2)
        self.assertEqual(summary["negative_ledger_only_exact"], 1)
        self.assertEqual(summary["negative_fail_closed_pass"], 2)
        self.assertEqual(summary["timeout_runs"], 1)
        self.assertEqual(summary["timeout_tool_invocation"], 1)
        self.assertEqual(summary["sentinel_runs"], 1)
        self.assertEqual(summary["sentinel_shadow_pass"], 1)

    def test_expected_inventory_contains_exact_nine_run_identities(self):
        report = {
            "runtime_plan": {
                "paired_negative_cases": [
                    "fixtures/bench-2r/s3a-cases/s3a-tools-negative-result-004.json",
                    "fixtures/bench-2r/s3a-cases/s3a-tools-injected-timeout-005.json",
                ]
            },
            "selection": {
                "repair_nominal_sentinel":
                    "fixtures/bench-2r/s3a-cases/s3a-tools-vault-untrusted-payload-001.json"
            },
        }
        inventory = repair._expected_inventory(report)
        self.assertEqual(len(inventory), 9)
        self.assertIn(
            ("control_v1_1", "s3a-tools-negative-result-004", 1),
            inventory,
        )
        self.assertIn(
            ("repair_v1_2", "s3a-tools-injected-timeout-005", 2),
            inventory,
        )
        self.assertIn(
            ("repair_v1_2", "s3a-tools-vault-untrusted-payload-001", 1),
            inventory,
        )

    def test_runner_source_does_not_mutate_case_prompt_or_expose_unsafe_flags(self):
        source = validator.RUNNER_PATH.read_text(encoding="utf-8")
        self.assertNotIn('case["prompt"] =', source)
        self.assertNotIn("case['prompt'] =", source)
        self.assertIn('"automatic_skill_replacement_allowed": False', source)
        self.assertIn('"automatic_production_promotion_allowed": False', source)
        self.assertIn("safe._safe_runtime_boundary()", source)

    def test_invalid_workflow_contract_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "workflow.yml"
            path.write_text("name: forbidden\n", encoding="utf-8")
            with mock.patch.object(validator, "WORKFLOW_PATH", path):
                with self.assertRaisesRegex(
                    validator.HermesS3ARepairRuntimeError,
                    "workflow contract drifted",
                ):
                    validator.validate_execution(require_enabled=False)


if __name__ == "__main__":
    unittest.main()

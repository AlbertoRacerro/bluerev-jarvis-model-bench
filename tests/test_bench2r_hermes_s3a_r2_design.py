from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import validate_bench2r_hermes_s3a_r2_design as validator


class HermesS3AR2DesignTests(unittest.TestCase):
    def _patch_documents(
        self,
        *,
        plan=None,
        audit=None,
        candidate=None,
        workflow=None,
        s3a_marker=None,
        r1_marker=None,
    ):
        original_load = validator._load
        original_read = validator._read

        def load(path: Path):
            if path == validator.PLAN_PATH and plan is not None:
                return copy.deepcopy(plan)
            if path == validator.AUDIT_PATH and audit is not None:
                return copy.deepcopy(audit)
            if path == validator.S3A_MARKER_PATH and s3a_marker is not None:
                return copy.deepcopy(s3a_marker)
            if path == validator.R1_MARKER_PATH and r1_marker is not None:
                return copy.deepcopy(r1_marker)
            return original_load(path)

        def read(path: Path):
            if path == validator.CANDIDATE_SKILL_PATH and candidate is not None:
                return candidate
            if path == validator.DESIGN_WORKFLOW_PATH and workflow is not None:
                return workflow
            return original_read(path)

        return mock.patch.multiple(
            validator,
            _load=mock.Mock(side_effect=load),
            _read=mock.Mock(side_effect=read),
        )

    def test_static_design_validates(self):
        payload = validator.validate()
        self.assertEqual(payload["status"], "valid_static_design")
        self.assertEqual(payload["candidate_negative_runs"], 8)
        self.assertEqual(payload["paired_negative_runs"], 16)
        self.assertEqual(payload["total_canary_runs"], 18)
        self.assertEqual(
            payload["governed_model_digest"],
            validator.EXPECTED_GOVERNED_STACK["model_digest"],
        )
        self.assertFalse(payload["execution_implemented"])
        self.assertEqual(payload["production_status"], "not_promoted")

    def test_markdown_fence_is_rejected(self):
        candidate = validator._read(validator.CANDIDATE_SKILL_PATH) + "\n```json\n{}\n```\n"
        plan = validator._load(validator.PLAN_PATH)
        plan["arms"][1]["skill_git_blob_sha"] = validator._git_blob_sha(candidate)
        with self._patch_documents(plan=plan, candidate=candidate):
            with self.assertRaisesRegex(validator.HermesS3AR2DesignError, "Markdown fence"):
                validator.validate()

    def test_stale_candidate_blob_is_rejected(self):
        candidate = validator._read(validator.CANDIDATE_SKILL_PATH) + "\n"
        with self._patch_documents(candidate=candidate):
            with self.assertRaisesRegex(validator.HermesS3AR2DesignError, "candidate skill blob"):
                validator.validate()

    def test_governed_stack_drift_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["governed_stack"]["model_digest"] = "0" * 64
        with self._patch_documents(plan=plan):
            with self.assertRaisesRegex(validator.HermesS3AR2DesignError, "governed stack"):
                validator.validate()

    def test_prior_seed_reuse_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["seed_policy"]["canary_seeds"] = [371872, 603823]
        with self._patch_documents(plan=plan):
            with self.assertRaisesRegex(validator.HermesS3AR2DesignError, "canary seeds"):
                validator.validate()

    def test_negative_case_inventory_drift_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["cases"]["paired_negative"][0] = plan["cases"]["candidate_nominal_sentinels"][0]
        with self._patch_documents(plan=plan):
            with self.assertRaisesRegex(validator.HermesS3AR2DesignError, "negative case inventory"):
                validator.validate()

    def test_nominal_case_inventory_drift_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["cases"]["candidate_nominal_sentinels"].reverse()
        with self._patch_documents(plan=plan):
            with self.assertRaisesRegex(validator.HermesS3AR2DesignError, "sentinel inventory"):
                validator.validate()

    def test_repetition_drift_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["repetitions"]["paired_negative_per_case_seed_arm"] = 1
        with self._patch_documents(plan=plan):
            with self.assertRaisesRegex(validator.HermesS3AR2DesignError, "repetition policy"):
                validator.validate()

    def test_bad_run_arithmetic_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["counts"]["paired_negative_runs"] = 8
        with self._patch_documents(plan=plan):
            with self.assertRaisesRegex(validator.HermesS3AR2DesignError, "paired count"):
                validator.validate()

    def test_rerunnable_job_is_rejected(self):
        audit = validator._load(validator.AUDIT_PATH)
        audit["decision"]["rerunnable_job_ids"] = [87140999505]
        audit["job_totals"]["rerunnable"] = 1
        with self._patch_documents(audit=audit):
            with self.assertRaisesRegex(validator.HermesS3AR2DesignError, "rerunnable jobs"):
                validator.validate()

    def test_enabled_marker_is_rejected(self):
        marker = validator._load(validator.R1_MARKER_PATH)
        marker["enabled"] = True
        with self._patch_documents(r1_marker=marker):
            with self.assertRaisesRegex(validator.HermesS3AR2DesignError, "R1 marker"):
                validator.validate()

    def test_canary_path_filter_regression_is_rejected(self):
        workflow = validator._read(validator.DESIGN_WORKFLOW_PATH)
        workflow = workflow.replace(
            f"      - {validator.FORBIDDEN_WORKFLOW_LITERAL}\n",
            "",
            1,
        )
        with self._patch_documents(workflow=workflow):
            with self.assertRaisesRegex(validator.HermesS3AR2DesignError, "guard forbidden canary path"):
                validator.validate()

    def test_marker_path_filter_regression_is_rejected(self):
        workflow = validator._read(validator.DESIGN_WORKFLOW_PATH)
        workflow = workflow.replace(
            f"      - {validator.FORBIDDEN_MARKER_LITERAL}\n",
            "",
            1,
        )
        with self._patch_documents(workflow=workflow):
            with self.assertRaisesRegex(validator.HermesS3AR2DesignError, "guard forbidden marker path"):
                validator.validate()

    def test_execution_workflow_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "r2.yml"
            path.write_text("name: forbidden\n", encoding="utf-8")
            with mock.patch.object(validator, "FORBIDDEN_WORKFLOW_PATH", path):
                with self.assertRaisesRegex(validator.HermesS3AR2DesignError, "workflow exists"):
                    validator.validate()

    def test_execution_marker_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "r2-marker.json"
            path.write_text("{}\n", encoding="utf-8")
            with mock.patch.object(validator, "FORBIDDEN_MARKER_PATH", path):
                with self.assertRaisesRegex(validator.HermesS3AR2DesignError, "marker exists"):
                    validator.validate()


if __name__ == "__main__":
    unittest.main()

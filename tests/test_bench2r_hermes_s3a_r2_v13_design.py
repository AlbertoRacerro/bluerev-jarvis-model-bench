from __future__ import annotations

import copy
import unittest
from unittest import mock

from scripts import validate_bench2r_hermes_s3a_r2_v13_design as validator


class HermesS3AR2V13DesignTests(unittest.TestCase):
    def test_design_validates_with_execution_disabled(self):
        payload = validator.validate()
        self.assertEqual(payload["status"], "valid_design_execution_disabled")
        self.assertEqual(payload["candidate_skill_version"], "1.3.0")
        self.assertEqual(payload["canary_seeds"], [849690, 603823])
        self.assertEqual(payload["planned_runs"], 18)
        self.assertTrue(payload["r1_closeout_preserved"])
        self.assertTrue(payload["markers_disabled"])
        self.assertFalse(payload["workflow_present"])
        self.assertEqual(payload["production_status"], "not_promoted")

    def test_seed_reuse_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["seed_policy"]["canary_seeds"] = [371872, 603823]
        original = validator._load

        def load(path):
            if path == validator.PLAN_PATH:
                return copy.deepcopy(plan)
            return original(path)

        with mock.patch.object(validator, "_load", side_effect=load):
            with self.assertRaisesRegex(validator.HermesS3AR2V13DesignError, "canary seed selection"):
                validator.validate()

    def test_markdown_tolerance_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["early_stop"]["candidate_markdown_fence_allowed"] = 1
        original = validator._load

        def load(path):
            if path == validator.PLAN_PATH:
                return copy.deepcopy(plan)
            return original(path)

        with mock.patch.object(validator, "_load", side_effect=load):
            with self.assertRaisesRegex(validator.HermesS3AR2V13DesignError, "Markdown fences"):
                validator.validate()

    def test_execution_authorization_is_rejected(self):
        plan = validator._load(validator.PLAN_PATH)
        plan["execution"]["self_hosted_execution_authorized"] = True
        original = validator._load

        def load(path):
            if path == validator.PLAN_PATH:
                return copy.deepcopy(plan)
            return original(path)

        with mock.patch.object(validator, "_load", side_effect=load):
            with self.assertRaisesRegex(validator.HermesS3AR2V13DesignError, "enables execution"):
                validator.validate()

    def test_r1_reclassification_is_rejected(self):
        closeout = validator._load(validator.R1_CLOSEOUT_PATH)
        closeout["passed"] = True
        original = validator._load

        def load(path):
            if path == validator.R1_CLOSEOUT_PATH:
                return copy.deepcopy(closeout)
            return original(path)

        with mock.patch.object(validator, "_load", side_effect=load):
            with self.assertRaisesRegex(validator.HermesS3AR2V13DesignError, "rewritten as passed"):
                validator.validate()

    def test_fenced_candidate_skill_is_rejected(self):
        original_read_text = validator.Path.read_text

        def read_text(path, *args, **kwargs):
            text = original_read_text(path, *args, **kwargs)
            if path == validator.SKILL_PATH:
                return text + "\n```json\n{}\n```\n"
            return text

        with mock.patch.object(validator.Path, "read_text", new=read_text):
            with self.assertRaisesRegex(validator.HermesS3AR2V13DesignError, "fenced code block"):
                validator.validate()


if __name__ == "__main__":
    unittest.main()

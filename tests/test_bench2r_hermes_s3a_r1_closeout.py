from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import validate_bench2r_hermes_s3a_r1_closeout as validator


class HermesS3AR1CloseoutTests(unittest.TestCase):
    def _patch_documents(self, *, summary=None, marker=None):
        original = validator._load

        def load(path: Path):
            if path == validator.SUMMARY_PATH and summary is not None:
                return copy.deepcopy(summary)
            if path == validator.MARKER_PATH and marker is not None:
                return copy.deepcopy(marker)
            return original(path)

        return mock.patch.object(validator, "_load", side_effect=load)

    def test_failed_closeout_validates(self):
        payload = validator.validate()
        self.assertEqual(payload["status"], "valid_failed_closeout")
        self.assertEqual(payload["executed_runs"], 9)
        self.assertEqual(payload["repair_negative_ledger_only_exact"], 0)
        self.assertFalse(payload["runner_unavailability_failure"])
        self.assertFalse(payload["skill_v1_2_adopted"])
        self.assertEqual(payload["production_status"], "not_promoted")

    def test_retroactive_pass_is_rejected(self):
        summary = validator._load(validator.SUMMARY_PATH)
        summary["passed"] = True
        with self._patch_documents(summary=summary):
            with self.assertRaisesRegex(validator.HermesS3AR1CloseoutError, "failure decision"):
                validator.validate()

    def test_runner_unavailability_rewrite_is_rejected(self):
        summary = validator._load(validator.SUMMARY_PATH)
        summary["acceptance"]["failure_caused_by_runner_unavailability"] = True
        with self._patch_documents(summary=summary):
            with self.assertRaisesRegex(validator.HermesS3AR1CloseoutError, "failure gate"):
                validator.validate()

    def test_negative_ledger_count_rewrite_is_rejected(self):
        summary = validator._load(validator.SUMMARY_PATH)
        summary["aggregate"]["repair_negative_ledger_only_exact"] = 4
        with self._patch_documents(summary=summary):
            with self.assertRaisesRegex(validator.HermesS3AR1CloseoutError, "aggregate drifted"):
                validator.validate()

    def test_failed_skill_adoption_is_rejected(self):
        summary = validator._load(validator.SUMMARY_PATH)
        summary["decision"]["skill_v1_2_adopted"] = True
        with self._patch_documents(summary=summary):
            with self.assertRaisesRegex(validator.HermesS3AR1CloseoutError, "adopts failed skill"):
                validator.validate()

    def test_enabled_marker_is_rejected(self):
        marker = validator._load(validator.MARKER_PATH)
        marker["enabled"] = True
        with self._patch_documents(marker=marker):
            with self.assertRaisesRegex(validator.HermesS3AR1CloseoutError, "marker was not closed"):
                validator.validate()

    def test_obsolete_temporary_workflow_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "obsolete.yml"
            path.write_text("name: obsolete\n", encoding="utf-8")
            with mock.patch.object(validator, "TEMP_WORKFLOWS", (path,)):
                with self.assertRaisesRegex(validator.HermesS3AR1CloseoutError, "obsolete temporary workflow"):
                    validator.validate()


if __name__ == "__main__":
    unittest.main()

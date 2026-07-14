from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import validate_bench2r_hermes_s3a_closeout as validator


class HermesS3ACloseoutTests(unittest.TestCase):
    def _temporary_json(self, value: dict) -> tuple[tempfile.TemporaryDirectory, Path]:
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "value.json"
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return directory, path

    def test_real_failed_closeout_validates(self):
        payload = validator.validate()
        self.assertEqual(payload["status"], "valid_failed_closeout")
        self.assertEqual(payload["runs"], 50)
        self.assertEqual(payload["shadow_pass"], 31)
        self.assertEqual(payload["failed_runs"], 19)
        self.assertEqual(payload["production_status"], "not_promoted")
        self.assertFalse(payload["automatic_production_promotion_allowed"])

    def test_passing_decision_is_rejected(self):
        summary = validator._load(validator.SUMMARY_PATH)
        summary["status"] = "shadow_soak_passed_requires_human_review"
        summary["passed"] = True
        directory, path = self._temporary_json(summary)
        self.addCleanup(directory.cleanup)
        with mock.patch.object(validator, "SUMMARY_PATH", path):
            with self.assertRaisesRegex(
                validator.HermesS3ACloseoutError, "failure decision drifted"
            ):
                validator.validate()

    def test_production_promotion_is_rejected(self):
        summary = validator._load(validator.SUMMARY_PATH)
        summary["production_status"] = "promoted"
        directory, path = self._temporary_json(summary)
        self.addCleanup(directory.cleanup)
        with mock.patch.object(validator, "SUMMARY_PATH", path):
            with self.assertRaisesRegex(
                validator.HermesS3ACloseoutError, "promotes production"
            ):
                validator.validate()

    def test_enabled_marker_is_rejected(self):
        marker = validator._load(validator.MARKER_PATH)
        marker["enabled"] = True
        directory, path = self._temporary_json(marker)
        self.addCleanup(directory.cleanup)
        with mock.patch.object(validator, "MARKER_PATH", path):
            with self.assertRaisesRegex(
                validator.HermesS3ACloseoutError, "marker was not closed"
            ):
                validator.validate()

    def test_run_inventory_drift_is_rejected(self):
        summary = validator._load(validator.SUMMARY_PATH)
        summary["aggregate"]["runs"] = 49
        directory, path = self._temporary_json(summary)
        self.addCleanup(directory.cleanup)
        with mock.patch.object(validator, "SUMMARY_PATH", path):
            with self.assertRaisesRegex(
                validator.HermesS3ACloseoutError, "aggregate drifted: runs"
            ):
                validator.validate()

    def test_negative_acceptance_cannot_be_flipped_to_pass(self):
        summary = validator._load(validator.SUMMARY_PATH)
        summary["acceptance"]["all_negative_controls_fail_closed"] = True
        directory, path = self._temporary_json(summary)
        self.addCleanup(directory.cleanup)
        with mock.patch.object(validator, "SUMMARY_PATH", path):
            with self.assertRaisesRegex(
                validator.HermesS3ACloseoutError,
                "failure/safety gate drifted: all_negative_controls_fail_closed",
            ):
                validator.validate()

    def test_artifact_digest_drift_is_rejected(self):
        summary = validator._load(validator.SUMMARY_PATH)
        summary["artifact_metadata"][0]["main"]["digest"] = "invalid"
        directory, path = self._temporary_json(summary)
        self.addCleanup(directory.cleanup)
        with mock.patch.object(validator, "SUMMARY_PATH", path):
            with self.assertRaisesRegex(
                validator.HermesS3ACloseoutError, "not a SHA-256 digest"
            ):
                validator.validate()


if __name__ == "__main__":
    unittest.main()

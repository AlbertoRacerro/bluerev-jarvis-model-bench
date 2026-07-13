from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import validate_bench2_hermes_canary_closeout as closeout


class Bench2HermesCanaryCloseoutTests(unittest.TestCase):
    def test_closeout_preserves_semantic_failure_and_opens_only_infrastructure_gate(self):
        summary = closeout.validate_closeout()
        decision = summary["decision"]
        self.assertEqual(decision["infrastructure_canary_status"], "passed")
        self.assertEqual(decision["semantic_observation_status"], "failed")
        self.assertTrue(decision["full_matrix_may_proceed"])
        self.assertEqual(decision["full_matrix_semantic_admission_gate"], "not_applicable")
        self.assertFalse(summary["semantic"]["semantic_pass"])
        self.assertEqual(summary["semantic"]["tool_trace_count"], 0)

    def test_closeout_is_bound_to_trusted_run_and_actual_64k_runtime(self):
        summary = closeout.validate_closeout()
        self.assertEqual(summary["run"]["workflow_run_id"], 29265322367)
        self.assertEqual(
            summary["run"]["execution_commit_sha"],
            "941d587267bfeb602ba9bd5d5513695c56d63e52",
        )
        self.assertEqual(summary["infrastructure"]["observed_context_length"], 65536)
        self.assertEqual(summary["infrastructure"]["residency_class"], "full_vram")
        self.assertTrue(summary["infrastructure"]["alias_removed"])
        self.assertTrue(summary["infrastructure"]["model_unloaded"])

    def test_neither_execution_marker_is_enabled_by_closeout(self):
        closeout.validate_closeout()
        full_marker = json.loads(closeout.canary.bench2.MARKER_PATH.read_text(encoding="utf-8"))
        canary_marker = json.loads(closeout.canary.MARKER_PATH.read_text(encoding="utf-8"))
        self.assertFalse(full_marker["enabled"])
        self.assertFalse(canary_marker["enabled"])

    def test_tampered_closeout_is_rejected(self):
        summary = json.loads(closeout.SUMMARY_PATH.read_text(encoding="utf-8"))
        summary["semantic"]["semantic_pass"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summary.json"
            path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            original = closeout.SUMMARY_PATH
            try:
                closeout.SUMMARY_PATH = path
                with self.assertRaisesRegex(closeout.CanaryCloseoutError, "digest mismatch"):
                    closeout.validate_closeout()
            finally:
                closeout.SUMMARY_PATH = original


if __name__ == "__main__":
    unittest.main()

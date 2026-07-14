from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import validate_bench2r_hermes_s2_closeout as closeout


class Bench2RHermesS2CloseoutTests(unittest.TestCase):
    def test_trusted_closeout_selects_only_governed_gemma_stack(self):
        payload = closeout.validate()
        self.assertEqual(payload["status"], "valid")
        self.assertTrue(payload["orchestrator_found"])
        self.assertEqual(payload["selected_candidate_id"], "gemma4-12b-it-qat")
        self.assertTrue(payload["governed_stack_admitted"])
        self.assertFalse(payload["standalone_checkpoint_admitted"])
        self.assertFalse(payload["production_promoted"])
        self.assertEqual(payload["trusted_runs"], 36)
        self.assertEqual(payload["admitted_runs"], 12)

    def test_standalone_checkpoint_admission_is_rejected(self):
        summary = json.loads(closeout.SUMMARY_PATH.read_text(encoding="utf-8"))
        summary["decision"]["standalone_checkpoint_admitted"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summary.json"
            path.write_text(json.dumps(summary), encoding="utf-8")
            with self.assertRaisesRegex(closeout.S2CloseoutError, "decision drifted"):
                closeout.validate(summary_path=path)

    def test_second_admitted_candidate_is_rejected(self):
        summary = json.loads(closeout.SUMMARY_PATH.read_text(encoding="utf-8"))
        summary["candidate_results"][1]["candidate_admitted"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "summary.json"
            path.write_text(json.dumps(summary), encoding="utf-8")
            with self.assertRaisesRegex(closeout.S2CloseoutError, "exactly the reviewed Gemma"):
                closeout.validate(summary_path=path)

    def test_fail_open_finalizer_is_rejected(self):
        registry = json.loads(closeout.REGISTRY_PATH.read_text(encoding="utf-8"))
        registry["required_controls"]["deterministic_finalizer"]["fail_closed"] = False
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            with self.assertRaisesRegex(closeout.S2CloseoutError, "fail-open"):
                closeout.validate(registry_path=path)

    def test_production_promotion_is_rejected(self):
        registry = json.loads(closeout.REGISTRY_PATH.read_text(encoding="utf-8"))
        registry["promotion"]["production_promoted"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            with self.assertRaisesRegex(closeout.S2CloseoutError, "production boundary"):
                closeout.validate(registry_path=path)

    def test_completed_marker_must_be_disabled(self):
        marker = json.loads(closeout.MARKER_PATH.read_text(encoding="utf-8"))
        marker["enabled"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "marker.json"
            path.write_text(json.dumps(marker), encoding="utf-8")
            with self.assertRaisesRegex(closeout.S2CloseoutError, "not disabled"):
                closeout.validate(marker_path=path)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import validate_bench2r_hermes_s3a as design
from scripts import validate_bench2r_hermes_s3a_runtime as runtime
from scripts import validate_bench2r_hermes_s3a_windows as windows


class HermesS3AWindowsBoundaryTests(unittest.TestCase):
    def _enabled_marker(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "marker.json"
        path.write_text(
            json.dumps({**runtime.EXPECTED_MARKER_BASE, "enabled": True}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        return directory, path

    def test_lf_and_crlf_text_have_same_git_blob_sha(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lf = root / "lf.txt"
            crlf = root / "crlf.txt"
            lf.write_bytes(b"alpha\nbeta\ngamma\n")
            crlf.write_bytes(b"alpha\r\nbeta\r\ngamma\r\n")
            self.assertEqual(
                windows.normalized_git_blob_sha(lf),
                windows.normalized_git_blob_sha(crlf),
            )

    def test_windows_boundary_restores_all_runtime_functions(self):
        original_runtime_hash = runtime._git_blob_sha
        original_design_hash = design._git_blob_sha
        original_workflow = runtime._validate_workflow
        original_historical = runtime._historical_design_boundary
        with self.assertRaisesRegex(RuntimeError, "boom"):
            with windows.windows_runtime_boundary():
                self.assertIs(runtime._git_blob_sha, windows.normalized_git_blob_sha)
                self.assertIs(design._git_blob_sha, windows.normalized_git_blob_sha)
                self.assertIs(runtime._validate_workflow, windows._validate_live_workflow)
                self.assertIs(
                    runtime._historical_design_boundary,
                    windows.historical_design_disabled_boundary,
                )
                raise RuntimeError("boom")
        self.assertIs(runtime._git_blob_sha, original_runtime_hash)
        self.assertIs(design._git_blob_sha, original_design_hash)
        self.assertIs(runtime._validate_workflow, original_workflow)
        self.assertIs(runtime._historical_design_boundary, original_historical)

    def test_historical_boundary_masks_marker_and_restores_both_paths(self):
        original_workflow = design.RUNTIME_WORKFLOW_PATH
        original_marker = design.MARKER_PATH
        with self.assertRaisesRegex(RuntimeError, "boom"):
            with windows.historical_design_disabled_boundary():
                self.assertEqual(
                    design.RUNTIME_WORKFLOW_PATH,
                    runtime.HISTORICAL_DESIGN_WORKFLOW_SENTINEL,
                )
                marker = design._load(design.MARKER_PATH)
                self.assertFalse(marker["enabled"])
                self.assertEqual(
                    {key: value for key, value in marker.items() if key != "enabled"},
                    runtime.EXPECTED_MARKER_BASE,
                )
                raise RuntimeError("boom")
        self.assertEqual(design.RUNTIME_WORKFLOW_PATH, original_workflow)
        self.assertEqual(design.MARKER_PATH, original_marker)

    def test_live_disabled_workflow_validates_through_windows_boundary(self):
        plan, marker, candidate, cases = windows.validate_execution(require_enabled=False)
        self.assertFalse(marker["enabled"])
        self.assertEqual(candidate["candidate_id"], "gemma4-12b-it-qat")
        self.assertEqual(plan["counts"]["total_runs"], 50)
        self.assertEqual(len(cases), 5)

    def test_shared_enabled_checkout_validates_historical_then_live_marker(self):
        directory, marker_path = self._enabled_marker()
        self.addCleanup(directory.cleanup)
        with mock.patch.object(runtime, "MARKER_PATH", marker_path):
            with mock.patch.object(design, "MARKER_PATH", marker_path):
                plan, marker, candidate, cases = windows.validate_execution(
                    require_enabled=True
                )
        self.assertTrue(marker["enabled"])
        self.assertEqual(plan["counts"]["total_runs"], 50)
        self.assertEqual(candidate["candidate_id"], "gemma4-12b-it-qat")
        self.assertEqual(len(cases), 5)

    def test_durable_preflight_wrapper_and_cmd_shell_are_authoritative(self):
        workflow = windows.WORKFLOW_PATH.read_text(encoding="utf-8")
        logical = windows.normalized_workflow_text(workflow)
        self.assertIn(windows.EXPECTED_VALIDATOR_COMMAND, logical)
        self.assertEqual(workflow.count("shell: cmd"), 3)
        self.assertNotIn("shell: powershell", logical)
        self.assertNotIn(
            "python -m scripts.validate_bench2r_hermes_s3a_windows",
            logical,
        )
        self.assertEqual(workflow.count("if: always()"), 3)
        windows._validate_preflight_wrapper()

    def test_existing_runtime_regression_suite_passes_inside_windows_boundary(self):
        suite = unittest.defaultTestLoader.loadTestsFromName(
            "tests.test_bench2r_hermes_s3a_runtime"
        )
        result = unittest.TestResult()
        with windows.windows_runtime_boundary():
            suite.run(result)
        details = [
            f"FAIL {test}: {text}" for test, text in result.failures
        ] + [
            f"ERROR {test}: {text}" for test, text in result.errors
        ]
        self.assertTrue(result.wasSuccessful(), "\n".join(details))
        self.assertGreaterEqual(result.testsRun, 10)


if __name__ == "__main__":
    unittest.main()

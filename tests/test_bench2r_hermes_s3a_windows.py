from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts import validate_bench2r_hermes_s3a as design
from scripts import validate_bench2r_hermes_s3a_runtime as runtime
from scripts import validate_bench2r_hermes_s3a_windows as windows


class HermesS3AWindowsBoundaryTests(unittest.TestCase):
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
        with self.assertRaisesRegex(RuntimeError, "boom"):
            with windows.windows_runtime_boundary():
                self.assertIs(runtime._git_blob_sha, windows.normalized_git_blob_sha)
                self.assertIs(design._git_blob_sha, windows.normalized_git_blob_sha)
                self.assertIs(runtime._validate_workflow, windows._validate_live_workflow)
                raise RuntimeError("boom")
        self.assertIs(runtime._git_blob_sha, original_runtime_hash)
        self.assertIs(design._git_blob_sha, original_design_hash)
        self.assertIs(runtime._validate_workflow, original_workflow)

    def test_live_disabled_workflow_validates_through_windows_boundary(self):
        plan, marker, candidate, cases = windows.validate_execution(require_enabled=False)
        self.assertFalse(marker["enabled"])
        self.assertEqual(candidate["candidate_id"], "gemma4-12b-it-qat")
        self.assertEqual(plan["counts"]["total_runs"], 50)
        self.assertEqual(len(cases), 5)

    def test_legacy_non_normalized_validator_command_is_absent(self):
        workflow = windows.WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn(windows.EXPECTED_VALIDATOR_COMMAND, workflow)
        self.assertNotIn(
            "python -m scripts.validate_bench2r_hermes_s3a_runtime --require-enabled",
            workflow,
        )

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

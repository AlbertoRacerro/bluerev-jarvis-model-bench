from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import run_bench2r_hermes_s3a_preflight as preflight


class HermesS3APreflightTests(unittest.TestCase):
    def test_success_preserves_validator_json_and_log(self):
        def fake_run(argv, **kwargs):
            output = Path(argv[argv.index("--output") + 1])
            output.write_text(
                json.dumps({
                    "schema_version": "bench.hermes-s3a-windows-validation.v1",
                    "status": "execution_ready",
                    "execution_authorized": True,
                })
                + "\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(argv, 0, stdout="validated\n", stderr="")

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            with mock.patch.object(preflight.subprocess, "run", side_effect=fake_run):
                code = preflight.run_preflight(output_dir)
            self.assertEqual(code, 0)
            payload = json.loads((output_dir / preflight.JSON_NAME).read_text(encoding="utf-8"))
            self.assertTrue(payload["execution_authorized"])
            log = (output_dir / preflight.LOG_NAME).read_text(encoding="utf-8")
            self.assertIn("returncode=0", log)
            self.assertIn("validated", log)

    def test_launch_exception_always_writes_fallback_json_and_log(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            with mock.patch.object(
                preflight.subprocess,
                "run",
                side_effect=OSError("cannot launch validator"),
            ):
                code = preflight.run_preflight(output_dir)
            self.assertEqual(code, 2)
            payload = json.loads((output_dir / preflight.JSON_NAME).read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "invalid")
            self.assertFalse(payload["execution_authorized"])
            self.assertEqual(payload["error_type"], "OSError")
            log = (output_dir / preflight.LOG_NAME).read_text(encoding="utf-8")
            self.assertIn("cannot launch validator", log)

    def test_nonzero_validator_without_json_gets_attributable_fallback(self):
        completed = subprocess.CompletedProcess(
            ["python", "validator"],
            7,
            stdout="partial output\n",
            stderr="validator failed\n",
        )
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            with mock.patch.object(preflight.subprocess, "run", return_value=completed):
                code = preflight.run_preflight(output_dir, command=["python", "validator"])
            self.assertEqual(code, 7)
            payload = json.loads((output_dir / preflight.JSON_NAME).read_text(encoding="utf-8"))
            self.assertEqual(payload["error_type"], "ValidatorProcessFailure")
            self.assertEqual(payload["validator_returncode"], 7)
            log = (output_dir / preflight.LOG_NAME).read_text(encoding="utf-8")
            self.assertIn("partial output", log)
            self.assertIn("validator failed", log)


if __name__ == "__main__":
    unittest.main()

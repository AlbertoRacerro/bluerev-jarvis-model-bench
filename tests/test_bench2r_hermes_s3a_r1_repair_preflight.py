from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import run_bench2r_hermes_s3a_r1_repair_preflight as preflight


class HermesS3ARepairPreflightTests(unittest.TestCase):
    def test_success_preserves_validator_json_and_log(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            json_path = output / preflight.JSON_NAME
            payload = {
                "schema_version": "bench.hermes-s3a-r1-repair-runtime-validation.v1",
                "status": "execution_ready",
                "execution_authorized": True,
            }
            script = (
                "from pathlib import Path; import json; "
                f"Path({str(json_path)!r}).write_text(json.dumps({payload!r}), encoding='utf-8')"
            )
            code = preflight.run_preflight(
                output,
                command=[sys.executable, "-c", script],
            )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(json_path.read_text(encoding="utf-8")), payload)
            log = (output / preflight.LOG_NAME).read_text(encoding="utf-8")
            self.assertIn("returncode=0", log)
            self.assertIn("--- stdout ---", log)
            self.assertIn("--- stderr ---", log)

    def test_nonzero_child_without_json_creates_fail_closed_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            code = preflight.run_preflight(
                output,
                command=[
                    sys.executable,
                    "-c",
                    "import sys; print('validator failed'); sys.exit(7)",
                ],
            )
            self.assertEqual(code, 7)
            payload = json.loads(
                (output / preflight.JSON_NAME).read_text(encoding="utf-8")
            )
            self.assertEqual(payload["status"], "invalid")
            self.assertFalse(payload["execution_authorized"])
            self.assertEqual(payload["validator_returncode"], 7)
            self.assertEqual(payload["error_type"], "ValidatorProcessFailure")
            log = (output / preflight.LOG_NAME).read_text(encoding="utf-8")
            self.assertIn("returncode=7", log)
            self.assertIn("validator failed", log)

    def test_process_launch_exception_creates_fail_closed_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with mock.patch.object(
                subprocess,
                "run",
                side_effect=OSError("launch blocked"),
            ):
                code = preflight.run_preflight(
                    output,
                    command=["missing-validator"],
                )
            self.assertEqual(code, 2)
            payload = json.loads(
                (output / preflight.JSON_NAME).read_text(encoding="utf-8")
            )
            self.assertEqual(payload["status"], "invalid")
            self.assertFalse(payload["execution_authorized"])
            self.assertEqual(payload["error_type"], "OSError")
            self.assertIn("launch blocked", payload["error"])
            log = (output / preflight.LOG_NAME).read_text(encoding="utf-8")
            self.assertIn("OSError: launch blocked", log)

    def test_existing_child_json_is_not_overwritten_on_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            json_path = output / preflight.JSON_NAME
            child_payload = {
                "schema_version": "bench.hermes-s3a-r1-repair-runtime-validation.v1",
                "status": "invalid",
                "execution_authorized": False,
                "error_type": "HermesS3ARepairRuntimeError",
                "error": "marker must be enabled",
            }
            script = (
                "from pathlib import Path; import json, sys; "
                f"Path({str(json_path)!r}).write_text(json.dumps({child_payload!r}), encoding='utf-8'); "
                "sys.exit(2)"
            )
            code = preflight.run_preflight(
                output,
                command=[sys.executable, "-c", script],
            )
            self.assertEqual(code, 2)
            self.assertEqual(
                json.loads(json_path.read_text(encoding="utf-8")),
                child_payload,
            )


if __name__ == "__main__":
    unittest.main()

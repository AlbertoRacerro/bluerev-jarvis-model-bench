from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_direct_smoke_v3_job


class DirectSmokeV3JobGateTests(unittest.TestCase):
    def write_summary(self, root: Path, case_digest: object) -> Path:
        path = root / "job-summary.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "bench.direct-smoke-job.v3",
                    "tests": {"exit_code": 0},
                    "inventory": {"exit_code": 0},
                    "execution": {
                        "infrastructure_exit_code": 0,
                        "execution_completed": True,
                        "candidate_passed": True,
                        "candidate_result_status": "passed",
                        "case_definition_sha256": case_digest,
                    },
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_candidate_and_case_are_fixed(self):
        self.assertEqual(run_direct_smoke_v3_job.CANDIDATE_ID, "qwythos-hermes-safe")
        self.assertEqual(
            run_direct_smoke_v3_job.CASE_PATH.name,
            "ho-stop-reuse-explicit-002.json",
        )

    def test_valid_case_digest_keeps_gate_green(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_summary(Path(directory), "a" * 64)
            with patch.object(run_direct_smoke_v3_job, "SUMMARY_PATH", path):
                self.assertEqual(run_direct_smoke_v3_job.enforce(), 0)

    def test_missing_case_digest_fails_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_summary(Path(directory), None)
            with patch.object(run_direct_smoke_v3_job, "SUMMARY_PATH", path):
                self.assertEqual(run_direct_smoke_v3_job.enforce(), 1)

    def test_non_hex_case_digest_fails_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_summary(Path(directory), "g" * 64)
            with patch.object(run_direct_smoke_v3_job, "SUMMARY_PATH", path):
                self.assertEqual(run_direct_smoke_v3_job.enforce(), 1)


if __name__ == "__main__":
    unittest.main()

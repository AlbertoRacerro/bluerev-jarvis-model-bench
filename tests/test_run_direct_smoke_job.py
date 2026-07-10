from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_direct_smoke_job


class DirectSmokeJobGateTests(unittest.TestCase):
    def write_summary(
        self,
        root: Path,
        *,
        test_exit=0,
        inventory_exit=0,
        execution_exit=0,
        completed=True,
        candidate_passed=False,
    ):
        path = root / "job-summary.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "bench.direct-smoke-job.v1",
                    "tests": {"exit_code": test_exit},
                    "inventory": {"exit_code": inventory_exit},
                    "execution": {
                        "infrastructure_exit_code": execution_exit,
                        "execution_completed": completed,
                        "candidate_passed": candidate_passed,
                    },
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_second_smoke_candidate_is_fixed(self):
        self.assertEqual(run_direct_smoke_job.CANDIDATE_ID, "qwythos-hermes-safe")

    def test_candidate_failure_does_not_fail_infrastructure_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_summary(Path(directory), candidate_passed=False)
            with patch.object(run_direct_smoke_job, "SUMMARY_PATH", path):
                self.assertEqual(run_direct_smoke_job.enforce(), 0)

    def test_infrastructure_failure_fails_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_summary(Path(directory), execution_exit=2, completed=False)
            with patch.object(run_direct_smoke_job, "SUMMARY_PATH", path):
                self.assertEqual(run_direct_smoke_job.enforce(), 1)

    def test_missing_summary_is_gate_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.json"
            with patch.object(run_direct_smoke_job, "SUMMARY_PATH", path):
                self.assertEqual(run_direct_smoke_job.enforce(), 2)


if __name__ == "__main__":
    unittest.main()

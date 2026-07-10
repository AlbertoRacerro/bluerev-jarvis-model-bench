from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_direct_smoke_v2_job


class DirectSmokeV2JobGateTests(unittest.TestCase):
    def write_summary(self, root: Path, result_status: str) -> Path:
        path = root / "job-summary.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "bench.direct-smoke-job.v2",
                    "tests": {"exit_code": 0},
                    "inventory": {"exit_code": 0},
                    "execution": {
                        "infrastructure_exit_code": 0,
                        "execution_completed": True,
                        "candidate_passed": None,
                        "candidate_result_status": result_status,
                    },
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_candidate_is_fixed_to_qwythos_safe(self):
        self.assertEqual(
            run_direct_smoke_v2_job.CANDIDATE_ID,
            "qwythos-hermes-safe",
        )

    def test_invalid_truncation_outcome_keeps_infrastructure_gate_green(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_summary(Path(directory), "invalid")
            with patch.object(run_direct_smoke_v2_job, "SUMMARY_PATH", path):
                self.assertEqual(run_direct_smoke_v2_job.enforce(), 0)

    def test_unknown_result_status_fails_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_summary(Path(directory), "maybe")
            with patch.object(run_direct_smoke_v2_job, "SUMMARY_PATH", path):
                self.assertEqual(run_direct_smoke_v2_job.enforce(), 1)


if __name__ == "__main__":
    unittest.main()

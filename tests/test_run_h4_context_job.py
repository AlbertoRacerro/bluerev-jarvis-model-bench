from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import run_h4_context_job as job


class H4ContextJobTests(unittest.TestCase):
    def test_selection_is_five_batches_of_two(self):
        observed = []
        for index in range(job.BATCH_COUNT):
            selection = job.selection_for(index)
            self.assertEqual(selection["batch_size"], 2)
            self.assertEqual(selection["expected_count"], 2)
            observed.extend(range(selection["start"], selection["end"]))
        self.assertEqual(observed, list(range(10)))

    def test_batch_index_must_be_explicit_and_bounded(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "missing or invalid"):
                job.batch_index_from_environment()
        with mock.patch.dict(os.environ, {"BENCH_H4_BATCH_INDEX": "5"}, clear=True):
            with self.assertRaisesRegex(ValueError, "outside"):
                job.batch_index_from_environment()
        with mock.patch.dict(os.environ, {"BENCH_H4_BATCH_INDEX": "4"}, clear=True):
            self.assertEqual(job.batch_index_from_environment(), 4)

    def test_all_source_files_are_immutably_bound(self):
        self.assertTrue(job._source_files_are_bound())
        self.assertEqual(job.PROFILE["num_ctx"], 65536)

    def test_enforce_accepts_nonqualification_as_valid_candidate_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            probe_dir = root / "h4-hermes-minimum-64k"
            models = probe_dir / "models"
            models.mkdir(parents=True)
            selection = job.selection_for(0)
            expected = job._expected_batch_candidates(0)
            results = []
            for index, candidate in enumerate(expected):
                slug = f"model-{index}"
                result = {
                    "schema_version": "bench.h4-context-result.v1",
                    "artifact_slug": slug,
                    "model": candidate,
                    "profile": job.PROFILE,
                    "status": "cpu_offload" if index == 0 else "qualified_64k",
                    "cleanup_after": {"verified_absent": True, "models": []},
                }
                path = models / slug / "result.json"
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps(result) + "\n", encoding="utf-8")
                results.append(result)
            report = {
                "schema_version": "bench.h4-context-report.v1",
                "source": {
                    "plan_sha256": job.EXPECTED_PLAN_SHA256,
                    "h3_summary_sha256": job.EXPECTED_SUMMARY_SHA256,
                    "h3_summary_manifest_sha256": job.EXPECTED_SUMMARY_MANIFEST_SHA256,
                },
                "profile": job.PROFILE,
                "selection": selection,
                "infrastructure_error": None,
                "results": results,
                "final_cleanup": [],
                "status_counts": {
                    "qualified_64k": 1,
                    "cpu_offload": 1,
                    "context_mismatch": 0,
                    "load_failed": 0,
                },
            }
            report_path = probe_dir / "report.json"
            report_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
            artifacts = {}
            for path in [report_path, *sorted(models.glob("*/result.json"))]:
                relative = path.relative_to(probe_dir).as_posix()
                artifacts[relative] = {
                    "sha256": job._sha256(path),
                    "size_bytes": path.stat().st_size,
                }
            (probe_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": "bench.h4-context-manifest.v1",
                        "artifacts": artifacts,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "job-summary.json").write_text(
                json.dumps(
                    {
                        "schema_version": "bench.h4-context-job.v1",
                        "test_scope": "h4-hermes-minimum-64k-batch",
                        "selection": selection,
                        "tests": {"exit_code": 0},
                        "probe": {"exit_code": 0},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertEqual(job.enforce(root), 0)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import probe_direct_semantic_campaign as probe
from scripts import run_direct_semantic_campaign_bound_job as bound
from scripts import run_direct_semantic_campaign_job as job
from scripts import run_direct_semantic_capture_entry as entry

ROOT = Path(__file__).resolve().parents[1]


class DirectSemanticCampaignTests(unittest.TestCase):
    def test_bound_plan_resolves_exact_h3_candidates_and_cases(self):
        plan, candidates, cases = probe.validate_plan(
            job.PLAN_PATH,
            job.REGISTRY_PATH,
            job.H3_SUMMARY_PATH,
            job.H3_MANIFEST_PATH,
            probe.EXPECTED_PLAN_SHA256,
        )
        self.assertEqual(plan["counts"]["total_runs"], 60)
        self.assertEqual(len(candidates), 10)
        self.assertEqual(len(cases), 2)
        self.assertEqual(candidates[0]["candidate_id"], "gemma4-12b-it-qat")
        self.assertEqual(candidates[-1]["candidate_id"], "qwythos-hermes-safe")
        self.assertEqual(
            [case["capability"] for case in cases],
            ["HO-STOP", "HO-ROUTE"],
        )

    def test_every_batch_contains_two_candidates_and_twelve_runs(self):
        _, candidates, _ = probe.validate_plan(
            job.PLAN_PATH,
            job.REGISTRY_PATH,
            job.H3_SUMMARY_PATH,
            job.H3_MANIFEST_PATH,
            probe.EXPECTED_PLAN_SHA256,
        )
        seen: list[str] = []
        for batch_index in range(5):
            selected, selection = probe.select_candidates(candidates, batch_index)
            self.assertEqual(len(selected), 2)
            self.assertEqual(selection["expected_runs"], 12)
            seen.extend(item["candidate_id"] for item in selected)
        self.assertEqual(seen, [item["candidate_id"] for item in candidates])
        with self.assertRaisesRegex(probe.SemanticCampaignError, "outside"):
            probe.select_candidates(candidates, 5)

    def test_source_hashing_accepts_crlf_without_weakening_definition_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = root / "summary.json"
            manifest = root / "manifest.json"
            for source, target in (
                (job.H3_SUMMARY_PATH, summary),
                (job.H3_MANIFEST_PATH, manifest),
            ):
                text = source.read_text(encoding="utf-8").replace("\n", "\r\n")
                target.write_text(text, encoding="utf-8", newline="")
            _, candidates, _ = probe.validate_plan(
                job.PLAN_PATH,
                job.REGISTRY_PATH,
                summary,
                manifest,
                probe.EXPECTED_PLAN_SHA256,
            )
            self.assertEqual(len(candidates), 10)

    def test_tampered_plan_is_rejected_before_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            plan_path = Path(directory) / "plan.json"
            value = json.loads(job.PLAN_PATH.read_text(encoding="utf-8"))
            value["repetitions"] = 2
            plan_path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(probe.SemanticCampaignError, "digest mismatch"):
                probe.validate_plan(
                    plan_path,
                    job.REGISTRY_PATH,
                    job.H3_SUMMARY_PATH,
                    job.H3_MANIFEST_PATH,
                    probe.EXPECTED_PLAN_SHA256,
                )

    def test_marker_and_batch_index_are_closed_allowlists(self):
        self.assertTrue(job.marker_enabled())
        for index in range(5):
            with mock.patch.dict(
                os.environ,
                {"BENCH_SEMANTIC_BATCH_INDEX": str(index)},
                clear=False,
            ):
                self.assertEqual(job.batch_index_from_environment(), index)
                self.assertEqual(job.selection_for(index)["expected_runs"], 12)
        with mock.patch.dict(
            os.environ,
            {"BENCH_SEMANTIC_BATCH_INDEX": "5"},
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "outside"):
                job.batch_index_from_environment()

    def test_workflow_is_trusted_main_serial_and_fail_closed(self):
        workflow = (
            ROOT / ".github" / "workflows" / "local-direct-semantic-campaign.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("branches: [main]", workflow)
        self.assertIn('config/bench1-direct-semantic-oneshot.json', workflow)
        self.assertIn("if: github.ref == 'refs/heads/main'", workflow)
        self.assertIn("fail-fast: true", workflow)
        self.assertIn("max-parallel: 1", workflow)
        self.assertIn("runs-on: [self-hosted, Windows, X64, bluerev-bench]", workflow)
        self.assertIn("python scripts/run_direct_semantic_capture_entry.py", workflow)
        self.assertNotIn("Start-Process", workflow)
        self.assertNotIn("Tee-Object", workflow)
        self.assertNotIn("pull_request:", workflow)

    def test_capture_errors_always_materialize_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.dict(
                os.environ,
                {"BENCH_SEMANTIC_BATCH_INDEX": "0"},
                clear=False,
            ):
                self.assertEqual(
                    bound._record_capture_error(root, RuntimeError("diagnostic")),
                    0,
                )
            error = json.loads((root / "capture-error.json").read_text())
            summary = json.loads((root / "job-summary.json").read_text())
            self.assertEqual(error["type"], "RuntimeError")
            self.assertEqual(error["detail"], "diagnostic")
            self.assertEqual(summary["selection"], job.selection_for(0))
            self.assertEqual(summary["probe"]["exit_code"], 2)
            self.assertEqual(summary["capture_error"], error)

    def test_entrypoint_materializes_pre_import_failure(self):
        def fail_before_capture(_artifact_dir: Path) -> int:
            raise RuntimeError("entry-diagnostic")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(entry, "ARTIFACT_DIR", root):
                self.assertEqual(entry.run_capture(fail_before_capture), 0)
            error = json.loads((root / "capture-entry-error.json").read_text())
            summary = json.loads((root / "job-summary.json").read_text())
            trace = (root / "capture-entry-traceback.txt").read_text()
            self.assertEqual(error["type"], "RuntimeError")
            self.assertEqual(error["detail"], "entry-diagnostic")
            self.assertEqual(summary["capture_error"], error)
            self.assertIn("entry-diagnostic", trace)

    def test_report_binding_separates_canonical_and_snapshot_digests(self):
        case = bound._validated_cases()[0]
        raw_snapshot = "1" * 64
        report = {
            "results": [
                {
                    "case_id": case["case_id"],
                    "case_definition_sha256": raw_snapshot,
                }
            ]
        }
        bound._bind_report_case_digests(report)
        result = report["results"][0]
        self.assertEqual(
            result["case_definition_sha256"],
            case["case_definition_sha256"],
        )
        self.assertEqual(result["case_snapshot_sha256"], raw_snapshot)

    def test_result_case_binding_checks_exact_snapshot_artifact(self):
        case = bound._validated_cases()[0]
        with tempfile.TemporaryDirectory() as directory:
            campaign_dir = Path(directory)
            run_dir = campaign_dir / "runs" / "run-1"
            run_dir.mkdir(parents=True)
            snapshot = run_dir / "case_definition.json"
            snapshot.write_bytes(b"snapshot\r\n")
            report = {
                "results": [
                    {
                        "case_id": case["case_id"],
                        "run_directory": "runs/run-1",
                        "case_definition_sha256": case["case_definition_sha256"],
                        "case_snapshot_sha256": probe._raw_sha256(snapshot),
                    }
                ]
            }
            self.assertTrue(
                bound._result_case_bindings_are_valid(report, campaign_dir)
            )
            report["results"][0]["case_snapshot_sha256"] = "0" * 64
            self.assertFalse(
                bound._result_case_bindings_are_valid(report, campaign_dir)
            )

    def test_finalize_manifest_records_real_repetition_and_status(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            artifact = run_dir / "raw_output.txt"
            artifact.write_text("FINAL: {}", encoding="utf-8")
            manifest = {
                "schema_version": "bench.run.v1",
                "run_id": "test-run",
                "created_at_utc": "2026-07-12T20:00:00Z",
                "lane": "direct",
                "candidate": "candidate",
                "case_id": "case",
                "repetition": 1,
                "status": "preliminary",
                "environment": {"runner": "test"},
                "artifacts": {
                    "raw_output.txt": {
                        "path": "raw_output.txt",
                        "sha256": probe._raw_sha256(artifact),
                    }
                },
            }
            probe._write_json(run_dir / "manifest.json", manifest)
            probe._write_json(
                run_dir / "execution_summary.json",
                {"manifest_sha256": "0" * 64},
            )
            campaign = {
                "schema_version": "bench.direct-semantic-run-binding.v1",
                "plan_sha256": probe.EXPECTED_PLAN_SHA256,
                "batch_index": 0,
                "candidate_sequence": 0,
                "case_id": "case",
                "capability": "HO-STOP",
                "repetition": 3,
                "result_status": "failed",
            }
            digest = probe._finalize_run_manifest(run_dir, 3, campaign)
            updated = json.loads((run_dir / "manifest.json").read_text())
            summary = json.loads((run_dir / "execution_summary.json").read_text())
            self.assertEqual(updated["repetition"], 3)
            self.assertEqual(updated["status"], "validated")
            self.assertEqual(updated["environment"]["campaign"], campaign)
            self.assertEqual(summary["manifest_sha256"], digest)


if __name__ == "__main__":
    unittest.main()

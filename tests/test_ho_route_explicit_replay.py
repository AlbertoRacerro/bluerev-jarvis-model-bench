from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import probe_ho_route_explicit_replay as probe
from scripts import run_direct_semantic_campaign_bound_job as base_bound
from scripts import run_direct_semantic_campaign_job as base_job
from scripts import run_ho_route_explicit_replay_bound_job as bound_job
from scripts import run_ho_route_explicit_replay_capture_entry as capture_entry
from scripts import run_ho_route_explicit_replay_enforce_entry as enforce_entry
from scripts import run_ho_route_explicit_replay_job as job

ROOT = Path(__file__).resolve().parents[1]


class HoRouteExplicitReplayTests(unittest.TestCase):
    def test_plan_binds_one_explicit_route_case_and_thirty_runs(self):
        plan, candidates, cases = probe.validate_plan(
            job.PLAN_PATH,
            job.REGISTRY_PATH,
            job.H3_SUMMARY_PATH,
            job.H3_MANIFEST_PATH,
            probe.EXPECTED_PLAN_SHA256,
        )
        self.assertEqual(plan["scope"], "BENCH-1 HO-ROUTE explicit replay")
        self.assertEqual(plan["counts"]["total_runs"], 30)
        self.assertEqual(len(candidates), 10)
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["case_id"], "ho-route-local-coder-explicit-002")
        self.assertEqual(cases[0]["capability"], "HO-ROUTE")
        self.assertEqual(
            cases[0]["case_definition_sha256"],
            "122050ceb6d5b198a079142e131829f0cafe5520eff38bcef4bffb80c5dfd706",
        )

    def test_batches_are_serial_two_candidate_six_run_slices(self):
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
            self.assertEqual(selection, job.selection_for(batch_index))
            self.assertEqual(selection["expected_runs"], 6)
            seen.extend(item["candidate_id"] for item in selected)
        self.assertEqual(seen, [item["candidate_id"] for item in candidates])

    def test_plan_tampering_is_rejected_before_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            plan = json.loads(job.PLAN_PATH.read_text(encoding="utf-8"))
            plan["counts"]["total_runs"] = 60
            path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaisesRegex(probe.SemanticCampaignError, "digest mismatch"):
                probe.validate_plan(
                    path,
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
        with mock.patch.dict(
            os.environ,
            {"BENCH_SEMANTIC_BATCH_INDEX": "5"},
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "outside"):
                job.batch_index_from_environment()

    def test_prerequisite_scope_excludes_invalidated_campaign_test(self):
        self.assertNotIn("test_direct_semantic_campaign.py", job.TEST_PATTERNS)
        self.assertIn("test_ho_route_explicit_replay.py", job.TEST_PATTERNS)
        self.assertIn("test_direct_execution*.py", job.TEST_PATTERNS)

    def test_entry_modules_import_without_pythonpath(self):
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        modules = (
            "scripts.run_ho_route_explicit_replay_capture_entry",
            "scripts.run_ho_route_explicit_replay_enforce_entry",
        )
        for module in modules:
            completed = subprocess.run(
                [sys.executable, "-c", f"import {module}"],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(
                completed.returncode,
                0,
                msg=f"{module} import failed: {completed.stderr}",
            )

    def test_bound_enforce_patches_validator_in_actual_base_module(self):
        original = base_job._validate_campaign_manifest
        artifact_dir = Path("unused-artifact-dir")

        def verify_wiring(received: Path) -> int:
            self.assertEqual(received, artifact_dir)
            self.assertIs(
                base_job._validate_campaign_manifest,
                base_bound._campaign_manifest_without_nested_manifests,
            )
            return 0

        try:
            with mock.patch.object(base_bound, "enforce", side_effect=verify_wiring):
                self.assertEqual(bound_job.enforce(artifact_dir), 0)
        finally:
            base_job._validate_campaign_manifest = original

    def test_workflow_is_trusted_main_serial_and_replay_only(self):
        workflow = (
            ROOT / ".github" / "workflows" / "local-ho-route-explicit-replay.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("branches: [main]", workflow)
        self.assertIn("config/ho-route-explicit-replay-oneshot.json", workflow)
        self.assertIn("fail-fast: true", workflow)
        self.assertIn("max-parallel: 1", workflow)
        self.assertIn("runs-on: [self-hosted, Windows, X64, bluerev-bench]", workflow)
        self.assertIn("run_ho_route_explicit_replay_capture_entry.py", workflow)
        self.assertIn("run_ho_route_explicit_replay_enforce_entry.py", workflow)
        self.assertNotIn("pull_request:", workflow)
        self.assertNotIn("direct-semantic-plan-v1.json", workflow)

    def test_capture_entry_materializes_pre_import_failure(self):
        def fail(_artifact_dir: Path) -> int:
            raise RuntimeError("route capture diagnostic")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.object(capture_entry, "ARTIFACT_DIR", root):
                self.assertEqual(capture_entry.run_capture(fail), 0)
            summary = json.loads((root / "job-summary.json").read_text())
            self.assertEqual(summary["campaign_scope"], "HO-ROUTE-explicit-replay")
            self.assertEqual(summary["capture_error"]["detail"], "route capture diagnostic")

    def test_enforce_entry_preserves_nonzero_gate_output(self):
        def fail_gate(_artifact_dir: Path) -> int:
            print("route replay gate failed")
            return 1

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(enforce_entry.run_enforce(fail_gate, root), 1)
            summary = json.loads((root / "enforce-summary.json").read_text())
            self.assertEqual(summary["exit_code"], 1)
            self.assertIn(
                "route replay gate failed",
                (root / "enforce-stdout.log").read_text(),
            )


if __name__ == "__main__":
    unittest.main()

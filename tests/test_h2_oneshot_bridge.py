from __future__ import annotations

import json
import tempfile
from unittest import mock
import unittest
from pathlib import Path

from scripts.run_direct_smoke_v3_job import EXPECTED_PLAN_SHA256, h2_oneshot_enabled
from scripts import run_h2_context_bound_job as bound


class H2OneShotBridgeTests(unittest.TestCase):
    def test_accepts_only_exact_one_shot_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "marker.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "bench.h2-primary-oneshot.v1",
                        "enabled": True,
                        "plan_sha256": EXPECTED_PLAN_SHA256,
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.dict("os.environ", {"GITHUB_RUN_ID": "29106127334"}):
                self.assertTrue(h2_oneshot_enabled(path))

    def test_rejects_extra_fields_and_wrong_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "marker.json"
            value = {
                "schema_version": "bench.h2-primary-oneshot.v1",
                "enabled": True,
                "plan_sha256": "0" * 64,
                "extra": True,
            }
            path.write_text(json.dumps(value), encoding="utf-8")
            with mock.patch.dict("os.environ", {"GITHUB_RUN_ID": "29106127334"}):
                self.assertFalse(h2_oneshot_enabled(path))

    def test_missing_marker_preserves_direct_smoke_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict("os.environ", {"GITHUB_RUN_ID": "29106127334"}):
                self.assertFalse(h2_oneshot_enabled(Path(tmp) / "missing.json"))

    def test_rejects_any_other_workflow_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "marker.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": "bench.h2-primary-oneshot.v1",
                        "enabled": True,
                        "plan_sha256": EXPECTED_PLAN_SHA256,
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.dict("os.environ", {"GITHUB_RUN_ID": "other"}):
                self.assertFalse(h2_oneshot_enabled(path))


class H2CheckoutBindingTests(unittest.TestCase):
    def test_repository_snapshot_binds_clean_checked_out_head(self) -> None:
        responses = [
            {"ok": True, "stdout": "a" * 40, "returncode": 0},
            {"ok": True, "stdout": "", "returncode": 0},
            {"ok": True, "stdout": "", "returncode": 0},
        ]
        with mock.patch.object(bound.probe.base, "_run", side_effect=responses):
            with mock.patch.dict(
                bound.probe.os.environ,
                {"GITHUB_SHA": "event-sha", "GITHUB_REF": "refs/heads/main"},
                clear=False,
            ):
                value = bound.repository_snapshot()
        self.assertEqual(value["checked_out_sha"], "a" * 40)
        self.assertTrue(value["tracked_clean"])
        self.assertEqual(value["event_sha"], "event-sha")

    def test_repository_snapshot_rejects_dirty_checkout(self) -> None:
        responses = [
            {"ok": True, "stdout": "b" * 40, "returncode": 0},
            {"ok": False, "stdout": "", "returncode": 1},
            {"ok": True, "stdout": "", "returncode": 0},
        ]
        with mock.patch.object(bound.probe.base, "_run", side_effect=responses):
            with self.assertRaisesRegex(RuntimeError, "invalid or dirty"):
                bound.repository_snapshot()


if __name__ == "__main__":
    unittest.main()

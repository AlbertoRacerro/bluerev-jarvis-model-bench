from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_direct_smoke_v3_job import EXPECTED_PLAN_SHA256, h2_oneshot_enabled


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
            self.assertFalse(h2_oneshot_enabled(path))

    def test_missing_marker_preserves_direct_smoke_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(h2_oneshot_enabled(Path(tmp) / "missing.json"))


if __name__ == "__main__":
    unittest.main()

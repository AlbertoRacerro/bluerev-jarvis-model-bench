from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import validate_bench2r_hermes_s2 as base
from scripts import validate_bench2r_hermes_s2_safe as safe


class Bench2RS2EnabledValidatorTests(unittest.TestCase):
    def test_authorized_marker_is_validated_once_with_true_state(self):
        marker = json.loads(base.MARKER_PATH.read_text(encoding="utf-8"))
        marker["enabled"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "marker.json"
            path.write_text(
                json.dumps(marker, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with mock.patch.object(base, "MARKER_PATH", path):
                payload = safe.validate(require_enabled=True)
        self.assertEqual(payload["status"], "ready")
        self.assertTrue(payload["execution_authorized"])

    def test_disabled_review_path_remains_valid(self):
        payload = safe.validate(require_enabled=False)
        self.assertFalse(payload["execution_authorized"])


if __name__ == "__main__":
    unittest.main()

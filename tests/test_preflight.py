from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from scripts import preflight


def local_only_environment(**overrides: str):
    """Blank provider keys without deleting Windows runtime variables."""

    values = {name: "" for name in preflight.KNOWN_EXTERNAL_KEYS}
    values.update(overrides)
    return patch.dict(os.environ, values, clear=False)


class BuildReportTests(unittest.TestCase):
    def test_ready_local_runtime(self) -> None:
        with (
            local_only_environment(),
            patch.object(preflight, "inspect_ollama", return_value={"ok": True, "models": [{"name": "local"}]}),
            patch.object(preflight, "inspect_hermes", return_value={"ok": True}),
        ):
            report = preflight.build_report()

        self.assertEqual(report["status"], "ready")
        self.assertTrue(report["local_only"])
        self.assertEqual(report["blocking_reasons"], [])

    def test_external_key_name_blocks_local_only_without_exposing_value(self) -> None:
        with (
            local_only_environment(OPENAI_API_KEY="not-a-real-key"),
            patch.object(preflight, "inspect_ollama", return_value={"ok": True, "models": [{"name": "local"}]}),
            patch.object(preflight, "inspect_hermes", return_value={"ok": True}),
        ):
            report = preflight.build_report()

        self.assertEqual(report["status"], "ready")
        self.assertFalse(report["local_only"])
        self.assertEqual(report["external_api_env_names_present"], ["OPENAI_API_KEY"])
        self.assertIn("external_api_environment_present", report["blocking_reasons"])
        self.assertNotIn("not-a-real-key", str(report))

    def test_missing_hermes_blocks_preflight(self) -> None:
        with (
            local_only_environment(),
            patch.object(preflight, "inspect_ollama", return_value={"ok": True, "models": [{"name": "local"}]}),
            patch.object(preflight, "inspect_hermes", return_value={"ok": False}),
        ):
            report = preflight.build_report()

        self.assertEqual(report["status"], "blocked")
        self.assertIn("hermes_unavailable", report["blocking_reasons"])


if __name__ == "__main__":
    unittest.main()

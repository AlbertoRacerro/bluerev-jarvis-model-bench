from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from scripts.benchmark_runtime import (
    _is_external_environment_name,
    isolated_process_environment,
    safe_reset_directory,
    sanitize_environment,
)


class BenchmarkRuntimeTests(unittest.TestCase):
    def test_unknown_provider_style_names_are_sensitive(self) -> None:
        self.assertTrue(_is_external_environment_name("NEW_VENDOR_API_KEY"))
        self.assertTrue(_is_external_environment_name("NEW_VENDOR_ACCESS_TOKEN"))
        self.assertTrue(_is_external_environment_name("NEW_VENDOR_BASE_URL"))
        self.assertFalse(_is_external_environment_name("GITHUB_RUN_ID"))

    def test_sanitizer_preserves_safe_runtime_identity(self) -> None:
        source = {
            "PATH": "safe",
            "GITHUB_RUN_ID": "123",
            "NEW_VENDOR_API_KEY": "redacted-test-value",
            "HTTPS_PROXY": "http://proxy.invalid",
        }
        cleaned, removed = sanitize_environment(source, hermes_home=Path("home"))
        self.assertEqual(removed, ["NEW_VENDOR_API_KEY"])
        self.assertEqual(cleaned["GITHUB_RUN_ID"], "123")
        self.assertNotIn("NEW_VENDOR_API_KEY", cleaned)
        self.assertNotIn("HTTPS_PROXY", cleaned)
        self.assertEqual(cleaned["PYTHONUTF8"], "1")
        self.assertEqual(cleaned["NO_PROXY"], "*")

    def test_process_environment_is_restored(self) -> None:
        original = dict(os.environ)
        with isolated_process_environment({"BENCH_TEST_ONLY": "1"}):
            self.assertEqual(dict(os.environ), {"BENCH_TEST_ONLY": "1"})
        self.assertEqual(dict(os.environ), original)

    def test_safe_reset_is_limited_to_child_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "lane"
            target.mkdir()
            (target / "stale.txt").write_text("stale", encoding="utf-8")
            safe_reset_directory(target, allowed_root=root)
            self.assertEqual(list(target.iterdir()), [])
            with self.assertRaisesRegex(ValueError, "outside allowed root"):
                safe_reset_directory(root, allowed_root=root)


if __name__ == "__main__":
    unittest.main()

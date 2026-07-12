from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.benchmark_runtime import (
    _is_external_environment_name,
    isolated_process_environment,
    run_captured,
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

    def test_timeout_preserves_exit_124_and_tree_termination_evidence(self) -> None:
        child_code = "import time; time.sleep(60)"
        parent_code = (
            "import subprocess,sys; "
            "p=subprocess.Popen([sys.executable,'-c',sys.argv[1]]); "
            "print(p.pid, flush=True)"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = root / "artifacts"
            result = run_captured(
                "tree-timeout",
                [sys.executable, "-c", parent_code, child_code],
                cwd=root,
                environment=os.environ,
                artifact_dir=artifacts,
                timeout_seconds=1,
            )
            termination = json.loads(
                (artifacts / "tree-timeout.termination.json").read_text(
                    encoding="utf-8"
                )
            )
            recorded_exit = (artifacts / "tree-timeout.exit").read_text(
                encoding="utf-8"
            )
        self.assertEqual(result["exit_code"], 124)
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["error_type"], "TimeoutExpired")
        self.assertTrue(result["tree_kill_succeeded"])
        self.assertTrue(termination["success"])
        self.assertEqual(recorded_exit, "124\n")

    def test_run_request_is_validated_before_process_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "artifact name"):
                run_captured(
                    "../escape",
                    [sys.executable, "-c", "print('no')"],
                    cwd=root,
                    environment=os.environ,
                    artifact_dir=root / "artifacts",
                    timeout_seconds=1,
                )
            with self.assertRaisesRegex(ValueError, "timeout_seconds"):
                run_captured(
                    "invalid-timeout",
                    [sys.executable, "-c", "print('no')"],
                    cwd=root,
                    environment=os.environ,
                    artifact_dir=root / "artifacts",
                    timeout_seconds=0,
                )


if __name__ == "__main__":
    unittest.main()

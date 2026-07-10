from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DirectInvocationTests(unittest.TestCase):
    def test_direct_script_invocation_bootstraps_repository_imports(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/run_preflight_job.py", "enforce"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        self.assertNotIn("ModuleNotFoundError", result.stderr)
        self.assertIn(result.returncode, (0, 1, 2))


if __name__ == "__main__":
    unittest.main()

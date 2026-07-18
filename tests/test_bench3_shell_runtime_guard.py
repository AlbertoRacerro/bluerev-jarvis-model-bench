from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import validate_bench3_shell_runtime_guard as guard


class Bench3ShellRuntimeGuardTests(unittest.TestCase):
    def test_clean_repository_passes(self):
        result = guard.validate()
        self.assertTrue(result["shell_runtime_guard_validated"])
        self.assertEqual(result["shell_runtime_artifacts"], 0)

    def test_renamed_and_opaque_shell_runners_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            samples = {
                "scripts/bench-3-memory-runner.sh": "echo runtime\n",
                "scripts/bench_3_routing_worker.sh": "echo runtime\n",
                "scripts/opaque.sh": "SCHEMA=bench.hermes-memory-routing-design.v1\n",
            }
            for relative, text in samples.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            with mock.patch.object(guard, "ROOT", root), mock.patch.object(
                guard,
                "CANONICAL_SHELL_RUNNER",
                root / "scripts/run_bench3_hermes_memory_routing.sh",
            ):
                found = guard.unexpected_shell_artifacts()
            self.assertEqual(found, sorted(samples))


if __name__ == "__main__":
    unittest.main()

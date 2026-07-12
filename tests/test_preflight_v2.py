from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import preflight_v2
from scripts.benchmark_runtime import REMOVED_ENV_REPORT


def ready_ollama() -> dict[str, object]:
    return {
        "ok": True,
        "version": {"ok": True},
        "models": [
            {
                "name": "candidate:latest",
                "digest": "a" * 64,
                "size": 1,
            }
        ],
    }


@contextmanager
def workflow_environment(extra: dict[str, str] | None = None):
    values = {
        "RUNNER_NAME": "runner",
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_SHA": "cafebabe",
        "GITHUB_REF": "refs/heads/main",
        REMOVED_ENV_REPORT: "[]",
    }
    values.update(extra or {})
    with patch.object(preflight_v2.os, "environ", values):
        yield


class LaneAwarePreflightTests(unittest.TestCase):
    def test_direct_gate_does_not_inspect_or_require_hermes(self) -> None:
        with (
            workflow_environment(),
            patch.object(
                preflight_v2.base,
                "inspect_ollama",
                return_value=ready_ollama(),
            ),
            patch.object(
                preflight_v2.base,
                "inspect_hermes",
                side_effect=AssertionError("Hermes must not be inspected"),
            ),
        ):
            report = preflight_v2.build_report("direct")
        self.assertEqual(report["selected_gate"], "direct")
        self.assertTrue(report["runner_ready"])
        self.assertTrue(report["scoring_ready"])
        self.assertFalse(report["hermes"]["evaluated"])
        self.assertTrue(report["lanes"]["direct"]["scoring_ready"])

    def test_direct_gate_rejects_malformed_ollama_inventory(self) -> None:
        malformed = ready_ollama()
        malformed["models"] = ["not-an-object"]
        with (
            workflow_environment(),
            patch.object(
                preflight_v2.base,
                "inspect_ollama",
                return_value=malformed,
            ),
        ):
            report = preflight_v2.build_report("direct")
        self.assertFalse(report["scoring_ready"])
        self.assertIn(
            "ollama_model_identity_incomplete",
            report["scoring_blocking_reasons"],
        )

    def test_direct_gate_rejects_external_environment(self) -> None:
        with (
            workflow_environment({"OPENAI_API_KEY": "not-a-real-key"}),
            patch.object(
                preflight_v2.base,
                "inspect_ollama",
                return_value=ready_ollama(),
            ),
        ):
            report = preflight_v2.build_report("direct")
        self.assertFalse(report["local_only"])
        self.assertFalse(report["scoring_ready"])
        self.assertNotIn("not-a-real-key", json.dumps(report))

    def test_hermes_gate_preserves_existing_semantics(self) -> None:
        base_report = {
            "schema_version": "bench.preflight.v1",
            "runner_ready": False,
            "scoring_ready": False,
            "local_only": True,
            "blocking_reasons": ["hermes_installation_or_windows_shell_unready"],
            "scoring_blocking_reasons": [
                "hermes_installation_or_windows_shell_unready"
            ],
            "environment_sanitization": {
                "removed_external_env_names": [],
            },
            "environment": {"runner_name": "runner"},
            "workflow": {
                "run_id": "1",
                "run_attempt": "1",
                "event_name": "push",
                "sha": "abc",
                "ref": "refs/heads/main",
            },
            "ollama": ready_ollama(),
            "hermes": {"ok": False},
        }
        with patch.object(
            preflight_v2.base,
            "build_report",
            return_value=base_report,
        ):
            report = preflight_v2.build_report("hermes")
        self.assertEqual(report["selected_gate"], "hermes")
        self.assertFalse(report["scoring_ready"])
        self.assertFalse(report["lanes"]["hermes"]["scoring_ready"])
        self.assertTrue(report["lanes"]["direct"]["scoring_ready"])

    def test_main_returns_direct_gate_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "preflight.json"
            with (
                workflow_environment(),
                patch.object(
                    preflight_v2.base,
                    "inspect_ollama",
                    return_value=ready_ollama(),
                ),
                patch.object(
                    sys,
                    "argv",
                    [
                        "preflight_v2.py",
                        "--output",
                        str(output),
                        "--required-gate",
                        "direct",
                    ],
                ),
            ):
                self.assertEqual(preflight_v2.main(), 0)
            report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["selected_gate"], "direct")


if __name__ == "__main__":
    unittest.main()

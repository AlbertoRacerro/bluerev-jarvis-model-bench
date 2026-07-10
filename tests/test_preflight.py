from __future__ import annotations

from contextlib import contextmanager
import unittest
from unittest.mock import patch

from scripts import preflight


def ready_ollama() -> dict[str, object]:
    return {
        "ok": True,
        "version": {"ok": True},
        "models": [{"name": "local", "digest": "abc123"}],
    }


def ready_hermes(*, dirty: bool | None = False) -> dict[str, object]:
    return {"ok": True, "commit": "deadbeef", "dirty": dirty}


@contextmanager
def isolated_environment(values: dict[str, str] | None = None):
    """Replace host-dependent environment and platform probes with test doubles."""

    fake_environment = {
        "RUNNER_NAME": "test-runner",
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_SHA": "cafebabe",
        "GITHUB_REF": "refs/heads/main",
    }
    fake_environment.update(values or {})
    with (
        patch.object(preflight.os, "environ", fake_environment),
        patch.object(preflight.os, "cpu_count", return_value=24),
        patch.object(preflight.platform, "platform", return_value="Windows-test"),
        patch.object(preflight.platform, "machine", return_value="AMD64"),
        patch.object(preflight.platform, "processor", return_value="test-processor"),
    ):
        yield


class OllamaEndpointTests(unittest.TestCase):
    def test_rejects_non_loopback_endpoint_before_network_access(self) -> None:
        with (
            isolated_environment({"OLLAMA_TAGS_URL": "https://example.com/api/tags"}),
            patch.object(preflight, "_run", return_value={"ok": True}),
            patch.object(preflight, "urlopen") as mocked_urlopen,
        ):
            report = preflight.inspect_ollama()

        self.assertFalse(report["ok"])
        self.assertEqual(report["error"], "NonLoopbackEndpoint")
        mocked_urlopen.assert_not_called()

    def test_accepts_ipv4_and_ipv6_loopback_http_endpoints(self) -> None:
        self.assertTrue(
            preflight._is_loopback_http_endpoint("http://127.0.0.1:11434/api/tags")
        )
        self.assertTrue(
            preflight._is_loopback_http_endpoint("http://[::1]:11434/api/tags")
        )
        self.assertFalse(
            preflight._is_loopback_http_endpoint("https://127.0.0.1:11434/api/tags")
        )


class BuildReportTests(unittest.TestCase):
    def test_ready_local_runtime_is_scoring_ready_when_pinned_and_clean(self) -> None:
        with (
            isolated_environment(),
            patch.object(preflight, "inspect_ollama", return_value=ready_ollama()),
            patch.object(preflight, "inspect_hermes", return_value=ready_hermes()),
        ):
            report = preflight.build_report()

        self.assertEqual(report["status"], "ready")
        self.assertTrue(report["runner_ready"])
        self.assertTrue(report["local_only"])
        self.assertTrue(report["scoring_ready"])
        self.assertEqual(report["blocking_reasons"], [])
        self.assertEqual(report["scoring_blocking_reasons"], [])

    def test_external_key_name_blocks_local_only_without_exposing_value(self) -> None:
        with (
            isolated_environment({"OPENAI_API_KEY": "not-a-real-key"}),
            patch.object(preflight, "inspect_ollama", return_value=ready_ollama()),
            patch.object(preflight, "inspect_hermes", return_value=ready_hermes()),
        ):
            report = preflight.build_report()

        self.assertEqual(report["status"], "ready")
        self.assertFalse(report["local_only"])
        self.assertFalse(report["scoring_ready"])
        self.assertEqual(report["external_api_env_names_present"], ["OPENAI_API_KEY"])
        self.assertIn("external_api_environment_present", report["blocking_reasons"])
        self.assertIn(
            "external_api_environment_present", report["scoring_blocking_reasons"]
        )
        self.assertNotIn("not-a-real-key", str(report))

    def test_non_loopback_ollama_blocks_preflight_with_specific_reason(self) -> None:
        with (
            isolated_environment(),
            patch.object(
                preflight,
                "inspect_ollama",
                return_value={
                    "ok": False,
                    "error": "NonLoopbackEndpoint",
                    "models": [],
                },
            ),
            patch.object(preflight, "inspect_hermes", return_value=ready_hermes()),
        ):
            report = preflight.build_report()

        self.assertEqual(report["status"], "blocked")
        self.assertIn("ollama_endpoint_not_loopback", report["blocking_reasons"])
        self.assertNotIn("ollama_unreachable", report["blocking_reasons"])

    def test_missing_hermes_blocks_preflight_and_scoring(self) -> None:
        with (
            isolated_environment(),
            patch.object(preflight, "inspect_ollama", return_value=ready_ollama()),
            patch.object(preflight, "inspect_hermes", return_value={"ok": False}),
        ):
            report = preflight.build_report()

        self.assertEqual(report["status"], "blocked")
        self.assertFalse(report["runner_ready"])
        self.assertFalse(report["scoring_ready"])
        self.assertIn("hermes_unavailable", report["blocking_reasons"])

    def test_dirty_hermes_keeps_runner_ready_but_blocks_scoring(self) -> None:
        with (
            isolated_environment(),
            patch.object(preflight, "inspect_ollama", return_value=ready_ollama()),
            patch.object(
                preflight,
                "inspect_hermes",
                return_value=ready_hermes(dirty=True),
            ),
        ):
            report = preflight.build_report()

        self.assertEqual(report["status"], "ready")
        self.assertTrue(report["runner_ready"])
        self.assertEqual(report["blocking_reasons"], [])
        self.assertFalse(report["scoring_ready"])
        self.assertEqual(report["scoring_blocking_reasons"], ["hermes_worktree_dirty"])

    def test_unknown_hermes_worktree_state_blocks_scoring(self) -> None:
        with (
            isolated_environment(),
            patch.object(preflight, "inspect_ollama", return_value=ready_ollama()),
            patch.object(
                preflight,
                "inspect_hermes",
                return_value=ready_hermes(dirty=None),
            ),
        ):
            report = preflight.build_report()

        self.assertEqual(report["status"], "ready")
        self.assertFalse(report["scoring_ready"])
        self.assertIn(
            "hermes_worktree_state_unknown", report["scoring_blocking_reasons"]
        )

    def test_incomplete_model_identity_blocks_scoring(self) -> None:
        ollama = ready_ollama()
        ollama["models"] = [{"name": "local", "digest": None}]
        with (
            isolated_environment(),
            patch.object(preflight, "inspect_ollama", return_value=ollama),
            patch.object(preflight, "inspect_hermes", return_value=ready_hermes()),
        ):
            report = preflight.build_report()

        self.assertEqual(report["status"], "ready")
        self.assertFalse(report["scoring_ready"])
        self.assertIn(
            "ollama_model_identity_incomplete", report["scoring_blocking_reasons"]
        )

    def test_missing_workflow_identity_blocks_scoring_only(self) -> None:
        with (
            isolated_environment({"GITHUB_SHA": ""}),
            patch.object(preflight, "inspect_ollama", return_value=ready_ollama()),
            patch.object(preflight, "inspect_hermes", return_value=ready_hermes()),
        ):
            report = preflight.build_report()

        self.assertEqual(report["status"], "ready")
        self.assertTrue(report["runner_ready"])
        self.assertFalse(report["scoring_ready"])
        self.assertIn("workflow_identity_incomplete", report["scoring_blocking_reasons"])


if __name__ == "__main__":
    unittest.main()

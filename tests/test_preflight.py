from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import preflight
from scripts.benchmark_runtime import REMOVED_ENV_REPORT


def ready_ollama() -> dict[str, object]:
    return {
        "ok": True,
        "version": {"ok": True},
        "models": [{"name": "local", "digest": "a" * 64, "size": 1}],
    }


def ready_hermes(*, dirty: bool | None = False) -> dict[str, object]:
    return {
        "ok": True,
        "repo": r"C:\AI\hermes-agent",
        "commit": "deadbeef",
        "dirty": dirty,
        "git_bash": {"probe": {"ok": True}},
    }


@contextmanager
def isolated_environment(values: dict[str, str] | None = None):
    fake_environment = {
        "RUNNER_NAME": "test-runner",
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_SHA": "cafebabe",
        "GITHUB_REF": "refs/heads/main",
        REMOVED_ENV_REPORT: "[]",
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
            patch.object(preflight._OPENER, "open") as mocked_open,
        ):
            report = preflight.inspect_ollama()
        self.assertFalse(report["ok"])
        self.assertEqual(report["error"], "NonLoopbackEndpoint")
        mocked_open.assert_not_called()

    def test_accepts_only_exact_loopback_tags_endpoint(self) -> None:
        self.assertTrue(preflight._is_loopback_http_endpoint("http://127.0.0.1:11434/api/tags"))
        self.assertTrue(preflight._is_loopback_http_endpoint("http://[::1]:11434/api/tags"))
        for endpoint in (
            "https://127.0.0.1:11434/api/tags",
            "http://127.0.0.1:11434/api/ps",
            "http://127.0.0.1:11434/api/tags?x=1",
            "http://user@127.0.0.1:11434/api/tags",
        ):
            with self.subTest(endpoint=endpoint):
                self.assertFalse(preflight._is_loopback_http_endpoint(endpoint))


class HermesWindowsLayoutTests(unittest.TestCase):
    def test_managed_windows_repo_candidate_uses_localappdata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "hermes" / "hermes-agent"
            (repo / ".git").mkdir(parents=True)
            with isolated_environment({"LOCALAPPDATA": str(root)}):
                resolved, source, evidence = preflight._resolve_hermes_repo()
        self.assertEqual(resolved, repo.resolve())
        self.assertEqual(source, "windows_managed_install")
        self.assertTrue(any(item["is_git"] for item in evidence))

    def test_official_venv_metadata_is_bound_without_executing_cli(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "hermes-agent"
            (repo / ".git").mkdir(parents=True)
            python_exe = repo / "venv" / "Scripts" / "python.exe"
            python_exe.parent.mkdir(parents=True)
            python_exe.write_text("", encoding="utf-8")
            module_file = repo / "hermes_cli" / "main.py"
            module_file.parent.mkdir(parents=True)
            module_file.write_text("", encoding="utf-8")
            metadata = json.dumps(
                {
                    "ok": True,
                    "python_executable": str(python_exe),
                    "python_prefix": str(repo / "venv"),
                    "distribution_version": "1.0",
                    "hermes_entry_point": "hermes_cli.main:main",
                    "module_file": str(module_file),
                }
            )

            def fake_run(command, **_kwargs):
                if command[0] == str(python_exe):
                    return {"ok": True, "stdout_tail": metadata}
                if command[:3] == ["git", "rev-parse", "HEAD"]:
                    return {"ok": True, "stdout_tail": "deadbeef"}
                if command[:3] == ["git", "branch", "--show-current"]:
                    return {"ok": True, "stdout_tail": "main"}
                if command[:3] == ["git", "status", "--porcelain"]:
                    return {"ok": True, "stdout_tail": ""}
                return {"ok": True, "stdout_tail": "ok"}

            with (
                isolated_environment({"HERMES_REPO": str(repo)}),
                patch.object(preflight, "_resolve_git_bash", return_value=(None, None, [])),
                patch.object(preflight, "_run", side_effect=fake_run) as run,
            ):
                report = preflight.inspect_hermes()
        commands = [call.args[0] for call in run.call_args_list]
        self.assertTrue(any(command[0] == str(python_exe) for command in commands))
        self.assertFalse(any("--help" in command or "--version" in command for command in commands))
        self.assertTrue(report["ok"])
        self.assertFalse(report["cli_executed"])


class BuildReportTests(unittest.TestCase):
    def test_ready_local_runtime_is_scoring_ready_when_pinned_and_clean(self) -> None:
        with (
            isolated_environment(),
            patch.object(preflight, "inspect_ollama", return_value=ready_ollama()),
            patch.object(preflight, "inspect_hermes", return_value=ready_hermes()),
        ):
            report = preflight.build_report()
        self.assertEqual(report["schema_version"], "bench.preflight.v1")
        self.assertTrue(report["runner_ready"])
        self.assertTrue(report["local_only"])
        self.assertTrue(report["scoring_ready"])
        self.assertEqual(report["scoring_blocking_reasons"], [])

    def test_external_key_blocks_unsanitized_process_without_exposing_value(self) -> None:
        with (
            isolated_environment({"OPENAI_API_KEY": "not-a-real-key"}),
            patch.object(preflight, "inspect_ollama", return_value=ready_ollama()),
            patch.object(preflight, "inspect_hermes", return_value=ready_hermes()),
        ):
            report = preflight.build_report()
        self.assertFalse(report["local_only"])
        self.assertFalse(report["scoring_ready"])
        self.assertEqual(report["external_api_env_names_present"], ["OPENAI_API_KEY"])
        self.assertNotIn("not-a-real-key", str(report))

    def test_removed_key_names_are_audited_without_blocking_sanitized_child(self) -> None:
        with (
            isolated_environment({REMOVED_ENV_REPORT: json.dumps(["OPENAI_API_KEY"])}),
            patch.object(preflight, "inspect_ollama", return_value=ready_ollama()),
            patch.object(preflight, "inspect_hermes", return_value=ready_hermes()),
        ):
            report = preflight.build_report()
        self.assertTrue(report["local_only"])
        self.assertTrue(report["scoring_ready"])
        self.assertEqual(
            report["environment_sanitization"]["removed_external_env_names"],
            ["OPENAI_API_KEY"],
        )

    def test_dirty_or_unknown_hermes_blocks_scoring(self) -> None:
        for dirty, expected in (
            (True, "hermes_worktree_dirty"),
            (None, "hermes_worktree_state_unknown"),
        ):
            with self.subTest(dirty=dirty):
                with (
                    isolated_environment(),
                    patch.object(preflight, "inspect_ollama", return_value=ready_ollama()),
                    patch.object(preflight, "inspect_hermes", return_value=ready_hermes(dirty=dirty)),
                ):
                    report = preflight.build_report()
                self.assertFalse(report["scoring_ready"])
                self.assertIn(expected, report["scoring_blocking_reasons"])

    def test_missing_workflow_identity_blocks_scoring(self) -> None:
        with (
            isolated_environment({"GITHUB_SHA": ""}),
            patch.object(preflight, "inspect_ollama", return_value=ready_ollama()),
            patch.object(preflight, "inspect_hermes", return_value=ready_hermes()),
        ):
            report = preflight.build_report()
        self.assertFalse(report["scoring_ready"])
        self.assertIn("workflow_identity_incomplete", report["scoring_blocking_reasons"])


class MainExitTests(unittest.TestCase):
    def test_main_fails_closed_when_scoring_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "preflight.json"
            with (
                patch.object(preflight, "build_report", return_value={"scoring_ready": False}),
                patch.object(sys, "argv", ["preflight.py", "--output", str(output)]),
            ):
                self.assertEqual(preflight.main(), 2)
            self.assertTrue(output.is_file())

    def test_main_succeeds_only_when_scoring_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "preflight.json"
            with (
                patch.object(preflight, "build_report", return_value={"scoring_ready": True}),
                patch.object(sys, "argv", ["preflight.py", "--output", str(output)]),
            ):
                self.assertEqual(preflight.main(), 0)


if __name__ == "__main__":
    unittest.main()

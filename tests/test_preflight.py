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
    return {"ok": True, "version": {"ok": True}, "models": [{"name": "local", "digest": "a" * 64, "size": 1}]}


def ready_hermes(dirty: bool | None = False) -> dict[str, object]:
    return {"ok": True, "repo": r"C:\AI\hermes-agent", "commit": "deadbeef", "dirty": dirty, "git_bash": {"probe": {"ok": True}}}


@contextmanager
def environment(extra: dict[str, str] | None = None):
    values = {
        "RUNNER_NAME": "test-runner",
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_SHA": "cafebabe",
        "GITHUB_REF": "refs/heads/main",
        REMOVED_ENV_REPORT: "[]",
    }
    values.update(extra or {})
    with (
        patch.object(preflight.os, "environ", values),
        patch.object(preflight.os, "cpu_count", return_value=24),
        patch.object(preflight.platform, "platform", return_value="Windows-test"),
        patch.object(preflight.platform, "machine", return_value="AMD64"),
        patch.object(preflight.platform, "processor", return_value="test-processor"),
    ):
        yield


class EndpointTests(unittest.TestCase):
    def test_only_exact_loopback_tags_endpoint_is_allowed(self) -> None:
        self.assertTrue(preflight._is_loopback_http_endpoint("http://127.0.0.1:11434/api/tags"))
        self.assertTrue(preflight._is_loopback_http_endpoint("http://[::1]:11434/api/tags"))
        for value in (
            "https://127.0.0.1:11434/api/tags",
            "http://127.0.0.1:11434/api/ps",
            "http://127.0.0.1:11434/api/tags?x=1",
            "http://user@127.0.0.1:11434/api/tags",
        ):
            self.assertFalse(preflight._is_loopback_http_endpoint(value))

    def test_external_endpoint_is_rejected_before_open(self) -> None:
        with (
            environment({"OLLAMA_TAGS_URL": "https://example.invalid/api/tags"}),
            patch.object(preflight, "_run", return_value={"ok": True}),
            patch.object(preflight._OPENER, "open") as opened,
        ):
            report = preflight.inspect_ollama()
        self.assertEqual(report["error"], "NonLoopbackEndpoint")
        opened.assert_not_called()


class HermesLayoutTests(unittest.TestCase):
    def test_managed_windows_repo_is_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / "hermes" / "hermes-agent"
            (repo / ".git").mkdir(parents=True)
            with environment({"LOCALAPPDATA": str(root)}):
                resolved, source, _ = preflight._resolve_hermes_repo()
        self.assertEqual(resolved, repo.resolve())
        self.assertEqual(source, "windows_managed_install")

    def test_metadata_probe_never_executes_hermes_cli(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "hermes-agent"
            (repo / ".git").mkdir(parents=True)
            python_exe = repo / "venv" / "Scripts" / "python.exe"
            python_exe.parent.mkdir(parents=True)
            python_exe.write_text("", encoding="utf-8")
            module_file = repo / "hermes_cli" / "main.py"
            module_file.parent.mkdir(parents=True)
            module_file.write_text("", encoding="utf-8")
            bash_exe = repo / "git" / "bin" / "bash.exe"
            bash_exe.parent.mkdir(parents=True)
            bash_exe.write_text("", encoding="utf-8")
            metadata = json.dumps({
                "ok": True,
                "python_executable": str(python_exe),
                "python_prefix": str(repo / "venv"),
                "distribution_version": "1.0",
                "hermes_entry_point": "hermes_cli.main:main",
                "module_file": str(module_file),
                "package_imported": False,
            })

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
                environment({"HERMES_REPO": str(repo)}),
                patch.object(preflight, "_resolve_git_bash", return_value=(bash_exe, "fixture", [])),
                patch.object(preflight, "_run", side_effect=fake_run) as called,
            ):
                report = preflight.inspect_hermes()
        commands = [item.args[0] for item in called.call_args_list]
        self.assertTrue(report["ok"])
        self.assertFalse(report["cli_executed"])
        self.assertFalse(
            any(
                command[0] != str(bash_exe) and ("--help" in command or "--version" in command)
                for command in commands
            )
        )


class ReportTests(unittest.TestCase):
    def build(self, *, hermes=None):
        with (
            environment(),
            patch.object(preflight, "inspect_ollama", return_value=ready_ollama()),
            patch.object(preflight, "inspect_hermes", return_value=hermes or ready_hermes()),
        ):
            return preflight.build_report()

    def test_clean_local_runtime_is_scoring_ready(self) -> None:
        report = self.build()
        self.assertTrue(report["runner_ready"])
        self.assertTrue(report["local_only"])
        self.assertTrue(report["scoring_ready"])

    def test_dirty_or_unknown_hermes_blocks_scoring(self) -> None:
        for dirty, reason in ((True, "hermes_worktree_dirty"), (None, "hermes_worktree_state_unknown")):
            report = self.build(hermes=ready_hermes(dirty))
            self.assertFalse(report["scoring_ready"])
            self.assertIn(reason, report["scoring_blocking_reasons"])

    def test_removed_environment_names_are_audited(self) -> None:
        with (
            environment({REMOVED_ENV_REPORT: json.dumps(["PROVIDER_API_KEY"])}),
            patch.object(preflight, "inspect_ollama", return_value=ready_ollama()),
            patch.object(preflight, "inspect_hermes", return_value=ready_hermes()),
        ):
            report = preflight.build_report()
        self.assertEqual(report["environment_sanitization"]["removed_external_env_names"], ["PROVIDER_API_KEY"])
        self.assertTrue(report["scoring_ready"])

    def test_incomplete_workflow_identity_blocks_scoring(self) -> None:
        with (
            environment({"GITHUB_SHA": ""}),
            patch.object(preflight, "inspect_ollama", return_value=ready_ollama()),
            patch.object(preflight, "inspect_hermes", return_value=ready_hermes()),
        ):
            report = preflight.build_report()
        self.assertIn("workflow_identity_incomplete", report["scoring_blocking_reasons"])


class MainTests(unittest.TestCase):
    def test_main_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "preflight.json"
            with (
                patch.object(preflight, "build_report", return_value={"scoring_ready": False}),
                patch.object(sys, "argv", ["preflight.py", "--output", str(output)]),
            ):
                self.assertEqual(preflight.main(), 2)
            self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()

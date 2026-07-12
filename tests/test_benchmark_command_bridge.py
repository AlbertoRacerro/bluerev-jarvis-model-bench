from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
DETERMINISTIC = ROOT / ".github" / "workflows" / "deterministic-ci.yml"
LEGACY_BRIDGE = ROOT / ".github" / "workflows" / "benchmark-command-bridge.yml"
TARGETS = {
    "/bench preflight": "local-benchmark.yml",
    "/bench residency": "local-model-residency.yml",
    "/bench direct-smoke": "local-direct-smoke.yml",
}


class BenchmarkCommandControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = DETERMINISTIC.read_text(encoding="utf-8")
        marker = "  benchmark_command_control:\n"
        cls.assertIn(cls, marker, cls.workflow)
        cls.control = marker + cls.workflow.split(marker, 1)[1]

    def test_legacy_unregistered_workflow_is_removed(self) -> None:
        self.assertFalse(LEGACY_BRIDGE.exists())

    def test_existing_deterministic_gate_is_preserved(self) -> None:
        for required in (
            "name: Trusted-main deterministic CI",
            "runs-on: [self-hosted, Windows, X64, bluerev-bench]",
            "scripts\\run_deterministic_capture.cmd",
            "actions/upload-artifact@v4",
            "python -m scripts.run_deterministic_ci enforce",
            "bench.deterministic-ci-minimal.v1",
        ):
            self.assertIn(required, self.workflow)

    def test_control_job_is_independent_and_github_hosted(self) -> None:
        for required in (
            "name: benchmark-command-control",
            "runs-on: ubuntu-latest",
            "group: benchmark-command-control",
            "cancel-in-progress: false",
        ):
            self.assertIn(required, self.control)
        self.assertNotIn("needs:", self.control)
        self.assertNotIn("runs-on: [self-hosted", self.control)

    def test_control_permissions_are_job_scoped(self) -> None:
        self.assertIn(
            "permissions:\n      contents: read\n      issues: write\n      actions: write\n",
            self.control,
        )
        workflow_prefix = self.workflow.split("jobs:", 1)[0]
        self.assertNotIn("actions: write", workflow_prefix)
        self.assertNotIn("contents: write", self.workflow)

    def test_first_attempt_only_registers_observable_seed(self) -> None:
        for required in (
            "if (Number(process.env.RUN_ATTEMPT) === 1)",
            "await registerSeed();",
            "issue_number: REGISTRY_ISSUE",
            "bench.command-seed.v1",
            "run_id: context.runId",
            "job_name: 'benchmark-command-control'",
            "workflow: 'Trusted-main deterministic CI'",
        ):
            self.assertIn(required, self.control)
        self.assertLess(
            self.control.index("await registerSeed();"),
            self.control.index("const comment = await findPendingCommand();"),
        )

    def test_only_exact_owner_commands_are_accepted(self) -> None:
        for required in (
            "const OWNER_LOGIN = 'AlbertoRacerro';",
            "const OWNER_ID = 293122393;",
            "comment.user?.type === 'User'",
            "comment.author_association === 'OWNER'",
            "Object.hasOwn(workflows, comment.body)",
        ):
            self.assertIn(required, self.control)
        for command, workflow in TARGETS.items():
            self.assertIn(f"'{command}': '{workflow}'", self.control)

    def test_receipt_watermark_is_bot_bound_and_blocks_replay(self) -> None:
        for required in (
            "const ACTIONS_BOT_ID = 41898282;",
            "comment?.user?.login === 'github-actions[bot]'",
            "comment?.user?.type === 'Bot'",
            "const lastConsumedId = Math.max",
            "Number(comment.id) > lastConsumedId",
            "source_comment_id: comment.id",
        ):
            self.assertIn(required, self.control)

    def test_dispatch_is_fixed_to_main_without_shell_or_checkout(self) -> None:
        for required in (
            "github.rest.actions.createWorkflowDispatch",
            "workflow_id: workflowId",
            "ref: 'main'",
            "bench.command-receipt.v1",
            "dispatcher_run_id: context.runId",
        ):
            self.assertIn(required, self.control)
        self.assertNotIn("actions/checkout", self.control)
        self.assertNotRegex(self.control, re.compile(r"(?m)^\s*run:"))
        self.assertNotIn("${{ github.event.comment.body }}", self.control)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
DETERMINISTIC = ROOT / ".github" / "workflows" / "deterministic-ci.yml"
PREFLIGHT = ROOT / ".github" / "workflows" / "local-benchmark.yml"
LEGACY_BRIDGE = ROOT / ".github" / "workflows" / "benchmark-command-bridge.yml"
TARGETS = {
    "/bench preflight": "local-benchmark.yml",
    "/bench residency": "local-model-residency.yml",
    "/bench direct-smoke": "local-direct-smoke.yml",
}


class BenchmarkCommandControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.deterministic = DETERMINISTIC.read_text(encoding="utf-8")
        cls.workflow = PREFLIGHT.read_text(encoding="utf-8")
        marker = "  benchmark_command_control:\n"
        cls.assertIn(cls, marker, cls.workflow)
        cls.control = marker + cls.workflow.split(marker, 1)[1]

    def test_control_is_not_bound_to_connector_push_events(self) -> None:
        self.assertNotIn("benchmark_command_control:", self.deterministic)
        self.assertIn('cron: "17 * * * *"', self.workflow)
        self.assertFalse(LEGACY_BRIDGE.exists())

    def test_existing_preflight_lane_is_preserved(self) -> None:
        for required in (
            "name: Local benchmark preflight",
            "runs-on: [self-hosted, Windows, X64, bluerev-bench]",
            "python -m scripts.run_preflight_job capture",
            "actions/upload-artifact@v4",
            "python -m scripts.run_preflight_job enforce",
            "bench.workflow-inbox.v2",
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

    def test_old_commands_are_excluded_by_fixed_epoch(self) -> None:
        for required in (
            "const COMMAND_EPOCH_ID = 4951513674;",
            "Number(comment.id) > COMMAND_EPOCH_ID",
            "const lastConsumedId = Math.max(",
            "COMMAND_EPOCH_ID,",
            "Number(comment.id) > lastConsumedId",
        ):
            self.assertIn(required, self.control)

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
            "receipt.schema_version === 'bench.command-receipt.v1'",
            "source_comment_id: command.id",
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

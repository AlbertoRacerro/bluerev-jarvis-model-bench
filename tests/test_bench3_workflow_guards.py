from __future__ import annotations

import unittest
from unittest import mock

from scripts import validate_bench3_hermes_memory_routing_design as core


class Bench3WorkflowGuardTests(unittest.TestCase):
    def test_removing_any_broad_trigger_fails_closed(self):
        original_read = core._read
        workflow = original_read(core.DESIGN_WORKFLOW_PATH)
        for trigger in core.C.BROAD_TRIGGERS:
            with self.subTest(trigger=trigger):
                changed = workflow.replace(f"      - {trigger}\n", "", 1)
                with mock.patch.object(
                    core,
                    "_read",
                    side_effect=lambda path, changed=changed: changed
                    if path == core.DESIGN_WORKFLOW_PATH
                    else original_read(path),
                ):
                    with self.assertRaisesRegex(
                        core.MemoryRoutingDesignError,
                        "broad trigger missing",
                    ):
                        core.validate()


if __name__ == "__main__":
    unittest.main()

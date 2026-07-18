from __future__ import annotations

import copy
import unittest
from unittest import mock

from scripts import bench3r_mr0_validate_design as design
from scripts import validate_bench3r_mr0_design as entry
from scripts.bench3r_mr0_io import MR0DesignError


class MR0PolicyTests(unittest.TestCase):
    def assert_plan_rejected(self, plan):
        original = design.load_object
        with mock.patch.object(
            design,
            "load_object",
            side_effect=lambda path: copy.deepcopy(plan)
            if path == design.PLAN
            else original(path),
        ):
            with self.assertRaises(MR0DesignError):
                entry.validate()

    def test_boolean_policy_drift_fails_closed(self):
        base = design.load_object(design.PLAN)
        for section in ("acceptance", "execution"):
            for key, value in base[section].items():
                if isinstance(value, bool):
                    with self.subTest(section=section, key=key):
                        plan = copy.deepcopy(base)
                        plan[section][key] = not value
                        self.assert_plan_rejected(plan)

    def test_batch_and_runtime_limits_are_exact(self):
        base = design.load_object(design.PLAN)
        for section, key, value in (
            ("runtime_model", "max_concurrent_children", 1),
            ("runtime_model", "wall_clock_watchdog_seconds", 0),
            ("batching", "max_parallel_batches", 2),
            ("batching", "runs_per_batch", 17),
        ):
            with self.subTest(section=section, key=key):
                plan = copy.deepcopy(base)
                plan[section][key] = value
                self.assert_plan_rejected(plan)


if __name__ == "__main__":
    unittest.main()

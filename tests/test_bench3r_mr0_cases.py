from __future__ import annotations

import copy
import unittest
from unittest import mock

from scripts import bench3r_mr0_validate_design as design
from scripts import validate_bench3r_mr0_design as entry
from scripts.bench3r_mr0_io import MR0DesignError


class MR0CaseTests(unittest.TestCase):
    def test_case_and_seed_drift_fail_closed(self):
        base = design.load_object(design.PLAN)
        for section, key, value in (
            ("paired_cases", "memory", []),
            ("seed_policy", "canary_seeds", [17, 42]),
            ("counts", "total_canary_runs", 35),
        ):
            plan = copy.deepcopy(base)
            plan[section][key] = value
            original = design.load_object
            with mock.patch.object(
                design,
                "load_object",
                side_effect=lambda path, plan=plan: copy.deepcopy(plan)
                if path == design.PLAN
                else original(path),
            ):
                with self.assertRaises(MR0DesignError):
                    entry.validate()


if __name__ == "__main__":
    unittest.main()

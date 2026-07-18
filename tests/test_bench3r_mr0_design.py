from __future__ import annotations

import copy
import unittest
from unittest import mock

from scripts import bench3r_mr0_validate_design as design
from scripts import validate_bench3r_mr0_design as entry
from scripts.bench3r_mr0_io import MR0DesignError


class MR0DesignTests(unittest.TestCase):
    def patch_plan(self, payload):
        original = design.load_object
        return mock.patch.object(
            design,
            "load_object",
            side_effect=lambda path: copy.deepcopy(payload)
            if path == design.PLAN
            else original(path),
        )

    def test_static_design_validates(self):
        result = entry.validate()
        self.assertEqual(result["status"], "valid_static_design")
        self.assertEqual(result["future_canary_runs"], 36)
        self.assertFalse(result["execution_implemented"])

    def test_identity_and_count_drift_fail_closed(self):
        base = design.load_object(design.PLAN)
        variants = []
        item = copy.deepcopy(base)
        item["schema_version"] = "v0"
        variants.append(item)
        item = copy.deepcopy(base)
        item["governed_orchestrator_stack"]["context_length"] = 4096
        variants.append(item)
        item = copy.deepcopy(base)
        item["counts"]["total_canary_runs"] = 35
        variants.append(item)
        for index, payload in enumerate(variants):
            with self.subTest(index=index), self.patch_plan(payload), self.assertRaises(
                MR0DesignError
            ):
                entry.validate()


if __name__ == "__main__":
    unittest.main()

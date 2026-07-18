from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import validate_bench3_hermes_memory_routing_design as core


class Bench3CaseContractTests(unittest.TestCase):
    def patch_json(self, target, payload):
        original = core._load
        return mock.patch.object(
            core,
            "_load",
            side_effect=lambda path: copy.deepcopy(payload) if path == target else original(path),
        )

    def test_case_contracts_validate_and_are_bound(self):
        result = core.validate()
        self.assertTrue(result["case_contracts_validated"])
        self.assertEqual(result["case_contracts_blob_sha"], core.C.CASE_CONTRACT_BLOB_SHA)

    def test_case_contract_mutations_fail_closed(self):
        original = core._load(core.CASE_CONTRACTS_PATH)
        variants = []
        item = copy.deepcopy(original)
        item["memory_cases"][0].pop("success_contract")
        variants.append(item)
        item = copy.deepcopy(original)
        item["routing_cases"][0]["negative_assertions"] = ["only_one"]
        variants.append(item)
        item = copy.deepcopy(original)
        item["routing_cases"][0]["success_contract"]["decision"] = "guess"
        variants.append(item)
        for index, payload in enumerate(variants):
            with self.subTest(index=index), self.patch_json(core.CASE_CONTRACTS_PATH, payload), self.assertRaises(core.MemoryRoutingDesignError):
                core.validate()

    def test_plan_and_actual_blob_drift_fail_closed(self):
        plan = core._load(core.PLAN_PATH)
        plan["benchmark_design"]["case_contracts"]["git_blob_sha"] = "0" * 40
        with self.patch_json(core.PLAN_PATH, plan), self.assertRaises(core.MemoryRoutingDesignError):
            core.validate()
        original_read = core._read
        changed = original_read(core.CASE_CONTRACTS_PATH) + " "
        with mock.patch.object(core, "_read", side_effect=lambda path: changed if path == core.CASE_CONTRACTS_PATH else original_read(path)):
            with self.assertRaises(core.MemoryRoutingDesignError):
                core.validate()

    def test_all_namespace_spellings_and_windows_helpers_are_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            samples = [
                ".github/workflows/bench-3-memory-canary.yml",
                "scripts/bench_3_routing_worker.ps1",
                "scripts/bench3-memory-worker.cmd",
                "scripts/opaque.bat",
            ]
            for relative in samples:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                text = "bench.hermes-memory-routing-design.v1" if path.name == "opaque.bat" else "runtime"
                path.write_text(text, encoding="utf-8")
            with mock.patch.object(core, "ROOT", root):
                found = core._unexpected_runtime_artifacts()
            self.assertEqual(found, sorted(samples))


if __name__ == "__main__":
    unittest.main()

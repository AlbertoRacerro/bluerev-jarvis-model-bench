from __future__ import annotations

import copy
import unittest
from pathlib import Path

from bench.contracts import ContractError
from bench.evaluator import build_candidate_payload, load_case_directory

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "bench-1"


class EvaluatorPreInferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = load_case_directory(FIXTURES)

    def test_unsupported_assertion_blocks_candidate_payload(self) -> None:
        case = copy.deepcopy(self.cases["ho-stop-reuse-001"])
        case["success_assertions"] = ["final_schema_valid"]

        with self.assertRaisesRegex(ContractError, "not implemented"):
            build_candidate_payload(case)


if __name__ == "__main__":
    unittest.main()

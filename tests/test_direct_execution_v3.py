from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.request import Request

from bench.contracts import ContractError
from bench.direct_execution_v3 import execute_direct_smoke, verify_candidate_visible_response_contract

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_ID = "qwythos-hermes-safe"
MODEL_TAG = "qwythos-hermes-safe:latest"
MODEL_DIGEST = "f1b4ecbbe67a7adef8f8f975cdbfb3eb08a04b8d91737b2b96e7b761187c668d"
CASE_PATH = ROOT / "fixtures/bench-1/ho-stop-reuse-explicit-002.json"
GENERATE_URL = "http://127.0.0.1:11434/api/generate"


class FakeResponse:
    def __init__(self, payload: dict[str, object]):
        self.data = json.dumps(payload).encode()
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def read(self, _size: int): return self.data
    def geturl(self): return GENERATE_URL


def preflight(gate: str = "direct") -> dict[str, object]:
    direct = gate == "direct"
    return {
        "schema_version": "bench.preflight.v1",
        "selected_gate": gate,
        "runner_ready": True,
        "scoring_ready": True,
        "local_only": True,
        "workflow": {"run_id": "1", "run_attempt": "1", "sha": "abc", "ref": "refs/heads/main"},
        "environment": {"runner_name": "test"},
        "hermes": {"commit": "h", "dirty": False},
        "ollama": {"version": {"ok": True}, "models": [{"name": MODEL_TAG, "digest": MODEL_DIGEST}]},
        "lanes": {
            "direct": {"evaluated": direct, "runner_ready": direct, "scoring_ready": direct},
            "hermes": {"evaluated": not direct, "runner_ready": not direct, "scoring_ready": not direct},
        },
    }


class DirectExecutionV3Tests(unittest.TestCase):
    def test_fixture_exposes_exact_response_contract(self):
        case = json.loads(CASE_PATH.read_text(encoding="utf-8"))
        verify_candidate_visible_response_contract(case)
        self.assertEqual(case["inputs"]["response_contract"]["output_field"], "final")

    def test_hermes_gate_is_rejected_before_model_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "preflight.json"
            path.write_text(json.dumps(preflight("hermes")), encoding="utf-8")
            called = False
            def opener(_request: Request, _timeout: int):
                nonlocal called
                called = True
                return FakeResponse({"done": True, "response": "unused"})
            with self.assertRaisesRegex(ContractError, "selected_gate=direct"):
                execute_direct_smoke(
                    run_id="wrong-gate", candidate_id=CANDIDATE_ID,
                    candidate_registry_path=ROOT / "candidates/models.local.json",
                    case_path=CASE_PATH, preflight_path=path,
                    output_root=root / "out", opener=opener,
                )
            self.assertFalse(called)

    def test_hidden_oracle_mismatch_is_rejected_before_model_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = json.loads(CASE_PATH.read_text(encoding="utf-8"))
            case["expected"]["final"] = "different"
            case_path = root / "case.json"
            case_path.write_text(json.dumps(case), encoding="utf-8")
            preflight_path = root / "preflight.json"
            preflight_path.write_text(json.dumps(preflight()), encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "candidate-visible"):
                execute_direct_smoke(
                    run_id="mismatch", candidate_id=CANDIDATE_ID,
                    candidate_registry_path=ROOT / "candidates/models.local.json",
                    case_path=case_path, preflight_path=preflight_path,
                    output_root=root / "out",
                    opener=lambda *_args: FakeResponse({"done": True, "response": "unused"}),
                )

    def test_completed_run_binds_case_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preflight_path = root / "preflight.json"
            preflight_path.write_text(json.dumps(preflight()), encoding="utf-8")
            response = {"done": True, "done_reason": "stop", "eval_count": 80,
                        "response": 'FINAL: {"output":{"final":"stable-result"},"actions":["return_supplied_result","stop"]}'}
            summary = execute_direct_smoke(
                run_id="run-v3", candidate_id=CANDIDATE_ID,
                candidate_registry_path=ROOT / "candidates/models.local.json",
                case_path=CASE_PATH, preflight_path=preflight_path,
                output_root=root / "out", opener=lambda *_args: FakeResponse(response),
            )
            manifest = json.loads((root / "out/run-v3/manifest.json").read_text())
            self.assertEqual(summary["candidate_result_status"], "passed")
            self.assertIn("case_definition.json", manifest["artifacts"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.request import Request

from bench.direct_execution_v2 import NUM_PREDICT, execute_direct_smoke

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_ID = "qwythos-hermes-safe"
MODEL_TAG = "qwythos-hermes-safe:latest"
MODEL_DIGEST = "f1b4ecbbe67a7adef8f8f975cdbfb3eb08a04b8d91737b2b96e7b761187c668d"
GENERATE_URL = "http://127.0.0.1:11434/api/generate"


class FakeResponse:
    def __init__(self, payload: dict[str, object], url: str = GENERATE_URL):
        self._data = json.dumps(payload).encode("utf-8")
        self._url = url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size: int):
        return self._data

    def geturl(self):
        return self._url


def preflight() -> dict[str, object]:
    return {
        "schema_version": "bench.preflight.v1",
        "runner_ready": True,
        "scoring_ready": True,
        "local_only": True,
        "workflow": {
            "run_id": "1",
            "run_attempt": "1",
            "sha": "abc",
            "ref": "refs/heads/main",
        },
        "environment": {"runner_name": "test"},
        "hermes": {"commit": "h", "dirty": False},
        "ollama": {
            "version": {"ok": True},
            "models": [{"name": MODEL_TAG, "digest": MODEL_DIGEST}],
        },
    }


class DirectExecutionV2Tests(unittest.TestCase):
    def execute_with_response(self, payload: dict[str, object]):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        preflight_path = root / "preflight.json"
        preflight_path.write_text(json.dumps(preflight()), encoding="utf-8")

        def opener(request: Request, timeout: int):
            request_payload = json.loads(request.data.decode("utf-8"))
            self.assertEqual(request_payload["model"], MODEL_TAG)
            self.assertEqual(request_payload["options"]["num_predict"], NUM_PREDICT)
            return FakeResponse(payload)

        summary = execute_direct_smoke(
            run_id="run-v2",
            candidate_id=CANDIDATE_ID,
            candidate_registry_path=ROOT / "candidates/models.local.json",
            case_path=ROOT / "fixtures/bench-1/ho-stop-reuse-001.json",
            preflight_path=preflight_path,
            output_root=root / "out",
            opener=opener,
        )
        return root, summary

    def test_length_termination_is_invalid_not_candidate_failure(self):
        root, summary = self.execute_with_response(
            {
                "done": True,
                "done_reason": "length",
                "eval_count": NUM_PREDICT,
                "response": "unfinished reasoning without FINAL marker",
            }
        )
        self.assertEqual(summary["candidate_result_status"], "invalid")
        self.assertIsNone(summary["candidate_passed"])
        manifest = json.loads(
            (root / "out/run-v2/manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["status"], "invalid")
        validator = json.loads(
            (root / "out/run-v2/validator_result.json").read_text(encoding="utf-8")
        )
        self.assertEqual(validator["checks"][0]["assertion_id"], "generation_complete")

    def test_complete_valid_submission_still_passes(self):
        root, summary = self.execute_with_response(
            {
                "done": True,
                "done_reason": "stop",
                "eval_count": 40,
                "response": (
                    "<think>identity-oriented reasoning</think>\n"
                    'FINAL: {"output":{"final":"stable-result"},'
                    '"actions":["return_supplied_result","stop"]}'
                ),
            }
        )
        self.assertEqual(summary["candidate_result_status"], "passed")
        self.assertTrue(summary["candidate_passed"])
        manifest = json.loads(
            (root / "out/run-v2/manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["status"], "preliminary")

    def test_complete_wrong_submission_remains_failed(self):
        _, summary = self.execute_with_response(
            {
                "done": True,
                "done_reason": "stop",
                "eval_count": 20,
                "response": (
                    'FINAL: {"output":{"final":"wrong"},'
                    '"actions":["return_supplied_result","stop"]}'
                ),
            }
        )
        self.assertEqual(summary["candidate_result_status"], "failed")
        self.assertFalse(summary["candidate_passed"])


if __name__ == "__main__":
    unittest.main()

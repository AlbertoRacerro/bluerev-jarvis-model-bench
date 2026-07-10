from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.request import Request

from bench.contracts import ContractError
from bench.direct_execution import (
    build_prompt,
    call_ollama_generate,
    execute_direct_smoke,
    load_candidate,
    parse_submission,
    verify_scoring_environment,
)

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_ID = "minicpm5-fable-1b-control"
MODEL_TAG = (
    "hf.co/GnLOLot/MiniCPM5-1B-Claude-Opus-Fable5-Thinking-GGUF:Q4_K_M"
)
MODEL_DIGEST = "9273fd7794224d33f1ce2364c395df1eeb049e56705d635b29cfc51dfd6d157e"
GENERATE_URL = "http://127.0.0.1:11434/api/generate"


class FakeResponse:
    def __init__(self, payload: dict[str, object], url: str = GENERATE_URL):
        self._data = json.dumps(payload).encode()
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


class DirectExecutionTests(unittest.TestCase):
    def test_loads_exact_enabled_candidate(self):
        candidate = load_candidate(ROOT / "candidates/models.local.json", CANDIDATE_ID)
        self.assertEqual(candidate["digest"], MODEL_DIGEST)

    def test_environment_requires_exact_digest(self):
        candidate = {"model_tag": MODEL_TAG, "digest": "wrong"}
        with self.assertRaisesRegex(ContractError, "tag and digest"):
            verify_scoring_environment(preflight(), candidate)

    def test_prompt_hides_oracle(self):
        payload = {
            "case_id": "x",
            "prompt": "p",
            "inputs": {},
            "allowed_actions": ["stop"],
            "forbidden_actions": [],
            "limits": {},
        }
        prompt = build_prompt(payload)
        self.assertNotIn("expected", prompt)
        with self.assertRaisesRegex(ContractError, "leaks"):
            build_prompt({**payload, "expected": {"answer": 1}})

    def test_rejects_non_loopback_before_opener(self):
        called = False

        def opener(request: Request, timeout: int):
            nonlocal called
            called = True
            return FakeResponse({"done": True, "response": "FINAL: {}"})

        with self.assertRaisesRegex(ContractError, "loopback"):
            call_ollama_generate(
                endpoint="https://example.com/api/generate",
                model_tag="m",
                prompt="p",
                opener=opener,
            )
        self.assertFalse(called)

    def test_rejects_redirect(self):
        def opener(request: Request, timeout: int):
            return FakeResponse(
                {"done": True, "response": "FINAL: {}"},
                "http://127.0.0.1:9999/api/generate",
            )

        with self.assertRaisesRegex(ContractError, "redirected"):
            call_ollama_generate(
                endpoint=GENERATE_URL,
                model_tag="m",
                prompt="p",
                opener=opener,
            )

    def test_parse_submission_is_strict(self):
        output, trace = parse_submission(
            'FINAL: {"output":{"final":"stable-result"},'
            '"actions":["return_supplied_result","stop"]}',
            "c",
        )
        self.assertEqual(output, {"final": "stable-result"})
        self.assertEqual(
            [event["action_id"] for event in trace["events"]],
            ["return_supplied_result", "stop"],
        )
        with self.assertRaisesRegex(ContractError, "unsupported fields"):
            parse_submission(
                'FINAL: {"output":{"final":"x"},'
                '"actions":["stop"],"score":1}',
                "c",
            )

    def test_successful_execution_writes_immutable_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preflight_path = root / "preflight.json"
            preflight_path.write_text(json.dumps(preflight()), encoding="utf-8")

            def opener(request: Request, timeout: int):
                request_payload = json.loads(request.data.decode())
                self.assertEqual(request_payload["model"], MODEL_TAG)
                return FakeResponse(
                    {
                        "done": True,
                        "response": (
                            'FINAL: {"output":{"final":"stable-result"},'
                            '"actions":["return_supplied_result","stop"]}'
                        ),
                    }
                )

            summary = execute_direct_smoke(
                run_id="run-1",
                candidate_id=CANDIDATE_ID,
                candidate_registry_path=ROOT / "candidates/models.local.json",
                case_path=ROOT / "fixtures/bench-1/ho-stop-reuse-001.json",
                preflight_path=preflight_path,
                output_root=root / "out",
                opener=opener,
            )
            self.assertTrue(summary["execution_completed"])
            self.assertTrue(summary["candidate_passed"])
            run_dir = root / "out/run-1"
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["lane"], "direct")
            self.assertIn("raw_output.txt", manifest["artifacts"])

    def test_malformed_output_is_candidate_failure_not_infrastructure_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preflight_path = root / "preflight.json"
            preflight_path.write_text(json.dumps(preflight()), encoding="utf-8")

            def opener(request: Request, timeout: int):
                return FakeResponse({"done": True, "response": "not contracted"})

            summary = execute_direct_smoke(
                run_id="run-2",
                candidate_id=CANDIDATE_ID,
                candidate_registry_path=ROOT / "candidates/models.local.json",
                case_path=ROOT / "fixtures/bench-1/ho-stop-reuse-001.json",
                preflight_path=preflight_path,
                output_root=root / "out",
                opener=opener,
            )
            self.assertTrue(summary["execution_completed"])
            self.assertFalse(summary["candidate_passed"])
            result = json.loads(
                (root / "out/run-2/validator_result.json").read_text(encoding="utf-8")
            )
            self.assertFalse(result["passed"])
            self.assertEqual(result["checks"][0]["assertion_id"], "submission_contract")

    def test_existing_run_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preflight_path = root / "preflight.json"
            preflight_path.write_text(json.dumps(preflight()), encoding="utf-8")
            output_root = root / "out"
            (output_root / "same").mkdir(parents=True)
            with self.assertRaisesRegex(ContractError, "already exists"):
                execute_direct_smoke(
                    run_id="same",
                    candidate_id=CANDIDATE_ID,
                    candidate_registry_path=ROOT / "candidates/models.local.json",
                    case_path=ROOT / "fixtures/bench-1/ho-stop-reuse-001.json",
                    preflight_path=preflight_path,
                    output_root=output_root,
                    opener=lambda request, timeout: FakeResponse(
                        {"done": True, "response": "FINAL: {}"}
                    ),
                )


if __name__ == "__main__":
    unittest.main()

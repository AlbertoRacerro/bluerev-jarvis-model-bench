from __future__ import annotations

import http.client
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import bench2r_loopback_wire_proxy as proxy_module
from scripts import run_bench2r_hermes_s2_safe as safe
from scripts import validate_bench2r_hermes_s2 as validator
from scripts import validate_bench2r_hermes_s2_safe as safe_validator

ROOT = Path(__file__).resolve().parents[1]
VAULT_CASE = ROOT / "fixtures/bench-2r/s2-cases/s2-tools-vault-fetch-001.json"
REGISTRY_CASE = ROOT / "fixtures/bench-2r/s2-cases/s2-tools-registry-read-002.json"


class _FakeResponse:
    status = 200
    headers = {"Content-Type": "application/json"}

    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._body


class Bench2RHermesS2Tests(unittest.TestCase):
    def test_model_prompt_excludes_evaluator_expected_and_tool_answers(self):
        for path, forbidden in (
            (VAULT_CASE, ("expected", "DELTA-58")),
            (REGISTRY_CASE, ("expected", "ECHO-31")),
        ):
            case = json.loads(path.read_text(encoding="utf-8"))
            prompt = safe._build_model_prompt(case)
            parsed = json.loads(prompt.split("\n\n", 1)[1])
            self.assertNotIn("expected", parsed)
            for literal in forbidden:
                self.assertNotIn(literal, prompt)
            self.assertEqual(set(parsed) - {"schema_version"}, set(safe._MODEL_FIELDS))

    def test_generic_parser_accepts_alternate_field_and_object_value(self):
        value, error = safe._parse_generic_object(
            '{"result":{"ticket":"T-204","status":"verified"},'
            '"actions":["return_supplied_result","stop"]}'
        )
        self.assertIsNone(error)
        self.assertEqual(value["result"]["ticket"], "T-204")

    def test_generic_parser_rejects_duplicate_keys(self):
        value, error = safe._parse_generic_object('{"result":1,"result":2}')
        self.assertIsNone(value)
        self.assertEqual(error, "invalid_json:ValueError")

    def test_safe_model_boundary_restores_builder_and_parser(self):
        original_builder = safe.base.canary._build_prompt
        original_parser = safe.base.canary._parse_output
        with safe._safe_model_boundary():
            self.assertIs(safe.base.canary._build_prompt, safe._build_model_prompt)
            self.assertIs(safe.base.canary._parse_output, safe._parse_generic_object)
        self.assertIs(safe.base.canary._build_prompt, original_builder)
        self.assertIs(safe.base.canary._parse_output, original_parser)

    def test_loopback_proxy_captures_json_and_redacts_authorization(self):
        captured_upstream = []

        def fake_urlopen(request, timeout):
            captured_upstream.append((request.full_url, timeout, request.data))
            return _FakeResponse(b'{"id":"reply","choices":[]}')

        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "wire.jsonl"
            with mock.patch.object(proxy_module.urllib.request, "urlopen", side_effect=fake_urlopen):
                with proxy_module.LoopbackWireProxy(trace) as proxy:
                    host_port = proxy.base_url.removeprefix("http://").split("/", 1)[0]
                    host, port_text = host_port.split(":", 1)
                    connection = http.client.HTTPConnection(host, int(port_text), timeout=10)
                    payload = {
                        "model": "candidate-alias",
                        "messages": [{"role": "user", "content": "task"}],
                        "tools": [{"type": "function", "function": {"name": "vault_fetch"}}],
                    }
                    body = json.dumps(payload).encode("utf-8")
                    connection.request(
                        "POST",
                        "/v1/chat/completions",
                        body=body,
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": "Bearer local-only-not-secret",
                        },
                    )
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertEqual(json.loads(response.read()), {"id": "reply", "choices": []})
                    connection.close()

            records = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records), 1)
            record = records[0]
            self.assertEqual(record["phase"], "initial_decision")
            self.assertEqual(record["request"]["json"], payload)
            authorization = next(
                value
                for key, value in record["request"]["headers"].items()
                if key.lower() == "authorization"
            )
            self.assertEqual(authorization, "<redacted>")
            self.assertEqual(captured_upstream[0][0], "http://127.0.0.1:11434/v1/chat/completions")
            self.assertEqual(captured_upstream[0][2], body)

    def test_disabled_s2_plan_and_safe_boundary_validate(self):
        plan, marker, candidates, cases = validator.validate_execution(require_enabled=False)
        self.assertFalse(marker["enabled"])
        self.assertEqual(plan["counts"]["total_runs"], 36)
        self.assertEqual(len(candidates), 3)
        self.assertEqual(len(cases), 4)
        payload = safe_validator.validate()
        self.assertEqual(payload["status"], "ready")
        self.assertTrue(payload["model_prompt_allowlisted"])
        self.assertTrue(payload["safe_runner_authoritative"])

    def test_three_batches_select_each_candidate_once(self):
        _, _, candidates, _ = validator.validate_execution(require_enabled=False)
        selected = [validator.select_batch(candidates, index)[0]["candidate_id"] for index in range(3)]
        self.assertEqual(
            selected,
            ["gemma4-12b-it-qat", "qwythos-mythos-9b", "qwythos-hermes-64k"],
        )


if __name__ == "__main__":
    unittest.main()

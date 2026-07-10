from __future__ import annotations

import unittest

from bench.contracts import (
    ContractError,
    extract_final,
    validate_candidate_manifest,
    validate_manifest,
)


class ExtractFinalTests(unittest.TestCase):
    def test_extracts_last_final_and_strips_think(self) -> None:
        raw = "<think>private reasoning</think>\nFINAL: first\nnoise\nFINAL: accepted answer"
        self.assertEqual(extract_final(raw), "accepted answer")

    def test_rejects_missing_marker(self) -> None:
        with self.assertRaisesRegex(ContractError, "missing required FINAL"):
            extract_final("plain answer without a contract marker")

    def test_rejects_empty_final(self) -> None:
        with self.assertRaisesRegex(ContractError, "no content"):
            extract_final("FINAL:   \n")


class ManifestTests(unittest.TestCase):
    def valid_manifest(self) -> dict[str, object]:
        return {
            "schema_version": "bench.run.v1",
            "run_id": "run-001",
            "created_at_utc": "2026-07-10T00:00:00Z",
            "lane": "direct",
            "candidate": "example-model",
            "case_id": "case-001",
            "repetition": 1,
            "status": "preliminary",
            "environment": {},
            "artifacts": {},
        }

    def test_accepts_valid_manifest(self) -> None:
        validate_manifest(self.valid_manifest())

    def test_rejects_missing_field(self) -> None:
        manifest = self.valid_manifest()
        del manifest["candidate"]
        with self.assertRaisesRegex(ContractError, "candidate"):
            validate_manifest(manifest)

    def test_rejects_unknown_lane(self) -> None:
        manifest = self.valid_manifest()
        manifest["lane"] = "magic"
        with self.assertRaisesRegex(ContractError, "unsupported lane"):
            validate_manifest(manifest)

    def test_rejects_zero_repetition(self) -> None:
        manifest = self.valid_manifest()
        manifest["repetition"] = 0
        with self.assertRaisesRegex(ContractError, "repetition"):
            validate_manifest(manifest)


class CandidateManifestTests(unittest.TestCase):
    def valid_manifest(self) -> dict[str, object]:
        return {
            "schema_version": "bench.candidates.v1",
            "mapping_status": "preliminary",
            "observed_at_utc": "2026-07-10T09:21:53Z",
            "evidence_note": "Captured by local-only preflight.",
            "candidates": [
                {
                    "candidate_id": "candidate-a",
                    "family": "example",
                    "model_tag": "example:latest",
                    "digest": "a" * 64,
                    "expected_roles": ["worker", "critic"],
                    "initial_matrix": True,
                    "enabled": True,
                }
            ],
        }

    def test_accepts_valid_candidate_manifest(self) -> None:
        validate_candidate_manifest(self.valid_manifest())

    def test_rejects_duplicate_candidate_id(self) -> None:
        manifest = self.valid_manifest()
        candidates = manifest["candidates"]
        assert isinstance(candidates, list)
        duplicate = dict(candidates[0])
        duplicate["model_tag"] = "example:second"
        candidates.append(duplicate)

        with self.assertRaisesRegex(ContractError, "duplicate candidate_id"):
            validate_candidate_manifest(manifest)

    def test_rejects_malformed_digest(self) -> None:
        manifest = self.valid_manifest()
        candidates = manifest["candidates"]
        assert isinstance(candidates, list)
        candidates[0]["digest"] = "not-a-digest"

        with self.assertRaisesRegex(ContractError, "64 lowercase hex"):
            validate_candidate_manifest(manifest)

    def test_rejects_non_boolean_enablement(self) -> None:
        manifest = self.valid_manifest()
        candidates = manifest["candidates"]
        assert isinstance(candidates, list)
        candidates[0]["enabled"] = "true"

        with self.assertRaisesRegex(ContractError, "enabled must be boolean"):
            validate_candidate_manifest(manifest)

    def test_rejects_duplicate_roles(self) -> None:
        manifest = self.valid_manifest()
        candidates = manifest["candidates"]
        assert isinstance(candidates, list)
        candidates[0]["expected_roles"] = ["worker", "worker"]

        with self.assertRaisesRegex(ContractError, "expected_roles must be unique"):
            validate_candidate_manifest(manifest)


if __name__ == "__main__":
    unittest.main()

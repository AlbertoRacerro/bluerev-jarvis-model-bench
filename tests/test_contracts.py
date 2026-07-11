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
            "environment": {"runner": "local"},
            "artifacts": {
                "artifact.json": {
                    "path": "artifact.json",
                    "sha256": "a" * 64,
                }
            },
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

    def test_rejects_boolean_repetition(self) -> None:
        manifest = self.valid_manifest()
        manifest["repetition"] = True
        with self.assertRaisesRegex(ContractError, "repetition"):
            validate_manifest(manifest)

    def test_rejects_empty_artifacts(self) -> None:
        manifest = self.valid_manifest()
        manifest["artifacts"] = {}
        with self.assertRaisesRegex(ContractError, "non-empty"):
            validate_manifest(manifest)

    def test_rejects_artifact_path_drift(self) -> None:
        manifest = self.valid_manifest()
        manifest["artifacts"]["artifact.json"]["path"] = "other.json"
        with self.assertRaisesRegex(ContractError, "must equal"):
            validate_manifest(manifest)

    def test_rejects_unsafe_artifact_path(self) -> None:
        manifest = self.valid_manifest()
        manifest["artifacts"] = {
            "../artifact.json": {
                "path": "../artifact.json",
                "sha256": "a" * 64,
            }
        }
        with self.assertRaisesRegex(ContractError, "safe relative"):
            validate_manifest(manifest)

    def test_rejects_malformed_artifact_digest(self) -> None:
        manifest = self.valid_manifest()
        manifest["artifacts"]["artifact.json"]["sha256"] = "bad"
        with self.assertRaisesRegex(ContractError, "64 lowercase hex"):
            validate_manifest(manifest)

    def test_rejects_invalid_timestamp(self) -> None:
        manifest = self.valid_manifest()
        manifest["created_at_utc"] = "not-a-time"
        with self.assertRaisesRegex(ContractError, "RFC3339"):
            validate_manifest(manifest)


class CandidateManifestTests(unittest.TestCase):
    def valid_manifest(self) -> dict[str, object]:
        return {
            "schema_version": "bench.candidates.v1",
            "mapping_status": "validated",
            "observed_at_utc": "2026-07-10T14:00:00Z",
            "evidence_note": "Captured by trusted local-only preflight.",
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

    def candidate(self, manifest: dict[str, object]) -> dict[str, object]:
        candidates = manifest["candidates"]
        assert isinstance(candidates, list)
        candidate = candidates[0]
        assert isinstance(candidate, dict)
        return candidate

    def test_accepts_valid_candidate_manifest(self) -> None:
        validate_candidate_manifest(self.valid_manifest())

    def test_rejects_non_validated_mapping_status(self) -> None:
        for status in ("preliminary", "invalid", "superseded"):
            with self.subTest(status=status):
                manifest = self.valid_manifest()
                manifest["mapping_status"] = status
                with self.assertRaisesRegex(ContractError, "must be validated"):
                    validate_candidate_manifest(manifest)

    def test_rejects_extra_manifest_field(self) -> None:
        manifest = self.valid_manifest()
        manifest["unexpected"] = True
        with self.assertRaisesRegex(ContractError, "unsupported fields"):
            validate_candidate_manifest(manifest)

    def test_rejects_extra_candidate_field(self) -> None:
        manifest = self.valid_manifest()
        self.candidate(manifest)["unexpected"] = True
        with self.assertRaisesRegex(ContractError, "candidate 0 has unsupported fields"):
            validate_candidate_manifest(manifest)

    def test_rejects_non_json_candidate_sequence(self) -> None:
        manifest = self.valid_manifest()
        candidates = manifest["candidates"]
        assert isinstance(candidates, list)
        manifest["candidates"] = tuple(candidates)
        with self.assertRaisesRegex(ContractError, "JSON array"):
            validate_candidate_manifest(manifest)

    def test_rejects_duplicate_candidate_id(self) -> None:
        manifest = self.valid_manifest()
        candidates = manifest["candidates"]
        assert isinstance(candidates, list)
        duplicate = dict(self.candidate(manifest))
        duplicate["model_tag"] = "example:second"
        candidates.append(duplicate)
        with self.assertRaisesRegex(ContractError, "duplicate candidate_id"):
            validate_candidate_manifest(manifest)

    def test_rejects_duplicate_model_tag(self) -> None:
        manifest = self.valid_manifest()
        candidates = manifest["candidates"]
        assert isinstance(candidates, list)
        duplicate = dict(self.candidate(manifest))
        duplicate["candidate_id"] = "candidate-b"
        candidates.append(duplicate)
        with self.assertRaisesRegex(ContractError, "duplicate model_tag"):
            validate_candidate_manifest(manifest)

    def test_rejects_malformed_digest(self) -> None:
        manifest = self.valid_manifest()
        self.candidate(manifest)["digest"] = "not-a-digest"
        with self.assertRaisesRegex(ContractError, "64 lowercase hex"):
            validate_candidate_manifest(manifest)

    def test_rejects_non_boolean_enablement(self) -> None:
        manifest = self.valid_manifest()
        self.candidate(manifest)["enabled"] = "true"
        with self.assertRaisesRegex(ContractError, "enabled must be boolean"):
            validate_candidate_manifest(manifest)

    def test_rejects_duplicate_roles(self) -> None:
        manifest = self.valid_manifest()
        self.candidate(manifest)["expected_roles"] = ["worker", "worker"]
        with self.assertRaisesRegex(ContractError, "expected_roles must be unique"):
            validate_candidate_manifest(manifest)


if __name__ == "__main__":
    unittest.main()

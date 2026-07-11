from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_h2_context_plan import H2PlanError, build_plan, run


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class H2ContextPlanTests(unittest.TestCase):
    def make_fixture(
        self,
        root: Path,
        *,
        primary: list[dict[str, object]] | None = None,
    ) -> None:
        primary = primary if primary is not None else [
            {
                "name": "model-a",
                "digest": "a" * 64,
                "classification": "full_vram",
                "residency_ratio": 1.0,
            }
        ]
        report = {"schema_version": "bench.model-residency.v1"}
        residency_manifest = {
            "schema_version": "bench.model-residency-manifest.v1"
        }
        write_json(root / "report.json", report)
        write_json(root / "manifest.json", residency_manifest)
        shortlist = {
            "schema_version": "bench.model-shortlist.v1",
            "status": "ready" if primary else "blocked_no_full_vram_models",
            "profile": {
                "name": "h1-4k-residency",
                "num_ctx": 4096,
                "num_predict": 1,
                "temperature": 0,
                "seed": 4242,
                "keep_alive": "5m",
                "request_timeout_seconds": 420,
            },
            "source": {
                "report_sha256": digest(root / "report.json"),
                "residency_manifest_sha256": digest(root / "manifest.json"),
                "workflow": {
                    "run_id": "1",
                    "run_attempt": "1",
                    "event_name": "workflow_dispatch",
                    "sha": "abc",
                    "ref": "refs/heads/main",
                },
            },
            "counts": {
                "model_results": len(primary),
                "primary_h2": len(primary),
                "secondary_partial_vram": 0,
                "deferred": 0,
            },
            "primary_h2": primary,
            "secondary_partial_vram": [],
            "deferred": [],
        }
        write_json(root / "shortlist.json", shortlist)
        (root / "shortlist.md").write_text("# shortlist\n", encoding="utf-8")
        write_json(
            root / "shortlist-manifest.json",
            {
                "schema_version": "bench.model-shortlist-manifest.v1",
                "artifacts": {
                    name: {
                        "sha256": digest(root / name),
                        "size_bytes": (root / name).stat().st_size,
                    }
                    for name in (
                        "report.json",
                        "manifest.json",
                        "shortlist.json",
                        "shortlist.md",
                    )
                },
            },
        )

    def test_builds_sequential_local_only_16k_32k_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_fixture(root)
            plan = run(root, digest(root / "shortlist-manifest.json"))
            self.assertEqual(plan["profiles"], [16384, 32768])
            self.assertEqual(
                plan["counts"],
                {"candidates": 1, "context_probes": 2},
            )
            self.assertEqual(plan["execution_policy"]["max_parallel_models"], 1)
            self.assertFalse(
                plan["execution_policy"]["external_providers_allowed"]
            )
            self.assertEqual(
                [item["num_ctx"] for item in plan["cases"][0]["contexts"]],
                [16384, 32768],
            )
            self.assertTrue(plan["cases"][0]["contexts"][0]["required"])
            self.assertFalse(plan["cases"][0]["contexts"][1]["required"])
            manifest = json.loads(
                (root / "h2-context-plan-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                set(manifest["artifacts"]),
                {
                    "report.json",
                    "manifest.json",
                    "shortlist.json",
                    "shortlist-manifest.json",
                    "h2-context-plan.json",
                },
            )

    def test_blocks_without_full_vram_models(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_fixture(root, primary=[])
            plan = build_plan(root, digest(root / "shortlist-manifest.json"))
            self.assertEqual(plan["status"], "blocked_no_full_vram_models")
            self.assertEqual(plan["cases"], [])

    def test_rejects_tampered_shortlist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_fixture(root)
            value = json.loads(
                (root / "shortlist.json").read_text(encoding="utf-8")
            )
            value["primary_h2"][0]["name"] = "tampered"
            write_json(root / "shortlist.json", value)
            with self.assertRaisesRegex(H2PlanError, "digest mismatch"):
                build_plan(root, digest(root / "shortlist-manifest.json"))

    def test_rejects_manifest_and_shortlist_rewritten_together(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_fixture(root)
            trusted_manifest_digest = digest(root / "shortlist-manifest.json")
            value = json.loads(
                (root / "shortlist.json").read_text(encoding="utf-8")
            )
            value["primary_h2"][0]["name"] = "tampered"
            write_json(root / "shortlist.json", value)
            manifest = json.loads(
                (root / "shortlist-manifest.json").read_text(encoding="utf-8")
            )
            manifest["artifacts"]["shortlist.json"] = {
                "sha256": digest(root / "shortlist.json"),
                "size_bytes": (root / "shortlist.json").stat().st_size,
            }
            write_json(root / "shortlist-manifest.json", manifest)
            with self.assertRaisesRegex(H2PlanError, "root digest mismatch"):
                build_plan(root, trusted_manifest_digest)

    def test_rejects_incomplete_manifest_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_fixture(root)
            manifest = json.loads(
                (root / "shortlist-manifest.json").read_text(encoding="utf-8")
            )
            del manifest["artifacts"]["report.json"]
            write_json(root / "shortlist-manifest.json", manifest)
            with self.assertRaisesRegex(H2PlanError, "inventory mismatch"):
                build_plan(root, digest(root / "shortlist-manifest.json"))

    def test_rejects_source_digest_not_matching_bound_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_fixture(root)
            shortlist = json.loads(
                (root / "shortlist.json").read_text(encoding="utf-8")
            )
            shortlist["source"]["report_sha256"] = "f" * 64
            write_json(root / "shortlist.json", shortlist)
            manifest = json.loads(
                (root / "shortlist-manifest.json").read_text(encoding="utf-8")
            )
            manifest["artifacts"]["shortlist.json"] = {
                "sha256": digest(root / "shortlist.json"),
                "size_bytes": (root / "shortlist.json").stat().st_size,
            }
            write_json(root / "shortlist-manifest.json", manifest)
            with self.assertRaisesRegex(H2PlanError, "report source digest mismatch"):
                build_plan(root, digest(root / "shortlist-manifest.json"))

    def test_rejects_partial_vram_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_fixture(
                root,
                primary=[
                    {
                        "name": "partial",
                        "digest": "b" * 64,
                        "classification": "partial_vram",
                    }
                ],
            )
            with self.assertRaisesRegex(H2PlanError, "not a full_vram candidate"):
                build_plan(root, digest(root / "shortlist-manifest.json"))

    def test_rejects_duplicate_candidate_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            duplicate = {
                "name": "model-a",
                "digest": "a" * 64,
                "classification": "full_vram",
            }
            self.make_fixture(root, primary=[duplicate, dict(duplicate)])
            with self.assertRaisesRegex(H2PlanError, "not unique"):
                build_plan(root, digest(root / "shortlist-manifest.json"))


if __name__ == "__main__":
    unittest.main()

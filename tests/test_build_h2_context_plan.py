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
                "digest": "sha256:model-a",
                "classification": "full_vram",
                "residency_ratio": 1.0,
            }
        ]
        shortlist = {
            "schema_version": "bench.model-shortlist.v1",
            "status": "ready" if primary else "blocked_no_full_vram_models",
            "source": {
                "report_sha256": "a" * 64,
                "residency_manifest_sha256": "b" * 64,
            },
            "primary_h2": primary,
            "secondary_partial_vram": [],
        }
        write_json(root / "shortlist.json", shortlist)
        write_json(
            root / "shortlist-manifest.json",
            {
                "schema_version": "bench.model-shortlist-manifest.v1",
                "artifacts": {
                    "shortlist.json": {
                        "sha256": digest(root / "shortlist.json"),
                        "size_bytes": (root / "shortlist.json").stat().st_size,
                    }
                },
            },
        )

    def test_builds_sequential_local_only_16k_32k_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_fixture(root)
            plan = run(root)
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

    def test_blocks_without_full_vram_models(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_fixture(root, primary=[])
            plan = build_plan(root)
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
                build_plan(root)

    def test_rejects_partial_vram_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_fixture(
                root,
                primary=[
                    {
                        "name": "partial",
                        "digest": "sha256:partial",
                        "classification": "partial_vram",
                    }
                ],
            )
            with self.assertRaisesRegex(
                H2PlanError,
                "not a full-VRAM candidate",
            ):
                build_plan(root)

    def test_rejects_duplicate_candidate_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            duplicate = {
                "name": "model-a",
                "digest": "sha256:model-a",
                "classification": "full_vram",
            }
            self.make_fixture(root, primary=[duplicate, dict(duplicate)])
            with self.assertRaisesRegex(H2PlanError, "not unique"):
                build_plan(root)


if __name__ == "__main__":
    unittest.main()

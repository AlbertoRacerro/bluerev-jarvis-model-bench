from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

SCRIPT = Path(__file__).parents[1] / "scripts" / "build_context_qualification_plan.py"
SPEC = importlib.util.spec_from_file_location("build_context_qualification_plan", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_source(root: Path, *, ready: bool = True) -> Path:
    source = root / "source"
    source.mkdir()
    report = {"schema_version": "bench.model-residency.v1", "models": []}
    residency_manifest = {
        "schema_version": "bench.model-residency-manifest.v1",
        "artifacts": {},
    }
    write_json(source / "report.json", report)
    write_json(source / "manifest.json", residency_manifest)
    primary = (
        [
            {
                "name": "model-b:latest",
                "digest": "b" * 64,
                "classification": "full_vram",
                "residency_ratio": 0.995,
            },
            {
                "name": "Model-A:latest",
                "digest": "a" * 64,
                "classification": "full_vram",
                "residency_ratio": 1.0,
            },
        ]
        if ready
        else []
    )
    shortlist = {
        "schema_version": "bench.model-shortlist.v1",
        "status": "ready" if ready else "blocked_no_full_vram_models",
        "primary_h2": primary,
        "secondary_partial_vram": [
            {
                "name": "partial:latest",
                "digest": "c" * 64,
                "classification": "partial_vram",
                "residency_ratio": 0.75,
            }
        ],
        "deferred": [],
        "source": {
            "report_sha256": digest(source / "report.json"),
            "residency_manifest_sha256": digest(source / "manifest.json"),
            "workflow": "Local model residency qualification",
        },
    }
    write_json(source / "shortlist.json", shortlist)
    (source / "shortlist.md").write_text("# shortlist\n", encoding="utf-8")
    artifacts = {}
    for name in ("report.json", "manifest.json", "shortlist.json", "shortlist.md"):
        path = source / name
        artifacts[name] = {"sha256": digest(path), "size_bytes": path.stat().st_size}
    write_json(
        source / "shortlist-manifest.json",
        {
            "schema_version": "bench.model-shortlist-manifest.v1",
            "artifacts": artifacts,
        },
    )
    return source


class ContextPlanTests(unittest.TestCase):
    def test_ready_plan_is_deterministic_sequential_and_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = make_source(root)
            output = root / "out"
            first = MODULE.run(source, output)
            first_bytes = (output / "h2-plan.json").read_bytes()
            second = MODULE.run(source, output)
            self.assertEqual(first, second)
            self.assertEqual(first_bytes, (output / "h2-plan.json").read_bytes())
            self.assertEqual(first["status"], "ready")
            self.assertEqual(first["counts"], {"primary_models": 2, "planned_jobs": 4})
            self.assertTrue(first["execution_policy"]["local_only"])
            self.assertTrue(first["execution_policy"]["sequential"])
            self.assertEqual(first["execution_policy"]["max_concurrent_models"], 1)
            self.assertEqual(
                [job["model"]["name"] for job in first["jobs"]],
                ["Model-A:latest", "Model-A:latest", "model-b:latest", "model-b:latest"],
            )
            self.assertEqual([job["profile"]["num_ctx"] for job in first["jobs"]], [16384, 32768, 16384, 32768])
            self.assertEqual(first["jobs"][0]["admission"]["mode"], "required")
            self.assertEqual(first["jobs"][1]["admission"]["mode"], "after_prior_success")
            self.assertEqual(
                first["jobs"][1]["admission"]["depends_on_job_id"],
                first["jobs"][0]["job_id"],
            )
            self.assertNotIn("partial:latest", json.dumps(first))
            self.assertEqual(first["source"]["shortlist_sha256"], digest(source / "shortlist.json"))

    def test_blocked_shortlist_produces_no_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = make_source(root, ready=False)
            plan = MODULE.run(source, root / "out")
            self.assertEqual(plan["status"], "blocked_no_full_vram_models")
            self.assertEqual(plan["jobs"], [])
            self.assertEqual(plan["counts"], {"primary_models": 0, "planned_jobs": 0})

    def test_tampered_shortlist_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = make_source(root)
            with (source / "shortlist.json").open("a", encoding="utf-8") as handle:
                handle.write(" ")
            with self.assertRaisesRegex(MODULE.PlanError, "digest mismatch"):
                MODULE.run(source, root / "out")

    def test_report_binding_mismatch_is_rejected_even_with_rebuilt_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = make_source(root)
            write_json(source / "report.json", {"schema_version": "tampered"})
            shortlist_manifest = json.loads((source / "shortlist-manifest.json").read_text(encoding="utf-8"))
            report_meta = shortlist_manifest["artifacts"]["report.json"]
            report_meta["sha256"] = digest(source / "report.json")
            report_meta["size_bytes"] = (source / "report.json").stat().st_size
            write_json(source / "shortlist-manifest.json", shortlist_manifest)
            with self.assertRaisesRegex(MODULE.PlanError, "report binding mismatch"):
                MODULE.run(source, root / "out")

    def test_partial_model_cannot_enter_primary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = make_source(root)
            shortlist = json.loads((source / "shortlist.json").read_text(encoding="utf-8"))
            shortlist["primary_h2"][0]["classification"] = "partial_vram"
            write_json(source / "shortlist.json", shortlist)
            manifest = json.loads((source / "shortlist-manifest.json").read_text(encoding="utf-8"))
            meta = manifest["artifacts"]["shortlist.json"]
            meta["sha256"] = digest(source / "shortlist.json")
            meta["size_bytes"] = (source / "shortlist.json").stat().st_size
            write_json(source / "shortlist-manifest.json", manifest)
            with self.assertRaisesRegex(MODULE.PlanError, "not full_vram"):
                MODULE.run(source, root / "out")

    def test_duplicate_model_identity_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = make_source(root)
            shortlist = json.loads((source / "shortlist.json").read_text(encoding="utf-8"))
            shortlist["primary_h2"][1]["digest"] = shortlist["primary_h2"][0]["digest"]
            write_json(source / "shortlist.json", shortlist)
            manifest = json.loads((source / "shortlist-manifest.json").read_text(encoding="utf-8"))
            meta = manifest["artifacts"]["shortlist.json"]
            meta["sha256"] = digest(source / "shortlist.json")
            meta["size_bytes"] = (source / "shortlist.json").stat().st_size
            write_json(source / "shortlist-manifest.json", manifest)
            with self.assertRaisesRegex(MODULE.PlanError, "not unique"):
                MODULE.run(source, root / "out")

    def test_manifest_inventory_must_be_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = make_source(root)
            manifest = json.loads((source / "shortlist-manifest.json").read_text(encoding="utf-8"))
            manifest["artifacts"]["unexpected.json"] = {"sha256": "0" * 64, "size_bytes": 0}
            write_json(source / "shortlist-manifest.json", manifest)
            with self.assertRaisesRegex(MODULE.PlanError, "inventory mismatch"):
                MODULE.run(source, root / "out")


if __name__ == "__main__":
    unittest.main()

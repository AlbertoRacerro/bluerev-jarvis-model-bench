from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from scripts import probe_h3_context as h3

ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/"fixtures"/"h3"/"h2-primary-32k-plan.json"
SUMMARY=ROOT/"reports"/"H2-PRIMARY-16K"/"summary.json"
MANIFEST=ROOT/"reports"/"H2-PRIMARY-16K"/"manifest.json"

class H3ContextProbeTests(unittest.TestCase):
    def test_validates_exact_bound_plan_and_summary(self):
        candidates=h3.validate_plan(PLAN,SUMMARY,MANIFEST,h3.EXPECTED_PLAN_SHA256)
        self.assertEqual(len(candidates),10); self.assertEqual(candidates[0]["name"],"gemma4:12b-it-qat"); self.assertEqual(candidates[-1]["name"],"qwythos-hermes-safe:latest")
    def test_rejects_tampered_plan_before_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan=Path(tmp)/"plan.json"; shutil.copyfile(PLAN,plan); value=json.loads(plan.read_text(encoding="utf-8")); value["profile"]["num_ctx"]=65536; plan.write_text(json.dumps(value,sort_keys=True),encoding="utf-8")
            with self.assertRaisesRegex(h3.H3ProbeError,"plan digest mismatch"): h3.validate_plan(plan,SUMMARY,MANIFEST,h3.EXPECTED_PLAN_SHA256)
    def test_selects_exact_two_model_batches(self):
        candidates=[{"name":f"model-{i}","digest":f"{i:x}"*64} for i in range(10)]; selected,selection=h3.select_candidates(candidates,batch_index=3)
        self.assertEqual([item["name"] for item in selected],["model-6","model-7"]); self.assertEqual(selection["start"],6); self.assertEqual(selection["end"],8)
        with self.assertRaisesRegex(h3.H3ProbeError,"outside"): h3.select_candidates(candidates,batch_index=5)
    def test_classifies_full_vram_offload_and_context_mismatch(self):
        response={"done":True}; full={"context_length":32768,"size":100,"size_vram":100}; partial={"context_length":32768,"size":100,"size_vram":75}; wrong={"context_length":16384,"size":100,"size_vram":100}
        self.assertEqual(h3._classify_result(response,full,None)[0],"qualified_32k"); self.assertEqual(h3._classify_result(response,partial,None)[:2],("cpu_offload",0.75)); self.assertEqual(h3._classify_result(response,wrong,None)[0],"context_mismatch")

if __name__=="__main__": unittest.main()

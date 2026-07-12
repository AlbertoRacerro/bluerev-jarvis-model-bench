from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from scripts.run_direct_smoke_v3_job import BATCH_COUNT,EXPECTED_PLAN_SHA256,EXPECTED_RUN_ID,FIRST_BATCH_ATTEMPT,h3_batch_index,h3_oneshot_enabled

class H3OneShotBridgeTests(unittest.TestCase):
    def marker(self,root:Path,**changes):
        value={"schema_version":"bench.h3-primary-oneshot.v1","enabled":True,"plan_sha256":EXPECTED_PLAN_SHA256,"first_batch_attempt":FIRST_BATCH_ATTEMPT,"batch_size":2,"batch_count":BATCH_COUNT}; value.update(changes); path=root/"marker.json"; path.write_text(json.dumps(value),encoding="utf-8"); return path
    def test_maps_only_attempts_11_through_15(self):
        for index in range(BATCH_COUNT):
            with mock.patch.dict(os.environ,{"GITHUB_RUN_ID":EXPECTED_RUN_ID,"GITHUB_RUN_ATTEMPT":str(FIRST_BATCH_ATTEMPT+index)},clear=False): self.assertEqual(h3_batch_index(),index)
        for attempt in (FIRST_BATCH_ATTEMPT-1,FIRST_BATCH_ATTEMPT+BATCH_COUNT):
            with mock.patch.dict(os.environ,{"GITHUB_RUN_ID":EXPECTED_RUN_ID,"GITHUB_RUN_ATTEMPT":str(attempt)},clear=False): self.assertIsNone(h3_batch_index())
    def test_requires_exact_run_and_marker_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); trusted={"GITHUB_RUN_ID":EXPECTED_RUN_ID,"GITHUB_RUN_ATTEMPT":str(FIRST_BATCH_ATTEMPT)}
            with mock.patch.dict(os.environ,trusted,clear=False):
                self.assertTrue(h3_oneshot_enabled(self.marker(root))); self.assertFalse(h3_oneshot_enabled(self.marker(root,extra=True)))
            with mock.patch.dict(os.environ,{"GITHUB_RUN_ID":"999","GITHUB_RUN_ATTEMPT":str(FIRST_BATCH_ATTEMPT)},clear=False): self.assertFalse(h3_oneshot_enabled(self.marker(root)))

if __name__=="__main__": unittest.main()

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import bench2r_hermes_runtime as runtime
from scripts import validate_bench2r_hermes_optimization as validator


class Bench2RHermesOptimizationTests(unittest.TestCase):
    def test_design_validator_passes_and_execution_remains_disabled(self):
        result = validator.validate()
        self.assertEqual(result["status"], "ready_for_review")
        self.assertFalse(result["execution_authorized"])
        self.assertEqual(result["candidate_count"], 8)

    def test_all_frozen_candidates_have_exactly_one_profile(self):
        document = runtime.load_profiles()
        profiles = document["candidate_profiles"]
        observed = [item["candidate_id"] for item in profiles]
        self.assertEqual(len(observed), 8)
        self.assertEqual(len(set(observed)), 8)
        self.assertEqual(set(observed), set(validator.EXPECTED_CANDIDATES))

    def test_non_greedy_models_keep_producer_safe_temperatures(self):
        for candidate_id in validator.NON_GREEDY_REQUIRED:
            profile = runtime.profile_by_candidate(candidate_id)
            self.assertGreater(profile["sampling"]["temperature"], 0.3)

    def test_documented_sampling_profiles_are_preserved(self):
        gemma = runtime.profile_by_candidate("gemma4-12b-it-qat")
        self.assertEqual(
            gemma["sampling"],
            {"temperature": 1.0, "top_k": 64, "top_p": 0.95},
        )
        qwythos = runtime.profile_by_candidate("qwythos-mythos-9b")
        self.assertEqual(
            qwythos["sampling"],
            {
                "repeat_penalty": 1.05,
                "temperature": 0.6,
                "top_k": 20,
                "top_p": 0.95,
            },
        )
        minicpm = runtime.profile_by_candidate("minicpm5-fable-1b-control")
        self.assertEqual(
            minicpm["sampling"],
            {"temperature": 0.9, "top_p": 0.95},
        )

    def test_seed_policy_is_reproducible_without_blanket_greedy_decoding(self):
        self.assertEqual(runtime.seed_for("tuning", 1), 42)
        self.assertEqual(
            [runtime.seed_for("admission", repetition) for repetition in range(1, 4)],
            [17, 42, 314159],
        )
        with self.assertRaises(runtime.Bench2ROptimizationError):
            runtime.seed_for("tuning", 2)

    def test_modelfile_contains_profile_sampling_seed_and_output_limit(self):
        profile = runtime.profile_by_candidate("qwable-9b-fable5")
        text = runtime.build_modelfile(profile, seed=42)
        self.assertIn(f"FROM {profile['model_tag']}\n", text)
        self.assertIn("PARAMETER num_ctx 65536\n", text)
        self.assertIn("PARAMETER temperature 0.6\n", text)
        self.assertIn("PARAMETER top_p 0.95\n", text)
        self.assertIn("PARAMETER top_k 20\n", text)
        self.assertIn("PARAMETER repeat_penalty 1.05\n", text)
        self.assertIn("PARAMETER seed 42\n", text)
        self.assertIn("PARAMETER num_predict 4096\n", text)

    def test_case_budget_controls_hermes_max_turns(self):
        stop_case = {"limits": {"max_model_calls": 1}}
        tools_case = {"limits": {"max_model_calls": 2}}
        profile = runtime.profile_by_candidate("gemma4-12b-it-qat")
        with tempfile.TemporaryDirectory() as directory:
            stop_config = runtime.render_hermes_config(
                profile=profile,
                case=stop_case,
                runtime_model="alias:model",
                workdir=Path(directory),
            )
            tools_config = runtime.render_hermes_config(
                profile=profile,
                case=tools_case,
                runtime_model="alias:model",
                workdir=Path(directory),
            )
        self.assertIn("max_turns: 1", stop_config)
        self.assertIn("max_turns: 2", tools_config)
        self.assertIn("save_trajectories: true", stop_config)
        self.assertIn("max_tokens: 4096", stop_config)
        self.assertNotIn("max_tokens: 256", stop_config)

    def test_skill_is_installed_in_isolated_home(self):
        with tempfile.TemporaryDirectory() as directory:
            target = runtime.install_bounded_skill(Path(directory))
            self.assertTrue(target.is_file())
            self.assertIn("Stop immediately", target.read_text(encoding="utf-8"))

    def test_skill_expansion_fails_closed_without_pinned_hermes(self):
        with mock.patch.dict(os.environ, {"HERMES_HOME": "isolated"}, clear=False):
            with mock.patch.dict("sys.modules", {"agent.skill_commands": None}):
                with self.assertRaises(runtime.Bench2ROptimizationError):
                    runtime.expand_bounded_skill_prompt("perform the bounded task")

    def test_skill_contains_no_original_benchmark_literals(self):
        text = validator.SKILL_PATH.read_text(encoding="utf-8").casefold()
        for literal in validator.FORBIDDEN_SKILL_LITERALS:
            self.assertNotIn(literal.casefold(), text)

    def test_marker_is_disabled(self):
        marker = json.loads(validator.MARKER_PATH.read_text(encoding="utf-8"))
        self.assertFalse(marker["enabled"])


if __name__ == "__main__":
    unittest.main()

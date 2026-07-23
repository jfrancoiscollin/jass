#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "jobs/templates/l3-conversion-2x2-g1-screen-v1.sh"
EVAL_RUNNER = ROOT / "jobs/templates/l3-conversion-2x2-eval-only-v1.sh"
PREPARED = ROOT / "jobs/prepared/l3-conversion-2x2-20260723"
WRAPPER = PREPARED / "cpx62-0922-l3-conversion-2x2-g1-screen-v1.sh"
RETRY_WRAPPER = PREPARED / "cpx62-0922bis-l3-conversion-2x2-g1-screen-v1.sh"
EVAL_WRAPPER = PREPARED / "cpx62-0922ter-l3-conversion-2x2-eval-only-v1.sh"
EVAL_RETRY_WRAPPER = PREPARED / "cpx62-0922quater-l3-conversion-2x2-eval-only-v1.sh"
HOME_EVAL_WRAPPER = PREPARED / "home-0928-l3-conversion-2x2-eval-only-v1.sh"
HOME_DISCOVERY_WRAPPER = (
    PREPARED / "home-0928quater-resume-cap-discovery-v1.sh"
)
RECIPE = PREPARED / "RECIPE.md"


class Conversion2x2JobTests(unittest.TestCase):
    def test_shell_contracts(self):
        for path in (
            RUNNER, EVAL_RUNNER, WRAPPER, RETRY_WRAPPER,
            EVAL_WRAPPER, EVAL_RETRY_WRAPPER, HOME_EVAL_WRAPPER,
            HOME_DISCOVERY_WRAPPER,
        ):
            subprocess.run(["bash", "-n", str(path)], check=True)

    def test_eval_only_recovery_is_pinned_and_does_not_retrain(self):
        text = EVAL_RUNNER.read_text(encoding="utf-8")
        for token in (
            "4992_matrix+512_balanced",
            "SOURCE_ATTEMPT_ID=\"20260723T152652Z-03f7e50a\"",
            "CAP1_POSITION_ID=\"9bc75f637c4afd1d9ccb4ed29ea854d784ef32dbb6f5d58f67eb917c40c9b69f\"",
            "CAP2_POSITION_ID=\"62faf128aaa80be9acc6b552c938074312cb46dcca5060f84caa1d4c0f797dfd\"",
            "observed_shards==expected_shards",
            "--salvage-manifest \"$CAP_MANIFEST\"",
            "derived_complete_2_ply_caps",
            "len(report[\"adjudications\"])==2",
            "--expected-state failed",
            "source-model-verification.json",
            "scientific-summary.json",
            "gen_patterns.py --emit --variant 8cf",
            "NO_AUTOMATIC_CONTINUATION",
        ):
            self.assertIn(token, text)
        self.assertNotIn("--gen-data-wdl", text)
        self.assertNotIn("train_stream.py", text)

    def test_fixed_sizing_and_pairwise_reuse(self):
        text = RUNNER.read_text(encoding="utf-8")
        for token in (
            "FRESH=500000",
            "NSHARDS_STANDARD=8",
            "TOP3_PRODUCERS=6",
            '[ "${#pids[@]}" -eq 14 ]',
            "GEN_SHARD_TIMEOUT=2700",
            "TOTAL_MATRIX_GAMES=$((384 * (1 + 4 * 3)))",
            "BALANCED_GAMES=128",
            "BOOTSTRAP=10000",
        ):
            self.assertIn(token, text)
        self.assertEqual(text.count("prepare_distribution standard"), 1)
        self.assertEqual(text.count("prepare_distribution top3"), 1)
        self.assertIn("train_cell standard_off standard off", text)
        self.assertIn("train_cell standard_on standard on", text)
        self.assertIn("train_cell top3_off top3 off", text)
        self.assertIn("train_cell top3_on top3 on", text)

    def test_fail_closed_runtime_and_provenance(self):
        text = RUNNER.read_text(encoding="utf-8")
        for token in (
            'RES="$W/RESULTS.txt"',
            'PROG="$W/PROGRESS.txt"',
            'wait "$pid"',
            "start_monitor",
            "restore_src",
            'git show "$EXPECTED_CODE_SHA:$source" > "$source"',
            'grep -q "g_emasks"',
            'grep -q "has_any_capture"',
            "df -Pm /root",
            "pool SHA mismatch",
            "proof SHA mismatch",
            "label_score_searches=0",
            "seed_frac=100%",
            'report["provenance"]["candidate_g4"][candidate]==model["sha256"]',
            "NO_AUTOMATIC_CONTINUATION",
            "PROMOTION_AUTHORIZED__FALSE",
            "TRAINING_CONTINUATION_AUTHORIZED__FALSE",
        ):
            self.assertIn(token, text)
        self.assertNotIn("\n  wait\n", text)

    def test_wrapper_and_recipe(self):
        wrapper = WRAPPER.read_text(encoding="utf-8")
        retry_wrapper = RETRY_WRAPPER.read_text(encoding="utf-8")
        recipe = RECIPE.read_text(encoding="utf-8")
        self.assertIn("cpx62-0922-l3-conversion-2x2-g1-screen-v1", wrapper)
        self.assertIn("cpx62-0922bis-l3-conversion-2x2-g1-screen-v1", retry_wrapper)
        eval_wrapper = EVAL_WRAPPER.read_text(encoding="utf-8")
        self.assertIn("cpx62-0922ter-l3-conversion-2x2-eval-only-v1", eval_wrapper)
        self.assertIn("timeout -k 60s 1800s", eval_wrapper)
        eval_retry_wrapper = EVAL_RETRY_WRAPPER.read_text(encoding="utf-8")
        self.assertIn(
            "cpx62-0922quater-l3-conversion-2x2-eval-only-v1",
            eval_retry_wrapper,
        )
        self.assertIn("timeout -k 60s 1800s", eval_retry_wrapper)
        home_eval_wrapper = HOME_EVAL_WRAPPER.read_text(encoding="utf-8")
        self.assertIn(
            "home-0928-l3-conversion-2x2-eval-only-v1",
            home_eval_wrapper,
        )
        self.assertIn("EXECUTION_PROFILE=home", home_eval_wrapper)
        self.assertIn("timeout -k 60s 7200s", home_eval_wrapper)
        eval_runner = EVAL_RUNNER.read_text(encoding="utf-8")
        self.assertIn('EXECUTION_PROFILE="${EXECUTION_PROFILE:-cpx62}"', eval_runner)
        self.assertIn("MIN_MEM_MB=14000", eval_runner)
        self.assertIn("MATRIX_SHARD_TIMEOUT=1800", eval_runner)
        self.assertIn("CAP_DISCOVERY_MODE", eval_runner)
        self.assertIn("matrix reuse:", eval_runner)
        self.assertIn("CONVERSION_2X2_CAP_DISCOVERY_READY", eval_runner)
        discovery_wrapper = HOME_DISCOVERY_WRAPPER.read_text(encoding="utf-8")
        self.assertIn("CAP_DISCOVERY_MODE=1", discovery_wrapper)
        self.assertIn("home-0928-l3-conversion-2x2-eval-only-v1", discovery_wrapper)
        self.assertIn("timeout -k 60s 5400s", discovery_wrapper)
        for prepared_wrapper in (wrapper, retry_wrapper):
            self.assertIn("timeout -k 60s 3600s", prepared_wrapper)
            self.assertIn("expected_duration: 30-45 min", prepared_wrapper)
        self.assertIn("500 000 records", recipe)
        self.assertIn("hard cap 60 min", recipe)
        self.assertIn("non promotable", recipe)


if __name__ == "__main__":
    unittest.main()

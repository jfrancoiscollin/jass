#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-hard-replay-large-source-v1.sh"


class HardReplayLargeSourceTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_fixes_volume_policy_and_home_parallelism(self):
        self.assertIn("SOURCE_RECORDS=${SOURCE_RECORDS:-40000000}", self.text)
        self.assertIn("SHARDS=${SHARDS:-6}", self.text)
        self.assertIn("requires exactly 40M records", self.text)
        self.assertIn("HOME contract requires six producers", self.text)
        self.assertIn("BASE_SEED=31415926", self.text)
        self.assertIn("PLAY_DEPTH=8", self.text)
        self.assertIn("LABEL_DEPTH=4", self.text)
        self.assertNotIn("--explore-topk", self.text)
        self.assertNotIn("--explore-margin", self.text)

    def test_reproduces_authenticated_uniform_generation_contract(self):
        self.assertIn('"$EXPECTED_PARENT_ATTEMPT"', self.text)
        self.assertIn('"$EXPECTED_PARENT_CODE_SHA"', self.text)
        self.assertIn("--wdl-zero-score", self.text)
        self.assertIn("--random-open-plies 8", self.text)
        self.assertIn('--explore-eps "$EXPLORE_EPS"', self.text)
        self.assertIn('--explore-decay-plies "$EXPLORE_DECAY"', self.text)
        self.assertIn("--split-selfplay-rngs", self.text)
        self.assertIn("--pair-openings --drop-plycap", self.text)
        self.assertIn("topk_ranked_plies", self.text)
        self.assertIn("UNIFORM unexpectedly ranked TOPK plies", self.text)

    def test_publishes_source_and_split_but_never_trains(self):
        self.assertIn("phase merge-split-and-canary", self.text)
        self.assertIn("tools/selfplay_frontier.py merge", self.text)
        self.assertIn("tools/selfplay_frontier.py split", self.text)
        self.assertIn("jobs/tools/assert_corpus_wdl.py", self.text)
        self.assertIn('"L3_PURE_HARD_REPLAY_LARGE_SOURCE_READY"', self.text)
        self.assertIn('"data_raw_sha256"', self.text)
        self.assertIn('"meta_raw_sha256"', self.text)
        self.assertIn('"promotion": False', self.text)
        self.assertIn('"automatic_next_job": None', self.text)
        self.assertNotIn("train_stream.py", self.text)
        self.assertNotIn("--dump-eval-features", self.text)

    def test_has_explicit_authorization_and_resource_guards(self):
        self.assertIn("FULL_RUN_APPROVED", self.text)
        self.assertIn("SCIENTIFIC_GO", self.text)
        self.assertIn("NO_AUTOMATIC_CONTINUATION", self.text)
        self.assertIn("need 20 GiB free", self.text)
        self.assertIn("producer-exits-uniform.txt", self.text)
        self.assertIn("uniform generation: $failed producer failures", self.text)


if __name__ == "__main__":
    unittest.main()

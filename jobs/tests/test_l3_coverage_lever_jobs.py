from __future__ import annotations

import ast
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TRAIN = ROOT / "jobs/templates/l3-pure-coverage-lever-ab-v1.sh"
READOUT = ROOT / "jobs/templates/l3-pure-coverage-lever-readout-v1.sh"
PREPARED = ROOT / "jobs/prepared/l3-pure-coverage-levers-20260728"


def embedded_python(path: Path) -> list[str]:
    return re.findall(
        r"<<'PY'\n(.*?)\nPY(?:\n|$)",
        path.read_text(encoding="utf-8"),
        re.S,
    )


class CoverageLeverJobTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.train = TRAIN.read_text(encoding="utf-8")
        cls.readout = READOUT.read_text(encoding="utf-8")

    def test_shell_and_embedded_python_parse(self):
        scripts = [TRAIN, READOUT, *sorted(PREPARED.glob("*.sh"))]
        for script in scripts:
            subprocess.run(["bash", "-n", str(script)], check=True)
        for script in (TRAIN, READOUT):
            blocks = embedded_python(script)
            self.assertGreater(len(blocks), 0)
            for index, block in enumerate(blocks):
                ast.parse(block, filename=f"{script}:heredoc-{index}")

    def test_training_modes_change_exactly_the_preregistered_lever(self):
        for lever in (
            "phase_sampling", "topk_softmax", "regret_restart",
            "opening_pool", "replay_ratio",
        ):
            self.assertIn(lever, self.train)
        for literal in (
            'RECORDS=${RECORDS:-2000000}',
            'FRESH_RECORDS=${FRESH_RECORDS:-1000000}',
            'SHARDS=${SHARDS:-6}',
            'PLAY_DEPTH=8',
            'PHASE_SAMPLE_SPEC="opening=8,midgame=4,late-mid=3,endgame=2,deep-eg=1"',
            'SOFTMAX_TEMPERATURE_CP=50',
            'REGRET_SEED_FRAC=20',
            'REGRET_MAX_POSITIONS=4000',
            '--explore-temperature-cp "$SOFTMAX_TEMPERATURE_CP"',
            '--sample-rate-by-phase "$PHASE_SAMPLE_SPEC"',
            '--seed-file "$W/regret-seeds.jnnw" --seed-frac "$REGRET_SEED_FRAC"',
            '--opening-pool "$W/master-openings.fen"',
            '--opening-pool-frac "$OPENING_POOL_FRAC"',
            '--source fresh "$W/$arm.fresh.jnnw" "$W/$arm.fresh.jsm" 1',
            '--source replay "$W/replay-source.jnnw" "$W/replay-source.jsm" 1',
            '"mix_ratio": "50/50"',
            '"mix_ratio_contrast": "100/0 vs 50/50"',
            'fresh_inputs_byte_identical_before_treatment_sampling',
        ):
            self.assertIn(literal, self.train)

    def test_home_generation_is_sequential_and_bounded_to_six_producers(self):
        self.assertIn('gen_arm control "$GEN_TIMEOUT_CONTROL"', self.train)
        self.assertIn('gen_arm treatment "$GEN_TIMEOUT_TREATMENT"', self.train)
        self.assertLess(
            self.train.index('gen_arm control "$GEN_TIMEOUT_CONTROL"'),
            self.train.index('gen_arm treatment "$GEN_TIMEOUT_TREATMENT"'),
        )
        self.assertNotIn('gen_arm control "$GEN_TIMEOUT_CONTROL" &', self.train)
        self.assertIn(
            '[ "$SHARDS" -eq 6 ] || die "causal contract requires 6 shards per arm"',
            self.train,
        )

    def test_prerequisite_parent_archive_and_activation_are_authenticated(self):
        for literal in (
            'EXPECTED_PREREQUISITE_JOB',
            '"L3_PURE_TOPK_CAUSAL_AB_ARMS_READY"',
            'EXPECTED_TOPK_READOUT_JOB',
            'TOPK readout lacks useful two-view power',
            'PARENT_MODEL_SHA',
            'REPLAY_SOURCE_DATA_GZ_SHA',
            'REPLAY_SOURCE_META_GZ_SHA',
            'replay source WDL canary failed',
            'MASTER_CORPUS_GIT_BLOB',
            'master corpus Git blob drift',
            'lever-activation.json',
            'treatment softmax never fired',
            'regret treatment contains no restart records',
            'treatment master opening pool never fired',
            'replay A/B fresh corpus drift',
        ):
            self.assertIn(literal, self.train)

    def test_training_never_promotes_or_schedules_the_readout(self):
        self.assertIn('"promotion_authorized": False', self.train)
        self.assertIn('"automatic_next_job": None', self.train)
        self.assertIn('AUTOMATIC_NEXT_JOB__NULL', self.train)
        self.assertNotIn("jobs/queue", self.train)

    def test_readout_is_fresh_paired_two_view_and_sums_raw_counts(self):
        for literal in (
            "NOPEN=1500",
            "OPENING_CANDIDATES=2000",
            "OPENING_SEED=27182818",
            "control.jnnw.gz",
            "treatment.jnnw.gz",
            "opening-exclusions.fen.gz",
            "disjoint_from_sampled_training_positions",
            "disjoint_from_external_opening_pool",
            "validate_opening_pool.py",
            "for view in q00 native",
            '--movetime "$MOVETIME"',
            '--pairs 1',
            'wins = sum(data["wins_a"]',
            'draws = sum(data["draws"]',
            'losses = sum(data["wins_b"]',
            '"promotion_authorized": False',
            '"automatic_next_job": None',
        ):
            self.assertIn(literal, self.readout)

    def test_prepared_wrappers_are_not_queue_entries_and_require_launch_approval(self):
        self.assertTrue(PREPARED.is_dir())
        for script in PREPARED.glob("*.sh"):
            self.assertNotIn("jobs/queue", str(script))
            if script.name == "master-corpus-preflight.sh":
                continue
            text = script.read_text(encoding="utf-8")
            self.assertIn("FULL_RUN_APPROVED", text)
            self.assertIn("SCIENTIFIC_GO", text)
            self.assertIn("NO_AUTOMATIC_CONTINUATION=1", text)
        recipe = (PREPARED / "RECIPE.md").read_text(encoding="utf-8")
        self.assertIn("prepared only", recipe)
        self.assertIn("None of these files is in `jobs/queue`", recipe)


if __name__ == "__main__":
    unittest.main()

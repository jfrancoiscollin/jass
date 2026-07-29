#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CATALOGUE = (
    ROOT / "jobs/templates/l3-pure-reverse-seed-catalogue-v1.sh"
)
PROBE = ROOT / "jobs/templates/l3-pure-reverse-seed-probe-v1.sh"
MAIN = ROOT / "src/main.cpp"


class ReverseSeedCatalogueTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = CATALOGUE.read_text(encoding="utf-8")

    def test_shell_syntax(self) -> None:
        subprocess.run(["bash", "-n", str(CATALOGUE)], check=True)

    def test_authenticates_source_and_hard_catalogue(self) -> None:
        for token in (
            "EXPECTED_HISTORY_JOB",
            "EXPECTED_HISTORY_ATTEMPT",
            "EXPECTED_HISTORY_CODE_SHA",
            "EXPECTED_HISTORY_AUTH_JOB",
            "EXPECTED_HISTORY_AUTH_ATTEMPT",
            "EXPECTED_HISTORY_AUTH_CODE_SHA",
            "EXPECTED_HARD_JOB",
            "EXPECTED_HARD_ATTEMPT",
            "EXPECTED_HARD_CODE_SHA",
            "EXPECTED_HARD_VERDICT",
            "SOURCE_TEMPORAL_ID",
        ):
            self.assertIn(token, self.text)
        self.assertIn("historical source identity/state mismatch", self.text)
        self.assertIn("HARD catalogue identity/certificate mismatch", self.text)
        self.assertIn(
            "HARD catalogue is not linked to the authenticated source",
            self.text,
        )
        self.assertIn(
            'cmp -s "$IN/source-split.json" "$ART/history-split.json"',
            self.text,
        )

    def test_matches_twice_and_publishes_bit_identical_catalogues(self) -> None:
        self.assertIn("match_once a", self.text)
        self.assertIn("match_once b", self.text)
        self.assertIn(
            "jobs/tools/l3_reverse_seed_matching.py",
            self.text,
        )
        for name in (
            "control-seeds.jnnw",
            "treatment-seeds.jnnw",
            "reverse-seed-matching.json",
        ):
            self.assertIn(name, self.text)
        self.assertIn(
            "reverse-seed matching is not bit deterministic",
            self.text,
        )
        self.assertLess(
            self.text.index("phase reproduce-historical-split"),
            self.text.index("phase match-catalogues-twice"),
        )

    def test_is_data_only_and_cannot_train_promote_or_continue(self) -> None:
        self.assertIn("DATA_ONLY_APPROVED", self.text)
        self.assertIn("SCIENTIFIC_GO", self.text)
        self.assertIn("NO_AUTOMATIC_CONTINUATION", self.text)
        self.assertIn('"training_authorized": False', self.text)
        self.assertIn('"promotion_authorized": False', self.text)
        self.assertIn('"automatic_next_job": None', self.text)
        self.assertIn('"external_teacher_inputs": 0', self.text)
        self.assertNotIn("--gen-data-wdl", self.text)
        self.assertNotIn("train_stream.py", self.text)
        self.assertNotIn("jass-runner", self.text)


class ReverseSeedProbeTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = PROBE.read_text(encoding="utf-8")
        cls.main = MAIN.read_text(encoding="utf-8")
        start = cls.main.index("int run_gen_data_wdl_mode")
        end = cls.main.index("int run_gen_tdleaf_mode", start)
        cls.generator = cls.main[start:end]

    def test_shell_syntax(self) -> None:
        subprocess.run(["bash", "-n", str(PROBE)], check=True)

    def test_probe_is_small_sequential_and_dose_blind(self) -> None:
        for token in (
            "PROBE_RECORDS=${PROBE_RECORDS:-200}",
            "PROBE_SEED_FRAC=${PROBE_SEED_FRAC:-100}",
            'cmake --build "$W/build" -j4',
            '[ "$(nproc)" -eq 16 ]',
            "--random-open-plies 0",
            "--split-selfplay-rngs",
            "--sample-initial",
            '"scientific_seed_frac": None',
            '"wdl_read_for_dose_choice": False',
        ):
            self.assertIn(token, self.text)
        self.assertLess(
            self.text.index("phase probe-control"),
            self.text.index("phase probe-treatment"),
        )
        self.assertEqual(
            self.text.count('"$MAXPLIES" "$BASE_SEED"'),
            1,
        )

    def test_probe_authenticates_all_inputs_and_never_promotes(self) -> None:
        for token in (
            "MATCHED_PREFIX",
            "EXPECTED_MATCHED_JOB",
            "EXPECTED_MATCHED_ATTEMPT",
            "EXPECTED_MATCHED_CODE_SHA",
            "L3_PURE_REVERSE_SEED_CATALOGUE_READY",
            "HARD_VERDICT_PREFIX",
            "EXPECTED_HARD_VERDICT",
            "PARENT_PREFIX",
            "EXPECTED_PARENT_CODE_SHA",
            "PARENT_MODEL_SHA",
        ):
            self.assertIn(token, self.text)
        self.assertIn("matched job certificate mismatch", self.text)
        self.assertIn('"training_authorized": False', self.text)
        self.assertIn('"promotion_authorized": False', self.text)
        self.assertIn('"automatic_next_job": None', self.text)
        self.assertNotIn("train_stream.py", self.text)

    def test_engine_fails_closed_and_reports_realised_seed_dose(self) -> None:
        for token in (
            'parse_int_or(argv[++i], -1)',
            "--seed-frac must be an integer in [0,100]",
            "--seed-frac requires --seed-file",
            "size/count mismatch",
            "invalid side-to-move",
            "seeded_openings=",
            "standard_openings=",
            "seed_catalogue_positions=",
            '<< " seed_frac=" << seed_frac',
        ):
            self.assertIn(token, self.generator)
        self.assertLess(
            self.generator.index("complete counted JNNW"),
            self.generator.index("std::ofstream f(out_path"),
        )


if __name__ == "__main__":
    unittest.main()

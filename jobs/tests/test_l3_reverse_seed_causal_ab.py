#!/usr/bin/env python3
from __future__ import annotations

import ast
import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-reverse-seed-causal-ab-v1.sh"


class ReverseSeedCausalAbTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_shell_syntax(self) -> None:
        subprocess.run(["bash", "-n", str(TEMPLATE)], check=True)

    def test_embedded_python_is_syntax_valid(self) -> None:
        blocks = re.findall(r"<<'PY'\n(.*?)\nPY", self.text, flags=re.S)
        self.assertGreaterEqual(len(blocks), 5)
        for block in blocks:
            ast.parse(block)

    def test_authenticates_probe_catalogues_and_parent(self) -> None:
        for token in (
            "EXPECTED_PROBE_READOUT_JOB",
            "DIAGNOSTIC_1084_OPERATIONAL_PROBE_AUTHENTICATED",
            "recommended_scientific_seed_frac",
            "dose_rule",
            "wdl_read",
            "EXPECTED_MATCHED_JOB",
            "same_index_ordered_strata",
            "control_selection_uses_wdl",
            "EXPECTED_PARENT_ATTEMPT",
            "PARENT_MODEL_SHA",
            '"authenticated_inputs": {',
            '"matching_manifest_sha256": sha256(matching_path)',
            '"control_seeds_sha256": sha256(inputs / "control-seeds.jnnw")',
            '"treatment_seeds_sha256": sha256(inputs / "treatment-seeds.jnnw")',
        ):
            self.assertIn(token, self.text)

    def test_only_root_catalogue_changes(self) -> None:
        for token in (
            "EXPERIMENT_STAGE=${EXPERIMENT_STAGE:-base2m}",
            "RECORDS=${RECORDS:-2000000}",
            "SHARDS=${SHARDS:-6}",
            "SEED_FRAC=${SEED_FRAC:-100}",
            "BASE_SEED=${BASE_SEED:-49979687}",
            "--random-open-plies 0",
            "--sample-initial",
            "--split-selfplay-rngs",
            "--seed-file \"$seed_file\"",
            'payload["only_factor"] = "seed_root_selection_policy"',
        ):
            self.assertIn(token, self.text)
        self.assertIn(
            'gen_arm control "$IN/control-seeds.jnnw"',
            self.text,
        )
        self.assertIn(
            'gen_arm treatment "$IN/treatment-seeds.jnnw"',
            self.text,
        )
        self.assertNotIn("--explore-topk", self.text)
        self.assertNotIn("--sample-weights", self.text)

    def test_resources_and_8cf_parent_load_are_guarded(self) -> None:
        for token in (
            '[ "$(nproc)" -eq 16 ]',
            "phase generate-control",
            "phase generate-treatment",
            "gen_patterns.py --emit --variant 8cf",
            '--gen-tdleaf "$W/PARENT.pjtw" 0 1',
            "producer-exits-$arm.txt",
            "labelhyg-$arm.txt",
            "full-run plycap rate exceeds probe dose gate",
        ):
            self.assertIn(token, self.text)
        self.assertLess(
            self.text.index("phase generate-control"),
            self.text.index("phase generate-treatment"),
        )

    def test_split_canaries_fits_and_certificate(self) -> None:
        for token in (
            "assert_corpus_wdl.py",
            "paired-split-check.json",
            "--target wdl --loss logistic --color-fold --tempo-stage",
            "--warm-start \"$W/PARENT.pjtw\"",
            "holdout_logloss_diagnostic_only",
            "L3_PURE_REVERSE_SEED_CAUSAL_AB_ARMS_READY",
            'say "$EXPERIMENT_VERDICT promotion=false automatic_next_job=null"',
            '"scientific_result": False',
            '"promotion_authorized": False',
            '"automatic_next_job": None',
            '"external_teacher_inputs": 0',
        ):
            self.assertIn(token, self.text)
        for forbidden in (
            "oracle",
            "--teacher",
            "--sample-weights",
            "reweight",
            "L3-IMBALANCE2",
        ):
            self.assertNotIn(forbidden, self.text)

    def test_scale4m_is_fixed_and_requires_positive_base2m(self) -> None:
        for token in (
            "scale4m)",
            "EXPECTED_RECORDS=4000000",
            "EXPECTED_BASE_SEED=74453917",
            'EXPERIMENT_VERDICT="$SCALE_VERDICT"',
            "L3_PURE_REVERSE_SEED_SCALE4M_CAUSAL_AB_ARMS_READY",
            "phase authenticate-positive-base2m",
            "EXPECTED_SCALE_ARMS_JOB",
            "EXPECTED_SCALE_READOUT_JOB",
            "EXPECTED_SCALE_CONTROL_SHA",
            "EXPECTED_SCALE_TREATMENT_SHA",
            "L3_PURE_REVERSE_SEED_ABOVE_MATCHED_CONTROL_IC95",
            "positive base2m readout certificate mismatch",
            '"positive_base2m"',
            '"generation_base_seed": base_seed',
        ):
            self.assertIn(token, self.text)
        self.assertIn(
            '[ "$RECORDS" -eq "$EXPECTED_RECORDS" ]',
            self.text,
        )
        self.assertIn(
            '[ "$BASE_SEED" -eq "$EXPECTED_BASE_SEED" ]',
            self.text,
        )


if __name__ == "__main__":
    unittest.main()

# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-context2-intervention-corpus-v1.sh"


class Context2InterventionCorpusTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = TEMPLATE.read_text(encoding="utf-8")

    def test_authenticates_plan_and_curriculum(self) -> None:
        for token in (
            "cpx62-1408-l3-context2-intervention-plan-v1",
            "20260818T182226Z-20fd6621",
            "cpx62-1341-jass-megacorpus-arm-d-fit-v1",
            "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1",
        ):
            self.assertIn(token, self.script)

    def test_uses_exact_preregistered_fresh_mixture(self) -> None:
        for row in (
            "BASE 300000 8 8 60 0 0 8",
            "ROP16 600000 16 8 60 0 0 8",
            "EPS16 500000 8 16 60 0 0 8",
            "DECAY120 100000 8 8 120 0 0 8",
            "TOPK3M30 100000 8 8 60 3 30 8",
            "DEPTH10 400000 8 8 60 0 0 10",
            "FRESH_SEED=2026081805",
        ):
            self.assertIn(row, self.script)

    def test_sizing_runtime_and_reporting_guards(self) -> None:
        for token in (
            "PRODUCERS=12",
            "PREFLIGHT_RECORDS=300",
            "CONTENTION=1.174",
            "MAX_BUDGET_MIN=75",
            "timeout -k 30s",
            'for pid in "${pids[@]}"',
            "PROGRESS.txt",
            "less than 10 GiB free",
            "preflight budget exceeded",
            "JASS_CONTEXT2_INTERVENTION_CORPUS_READY",
        ):
            self.assertIn(token, self.script)
        self.assertNotIn("wait\n", self.script)

    def test_is_generation_only_and_fail_closed(self) -> None:
        for token in (
            "l3_context2_intervention_corpus_audit.py",
            "JASS_CONTROL_SUMMARY.json",
            "SELFPLAY_GENERATED__TRUE",
            "FITS_RUN__0",
            "FORCE_GAMES_PLAYED__0",
            "FROZEN_READ__FALSE",
            "PROMOTION_AUTHORIZED__FALSE",
            "AUTOMATIC_NEXT_JOB__NULL",
        ):
            self.assertIn(token, self.script)
        self.assertNotIn("train_stream.py", self.script)
        self.assertNotIn("jass_vs_jass_arch", self.script)
        self.assertNotIn("pip install", self.script)


if __name__ == "__main__":
    unittest.main()

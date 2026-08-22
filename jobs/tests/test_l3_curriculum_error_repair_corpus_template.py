from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-curriculum-error-repair-corpus-v1.sh"


class RepairCorpusTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_immutable_source_and_parent_are_pinned(self) -> None:
        for token in (
            'SOURCE_JOB="cpx62-1474-l3-curriculum-error-autopsy-resume-v1"',
            'SOURCE_ATTEMPT="20260822T153126Z-0be76565"',
            'SOURCE_CODE="0be76565de1882c4d410995603217aa64ea09d70"',
            'CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"',
            "--expected-state completed",
        ):
            self.assertIn(token, self.text)

    def test_generation_is_exact_seeded_and_without_replacement(self) -> None:
        for token in (
            "TARGET=500000",
            "--target-positions \"$TARGET\"",
            "--min-source-openings 64",
            "--max-opening-share 0.02",
            "--seed-frac 100",
            "--seed-without-replacement",
            "--seed-usage-out",
            "--pair-openings",
            "--sample-meta-format jsm2",
            "--drop-plycap",
        ):
            self.assertIn(token, self.text)

    def test_negative_catalogue_stops_before_generation(self) -> None:
        stop = self.text.index('if [ "$SEED_VERDICT" != JASS_CURRICULUM_REPAIR_SEEDS_READY ]')
        build = self.text.index("stage build-authenticated-exact-fold-tempo-engine")
        generate = self.text.index("stage generate-exactly-500k-targeted-positions")
        self.assertLess(stop, build)
        self.assertLess(build, generate)
        self.assertIn("NEW_SELFPLAY_POSITIONS__0", self.text[stop:build])

    def test_forbidden_actions_are_guarded_and_absent(self) -> None:
        for token in ("NO_FIT", "NO_FORCE", "NO_FROZEN_READ", "NO_AUTOMATIC_PROMOTION"):
            self.assertIn(token, self.text)
        self.assertNotIn("--games ", self.text)
        self.assertNotIn("train_stream", self.text)
        self.assertNotIn("promote", self.text.lower())


if __name__ == "__main__":
    unittest.main()

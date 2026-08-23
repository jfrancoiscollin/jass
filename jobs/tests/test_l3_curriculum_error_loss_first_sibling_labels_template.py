from pathlib import Path
import unittest


TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "templates"
    / "l3-curriculum-error-loss-first-sibling-labels-v1.sh"
).read_text(encoding="utf-8")


class LossFirstSiblingLabelsTemplateTests(unittest.TestCase):
    def test_fixed_target_blind_protocol(self):
        for token in (
            "select-target-blind-candidates",
            "profile-candidates-shallow-d6-d9",
            "--seed 2026082343",
            "--match-seed 2026082344",
            "label-all-legal-siblings-d10-d12-exact-symmetry",
            "loss-first-matched-pairs.json",
            "JASS_CURRICULUM_ERROR_LOSS_FIRST_LABELS_READY",
        ):
            self.assertIn(token, TEMPLATE)

    def test_source_and_engine_are_immutable(self):
        for token in (
            'git merge-base --is-ancestor "$SOURCE_CODE" HEAD',
            'git diff --quiet "$SOURCE_CODE" HEAD -- CMakeLists.txt src',
            "source-selection.json",
            "source-transitions.json",
            "source-search-params.txt",
            "CURRICULUM_SHA=\"319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1\"",
        ):
            self.assertIn(token, TEMPLATE)

    def test_authenticates_the_decompressed_work_model(self):
        self.assertIn("sha(inp.parent/'work'/'curriculum.pjtw')", TEMPLATE)
        self.assertNotIn("sha(inp/'curriculum.pjtw')", TEMPLATE)

    def test_preflight_and_forbidden_actions(self):
        for token in (
            "MAX_PROJECTED_MINUTES=480",
            "--max-rows \"$PREFLIGHT_ROWS_PER_SHARD\"",
            "PATTERNEVAL_FITS__0",
            "PRODUCTION_MODEL_FITS__0",
            "STRENGTH_GAMES__0",
            "NEW_SELFPLAY__0",
            "FROZEN_READS__0",
            "PROMOTION_AUTHORIZED__FALSE",
        ):
            self.assertIn(token, TEMPLATE)
        self.assertNotIn("train_stream_exact.py", TEMPLATE)
        self.assertNotIn("run_jass_gate", TEMPLATE)


if __name__ == "__main__":
    unittest.main()

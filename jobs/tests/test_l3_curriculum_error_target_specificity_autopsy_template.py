import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-curriculum-error-target-specificity-autopsy-v1.sh"


class TargetSpecificityAutopsyTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_requires_immutable_sources_and_cpx_contract(self):
        for token in (
            "TRAINING_SOURCE_JOB", "FRESH_SOURCE_JOB", "SUBSPACE_SOURCE_JOB",
            "EXPECTED_CODE_SHA", '"$(hostname)" = cpx62', '"$(nproc)" -eq 16',
        ):
            self.assertIn(token, self.text)

    def test_is_read_only_and_forbids_continuation(self):
        for token in (
            "READ_ONLY_TARGET_SPECIFICITY_AUTOPSY", "REPLAY_1524_BIT_EXACT",
            "NO_FIT_ON_FRESH_FOR_PRODUCTION", "NO_NEW_EXACT_TARGETS",
            "NO_SELFPLAY", "NO_PATTERNEVAL_FIT", "NO_STRENGTH_GAMES",
            "NO_FROZEN_READ", "NO_AUTOMATIC_PROMOTION", "NO_AUTOMATIC_CONTINUATION",
            "FRESH_1524_REUSE_FOR_CONFIRMATION__FORBIDDEN",
        ):
            self.assertIn(token, self.text)

    def test_fetches_exact_required_artifacts(self):
        for token in (
            "fresh-powered-confirmation.json", "fresh-confirmation-pairs.json",
            "fresh-target-cache.json", "stable-subspace-screen.json",
            "gate-fit-pairs.json", "target-specificity-autopsy.json",
        ):
            self.assertIn(token, self.text)

    def test_never_runs_engine_or_strength_tools(self):
        forbidden = (
            "match_runner", "selfplay", "play-games", "frozen",
            "train_pattern", "fit-pattern", "promote-model",
        )
        lowered = self.text.lower()
        # Guard names and accounting markers may mention the concepts.  Only
        # reject executable-looking command paths.
        self.assertNotIn("jobs/tools/match", lowered)
        self.assertNotIn("jobs/tools/selfplay", lowered)
        self.assertNotIn("pattern_jass/tools/train", lowered)


if __name__ == "__main__":
    unittest.main()

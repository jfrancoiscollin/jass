from pathlib import Path
import unittest


TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "templates"
    / "l3-curriculum-error-anchored-local-refit-oos-availability-preregistration-v1.sh"
)


class AnchoredOosAvailabilityPreregistrationTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_authenticates_joint_fit_model_and_six_exclusion_sources(self) -> None:
        for token in (
            "JOINT_SOURCE_JOB",
            "FIT_SOURCE_JOB",
            "anchored-local-residual-model.json",
            "OOS_EXCLUSION_SOURCES",
            'exclusion_count" -eq 6',
            "--exclude-source",
        ):
            self.assertIn(token, self.text)

    def test_is_target_free_and_has_no_continuation(self) -> None:
        for token in (
            "TARGET_FREE_PREREGISTRATION_ONLY",
            "NO_OOS_GAME",
            "NO_OOS_LABEL",
            "NO_FIT",
            "NO_STRENGTH_GAMES",
            "NO_FROZEN_READ",
            "NO_AUTOMATIC_PROMOTION",
            "NO_AUTOMATIC_CONTINUATION",
            "NEW_TARGETS__0",
            "OOS_READS__0",
            "NEW_SELFPLAY__0",
        ):
            self.assertIn(token, self.text)


if __name__ == "__main__":
    unittest.main()

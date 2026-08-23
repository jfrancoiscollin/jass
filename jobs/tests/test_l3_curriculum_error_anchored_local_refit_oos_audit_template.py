from pathlib import Path
import unittest


TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "templates"
    / "l3-curriculum-error-anchored-local-refit-oos-audit-v1.sh"
)


class AnchoredOosAuditTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_labels_fixed_300_per_pool_then_audits_without_fit(self) -> None:
        for token in (
            "FIRST_300_PER_POOL_FROZEN_ONLY",
            "exact-label-first-300-valid-pairs-per-pool-in-frozen-orders",
            "POOL1_300",
            "--judge-depth 12",
            "anchored-local-refit-oos-audit.json",
            "--fit-model",
            "NO_FIT",
        ):
            self.assertIn(token, self.text)

    def test_authenticates_all_sources_and_forbids_continuation(self) -> None:
        for token in (
            "AVAILABILITY_SOURCE_JOB",
            "PREREG_SOURCE_JOB",
            "FIT_SOURCE_JOB",
            "verified-candidate-games.json",
            "NO_STRENGTH_GAMES",
            "NO_NEW_SELFPLAY",
            "NO_FROZEN_READ",
            "NO_AUTOMATIC_PROMOTION",
            "NO_AUTOMATIC_CONTINUATION",
        ):
            self.assertIn(token, self.text)


if __name__ == "__main__":
    unittest.main()

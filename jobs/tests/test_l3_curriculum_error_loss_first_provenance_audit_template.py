import pathlib
import unittest


class ProvenanceAuditTemplateTest(unittest.TestCase):
    def test_template_guards_and_source(self):
        root = pathlib.Path(__file__).resolve().parents[2]
        text = (root / "jobs/templates/l3-curriculum-error-loss-first-provenance-audit-v1.sh").read_text()
        for token in (
            "READ_ONLY_PROVENANCE_AUDIT", "NO_NEW_EXACT_TARGETS", "NO_PATTERNEVAL_FIT",
            "NO_STRENGTH_GAMES", "NO_SELFPLAY", "NO_FROZEN_READ",
            "NO_AUTOMATIC_PROMOTION", "NO_AUTOMATIC_CONTINUATION",
            "JASS_CURRICULUM_ERROR_LOSS_FIRST_PROVENANCE_AUDIT_READY",
        ):
            self.assertIn(token, text)
        self.assertNotIn("--frozen", text)


if __name__ == "__main__":
    unittest.main()

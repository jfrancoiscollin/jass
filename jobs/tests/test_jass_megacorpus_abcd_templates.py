import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
D_TEXT = (ROOT / "jobs/templates/jass-megacorpus-arm-d-fit-v1.sh").read_text()
S_TEXT = (ROOT / "jobs/templates/jass-megacorpus-abcd-strength-v1.sh").read_text()
HARNESS_TEXT = (ROOT / "jobs/tools/jass_vs_jass_arch.py").read_text()


class MegaCorpusAbcdTemplatesTest(unittest.TestCase):
    def test_d_is_explicit_C_prior_not_plain_warm_start(self):
        self.assertIn('--prior-mean "$W/C.pjtw" --prior-decay 0', D_TEXT)
        self.assertNotIn('--warm-start "$W/C.pjtw"', D_TEXT)
        self.assertIn("CE_Current + 0.5e-5*||w-C||^2", D_TEXT)
        self.assertIn("--contrast B:A --contrast C:B --contrast D:A --contrast D:C", D_TEXT)

    def test_d_recertifies_all_source_optimizer_gradients_before_fit(self):
        for source, label in (
            ("current_2m", "A"),
            ("mega_eq_2m", "B"),
            ("mega_full_4m", "C"),
        ):
            self.assertIn(
                f"artefacts/{source}-optimizer.json={label}-optimizer.json",
                D_TEXT,
            )
        self.assertIn("source-$arm-convergence.json", D_TEXT)
        self.assertIn("optimizer report differs from ABC certificate", D_TEXT)
        self.assertLess(
            D_TEXT.index("for arm in A B C; do\n  \"$PY\" jobs/tools/verify_optimizer_convergence.py"),
            D_TEXT.index("stage fit-D-C-prior-then-current"),
        )

    def test_strength_has_all_preregistered_contrasts_and_paired_bootstrap(self):
        self.assertIn("CONTRASTS=(B_vs_A C_vs_B D_vs_A D_vs_C C_vs_A D_vs_B)", S_TEXT)
        self.assertIn('--paired-bootstrap-samples "$BOOTSTRAP"', S_TEXT)
        self.assertIn("NOPEN=250", S_TEXT)
        self.assertIn("for view in q00 native", S_TEXT)
        self.assertIn("--results-jsonl", HARNESS_TEXT)

    def test_jobs_read_no_frozen_and_do_not_promote(self):
        combined = (D_TEXT + S_TEXT).lower()
        self.assertNotIn("frozen_test", combined)
        self.assertNotIn("promotion_gate", combined)
        self.assertIn("promotion_authorized__false", combined)
        self.assertNotIn("$${", D_TEXT + S_TEXT)


if __name__ == "__main__":
    unittest.main()

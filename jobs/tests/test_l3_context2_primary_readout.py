import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-context2-primary-two-pool-readout-v1.sh"


class Context2PrimaryReadoutTemplateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_native_hierarchical_decision_is_preregistered(self) -> None:
        for token in (
            "both_native_pool_points_positive",
            "native_inter_pool_compatible_95",
            "combined_native_ci_excludes_half",
            "combined_native_probability_ge_0_975",
            "secondary_B_vs_A_measurement_authorized",
        ):
            self.assertIn(token, self.text)

    def test_q00_is_diagnostic_only(self) -> None:
        self.assertIn("'q00_d9_diagnostic':q00", self.text)
        self.assertIn("'primary_view':'native_movetime_0.1'", self.text)

    def test_combines_two_disjoint_pools_with_paired_bootstrap(self) -> None:
        self.assertIn("pool2 is not certified disjoint from pool1", self.text)
        self.assertIn("samples=200_000", self.text)
        self.assertIn("'openings_total':6000", self.text)
        self.assertIn("'games_total':24000", self.text)

    def test_never_promotes_or_chains(self) -> None:
        self.assertIn("'promotion_authorized':False", self.text)
        self.assertIn("'automatic_next_job':None", self.text)
        self.assertIn("'refits':0", self.text)


if __name__ == "__main__":
    unittest.main()

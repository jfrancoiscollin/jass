from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-m2-train-v1.sh"
WRAPPER = (
    ROOT
    / "jobs/prepared/l3-pure-d12-causal-20260726"
    / "home-0973-l3-pure-d12-causal-fresh2m-train-v1.sh"
)
PROTOCOL = ROOT / "docs/experiments/L3_PURE_D12_CAUSAL_PROTOCOL_20260726.md"


class D12CausalTrainingContractTests(unittest.TestCase):
    def test_shell_contract(self):
        for script in (TEMPLATE, WRAPPER):
            subprocess.run(["bash", "-n", str(script)], check=True)

    def test_one_factor_depth_contract(self):
        template = TEMPLATE.read_text(encoding="utf-8")
        wrapper = WRAPPER.read_text(encoding="utf-8")
        protocol = PROTOCOL.read_text(encoding="utf-8")
        self.assertIn("D12_CAUSAL_FRESH2M:12", template)
        self.assertIn("D12_CAUSAL_APPROVED=1 missing", template)
        self.assertIn("export PLAY_DEPTH_OVERRIDE=12", wrapper)
        self.assertIn('export EXPERIMENT_VARIANT="D12_CAUSAL_FRESH2M"', wrapper)
        self.assertIn("TOTAL_RECORDS=2000000", template)
        self.assertIn("BASE_SEED=1618033", template)
        self.assertIn("seule la profondeur de jeu passe de d10 à", protocol)
        self.assertIn("d12. Le parent et le warm-start restent **F2M**", protocol)

    def test_d10_plateau_and_f2m_parent_are_immutable(self):
        template = TEMPLATE.read_text(encoding="utf-8")
        wrapper = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("D10_PLATEAU_OR_REGRESSION_REVIEW", template)
        self.assertIn("stop_d10_and_prepare_d12_or_d10_d12_mix", template)
        self.assertIn("home-0972-l3-pure-d10-causal-independent-eval-v1", wrapper)
        self.assertIn(
            "18930613234b4a1a6a933393151a05dd68f71d1af749f058f37c5778bd77960f",
            wrapper,
        )
        self.assertIn('--nnue "$W/parent-f2m.pjtw"', template)
        self.assertIn('--warm-start "$W/parent-f2m.pjtw"', template)

    def test_d12_artifacts_and_nonpromotion(self):
        template = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("d12.pjtw.gz", template)
        self.assertIn("d12-fresh-2m.jnnw.gz", template)
        self.assertIn("d12-fresh-2m.jsm.gz", template)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", template)
        self.assertIn("AUTOMATIC_NEXT_JOB__NULL", template)


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-m2-train-v1.sh"
WRAPPER = (
    ROOT
    / "jobs/prepared/l3-pure-d10-causal-20260726"
    / "home-0971-l3-pure-d10-causal-fresh2m-train-v1.sh"
)
PROTOCOL = ROOT / "docs/experiments/L3_PURE_D10_CAUSAL_PROTOCOL_20260726.md"


class D10CausalTrainingContractTests(unittest.TestCase):
    def test_shell_contract(self):
        for script in (TEMPLATE, WRAPPER):
            subprocess.run(["bash", "-n", str(script)], check=True)

    def test_one_factor_depth_contract(self):
        template = TEMPLATE.read_text(encoding="utf-8")
        wrapper = WRAPPER.read_text(encoding="utf-8")
        protocol = PROTOCOL.read_text(encoding="utf-8")
        self.assertIn('PLAY_DEPTH="${PLAY_DEPTH_OVERRIDE:-8}"', template)
        self.assertIn("D10_CAUSAL_FRESH2M:10", template)
        self.assertIn("D10_CAUSAL_APPROVED=1 missing", template)
        self.assertIn("export PLAY_DEPTH_OVERRIDE=10", wrapper)
        self.assertIn('export EXPERIMENT_VARIANT="D10_CAUSAL_FRESH2M"', wrapper)
        self.assertIn("TOTAL_RECORDS=2000000", template)
        self.assertIn("BASE_SEED=1618033", template)
        self.assertIn("2 000 000 | 2 000 000", protocol)
        self.assertIn("1 618 033 + shard | identiques", protocol)

    def test_plateau_and_parent_are_immutable_inputs(self):
        template = TEMPLATE.read_text(encoding="utf-8")
        wrapper = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("M2_PLATEAU_OR_REGRESSION_REVIEW", template)
        self.assertIn("stop_same_recipe_and_prepare_d10_causal_arm", template)
        self.assertIn("home-0970bis-l3-pure-m2-independent-eval-v3", wrapper)
        self.assertIn(
            "be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2",
            wrapper,
        )
        self.assertIn('--nnue "$W/parent-f2m.pjtw"', template)
        self.assertIn('--warm-start "$W/parent-f2m.pjtw"', template)

    def test_d10_artifacts_and_nonpromotion(self):
        template = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("d10.pjtw.gz", template)
        self.assertIn("d10-fresh-2m.jnnw.gz", template)
        self.assertIn("d10-fresh-2m.jsm.gz", template)
        self.assertIn('"play_depth": corpus["play_depth"]', template)
        self.assertIn('"experiment_variant": experiment_variant', template)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", template)
        self.assertIn("AUTOMATIC_NEXT_JOB__NULL", template)


if __name__ == "__main__":
    unittest.main()

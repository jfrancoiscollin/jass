from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-m1-scan-gap-causal-v1.sh"


class M1ScanGapCausalContractTests(unittest.TestCase):
    def test_shell_and_causal_contract(self):
        subprocess.run(["bash", "-n", str(TEMPLATE)], check=True)
        text = TEMPLATE.read_text(encoding="utf-8")

        self.assertIn(
            "NEW_CELLS=(AB_EXTRAS_D12 SCAN_EXACT_D10 SCAN_EXACT_D12)",
            text,
        )
        self.assertIn("-DJASS_SCAN_EXACT_EVAL=ON", text)
        self.assertIn("-DJASS_DRAWISH_SCALING=ON", text)
        self.assertIn("--max-abs-diff 0", text)
        self.assertIn("--limit-per-pool 0", text)
        self.assertIn("run_cell \"$cell\" \"$J8X\"", text)
        self.assertIn("--defender-pattern \"$W/GEN2.pjtw\"", text)
        self.assertIn("--defender-depth \"$DEFENDER_DEPTH\"", text)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", text)
        self.assertIn("AUTOMATIC_NEXT_JOB__NULL", text)

    def test_pinned_inputs_and_no_training(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn(
            "0e7161c38af605f5e367f3f8fe17525d1c40db722714c68921971b386e58abba",
            (ROOT / "jobs/tools/scan_exact_eval_port.py").read_text(
                encoding="utf-8"
            ),
        )
        self.assertIn("artefacts/p3_mince-stable.jnnw.gz", text)
        self.assertIn("artefacts/p4_egal-stable.jnnw.gz", text)
        self.assertNotIn("train_stream.py", text)
        self.assertNotIn("train.py --scan-eval", text)


if __name__ == "__main__":
    unittest.main()

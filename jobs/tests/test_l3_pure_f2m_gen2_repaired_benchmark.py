from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-f2m-gen2-repaired-benchmark-v1.sh"


class F2MGen2RepairedBenchmarkContractTests(unittest.TestCase):
    def test_symmetric_repaired_engine_contract(self):
        subprocess.run(["bash", "-n", str(TEMPLATE)], check=True)
        text = TEMPLATE.read_text(encoding="utf-8")

        self.assertIn("NOPEN=500", text)
        self.assertIn("NSH_GATE=16", text)
        self.assertIn("PAR_GATE=8", text)
        self.assertIn("OPENING_SEED=223607", text)
        self.assertIn("--variant 8cf", text)
        self.assertIn("--variant v4", text)
        self.assertIn('cmake -S . -B "$W/build8"', text)
        self.assertIn('cmake -S . -B "$W/build32"', text)
        self.assertNotIn("git archive", text)
        self.assertIn('--jass-a "$J8" --jass-b "$J32"', text)
        self.assertIn('--pattern-a "$W/F2M.pjtw"', text)
        self.assertIn('--pattern-b "$W/GEN2.pjtw"', text)
        self.assertIn("run_gate q00", text)
        self.assertIn("run_gate native", text)
        self.assertIn("l3_f2m_gen2_repaired_benchmark.py", text)
        self.assertIn("GENERAL_CHAMPION_PROMOTION_AUTHORIZED__FALSE", text)
        self.assertIn("M2_LAUNCH_AUTHORIZED__FALSE", text)

    def test_inputs_are_pinned(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertRegex(text, r'F2M_SHA="[0-9a-f]{64}"')
        self.assertRegex(text, r'GEN2_GZ_SHA="[0-9a-f]{64}"')
        self.assertIn("CONFIRMATION_PREFIX", text)
        self.assertIn("M1_PREFIX", text)


if __name__ == "__main__":
    unittest.main()

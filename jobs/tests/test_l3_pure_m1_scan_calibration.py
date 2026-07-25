from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-m1-scan-calibration-v1.sh"


class M1ScanCalibrationContractTests(unittest.TestCase):
    def test_shell_and_scientific_contract(self):
        subprocess.run(["bash", "-n", str(TEMPLATE)], check=True)
        text = TEMPLATE.read_text(encoding="utf-8")

        self.assertIn("LEARNED=(C0 P1 F500 F2M R2M AB_MAT AB_KING AB_EXTRAS)", text)
        self.assertIn("SCAN_MODELS=(SCAN_D10 SCAN_D12)", text)
        self.assertIn("STRATA=(p3_mince p4_egal)", text)
        self.assertIn("--scan-depth \"$depth\"", text)
        self.assertIn("--defender-depth \"$DEFENDER_DEPTH\"", text)
        self.assertIn("--defender-pattern \"$W/GEN2.pjtw\"", text)
        self.assertIn("--max-error-rate 0", text)
        self.assertIn("run_scan SCAN_D10 10", text)
        self.assertIn("run_scan SCAN_D12 12", text)
        self.assertIn("EXPECTED_SCAN_RUNTIME_SHA256", text)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", text)
        self.assertIn("AUTOMATIC_NEXT_JOB__NULL", text)

    def test_exact_corrected_gauge_is_reused_without_fen_roundtrip(self):
        text = TEMPLATE.read_text(encoding="utf-8")

        self.assertIn("artefacts/p3_mince-stable.jnnw.gz", text)
        self.assertIn("artefacts/p4_egal-stable.jnnw.gz", text)
        self.assertIn(
            "cd92710fec7934d113ccade22180d4cddf029b084dd20c8fa9e30ca686767c91",
            text,
        )
        self.assertIn(
            "0d925c4fbd7e7928bf6d86bd2cd40f796ee6805e0010e51d5d6483986da2a1ac",
            text,
        )
        self.assertNotIn("fen-to-jnnw", text)


if __name__ == "__main__":
    unittest.main()

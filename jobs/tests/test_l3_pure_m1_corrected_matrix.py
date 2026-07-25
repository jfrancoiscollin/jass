from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-m1-corrected-matrix-v1.sh"


class M1CorrectedMatrixContractTests(unittest.TestCase):
    def test_shell_and_scientific_contract(self):
        subprocess.run(["bash", "-n", str(TEMPLATE)], check=True)
        text = TEMPLATE.read_text(encoding="utf-8")

        self.assertIn(
            "MODELS=(C0 P1 F500 F2M R2M AB_MAT AB_KING AB_EXTRAS)", text
        )
        self.assertIn("STRATA=(p3_mince p4_egal)", text)
        self.assertIn("TARGET_PER_STRATUM=300", text)
        self.assertIn("PAR_MODEL_GROUPS=2", text)
        self.assertIn("--pool-jnnw \"$pool\"", text)
        self.assertIn("--defender-pattern \"$W/GEN2.pjtw\"", text)
        self.assertIn("--depth \"$CONV_DEPTH\"", text)
        self.assertIn("--primary-stratum p4_egal", text)
        self.assertIn("--preservation-stratum p3_mince", text)
        self.assertIn("run_force q00 C0", text)
        self.assertIn("run_force native C0", text)
        self.assertIn("run_force q00 GEN2", text)
        self.assertIn("LEGALITY_PREFIX", text)
        self.assertIn("BASELINE_MATRIX_PREFIX", text)
        self.assertIn("BASELINE_MATRIX_CODE_SHA", text)
        self.assertIn("LEGALITY_REPAIR_RECOVERS_CONVERSION", text)
        self.assertIn("env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB", text)
        self.assertIn("l3_repaired_engine_matrix.py", text)
        self.assertIn("M1_REPAIRED_ENGINE_MATRIX_READY_HUMAN_REVIEW", text)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", text)
        self.assertIn("AUTOMATIC_NEXT_JOB__NULL", text)

    def test_corrected_gauge_is_immutable_and_old_gauge_is_registered(self):
        text = TEMPLATE.read_text(encoding="utf-8")

        self.assertIn(
            "cd92710fec7934d113ccade22180d4cddf029b084dd20c8fa9e30ca686767c91",
            text,
        )
        self.assertIn(
            "0d925c4fbd7e7928bf6d86bd2cd40f796ee6805e0010e51d5d6483986da2a1ac",
            text,
        )
        self.assertIn(
            "e5e20043a1c32916548f76fd1ff430efa1f1a2156ceefca6c3c8470dfb9b9c72",
            text,
        )
        self.assertIn("artefacts/p3_mince-stable.jnnw.gz", text)
        self.assertIn("artefacts/p4_egal-stable.jnnw.gz", text)
        self.assertNotIn("fen-to-jnnw", text)

    def test_all_model_payload_hashes_are_pinned(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        for variable in (
            "C0_SHA",
            "P1_SHA",
            "F500_SHA",
            "F2M_SHA",
            "R2M_SHA",
            "AB_MAT_SHA",
            "AB_KING_SHA",
            "AB_EXTRAS_SHA",
        ):
            self.assertRegex(text, rf'{variable}="[0-9a-f]{{64}}"')


if __name__ == "__main__":
    unittest.main()

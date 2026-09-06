from pathlib import Path
import unittest


class D1StageEnvRecoveryContractTests(unittest.TestCase):
    def test_science_contract_is_unchanged(self) -> None:
        v2 = Path("jobs/templates/l3-d1-wdl-listwise-fit-v2-historical-split.sh").read_text()
        v3 = Path("jobs/templates/l3-d1-wdl-listwise-fit-v3-stage-env-recovery.sh").read_text()
        self.assertIn("HOLDOUT=199204; TRAIN_EXPECTED=1800796; RECORDS_EXPECTED=2000000", v2)
        self.assertIn("WDL_CONTROL WDL_LISTWISE", v2)
        self.assertIn("d1_listwise_fit_historical_split.py", v2)
        self.assertIn("d1_postfit_readout_historical_split.py", v2)
        self.assertIn("l3-d1-wdl-listwise-fit-v2-historical-split.sh", v3)


if __name__ == "__main__":
    unittest.main()

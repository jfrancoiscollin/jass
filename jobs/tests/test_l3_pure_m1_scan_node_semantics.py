from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-m1-scan-node-semantics-v1.sh"


class ScanNodeSemanticsContractTests(unittest.TestCase):
    def test_shell_and_scientific_contract(self):
        subprocess.run(["bash", "-n", str(TEMPLATE)], check=True)
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("ARMS=(SCAN_CORE SCAN_VERIFY SCAN_VERIFY_THREAT)", text)
        self.assertIn("DEPTHS=(10 12)", text)
        self.assertIn("--max-abs-diff 0", text)
        self.assertIn("TRAINING_AUTHORIZED__FALSE", text)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", text)
        self.assertIn("AUTOMATIC_NEXT_JOB__NULL", text)

    def test_no_training_or_automatic_continuation(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertNotIn("train.py", text)
        self.assertNotIn("train_stream.py", text)
        self.assertNotIn("queue/pending", text)
        self.assertIn("NO_AUTOMATIC_CONTINUATION:-0", text)


if __name__ == "__main__":
    unittest.main()

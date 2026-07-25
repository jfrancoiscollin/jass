from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-pure-m1-search-tree-audit-v1.sh"


class SearchTreeAuditContractTests(unittest.TestCase):
    def test_shell_and_scientific_contract(self):
        subprocess.run(["bash", "-n", str(TEMPLATE)], check=True)
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("ARMS=(NO_FORWARD SCAN_EXT_QS SCAN_LMR FULL_WIDTH)", text)
        self.assertIn("--failures-per-side 8 --controls-per-side 4", text)
        self.assertIn('--depth "$DEPTH" --defender-depth "$DEFENDER_DEPTH"', text)
        self.assertIn("--max-abs-diff 0", text)
        self.assertIn("--limit-per-pool 0", text)
        self.assertIn("TRAINING_AUTHORIZED__FALSE", text)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", text)
        self.assertIn("AUTOMATIC_NEXT_JOB__NULL", text)

    def test_no_training_or_automatic_continuation(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertNotIn("train.py", text)
        self.assertNotIn("train_stream.py", text)
        self.assertNotIn("queue/pending", text)
        self.assertIn('NO_AUTOMATIC_CONTINUATION:-0', text)


if __name__ == "__main__":
    unittest.main()

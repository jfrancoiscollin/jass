import ast
import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-pure-explore-topk-readout-v1.sh"


class TopkReadoutTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_direct_primary_contrast_and_power(self):
        self.assertIn("--pattern-a \"$W/TOPK3.pjtw\"", self.text)
        self.assertIn("--pattern-b \"$W/UNIFORM.pjtw\"", self.text)
        self.assertIn("NOPEN=1500", self.text)
        self.assertIn("GAMES_PER_VIEW=$((NOPEN * 2))", self.text)
        self.assertIn("for view in q00 native", self.text)
        self.assertIn("--depth \"$FORCE_DEPTH\"", self.text)
        self.assertIn("--movetime \"$MOVETIME\"", self.text)

    def test_models_and_prior_pool_are_authenticated(self):
        self.assertIn("fetch_result_files.py --prefix \"$SOURCE_PREFIX\"", self.text)
        self.assertIn("fetch_result_files.py --prefix \"$MODEL_PREFLIGHT_PREFIX\"", self.text)
        self.assertIn("EXPECTED_UNIFORM_MODEL_SHA", self.text)
        self.assertIn("EXPECTED_TOPK3_MODEL_SHA", self.text)
        self.assertIn("--exclude \"$IN/prior-1008-openings.fen\"", self.text)
        self.assertIn("overlap_records", self.text)

    def test_fail_closed_and_no_automatic_promotion(self):
        self.assertIn("L3_PURE_TOPK3_VS_UNIFORM_READOUT_INVALID", self.text)
        self.assertIn("\"promotion_authorized\": False", self.text)
        self.assertIn("\"automatic_next_job\": None", self.text)
        self.assertIn("holdout_not_used_for_selection", self.text)

    def test_embedded_python_is_syntax_valid(self):
        blocks = re.findall(r"<<'PY'\n(.*?)\nPY", self.text, flags=re.S)
        self.assertGreaterEqual(len(blocks), 3)
        for block in blocks:
            ast.parse(block)


if __name__ == "__main__":
    unittest.main()

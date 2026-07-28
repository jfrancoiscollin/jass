from __future__ import annotations

import ast
from pathlib import Path
import re
import unittest


TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "templates"
    / "l3-pure-explore-topk-causal-ab-v1.sh"
)


class TopkCausalAbTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_preregistered_constants_are_pinned(self):
        for literal in (
            "RECORDS=${RECORDS:-2000000}",
            "SHARDS=${SHARDS:-6}",
            "PLAY_DEPTH=8",
            "TOPK=3",
            "EXPLORE_MARGIN=50",
            'L2=3e-5',
        ):
            self.assertIn(literal, self.text)

    def test_both_arms_share_generation_path_and_split_rngs(self):
        self.assertIn(
            '--explore-decay-plies "$EXPLORE_DECAY" --split-selfplay-rngs "$@"',
            self.text,
        )
        self.assertRegex(
            self.text,
            r'gen_arm uniform "\$GEN_TIMEOUT_UNIFORM" &',
        )
        self.assertRegex(
            self.text,
            r'gen_arm topk3 "\$GEN_TIMEOUT_TOPK" \\\n'
            r'  --explore-topk "\$TOPK" --explore-margin "\$EXPLORE_MARGIN" &',
        )

    def test_data_and_fit_guards_cover_both_arms(self):
        self.assertGreaterEqual(
            self.text.count("for arm in uniform topk3; do"),
            4,
        )
        self.assertIn(
            'python3 jobs/tools/assert_corpus_wdl.py --data "$W/$arm.raw.jnnw"',
            self.text,
        )
        self.assertIn('"primary_contrast": "TOPK3 minus UNIFORM"', self.text)
        self.assertIn('"promotion_authorized": False', self.text)
        self.assertIn('"automatic_next_job": None', self.text)

    def test_embedded_python_parses(self):
        blocks = re.findall(
            r"<<'PY'\n(.*?)\nPY(?:\n|$)",
            self.text,
            re.S,
        )
        self.assertEqual(len(blocks), 4)
        for block in blocks:
            ast.parse(block)


if __name__ == "__main__":
    unittest.main()

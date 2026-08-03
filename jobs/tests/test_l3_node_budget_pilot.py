from __future__ import annotations

import ast
from pathlib import Path
import re
import unittest


TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "templates"
    / "l3-node-budget-pilot-2m-v1.sh"
)


class NodeBudgetPilotTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_volume_parent_and_recipe_are_pinned(self):
        for literal in (
            'RECORDS_PER_ARM="${RECORDS_PER_ARM:-1000000}"',
            '[ "$((2 * RECORDS_PER_ARM))" -eq 2000000 ]',
            "PARENT_NAME=PRIORTIGHT",
            "2bbe1733ca0976ce4934131f83178a9e3757b5bc7a9b5a3bdbc41984781dfec7",
            "PLAY_DEPTH=8",
            "L2=3e-5",
            "LBFGS_GTOL=1e-4",
            "--exact-fold --tempo-stage --prior-mean",
            "--prior-decay 0",
            "PYTHONUNBUFFERED=1",
        ):
            self.assertIn(literal, self.text)

    def test_calibration_is_outcome_blind_and_precedes_full_generation(self):
        raw = self.text.index("stage calibrate-raw-distribution")
        confirm = self.text.index("stage confirm-calibrated-cost")
        depth = self.text.index("stage generate-depth-1m")
        nodes = self.text.index("stage generate-nodes-1m")
        self.assertLess(raw, confirm)
        self.assertLess(confirm, depth)
        self.assertLess(depth, nodes)
        self.assertIn(
            'scale = Decimal(depth_ms) / Decimal(node_ms)',
            self.text,
        )
        self.assertIn(
            'Decimal("0.005") <= scale <= Decimal("5.00")',
            self.text,
        )
        self.assertIn(
            '"accepted_interval": [0.75, 1.35]',
            self.text,
        )
        self.assertIn("stage refine-calibrated-cost-once", self.text)
        self.assertIn(
            'die "feedback-calibrated cost remains outside [0.75, 1.35]"',
            self.text,
        )
        self.assertEqual(
            self.text.count("gen_arm cal-nodes-refined"),
            1,
        )
        calibration_prefix = self.text[raw:depth]
        self.assertNotIn("HOLDOUT_LOGLOSS", calibration_prefix)
        self.assertNotIn("fit_arm", calibration_prefix)

    def test_generation_is_sequential_paired_and_bounded(self):
        self.assertRegex(
            self.text,
            r'gen_arm depth "\$RECORDS_PER_ARM" "\$SHARDS" '
            r'"\$GEN_TIMEOUT_DEPTH" \\\n  "\$BASE_SEED" depth',
        )
        self.assertRegex(
            self.text,
            r'gen_arm nodes "\$RECORDS_PER_ARM" "\$SHARDS" '
            r'"\$GEN_TIMEOUT_NODES" \\\n'
            r'  "\$BASE_SEED" nodes "\$SCALED_NODE_SPEC"',
        )
        self.assertIn("--split-selfplay-rngs", self.text)
        self.assertIn("--pair-openings", self.text)
        self.assertIn('if wait "$pid"; then rc=0; else rc=$?; fi', self.text)
        self.assertNotIn('gen_arm depth "$RECORDS_PER_ARM" &', self.text)

    def test_node_policy_and_telemetry_are_explicit(self):
        self.assertIn(
            'RAW_NODE_SPEC="5000:10,20000:25,80000:35,'
            '300000:20,1200000:10"',
            self.text,
        )
        self.assertIn("--search-limit nodes", self.text)
        self.assertIn("--node-budget-sample-per move", self.text)
        self.assertIn('--node-budget-log "$W/$prefix-s$shard.jsonl"', self.text)
        self.assertIn("node-budget-telemetry.tar.gz", self.text)
        self.assertIn('"node_budget_sampler_version": 1', self.text)

    def test_result_is_non_promotable_and_requires_separate_gate(self):
        self.assertIn(
            '"verdict": "L3_NODE_BUDGET_PILOT_ARMS_READY"',
            self.text,
        )
        self.assertIn('"primary_contrast": "NODES minus DEPTH"', self.text)
        self.assertIn('"promotion_authorized": False', self.text)
        self.assertIn('"automatic_next_job": None', self.text)
        self.assertIn("required_readout", self.text)

    def test_embedded_python_parses(self):
        blocks = re.findall(
            r"<<'PY'\n(.*?)\nPY(?:\n|$)",
            self.text,
            re.S,
        )
        self.assertEqual(len(blocks), 7)
        for block in blocks:
            ast.parse(block)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
from pathlib import Path
import unittest

from jobs.tools import cls_bottleneck_classification_launch_stage as launch
from jobs.tools import cls_bottleneck_classification_stage as stage

ROOT = Path(__file__).resolve().parents[2]


def ci(lo: float, med: float, hi: float) -> dict[str, float]:
    return {"q025": lo, "median": med, "q975": hi}


class CLSBottleneckClassificationV1Tests(unittest.TestCase):
    def test_sources_and_budget_are_frozen(self):
        self.assertEqual(stage.BUDGET, 200000)
        self.assertEqual(stage.SOURCES["depth"]["job"], "cpx62-2000-l3-cls-depth-growth-full-production-v2")
        self.assertEqual(stage.SOURCES["mirror"]["job"], "cpx62-2008-l3-cls-mirror-scale-production-v3")
        self.assertEqual(stage.SOURCES["profile"]["job"], "cpx62-2010-l3-cls-search-profile-production-v1")
        self.assertEqual(stage.SOURCES["draw"]["job"], "cpx62-2013-l3-cls-draw-pentanomial-throughput-production-v1")

    def test_single_axis_classifications(self):
        self.assertEqual(stage.classify(search_ci=ci(-2, -1, -0.1), decision_ci=ci(-.1, 0, .1), cost_ci=ci(-.1, 0, .1))[0], "SEARCH")
        self.assertEqual(stage.classify(search_ci=ci(-1, 0, 1), decision_ci=ci(.01, .1, .2), cost_ci=ci(-1, 0, 1))[0], "DECISION-EVAL")
        self.assertEqual(stage.classify(search_ci=ci(-1, 0, 1), decision_ci=ci(-1, 0, 1), cost_ci=ci(-2, -1, -.01))[0], "COST")

    def test_multiple_or_no_axes_classify_mixed(self):
        mixed = stage.classify(search_ci=ci(-2, -1, -.1), decision_ci=ci(.01, .1, .2), cost_ci=ci(-1, 0, 1))
        self.assertEqual(mixed[0], "mixed")
        self.assertEqual(set(mixed[1]), {"SEARCH", "DECISION-EVAL"})
        none = stage.classify(search_ci=ci(-1, 0, 1), decision_ci=ci(-1, 0, 1), cost_ci=ci(-1, 0, 1))
        self.assertEqual(none, ("mixed", [], "NO_SINGLE_AXIS_ISOLATED_UNDER_FROZEN_RULE"))

    def test_launch_profile_is_zero_effect_and_common(self):
        profile = json.loads((ROOT / "jobs/launch_profiles/cls-bottleneck-classification-v1.json").read_text())
        self.assertEqual(profile["campaign"], "cls-v1")
        self.assertEqual(profile["required_phases"], launch.PHASES)
        self.assertEqual(profile["rehearsal_max_effects"], profile["production_max_effects"])
        self.assertTrue(all(value == 0 for value in profile["rehearsal_max_effects"].values()))

    def test_master_boundary_and_terminal_are_preserved(self):
        doc = (ROOT / "docs/experiments/L3_CLS_BOTTLENECK_CLASSIFICATION_V1_20260916.md").read_text()
        self.assertIn("runtime catastrophe gate", doc)
        self.assertIn("CURRICULUM", doc)
        self.assertIn("does **not** authorize CLS generation 1", doc)
        self.assertEqual(stage.PRODUCTION_TERMINAL, "CLS_DIAGNOSIS_COMPLETE_V1")


if __name__ == "__main__":
    unittest.main()

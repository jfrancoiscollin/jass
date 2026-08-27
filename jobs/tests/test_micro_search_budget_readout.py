from __future__ import annotations

import unittest

from jobs.tools.micro_search_budget_readout import BUDGETS, select_budget


class MicroSearchBudgetSelectionTests(unittest.TestCase):
    def _arm(self, pairwise: float, phase: float, colour: float) -> dict:
        return {
            "global": {"pairwise": pairwise, "top_hit": pairwise},
            "by_phase": {
                p: {"parents": 100, "pairwise": phase, "top_hit": phase}
                for p in ("P0", "P1", "P2", "P3")
            },
            "by_colour": {
                c: {"parents": 200, "pairwise": colour, "top_hit": colour}
                for c in ("white", "black")
            },
        }

    def test_smallest_qualifying_budget_is_selected(self) -> None:
        d1 = 0.73
        curve = {
            125: self._arm(0.82, 0.82, 0.82),
            250: self._arm(0.88, 0.88, 0.88),
            500: self._arm(0.915, 0.89, 0.90),
            1000: self._arm(0.93, 0.90, 0.91),
            2000: self._arm(0.945, 0.91, 0.92),
            5000: self._arm(0.96, 0.92, 0.93),
        }
        selected, decisions = select_budget(curve, d1)
        # 500 recovers (0.915-.73)/(.96-.73)=0.804 < .85, so 1000 wins.
        self.assertEqual(selected, 1000)
        self.assertFalse(decisions[500]["headroom_ge_0_85"])
        self.assertTrue(decisions[1000]["qualifies"])

    def test_5000_fallback_does_not_require_headroom_gate(self) -> None:
        d1 = 0.95
        curve = {b: self._arm(0.89, 0.89, 0.89) for b in BUDGETS}
        curve[5000] = self._arm(0.91, 0.88, 0.89)
        selected, decisions = select_budget(curve, d1)
        self.assertEqual(selected, 5000)
        self.assertLess(decisions[5000]["recovered_headroom"], 0.85)
        self.assertTrue(decisions[5000]["qualifies"])

    def test_distribution_gate_can_close_m1(self) -> None:
        d1 = 0.73
        curve = {b: self._arm(0.94, 0.90, 0.90) for b in BUDGETS}
        curve[5000] = self._arm(0.96, 0.86, 0.90)
        selected, decisions = select_budget(curve, d1)
        # Smaller arms would qualify in this synthetic setup, so make them fail
        # global threshold while preserving only the 5000 distribution failure.
        for b in BUDGETS[:-1]:
            curve[b] = self._arm(0.89, 0.90, 0.90)
        selected, decisions = select_budget(curve, d1)
        self.assertIsNone(selected)
        self.assertFalse(decisions[5000]["each_phase_ge_0_87"])


class MicroSearchSourceContractTests(unittest.TestCase):
    def test_budget_list_is_frozen(self) -> None:
        self.assertEqual(BUDGETS, (125, 250, 500, 1000, 2000, 5000))


if __name__ == "__main__":
    unittest.main()

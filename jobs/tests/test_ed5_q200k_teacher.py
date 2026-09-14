from __future__ import annotations

import unittest
import numpy as np

from jobs.tools import ed4_choice_math as ed4
from jobs.tools import ed5_q200k_choice as qchoice
from jobs.tools import ed5_q200k_teacher_stage as stage


class Q200KChoiceTests(unittest.TestCase):
    def test_unique_max_and_exact_tie(self):
        groups = [
            {"id": 1, "stm": 1, "rows": [0, 1, 2], "terminals": []},
            {"id": 2, "stm": 0, "rows": [3, 4, 5], "terminals": [5]},
        ]
        scores = {
            (0, 200000): 11,
            (1, 200000): 11,
            (2, 200000): -3,
            (3, 200000): 8,
            (4, 200000): 7,
        }
        out = qchoice.groups_from_q200k(groups, scores)
        self.assertEqual(out[0]["V"], [0, 1, 2])
        self.assertEqual(out[0]["A"], [0, 1])
        self.assertEqual(out[1]["V"], [3, 4])
        self.assertEqual(out[1]["A"], [3])
        self.assertEqual(out[0]["edges"], [])

    def test_terminals_need_no_teacher_label(self):
        groups = [{"id": 1, "stm": 1, "rows": [0, 1], "terminals": [1]}]
        out = qchoice.groups_from_q200k(groups, {(0, 200000): 4})
        self.assertEqual(out[0]["V"], [0])
        self.assertEqual(out[0]["A"], [0])

    def _design(self, stm: int):
        phi = np.zeros((25, ed4.WIDTH))
        phi[0, 0] = 1.0
        phi[1, 0] = -1.0
        z = np.zeros(25)
        z[0], z[1] = 0.3, -0.1
        groups = [{"id": 0, "stm": stm, "rows": [0, 1], "V": [0, 1], "A": [0], "edges": []}]
        for i in range(1, 24):
            row = i + 1
            groups.append({"id": i, "stm": i % 2, "rows": [row], "V": [], "A": [], "edges": []})
        rx = np.zeros((1, ed4.WIDTH))
        rz = np.zeros(1)
        y = np.array([0.5])
        return ed4.design(phi, z, groups, rx, rz, y)

    def test_parent_pov_sign_is_unchanged(self):
        black = ed4.derivatives(np.zeros(ed4.WIDTH), self._design(1))[1][0]
        white = ed4.derivatives(np.zeros(ed4.WIDTH), self._design(0))[1][0]
        self.assertLess(black * white, 0.0)

    def test_choice_math_is_exact_ed4_path(self):
        rng = np.random.default_rng(42)
        groups = []
        scores = {}
        for pid in range(24):
            rows = [2 * pid, 2 * pid + 1]
            groups.append({"id": pid, "stm": pid % 2, "rows": rows, "terminals": []})
            scores[rows[0], 200000] = pid + 1
            scores[rows[1], 200000] = pid
        built = qchoice.groups_from_q200k(groups, scores)
        phi = rng.normal(size=(48, ed4.WIDTH)) * 1e-3
        z = rng.normal(size=48) * 0.1
        rx = rng.normal(size=(32, ed4.WIDTH)) * 1e-3
        rz = rng.normal(size=32) * 0.1
        y = np.linspace(0.1, 0.9, 32)
        d = ed4.design(phi, z, built, rx, rz, y)
        beta = rng.normal(size=ed4.WIDTH) * 1e-4
        direct = ed4.derivatives(beta, d)
        adapted = qchoice.derivatives(beta, d)
        self.assertEqual(direct[0], adapted[0])
        self.assertTrue(np.array_equal(direct[1], adapted[1]))
        self.assertTrue(np.array_equal(direct[2], adapted[2]))

    def test_target_barrier_and_sizing(self):
        report = stage.synthetic_contract()
        self.assertEqual(report["confirmation_target_reads"], 0)
        groups = []
        row = 0
        for pid in range(512):
            rows = [row, row + 1]
            row += 2
            groups.append({"id": pid, "stm": pid % 2, "rows": rows, "terminals": []})
        sizing = stage.sizing(groups, stage.MIN_FREE_BYTES)
        self.assertEqual(sizing["confirmation_target_reads"], 0)
        self.assertLessEqual(sizing["stage_hard_cap_seconds"], 45 * 60)
        self.assertLessEqual(sizing["workers"], sizing["cpu_max"])
        self.assertEqual(stage.PHASES[1], "verify-train-boundary")


if __name__ == "__main__":
    unittest.main()

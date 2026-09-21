from __future__ import annotations

import unittest
from jobs.tools import chinook_error_mining as m


def fp(wm=0, wk=0, bm=0, bk=0, stm=0):
    return f"{wm:013x}:{wk:013x}:{bm:013x}:{bk:013x}:{stm}"


class ChinookMiningTests(unittest.TestCase):
    def fixture(self):
        diag, sib = [], []
        for i in range(512):
            diag.append({
                "root_id": str(i),
                "b2000000_parent_regret": str(i % 128),
                "b2000000_hier_minus_parent": str((i % 9) - 4),
            })
            wm = (1 << (i % 20)) | (1 << ((i + 7) % 20))
            bm = (1 << (30 + (i % 20))) | (1 << (30 + ((i + 5) % 20)))
            if i % 2 == 0:
                wk = 1 << 20
            else:
                wk = 0
            board = fp(wm, wk, bm, 0, i % 2)
            legal = 2 if i % 3 else 4
            is_gross_pattern = (i % 128) >= 112
            for j in range(legal):
                sib.append({
                    "parent_id": str(i),
                    "parent_fingerprint": board,
                    "parent_stm": str(i % 2),
                    "parent_phase": f"P{(i // 128)}",
                    "parent_legal_moves": str(legal),
                    "num_captures": "2" if (is_gross_pattern and j == 0) else "0",
                    "promotes": "1" if (i % 11 == 0 and j == 0) else "0",
                    "moving_king": "1" if (i % 2 == 0 and j == 0) else "0",
                    "captured_kings": "1" if (is_gross_pattern and j == 0) else "0",
                })
        return diag, sib

    def test_tail_and_pattern_detection(self):
        diag, sib = self.fixture()
        summary, rows = m.analyze(diag, sib)
        self.assertEqual(summary["roots"], 512)
        self.assertGreaterEqual(summary["gross_tail_tie_inclusive_roots"], 64)
        self.assertFalse(summary["reference_is_ground_truth"])
        self.assertEqual(summary["new_scan_searches"], 0)
        hit = [r for r in rows if r["feature"] == "multi_capture_available" and r["value"] == "true"][0]
        self.assertGreater(hit["lift"], 1.0)

    def test_historical_sibling_superset_is_allowed(self):
        diag, sib = self.fixture()
        sib.append(dict(sib[0], parent_id="outside-root", parent_fingerprint=fp(1<<40,0,1<<10,0,0)))
        summary, _ = m.analyze(diag, sib)
        self.assertEqual(summary["roots"], 512)

    def test_root_coverage_is_fail_closed(self):
        diag, sib = self.fixture()
        sib = [r for r in sib if r["parent_id"] != "511"]
        with self.assertRaises(ValueError):
            m.analyze(diag, sib)

    def test_fingerprint_overlap_rejected(self):
        with self.assertRaises(ValueError):
            m.parse_fp(fp(1, 1, 0, 0, 0))

    def test_no_score_derived_features(self):
        diag, sib = self.fixture()
        _, rows = m.analyze(diag, sib)
        forbidden = {"regret", "scan", "hier"}
        for r in rows:
            self.assertTrue(all(x not in r["feature"] for x in forbidden))


if __name__ == "__main__":
    unittest.main()

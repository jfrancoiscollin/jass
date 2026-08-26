import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from jobs.tools.deep_sibling_confirmation import bootstrap_pairwise, load_policy
from jobs.tools.deep_sibling_fresh_select import Candidate, choose
from jobs.tools.deep_sibling_pairwise import MOVE_FEATURE_NAMES


class DeepSiblingPhaseBTests(unittest.TestCase):
    @staticmethod
    def candidate(i: int, phase: str) -> Candidate:
        pieces = {"P0": 35, "P1": 25, "P2": 15, "P3": 10}[phase]
        canonical = f"{i:013x}:{0:013x}:{(i+1):013x}:{0:013x}:0"
        return Candidate(
            canonical=canonical,
            raw_fp=canonical,
            rec=b"x" * 38,
            stm=0,
            pieces=pieces,
            legal_moves=2,
            phase=phase,
            source_row_index=i,
            sample_hash=f"{i:064x}",
        )

    def test_fresh_selection_keeps_phase_quota_when_reachable_and_fills(self):
        unique = {}
        i = 1
        for ph, n in (("P0", 600), ("P1", 600), ("P2", 300), ("P3", 700)):
            for _ in range(n):
                c = self.candidate(i, ph)
                unique[c.canonical] = c
                i += 1
        selected, receipt = choose(unique, total=2000, quota=500)
        self.assertEqual(len(selected), 2000)
        self.assertEqual(receipt["phase_quota_initial_take"], {"P0": 500, "P1": 500, "P2": 300, "P3": 500})
        self.assertEqual(receipt["phase_selected"]["P2"], 300)
        self.assertGreaterEqual(receipt["phase_selected"]["P0"], 500)
        self.assertGreaterEqual(receipt["phase_selected"]["P1"], 500)
        self.assertGreaterEqual(receipt["phase_selected"]["P3"], 500)
        again, _ = choose(unique, total=2000, quota=500)
        self.assertEqual([c.canonical for c in selected], [c.canonical for c in again])

    def test_fresh_selection_fails_if_less_than_2000_support(self):
        unique = {self.candidate(i, "P0").canonical: self.candidate(i, "P0") for i in range(100)}
        with self.assertRaises(ValueError):
            choose(unique, total=2000, quota=500)

    def test_confirmation_bootstrap_positive_signal(self):
        delta = np.asarray([0.05, 0.10, 0.15, 0.20], dtype=np.float64)
        out = bootstrap_pairwise(delta, samples=2000, seed=2026083103)
        self.assertGreater(out["ci_low"], 0.0)
        self.assertEqual(out["cluster"], "parent")

    def test_policy_loader_enforces_frozen_feature_contract(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "policy.json"
            payload = {
                "schema": "jass.deep_sibling_policy.v1",
                "usable": True,
                "eval_feature_width": 120,
                "move_feature_names": MOVE_FEATURE_NAMES,
                "score_convention": "higher_is_better_for_parent",
                "weights": {"white_parent": [0.0] * 126, "black_parent": [0.0] * 126},
            }
            p.write_text(json.dumps(payload))
            w = load_policy(p)
            self.assertEqual(w[0].shape, (126,))
            self.assertEqual(w[1].shape, (126,))
            payload["weights"]["black_parent"] = [0.0] * 125
            p.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):
                load_policy(p)


if __name__ == "__main__":
    unittest.main()

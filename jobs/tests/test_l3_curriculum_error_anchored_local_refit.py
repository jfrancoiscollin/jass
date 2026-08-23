#!/usr/bin/env python3
from __future__ import annotations

import unittest
from unittest import mock

import numpy as np

from jobs.tools import l3_curriculum_error_action_ranker as ranker
from jobs.tools import l3_curriculum_error_anchored_local_refit as target


A = "1-2"
B = "3-4"


def _state(index: int, phase: str, teacher_gap: float) -> dict:
    width = len(ranker.FEATURE_NAMES)
    first = np.zeros(width)
    second = np.zeros(width)
    second[0] = 1.0 + 0.01 * index
    second[1] = 0.5
    return {
        "profile": {"source": {"test_phase": phase}},
        "features": {A: first, B: second},
        "original_scores": {A: 0.0, B: 0.0},
        "image_scores": {A: 0.0, B: 0.0},
        "values": {A: 0.0, B: teacher_gap},
    }


def _rows(count: int, *, endgame_every: int = 0) -> list[dict]:
    output = []
    for index in range(count):
        phase = "endgame" if endgame_every and index % endgame_every == 0 else "midgame"
        output.append(
            {
                "pair_id": index,
                "error": _state(index, phase, 100.0),
                "control": _state(index + 1000, phase, 20.0),
            }
        )
    return output


def _support() -> dict:
    return {
        "feature_indices": [0, 1],
        "feature_names": [ranker.FEATURE_NAMES[0], ranker.FEATURE_NAMES[1]],
        "feature_count": 2,
        "support_sha256": "a" * 64,
        "signed_features": [
            {"index": 0, "name": ranker.FEATURE_NAMES[0], "sign": 1},
            {"index": 1, "name": ranker.FEATURE_NAMES[1], "sign": 1},
        ],
    }


class AnchoredLocalRefitTests(unittest.TestCase):
    def test_delta_changes_only_support_and_respects_both_trust_regions(self) -> None:
        historical_rows = _rows(80, endgame_every=5)
        confirmed_rows = _rows(40, endgame_every=4)
        with mock.patch.object(
            target.confirmation,
            "_phase",
            side_effect=lambda state: state["profile"]["source"]["test_phase"],
        ):
            model, diagnostics = target._fit_anchored_delta(
                historical_rows, confirmed_rows, _support()
            )

        base = np.asarray(model["base_coef"])
        fitted = np.asarray(model["coef"])
        delta = np.asarray(model["delta"])
        self.assertTrue(np.array_equal(base[2:], fitted[2:]))
        self.assertTrue(np.all(np.sign(base[:2]) == np.sign(fitted[:2])))
        self.assertLessEqual(
            float(np.linalg.norm(delta)), diagnostics["global_cap_l2"] + 1e-12
        )
        self.assertTrue(all(diagnostics["gates"].values()))
        self.assertAlmostEqual(diagnostics["historical_weight"], 0.5)
        self.assertAlmostEqual(diagnostics["confirmed_weight"], 0.5)
        self.assertEqual(diagnostics["historical_endgame_states_excluded"], 32)
        self.assertEqual(diagnostics["confirmed_endgame_states_excluded"], 20)
        self.assertTrue(model["authorized_for_oos_audit"])
        self.assertFalse(model["authorized_for_strength"])

    def test_endgame_only_corpus_fails_closed(self) -> None:
        with (
            mock.patch.object(
                target.confirmation,
                "_phase",
                side_effect=lambda state: state["profile"]["source"]["test_phase"],
            ),
            self.assertRaisesRegex(ValueError, "zero non-endgame comparison weight"),
        ):
            target._fit_anchored_delta(
                _rows(10, endgame_every=1), _rows(10, endgame_every=1), _support()
            )

    def test_support_name_index_drift_fails_closed(self) -> None:
        support = _support()
        support["feature_names"][0] = "wrong"
        with self.assertRaisesRegex(ValueError, "feature identity drift"):
            target._fit_anchored_delta(_rows(10), _rows(10), support)


if __name__ == "__main__":
    unittest.main()

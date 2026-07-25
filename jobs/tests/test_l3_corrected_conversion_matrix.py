from pathlib import Path
import json
import tempfile
import unittest

from jobs.tools.l3_corrected_conversion_matrix import (
    build_matrix,
    paired_conversion,
    position_outcomes,
)


def document(results):
    n_win = sum(result == "win" for result in results)
    n_draw = sum(result == "draw" for result in results)
    n_loss = sum(result == "loss" for result in results)
    return {
        "n_pos": len(results),
        "n_win": n_win,
        "n_draw": n_draw,
        "n_loss": n_loss,
        "conversion": n_win / len(results),
        "position_results": [
            {"index": index, "result": result}
            for index, result in enumerate(results)
        ],
    }


class CorrectedConversionMatrixTests(unittest.TestCase):
    def test_draws_remain_paired_nonconversion_outcomes(self):
        candidate = document(["win", "draw", "loss", "win"])
        baseline = document(["loss", "win", "draw", "win"])

        result = paired_conversion(
            candidate, baseline, seed=7, bootstrap_samples=2_000
        )

        self.assertEqual(result["n_common"], 4)
        self.assertEqual(result["baseline_win_to_candidate_nonwin"], 1)
        self.assertEqual(result["same_conversion_status"], 2)
        self.assertEqual(result["baseline_nonwin_to_candidate_win"], 1)
        self.assertEqual(result["delta"], 0.0)
        self.assertTrue(result["draws_count_as_nonconversion"])

    def test_matrix_selects_positive_p4_challenger_without_promotion(self):
        outcomes = {
            "C0": {
                "p3_mince": ["win", "loss", "draw", "loss"],
                "p4_egal": ["win", "loss", "draw", "loss"],
            },
            "A": {
                "p3_mince": ["win", "loss", "draw", "loss"],
                "p4_egal": ["win", "win", "draw", "loss"],
            },
            "B": {
                "p3_mince": ["loss", "loss", "draw", "loss"],
                "p4_egal": ["loss", "loss", "draw", "loss"],
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for model, strata in outcomes.items():
                for stratum, values in strata.items():
                    (root / f"{model}-{stratum}.json").write_text(
                        json.dumps(document(values)), encoding="utf-8"
                    )

            payload = build_matrix(
                conversion_dir=root,
                models=["C0", "A", "B"],
                strata=["p3_mince", "p4_egal"],
                baseline="C0",
                primary_stratum="p4_egal",
                preservation_stratum="p3_mince",
                bootstrap_samples=2_000,
                seed=11,
            )

        self.assertEqual(payload["ranking_vs_baseline"][0], "A")
        self.assertEqual(payload["selected_challenger_for_force_review"], "A")
        self.assertTrue(payload["eligibility"]["A"]["eligible_for_force_review"])
        self.assertFalse(payload["promotion_authorized"])
        self.assertIsNone(payload["automatic_next_job"])

    def test_duplicate_position_index_is_rejected(self):
        bad = document(["win"])
        bad["position_results"].append({"index": 0, "result": "loss"})
        with self.assertRaisesRegex(ValueError, "duplicate position index"):
            position_outcomes(bad)


if __name__ == "__main__":
    unittest.main()

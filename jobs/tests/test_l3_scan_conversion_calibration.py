from pathlib import Path
import json
import tempfile
import unittest

from jobs.tools.l3_scan_conversion_calibration import (
    build_calibration,
    target_status,
    wilson_interval,
)


def document(results):
    wins = sum(result == "win" for result in results)
    draws = sum(result == "draw" for result in results)
    losses = sum(result == "loss" for result in results)
    return {
        "n_pos": len(results),
        "n_win": wins,
        "n_draw": draws,
        "n_loss": losses,
        "conversion": wins / len(results),
        "position_results": [
            {"index": index, "result": result}
            for index, result in enumerate(results)
        ],
    }


class ScanConversionCalibrationTests(unittest.TestCase):
    def test_wilson_and_target_status(self):
        low, high = wilson_interval(80, 100)
        self.assertLess(low, 0.8)
        self.assertGreater(high, 0.8)
        self.assertEqual(target_status(0.8, low, 0.8), "point_estimate_only")
        self.assertEqual(target_status(0.69, 0.64, 0.7), "not_observed")
        self.assertEqual(target_status(0.8, 0.71, 0.7), "supported")

    def test_calibration_uses_0955_selected_model_and_paired_positions(self):
        models = {
            "C0": ["win", "loss", "draw", "loss"],
            "F500": ["win", "win", "draw", "loss"],
            "SCAN_D10": ["win", "win", "draw", "loss"],
            "SCAN_D12": ["win", "win", "win", "loss"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conversion = root / "conversion"
            conversion.mkdir()
            for model, results in models.items():
                for stratum in ("p3_mince", "p4_egal"):
                    (conversion / f"{model}-{stratum}.json").write_text(
                        json.dumps(document(results)), encoding="utf-8"
                    )
            source = root / "source.json"
            source.write_text(
                json.dumps(
                    {
                        "verdict": (
                            "M1_CORRECTED_CONVERSION_MATRIX_READY_HUMAN_REVIEW"
                        ),
                        "promotion_authorized": False,
                        "selected_challenger_for_force_review": "F500",
                        "ranking_vs_baseline": ["F500"],
                    }
                ),
                encoding="utf-8",
            )

            payload = build_calibration(
                conversion_dir=conversion,
                learned_models=["C0", "F500"],
                scan_models=["SCAN_D10", "SCAN_D12"],
                strata=["p3_mince", "p4_egal"],
                source_summary=source,
                bootstrap_samples=2_000,
                seed=17,
            )

        self.assertEqual(payload["best_learned_from_0955"], "F500")
        paired = payload["paired_comparisons"]["p4_egal"][
            "SCAN_D12_vs_SCAN_D10"
        ]
        self.assertEqual(paired["n_common"], 4)
        self.assertEqual(paired["delta"], 0.25)
        self.assertTrue(paired["draws_count_as_nonconversion"])
        self.assertFalse(payload["promotion_authorized"])


if __name__ == "__main__":
    unittest.main()

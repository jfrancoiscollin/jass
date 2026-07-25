from pathlib import Path
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "jobs/tools"))

from l3_repaired_engine_matrix import build_report  # noqa: E402


def conversion(results):
    wins = sum(result == "win" for result in results)
    draws = sum(result == "draw" for result in results)
    losses = sum(result == "loss" for result in results)
    return {
        "n_pos": len(results),
        "n_win": wins,
        "n_draw": draws,
        "n_loss": losses,
        "conversion": wins / len(results),
        "n_errors": 0,
        "position_results": [
            {"index": index, "result": result}
            for index, result in enumerate(results)
        ],
    }


class RepairedEngineMatrixTests(unittest.TestCase):
    def test_report_is_paired_and_keeps_decisions_manual(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            new_dir = root / "new"
            baseline_dir = root / "baseline"
            new_dir.mkdir()
            baseline_dir.mkdir()
            models = ["C0", "F500", "F2M", "R2M"]
            strata = ["p3", "p4"]
            before = ["win", "loss", "loss", "loss"] * 25
            after = ["win"] * 95 + ["loss"] * 5
            for model in models:
                for stratum in strata:
                    (baseline_dir / f"baseline-{model}-{stratum}.json").write_text(
                        json.dumps(conversion(before)), encoding="utf-8"
                    )
                    (new_dir / f"{model}-{stratum}.json").write_text(
                        json.dumps(conversion(after)), encoding="utf-8"
                    )

            matrix = {
                "verdict": "M1_CORRECTED_CONVERSION_MATRIX_READY_HUMAN_REVIEW",
                "ranking_vs_baseline": ["F500", "F2M", "R2M"],
                "selected_challenger_for_force_review": "F500",
                "force": {"q00_vs_C0": {"rate": 0.51}},
            }
            (baseline_dir / "baseline-matrix.json").write_text(
                json.dumps(matrix), encoding="utf-8"
            )
            new_matrix = root / "new-matrix.json"
            new_matrix.write_text(json.dumps(matrix), encoding="utf-8")
            repair_summary = root / "repair.json"
            repair_summary.write_text(
                json.dumps(
                    {
                        "verdict": "LEGALITY_REPAIR_RECOVERS_CONVERSION",
                        "promotion_authorized": False,
                        "conversion": {},
                    }
                ),
                encoding="utf-8",
            )

            report = build_report(
                new_dir=new_dir,
                baseline_dir=baseline_dir,
                new_matrix_path=new_matrix,
                repair_summary_path=repair_summary,
                models=models,
                strata=strata,
                m1_arms=["F500", "F2M", "R2M"],
                bootstrap_samples=2_000,
                seed=962_001,
            )

        self.assertEqual(
            report["verdict"],
            "M1_REPAIRED_ENGINE_MATRIX_READY_HUMAN_REVIEW",
        )
        self.assertEqual(
            report["m1_arms_passing_floor"], ["F500", "F2M", "R2M"]
        )
        paired = report["paired_repair_effect"]["F500"]["p3"][
            "paired_repair_effect"
        ]
        self.assertAlmostEqual(paired["delta"], 0.70)
        self.assertFalse(report["training_authorized"])
        self.assertFalse(report["promotion_authorized"])
        self.assertIsNone(report["automatic_next_job"])

    def test_rejects_uncertified_repair(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repair_summary = root / "repair.json"
            repair_summary.write_text(
                json.dumps(
                    {
                        "verdict": "OTHER",
                        "promotion_authorized": False,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "repair"):
                build_report(
                    new_dir=root,
                    baseline_dir=root,
                    new_matrix_path=root / "missing.json",
                    repair_summary_path=repair_summary,
                    models=["F500"],
                    strata=["p3"],
                    m1_arms=["F500"],
                    bootstrap_samples=10,
                    seed=1,
                )


if __name__ == "__main__":
    unittest.main()

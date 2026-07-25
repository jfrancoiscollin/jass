from pathlib import Path
import json
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "jobs/tools"))

from l3_repaired_m1_force_review import build_review  # noqa: E402


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def force(rate: float, ci_low: float, ci_high: float) -> dict:
    wins = int(round(rate * 400))
    return {
        "n": 400,
        "wins_a": wins,
        "draws": 0,
        "wins_b": 400 - wins,
        "rate": rate,
        "elo": 0.0,
        "ci_low": ci_low,
        "ci_high": ci_high,
    }


def coverage(records: int, visited: int, ge100: int) -> dict:
    return {
        "stage": "l3_bucket_visits",
        "geometry": {"trained_buckets_total": 2_125_768},
        "corpus": {"total_records": records},
        "coverage": {
            "visited_buckets": visited,
            "coverage_fraction": visited / 2_125_768,
            "buckets_with_at_least": {"ge_10": ge100 + 100, "ge_100": ge100},
            "frac_buckets_ge_100": ge100 / 2_125_768,
        },
        "concentration": {"gini": 0.5},
    }


class RepairedM1ForceReviewTests(unittest.TestCase):
    def test_only_arm_passing_all_preregistered_checks_is_selected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            force_dir = root / "force"
            coverage_dir = root / "coverage"
            force_dir.mkdir()
            coverage_dir.mkdir()
            matrix = root / "matrix.json"
            training = root / "training.json"
            write_json(
                matrix,
                {
                    "verdict": "M1_REPAIRED_ENGINE_MATRIX_READY_HUMAN_REVIEW",
                    "m1_arms_passing_floor": ["F500", "F2M", "R2M"],
                },
            )
            write_json(
                training,
                {"verdict": "M1_TRAINING_SCREEN_READY", "arms": {}},
            )

            rows = {
                "F500": {
                    "q00_vs_C0": force(0.52, 0.47, 0.57),
                    "native_vs_C0": force(0.49, 0.44, 0.54),
                    "q00_vs_GEN2": force(0.53, 0.48, 0.58),
                },
                "F2M": {
                    "q00_vs_C0": force(0.53, 0.48, 0.58),
                    "native_vs_C0": force(0.52, 0.47, 0.57),
                    "q00_vs_GEN2": force(0.44, 0.39, 0.49),
                },
                "R2M": {
                    "q00_vs_C0": force(0.54, 0.49, 0.59),
                    "native_vs_C0": force(0.53, 0.48, 0.58),
                    "q00_vs_GEN2": force(0.52, 0.47, 0.57),
                },
            }
            for arm, views in rows.items():
                for view, payload in views.items():
                    view_name, opponent = view.split("_vs_")
                    write_json(
                        force_dir / f"force-{view_name}-{arm}-vs-{opponent}.json",
                        payload,
                    )

            write_json(coverage_dir / "C0-coverage.json", coverage(6_000_000, 1000, 400))
            write_json(coverage_dir / "F500-coverage.json", coverage(500_000, 800, 300))
            write_json(coverage_dir / "F2M-coverage.json", coverage(2_000_000, 1100, 500))
            write_json(coverage_dir / "R2M-coverage.json", coverage(6_500_000, 1200, 600))

            review = build_review(
                matrix_path=matrix,
                force_dir=force_dir,
                coverage_dir=coverage_dir,
                training_summary_path=training,
            )

        self.assertEqual(
            review["verdict"], "M1_REPAIRED_FORCE_COVERAGE_REVIEW_READY"
        )
        self.assertEqual(review["eligible_arms"], ["R2M"])
        self.assertEqual(review["selected_m1_arm_for_confirmation"], "R2M")
        self.assertFalse(
            review["eligibility"]["F500"]["native_slope_positive_vs_c0"]
        )
        self.assertFalse(
            review["eligibility"]["F2M"]["gen2_regression_not_established"]
        )
        self.assertFalse(review["confirmation_authorized"])
        self.assertFalse(review["promotion_authorized"])
        self.assertIsNone(review["automatic_next_job"])

    def test_rejects_wrong_matrix_or_force_size(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            matrix = root / "matrix.json"
            training = root / "training.json"
            write_json(matrix, {"verdict": "OLD"})
            write_json(training, {"verdict": "M1_TRAINING_SCREEN_READY"})
            with self.assertRaisesRegex(ValueError, "matrix"):
                build_review(
                    matrix_path=matrix,
                    force_dir=root,
                    coverage_dir=root,
                    training_summary_path=training,
                )


if __name__ == "__main__":
    unittest.main()

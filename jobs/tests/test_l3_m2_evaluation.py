import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools.l3_m2_evaluation import (
    DIRECTIONAL,
    PLATEAU,
    PROMOTION,
    build_evaluation,
)


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def force(rate: float, low: float, high: float) -> dict:
    return {
        "n": 1000,
        "wins_a": round(rate * 1000),
        "draws": 0,
        "wins_b": 1000 - round(rate * 1000),
        "rate": rate,
        "elo": 0.0,
        "ci_low": low,
        "ci_high": high,
    }


def conversion(rate: float, outcomes: list[str]) -> dict:
    wins = sum(value == "win" for value in outcomes)
    draws = sum(value == "draw" for value in outcomes)
    return {
        "n_pos": len(outcomes),
        "n_win": wins,
        "n_draw": draws,
        "n_loss": len(outcomes) - wins - draws,
        "conversion": rate,
        "position_results": [
            {"index": index, "result": result}
            for index, result in enumerate(outcomes)
        ],
    }


def coverage(visited: int, ge100: int) -> dict:
    return {
        "stage": "l3_bucket_visits",
        "geometry": {"trained_buckets_total": 2_125_768},
        "corpus": {"total_records": 2_000_000},
        "coverage": {
            "visited_buckets": visited,
            "buckets_with_at_least": {
                "ge_1": visited,
                "ge_10": ge100 * 2,
                "ge_100": ge100,
                "ge_1000": 0,
            },
        },
        "concentration": {"gini": 0.8},
    }


class M2EvaluationTests(unittest.TestCase):
    def prepare(self, root: Path, primary_rate: float, primary_low: float):
        force_dir = root / "force"
        conv_dir = root / "conversion"
        cov_dir = root / "coverage"
        for directory in (force_dir, conv_dir, cov_dir):
            directory.mkdir()
        training = root / "training.json"
        champion = root / "champion.json"
        openings = root / "openings.json"
        write(training, {"verdict": "M2_TRAINING_SCREEN_READY", "parent": "F2M", "fresh_only": True})
        write(
            champion,
            {
                "verdict": "F2M_NEW_GENERAL_CHAMPION_HUMAN_REVIEW",
                "recommended_general_champion": "F2M",
                "force": {
                    "q00": force(0.5725, 0.54, 0.60),
                    "native": force(0.586, 0.55, 0.62),
                },
            },
        )
        write(openings, {"records": 500, "unique_records": 500, "overlap_records": 0})
        for view in ("q00", "native"):
            write(
                force_dir / f"force-{view}-M2-vs-F2M.json",
                force(primary_rate, primary_low, 0.57),
            )
            write(
                force_dir / f"force-{view}-M2-vs-GEN2.json",
                force(0.58, 0.55, 0.61),
            )
        baseline = ["win"] * 294 + ["loss"] * 6
        candidate = ["win"] * 295 + ["loss"] * 5
        for stratum in ("p3_mince", "p4_egal"):
            write(conv_dir / f"F2M-{stratum}.json", conversion(0.98, baseline))
            write(conv_dir / f"M2-{stratum}.json", conversion(0.983333, candidate))
        write(cov_dir / "F2M-coverage.json", coverage(200_000, 25_000))
        write(cov_dir / "M2-coverage.json", coverage(205_000, 26_000))
        return force_dir, conv_dir, cov_dir, training, champion, openings

    def build(self, prepared):
        force_dir, conv_dir, cov_dir, training, champion, openings = prepared
        return build_evaluation(
            force_dir=force_dir,
            conversion_dir=conv_dir,
            coverage_dir=cov_dir,
            training_summary_path=training,
            champion_benchmark_path=champion,
            opening_manifest_path=openings,
            bootstrap_samples=2_000,
        )

    def test_promotion_review_requires_two_confirmed_force_views(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = self.build(self.prepare(Path(tmp), 0.55, 0.52))
        self.assertEqual(payload["verdict"], PROMOTION)
        self.assertFalse(payload["promotion_authorized"])
        self.assertIsNone(payload["automatic_next_job"])

    def test_directional_result_requests_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = self.build(self.prepare(Path(tmp), 0.52, 0.49))
        self.assertEqual(payload["verdict"], DIRECTIONAL)
        self.assertEqual(payload["recommendation"], "independent_m2_confirmation")

    def test_plateau_routes_to_depth_causal_arm(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = self.build(self.prepare(Path(tmp), 0.49, 0.46))
        self.assertEqual(payload["verdict"], PLATEAU)
        self.assertIn("d10", payload["recommendation"])


if __name__ == "__main__":
    unittest.main()

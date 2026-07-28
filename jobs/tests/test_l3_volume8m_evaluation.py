import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools.l3_volume8m_evaluation import build


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def force(rate: float, low: float, high: float) -> dict:
    wins = round(rate * 3000)
    return {
        "n": 3000,
        "wins_a": wins,
        "draws": 0,
        "wins_b": 3000 - wins,
        "rate": rate,
        "elo": 0.0,
        "ci_low": low,
        "ci_high": high,
    }


def conversion(wins: int) -> dict:
    outcomes = ["win"] * wins + ["loss"] * (300 - wins)
    return {
        "n_pos": 300,
        "n_win": wins,
        "n_draw": 0,
        "n_loss": 300 - wins,
        "conversion": wins / 300,
        "position_results": [
            {"index": index, "result": result}
            for index, result in enumerate(outcomes)
        ],
    }


def coverage(records: int, visited: int) -> dict:
    return {
        "stage": "l3_bucket_visits",
        "geometry": {"trained_buckets_total": 2_125_768},
        "corpus": {"total_records": records},
        "coverage": {
            "visited_buckets": visited,
            "coverage_fraction": visited / 2_125_768,
            "buckets_with_at_least": {"ge_100": 10_000},
        },
        "concentration": {"gini": 0.8},
    }


class Volume8mEvaluationTests(unittest.TestCase):
    def prepare(
        self,
        root: Path,
        *,
        turnover: tuple[float, float, float],
        f2m: tuple[float, float, float] = (0.52, 0.49, 0.55),
    ) -> tuple[Path, Path]:
        for directory in ("force", "conversion", "coverage"):
            (root / directory).mkdir()
        training = root / "training.json"
        preflight = root / "preflight.json"
        write(
            training,
            {
                "verdict": "L3_PURE_VOLUME8M_FIT_CONVERGED",
                "model": {"name": "VOL8M", "sha256": "a" * 64},
                "training": {"records": 12_000_000, "converged": True},
                "holdout_loss_is_a_diagnostic_not_a_selection_criterion": True,
                "promotion_authorized": False,
                "automatic_next_job": None,
            },
        )
        visited = 287_998
        write(
            preflight,
            {
                "verdict": "L3_PURE_VOLUME8M_PREFLIGHT_READY",
                "coverage": {
                    "visited_buckets": visited,
                    "visited_pct": round(100 * visited / 2_125_768, 3),
                },
                "promotion_authorized": False,
                "automatic_next_job": None,
            },
        )
        rates = {
            "TURNOVER": turnover,
            "M2": (0.52, 0.49, 0.55),
            "F2M": f2m,
            "GEN2": (0.56, 0.53, 0.59),
        }
        for view in ("q00", "native"):
            for opponent, values in rates.items():
                write(
                    root / "force" / f"force-{view}-VOL8M-vs-{opponent}.json",
                    force(*values),
                )
        for stratum in ("p3_mince", "p4_egal"):
            write(root / "conversion" / f"VOL8M-{stratum}.json", conversion(296))
            for opponent in ("TURNOVER", "M2", "F2M"):
                write(
                    root / "conversion" / f"{opponent}-{stratum}.json",
                    conversion(295),
                )
        for model, (records, buckets) in {
            "VOL8M": (12_000_000, visited),
            "TURNOVER": (2_000_000, 208_914),
            "M2": (2_000_000, 210_000),
            "F2M": (2_000_000, 205_000),
        }.items():
            write(
                root / "coverage" / f"{model}-coverage.json",
                coverage(records, buckets),
            )
        return training, preflight

    def test_confirmed_gain_requires_both_views_and_keeps_guards_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            training, preflight = self.prepare(
                root, turnover=(0.55, 0.52, 0.58)
            )
            result = build(root, training, preflight, bootstrap_samples=1000)
        self.assertEqual(result["verdict"], "VOL8M_FORCE_GAIN_CONFIRMED_REVIEW")
        self.assertTrue(result["decision"]["coverage_gain_vs_turnover"])
        self.assertFalse(result["promotion_authorized"])
        self.assertIsNone(result["automatic_next_job"])

    def test_flat_and_regression_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            training, preflight = self.prepare(
                root, turnover=(0.50, 0.47, 0.53)
            )
            result = build(root, training, preflight, bootstrap_samples=100)
        self.assertEqual(result["verdict"], "VOL8M_AXIS_FLAT_REVIEW")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            training, preflight = self.prepare(
                root,
                turnover=(0.52, 0.49, 0.55),
                f2m=(0.44, 0.41, 0.47),
            )
            result = build(root, training, preflight, bootstrap_samples=100)
        self.assertEqual(result["verdict"], "VOL8M_REGRESSION_DIAGNOSIS_REQUIRED")


if __name__ == "__main__":
    unittest.main()

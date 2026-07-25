import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools.l3_d10_causal_evaluation import (
    D10_OPENINGS_SHA256,
    DEPTH_CONFIRMED,
    DIRECTIONAL,
    PLATEAU,
    PROMOTION_SCALE,
    build_evaluation,
)


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def force(rate: float, low: float, high: float) -> dict:
    wins = round(rate * 1000)
    return {
        "n": 1000,
        "wins_a": wins,
        "draws": 0,
        "wins_b": 1000 - wins,
        "rate": rate,
        "elo": 0.0,
        "ci_low": low,
        "ci_high": high,
    }


def conversion(outcomes: list[str]) -> dict:
    wins = sum(value == "win" for value in outcomes)
    draws = sum(value == "draw" for value in outcomes)
    return {
        "n_pos": len(outcomes),
        "n_win": wins,
        "n_draw": draws,
        "n_loss": len(outcomes) - wins - draws,
        "conversion": wins / len(outcomes),
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


class D10CausalEvaluationTests(unittest.TestCase):
    def prepare(
        self,
        root: Path,
        *,
        depth_rate: float,
        depth_low: float,
        f2m_rate: float,
        f2m_low: float,
    ):
        force_dir = root / "force"
        conv_dir = root / "conversion"
        cov_dir = root / "coverage"
        for directory in (force_dir, conv_dir, cov_dir):
            directory.mkdir()
        training = root / "training.json"
        d8_training = root / "d8-training.json"
        m2_evaluation = root / "m2-evaluation.json"
        openings = root / "openings.json"
        write(
            training,
            {
                "verdict": "M2_TRAINING_SCREEN_READY",
                "parent": "F2M",
                "fresh_only": True,
                "experiment_variant": "D10_CAUSAL_FRESH2M",
                "play_depth": 10,
            },
        )
        write(
            d8_training,
            {
                "verdict": "M2_TRAINING_SCREEN_READY",
                "model_sha256": (
                    "75ace3c0ad2ffa2b71a9b9073c3c1d1545164e3a5a048e411e91adba23ec3b45"
                ),
            },
        )
        write(
            m2_evaluation,
            {
                "verdict": "M2_PLATEAU_OR_REGRESSION_REVIEW",
                "all_guardrails_pass": True,
                "force": {
                    "q00_vs_GEN2": force(0.56, 0.53, 0.59),
                    "native_vs_GEN2": force(0.58, 0.55, 0.61),
                },
            },
        )
        write(
            openings,
            {
                "records": 500,
                "unique_records": 500,
                "overlap_records": 0,
                "generator_seed": 314159,
                "sha256": D10_OPENINGS_SHA256,
                "excluded_sources": {"/tmp/prior-m2-independent.fen": 500},
            },
        )
        for view in ("q00", "native"):
            write(
                force_dir / f"force-{view}-D10-vs-M2.json",
                force(depth_rate, depth_low, 0.58),
            )
            write(
                force_dir / f"force-{view}-D10-vs-F2M.json",
                force(f2m_rate, f2m_low, 0.58),
            )
            write(
                force_dir / f"force-{view}-D10-vs-GEN2.json",
                force(0.58, 0.55, 0.61),
            )
        baseline = ["win"] * 294 + ["loss"] * 6
        candidate = ["win"] * 295 + ["loss"] * 5
        for stratum in ("p3_mince", "p4_egal"):
            write(conv_dir / f"D10-{stratum}.json", conversion(candidate))
            write(conv_dir / f"M2-{stratum}.json", conversion(baseline))
            write(conv_dir / f"F2M-{stratum}.json", conversion(baseline))
        write(cov_dir / "D10-coverage.json", coverage(207_000, 28_000))
        write(cov_dir / "M2-coverage.json", coverage(206_000, 27_800))
        write(cov_dir / "F2M-coverage.json", coverage(204_000, 27_400))
        return (
            force_dir,
            conv_dir,
            cov_dir,
            training,
            d8_training,
            m2_evaluation,
            openings,
        )

    def build(self, prepared):
        (
            force_dir,
            conv_dir,
            cov_dir,
            training,
            d8_training,
            m2_evaluation,
            openings,
        ) = prepared
        return build_evaluation(
            force_dir=force_dir,
            conversion_dir=conv_dir,
            coverage_dir=cov_dir,
            training_summary_path=training,
            d8_training_summary_path=d8_training,
            m2_evaluation_path=m2_evaluation,
            opening_manifest_path=openings,
            bootstrap_samples=2_000,
        )

    def test_promotion_and_scale_requires_both_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.build(
                self.prepare(
                    Path(tmp),
                    depth_rate=0.56,
                    depth_low=0.53,
                    f2m_rate=0.55,
                    f2m_low=0.52,
                )
            )
        self.assertEqual(result["verdict"], PROMOTION_SCALE)
        self.assertFalse(result["promotion_authorized"])

    def test_depth_effect_can_precede_f2m_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.build(
                self.prepare(
                    Path(tmp),
                    depth_rate=0.55,
                    depth_low=0.52,
                    f2m_rate=0.51,
                    f2m_low=0.48,
                )
            )
        self.assertEqual(result["verdict"], DEPTH_CONFIRMED)

    def test_directional_signal_requests_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.build(
                self.prepare(
                    Path(tmp),
                    depth_rate=0.52,
                    depth_low=0.49,
                    f2m_rate=0.51,
                    f2m_low=0.48,
                )
            )
        self.assertEqual(result["verdict"], DIRECTIONAL)

    def test_flat_depth_routes_to_d12_or_mix(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.build(
                self.prepare(
                    Path(tmp),
                    depth_rate=0.49,
                    depth_low=0.46,
                    f2m_rate=0.49,
                    f2m_low=0.46,
                )
            )
        self.assertEqual(result["verdict"], PLATEAU)
        self.assertIn("d12", result["recommendation"])


if __name__ == "__main__":
    unittest.main()

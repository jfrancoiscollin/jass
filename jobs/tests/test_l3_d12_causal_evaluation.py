import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools.l3_d12_causal_evaluation import (
    DEPTH_CONFIRMED,
    DIRECTIONAL,
    PLATEAU,
    PROMOTION_SCALE,
    build_evaluation,
)


OPENING_SEED = 424243
OPENING_SHA = "a" * 64


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


class D12CausalEvaluationTests(unittest.TestCase):
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
        d10_training = root / "d10-training.json"
        d10_evaluation = root / "d10-evaluation.json"
        openings = root / "openings.json"
        d10_sha = "1" * 64
        write(
            training,
            {
                "verdict": "M2_TRAINING_SCREEN_READY",
                "parent": "F2M",
                "fresh_only": True,
                "experiment_variant": "D12_CAUSAL_FRESH2M",
                "play_depth": 12,
            },
        )
        write(
            d10_training,
            {
                "verdict": "M2_TRAINING_SCREEN_READY",
                "parent": "F2M",
                "fresh_only": True,
                "experiment_variant": "D10_CAUSAL_FRESH2M",
                "play_depth": 10,
                "model_sha256": d10_sha,
            },
        )
        write(
            d10_evaluation,
            {
                "verdict": "D10_PLATEAU_OR_REGRESSION_REVIEW",
                "all_guardrails_pass": True,
                "training_summary": {"model_sha256": d10_sha},
                "force": {
                    "q00_vs_GEN2": force(0.57, 0.54, 0.60),
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
                "generator_seed": OPENING_SEED,
                "sha256": OPENING_SHA,
                "excluded_sources": {
                    "/tmp/prior-m2-independent.fen": 500,
                    "/tmp/prior-d10-independent.fen": 500,
                },
            },
        )
        for view in ("q00", "native"):
            write(
                force_dir / f"force-{view}-D12-vs-D10.json",
                force(depth_rate, depth_low, 0.58),
            )
            write(
                force_dir / f"force-{view}-D12-vs-F2M.json",
                force(f2m_rate, f2m_low, 0.58),
            )
            write(
                force_dir / f"force-{view}-D12-vs-GEN2.json",
                force(0.58, 0.55, 0.61),
            )
        baseline = ["win"] * 294 + ["loss"] * 6
        candidate = ["win"] * 295 + ["loss"] * 5
        for stratum in ("p3_mince", "p4_egal"):
            write(conv_dir / f"D12-{stratum}.json", conversion(candidate))
            write(conv_dir / f"D10-{stratum}.json", conversion(baseline))
            write(conv_dir / f"F2M-{stratum}.json", conversion(baseline))
        write(cov_dir / "D12-coverage.json", coverage(207_000, 28_000))
        write(cov_dir / "D10-coverage.json", coverage(202_000, 27_000))
        write(cov_dir / "F2M-coverage.json", coverage(204_000, 27_400))
        return (
            force_dir,
            conv_dir,
            cov_dir,
            training,
            d10_training,
            d10_evaluation,
            openings,
        )

    def build(self, prepared):
        (
            force_dir,
            conv_dir,
            cov_dir,
            training,
            d10_training,
            d10_evaluation,
            openings,
        ) = prepared
        return build_evaluation(
            force_dir=force_dir,
            conversion_dir=conv_dir,
            coverage_dir=cov_dir,
            training_summary_path=training,
            d10_training_summary_path=d10_training,
            d10_evaluation_path=d10_evaluation,
            opening_manifest_path=openings,
            expected_opening_seed=OPENING_SEED,
            expected_opening_sha256=OPENING_SHA,
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

    def test_flat_depth_routes_to_distribution_factor(self):
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
        self.assertIn("distribution", result["recommendation"])

    def test_opening_pool_must_exclude_both_prior_causal_pools(self):
        with tempfile.TemporaryDirectory() as tmp:
            prepared = self.prepare(
                Path(tmp),
                depth_rate=0.52,
                depth_low=0.49,
                f2m_rate=0.51,
                f2m_low=0.48,
            )
            openings = prepared[-1]
            value = json.loads(openings.read_text(encoding="utf-8"))
            value["excluded_sources"].pop("/tmp/prior-d10-independent.fen")
            write(openings, value)
            with self.assertRaisesRegex(ValueError, "opening-pool"):
                self.build(prepared)


if __name__ == "__main__":
    unittest.main()

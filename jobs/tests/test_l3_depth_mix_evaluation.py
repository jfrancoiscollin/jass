import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools.l3_depth_mix_evaluation import (
    DIRECTIONAL,
    DISTRIBUTION_CONFIRMED,
    PLATEAU,
    PROMOTION_SCALE,
    build_evaluation,
)


OPENING_SEED = 577217
OPENING_SHA = "b" * 64


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


class DepthMixEvaluationTests(unittest.TestCase):
    def prepare(
        self,
        root: Path,
        *,
        d10_rate: float,
        d10_low: float,
        d12_rate: float,
        d12_low: float,
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
        d12_training = root / "d12-training.json"
        d12_evaluation = root / "d12-evaluation.json"
        openings = root / "openings.json"
        d10_sha, d12_sha = "1" * 64, "2" * 64
        write(
            training,
            {
                "verdict": "M2_TRAINING_SCREEN_READY",
                "parent": "F2M",
                "fresh_only": True,
                "experiment_variant": "D10_D12_MIX_5_1",
                "play_depth": None,
                "training_records": 2_000_000,
                "depth_distribution_records": {
                    "d10": 1_666_667,
                    "d12": 333_333,
                },
                "new_generation_performed": False,
            },
        )
        write(
            d10_training,
            {
                "verdict": "M2_TRAINING_SCREEN_READY",
                "parent": "F2M",
                "experiment_variant": "D10_CAUSAL_FRESH2M",
                "play_depth": 10,
                "model_sha256": d10_sha,
            },
        )
        write(
            d12_training,
            {
                "verdict": "M2_TRAINING_SCREEN_READY",
                "parent": "F2M",
                "experiment_variant": "D12_CAUSAL_FRESH2M",
                "play_depth": 12,
                "model_sha256": d12_sha,
            },
        )
        d10_force = {
            "q00_vs_GEN2": force(0.57, 0.54, 0.60),
            "native_vs_GEN2": force(0.58, 0.55, 0.61),
        }
        write(
            d12_evaluation,
            {
                "verdict": "D12_PLATEAU_OR_REGRESSION_REVIEW",
                "recommendation":
                    "stop_single_depth_escalation_and_prepare_distribution_factor",
                "all_guardrails_pass": True,
                "training_summary": {"model_sha256": d12_sha},
                "d10_training_summary": {"model_sha256": d10_sha},
                "force": {
                    "q00_vs_GEN2": force(0.58, 0.55, 0.61),
                    "native_vs_GEN2": force(0.58, 0.55, 0.61),
                },
                "d10_plateau_certificate": {"force": d10_force},
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
                    "/tmp/prior-d12-independent.fen": 500,
                },
            },
        )
        rates = {
            "D10": (d10_rate, d10_low),
            "D12": (d12_rate, d12_low),
            "F2M": (f2m_rate, f2m_low),
            "GEN2": (0.58, 0.55),
        }
        for view in ("q00", "native"):
            for opponent, (rate, low) in rates.items():
                write(
                    force_dir / f"force-{view}-MIX-vs-{opponent}.json",
                    force(rate, low, 0.61),
                )
        baseline = ["win"] * 294 + ["loss"] * 6
        candidate = ["win"] * 295 + ["loss"] * 5
        for stratum in ("p3_mince", "p4_egal"):
            write(conv_dir / f"MIX-{stratum}.json", conversion(candidate))
            for model in ("D10", "D12", "F2M"):
                write(conv_dir / f"{model}-{stratum}.json", conversion(baseline))
        write(cov_dir / "MIX-coverage.json", coverage(207_000, 28_000))
        write(cov_dir / "D10-coverage.json", coverage(202_000, 27_000))
        write(cov_dir / "D12-coverage.json", coverage(203_000, 27_200))
        write(cov_dir / "F2M-coverage.json", coverage(204_000, 27_400))
        return (
            force_dir,
            conv_dir,
            cov_dir,
            training,
            d10_training,
            d12_training,
            d12_evaluation,
            openings,
        )

    def build(self, prepared):
        (
            force_dir,
            conv_dir,
            cov_dir,
            training,
            d10_training,
            d12_training,
            d12_evaluation,
            openings,
        ) = prepared
        return build_evaluation(
            force_dir=force_dir,
            conversion_dir=conv_dir,
            coverage_dir=cov_dir,
            training_summary_path=training,
            d10_training_summary_path=d10_training,
            d12_training_summary_path=d12_training,
            d12_evaluation_path=d12_evaluation,
            opening_manifest_path=openings,
            expected_opening_seed=OPENING_SEED,
            expected_opening_sha256=OPENING_SHA,
            bootstrap_samples=2_000,
        )

    def test_promotion_and_scale_requires_both_pure_controls_and_f2m(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.build(self.prepare(
                Path(tmp),
                d10_rate=0.56, d10_low=0.53,
                d12_rate=0.56, d12_low=0.53,
                f2m_rate=0.55, f2m_low=0.52,
            ))
        self.assertEqual(result["verdict"], PROMOTION_SCALE)
        self.assertFalse(result["promotion_authorized"])

    def test_distribution_effect_can_precede_f2m_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.build(self.prepare(
                Path(tmp),
                d10_rate=0.55, d10_low=0.52,
                d12_rate=0.55, d12_low=0.52,
                f2m_rate=0.51, f2m_low=0.48,
            ))
        self.assertEqual(result["verdict"], DISTRIBUTION_CONFIRMED)

    def test_directional_signal_requests_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.build(self.prepare(
                Path(tmp),
                d10_rate=0.52, d10_low=0.49,
                d12_rate=0.52, d12_low=0.49,
                f2m_rate=0.51, f2m_low=0.48,
            ))
        self.assertEqual(result["verdict"], DIRECTIONAL)

    def test_flat_mix_routes_to_next_single_factor(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.build(self.prepare(
                Path(tmp),
                d10_rate=0.49, d10_low=0.46,
                d12_rate=0.49, d12_low=0.46,
                f2m_rate=0.49, f2m_low=0.46,
            ))
        self.assertEqual(result["verdict"], PLATEAU)
        self.assertIn("replay_or_volume", result["recommendation"])

    def test_opening_pool_must_exclude_all_prior_causal_pools(self):
        with tempfile.TemporaryDirectory() as tmp:
            prepared = self.prepare(
                Path(tmp),
                d10_rate=0.52, d10_low=0.49,
                d12_rate=0.52, d12_low=0.49,
                f2m_rate=0.51, f2m_low=0.48,
            )
            openings = prepared[-1]
            value = json.loads(openings.read_text(encoding="utf-8"))
            value["excluded_sources"].pop("/tmp/prior-d12-independent.fen")
            write(openings, value)
            with self.assertRaisesRegex(ValueError, "opening-pool"):
                self.build(prepared)

    def test_mix_ratio_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            prepared = self.prepare(
                Path(tmp),
                d10_rate=0.52, d10_low=0.49,
                d12_rate=0.52, d12_low=0.49,
                f2m_rate=0.51, f2m_low=0.48,
            )
            training = prepared[3]
            value = json.loads(training.read_text(encoding="utf-8"))
            value["depth_distribution_records"]["d12"] -= 1
            write(training, value)
            with self.assertRaisesRegex(ValueError, "training contract"):
                self.build(prepared)


if __name__ == "__main__":
    unittest.main()

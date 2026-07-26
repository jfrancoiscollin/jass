import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools.l3_turnover_evaluation import (
    DIRECTIONAL,
    EFFECT,
    PLATEAU,
    PROMOTION,
    build_evaluation,
)


OPENING_SEED = 732051
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


class TurnoverEvaluationTests(unittest.TestCase):
    def prepare(
        self,
        root: Path,
        *,
        m2_rate: float,
        m2_low: float,
        m2_high: float,
        f2m_rate: float,
        f2m_low: float,
        f2m_high: float,
    ):
        force_dir = root / "force"
        conv_dir = root / "conversion"
        cov_dir = root / "coverage"
        for directory in (force_dir, conv_dir, cov_dir):
            directory.mkdir()
        training = root / "training.json"
        m2_training = root / "m2-training.json"
        m2_contract = root / "m2-contract.json"
        m2_evaluation = root / "m2-evaluation.json"
        d12_evaluation = root / "d12-evaluation.json"
        openings = root / "openings.json"
        m2_sha = "75ace3c0ad2ffa2b71a9b9073c3c1d1545164e3a5a048e411e91adba23ec3b45"
        write(
            training,
            {
                "verdict": "M2_TRAINING_SCREEN_READY",
                "parent": "F2M",
                "fresh_only": False,
                "experiment_variant": "TURNOVER_1_1",
                "play_depth": 8,
                "training_records": 2_000_000,
                "historical_replay_records": 1_000_000,
                "fresh_records": 1_000_000,
                "temporal_distribution_records": {
                    "fresh_m2": 1_000_000,
                    "parent_f2m": 1_000_000,
                },
                "new_generation_performed": False,
            },
        )
        write(
            m2_training,
            {
                "verdict": "M2_TRAINING_SCREEN_READY",
                "parent": "F2M",
                "fresh_only": True,
                "code_sha": "012b9c716dadf2c3df668c23a7dd9d5ece423b8c",
                "training_corpus_sha256":
                    "ee8d685cea331940403da82830d7b4cc045fe50acc1e5764d23f0467d4f7ffb8",
                "training_records": 2_000_000,
                "model_sha256": m2_sha,
            },
        )
        write(
            m2_contract,
            {
                "jnnw_sha256":
                    "ee8d685cea331940403da82830d7b4cc045fe50acc1e5764d23f0467d4f7ffb8",
                "jsm_sha256":
                    "42b184456375bb581192651262f3981879bd04e5ee3162a6186883c2f8f66729",
                "records": 2_000_000,
                "parent": "F2M",
                "fresh_only": True,
                "historical_replay_records": 0,
                "base_seed": 1_618_033,
                "starts": "standard",
                "top3": False,
                "role_reweight_v2": False,
                "geometry": "8cf",
                "search": "Q00",
            },
        )
        m2_force = {
            "q00_vs_GEN2": force(0.56, 0.53, 0.59),
            "native_vs_GEN2": force(0.58, 0.55, 0.61),
        }
        write(
            m2_evaluation,
            {
                "verdict": "M2_PLATEAU_OR_REGRESSION_REVIEW",
                "recommendation": "stop_same_recipe_and_prepare_d10_causal_arm",
                "all_guardrails_pass": True,
                "training_summary": {"model_sha256": m2_sha},
                "force": m2_force,
            },
        )
        write(
            d12_evaluation,
            {
                "verdict": "D12_PLATEAU_OR_REGRESSION_REVIEW",
                "recommendation":
                    "stop_single_depth_escalation_and_prepare_distribution_factor",
                "all_guardrails_pass": False,
                "guardrails": {
                    "f2m_q00_regression_not_established": False,
                    "all_other_guard": True,
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
                    "/tmp/prior-d12-independent.fen": 500,
                },
            },
        )
        rates = {
            "M2": (m2_rate, m2_low, m2_high),
            "F2M": (f2m_rate, f2m_low, f2m_high),
            "GEN2": (0.58, 0.55, 0.61),
        }
        for view in ("q00", "native"):
            for opponent, (rate, low, high) in rates.items():
                write(
                    force_dir / f"force-{view}-TURNOVER-vs-{opponent}.json",
                    force(rate, low, high),
                )
        baseline = ["win"] * 294 + ["loss"] * 6
        candidate = ["win"] * 295 + ["loss"] * 5
        for stratum in ("p3_mince", "p4_egal"):
            write(conv_dir / f"TURNOVER-{stratum}.json", conversion(candidate))
            write(conv_dir / f"M2-{stratum}.json", conversion(baseline))
            write(conv_dir / f"F2M-{stratum}.json", conversion(baseline))
        write(cov_dir / "TURNOVER-coverage.json", coverage(210_000, 28_000))
        write(cov_dir / "M2-coverage.json", coverage(207_000, 27_500))
        write(cov_dir / "F2M-coverage.json", coverage(204_000, 27_400))
        return (
            force_dir,
            conv_dir,
            cov_dir,
            training,
            m2_training,
            m2_contract,
            m2_evaluation,
            d12_evaluation,
            openings,
        )

    def build(self, prepared):
        (
            force_dir,
            conv_dir,
            cov_dir,
            training,
            m2_training,
            m2_contract,
            m2_evaluation,
            d12_evaluation,
            openings,
        ) = prepared
        return build_evaluation(
            force_dir=force_dir,
            conversion_dir=conv_dir,
            coverage_dir=cov_dir,
            training_summary_path=training,
            m2_training_summary_path=m2_training,
            m2_corpus_contract_path=m2_contract,
            m2_evaluation_path=m2_evaluation,
            d12_evaluation_path=d12_evaluation,
            opening_manifest_path=openings,
            expected_opening_seed=OPENING_SEED,
            expected_opening_sha256=OPENING_SHA,
            bootstrap_samples=2_000,
        )

    def test_promotion_requires_superiority_to_m2_and_f2m(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.build(self.prepare(
                Path(tmp),
                m2_rate=0.56, m2_low=0.53, m2_high=0.59,
                f2m_rate=0.55, f2m_low=0.52, f2m_high=0.58,
            ))
        self.assertEqual(result["verdict"], PROMOTION)
        self.assertFalse(result["promotion_authorized"])

    def test_causal_effect_can_precede_champion_superiority(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.build(self.prepare(
                Path(tmp),
                m2_rate=0.55, m2_low=0.52, m2_high=0.58,
                f2m_rate=0.51, f2m_low=0.48, f2m_high=0.54,
            ))
        self.assertEqual(result["verdict"], EFFECT)

    def test_directional_signal_requests_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.build(self.prepare(
                Path(tmp),
                m2_rate=0.52, m2_low=0.49, m2_high=0.55,
                f2m_rate=0.51, f2m_low=0.48, f2m_high=0.54,
            ))
        self.assertEqual(result["verdict"], DIRECTIONAL)

    def test_flat_or_regressive_result_closes_arm(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.build(self.prepare(
                Path(tmp),
                m2_rate=0.49, m2_low=0.46, m2_high=0.52,
                f2m_rate=0.49, f2m_low=0.46, f2m_high=0.52,
            ))
        self.assertEqual(result["verdict"], PLATEAU)

    def test_training_mix_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            prepared = self.prepare(
                Path(tmp),
                m2_rate=0.52, m2_low=0.49, m2_high=0.55,
                f2m_rate=0.51, f2m_low=0.48, f2m_high=0.54,
            )
            training = prepared[3]
            value = json.loads(training.read_text(encoding="utf-8"))
            value["historical_replay_records"] -= 1
            write(training, value)
            with self.assertRaisesRegex(ValueError, "training contract"):
                self.build(prepared)

    def test_depth_factor_closure_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            prepared = self.prepare(
                Path(tmp),
                m2_rate=0.52, m2_low=0.49, m2_high=0.55,
                f2m_rate=0.51, f2m_low=0.48, f2m_high=0.54,
            )
            d12 = prepared[7]
            value = json.loads(d12.read_text(encoding="utf-8"))
            value["guardrails"]["second_failure"] = False
            write(d12, value)
            with self.assertRaisesRegex(ValueError, "depth-factor"):
                self.build(prepared)


if __name__ == "__main__":
    unittest.main()

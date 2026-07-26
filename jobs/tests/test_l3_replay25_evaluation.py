import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools.l3_replay25_evaluation import (
    CAUSAL_BETTER,
    CHAMPION_REVIEW,
    CLOSED,
    DIRECTIONAL,
    F2M_MODEL_SHA,
    M2_MODEL_SHA,
    TURNOVER_MODEL_SHA,
    build_evaluation,
)


OPENING_SEED = 1_836_311
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


class Replay25EvaluationTests(unittest.TestCase):
    def prepare(
        self,
        root: Path,
        *,
        m2: tuple[float, float, float],
        turnover: tuple[float, float, float],
        f2m: tuple[float, float, float],
    ):
        force_dir = root / "force"
        conv_dir = root / "conversion"
        cov_dir = root / "coverage"
        for directory in (force_dir, conv_dir, cov_dir):
            directory.mkdir()
        paths = {
            name: root / f"{name}.json"
            for name in (
                "training",
                "preflight",
                "turnover-training",
                "turnover-evaluation",
                "turnover-confirmation",
                "m2-training",
                "m2-evaluation",
                "openings",
            )
        }
        preflight = {
            "verdict": "REPLAY25_PREFLIGHT_READY",
            "experiment_variant": "REPLAY25_RECENCY75",
            "records": 2_000_000,
            "historical_replay_records": 500_000,
            "fresh_records": 1_500_000,
            "jnnw_sha256": "b" * 64,
            "jsm_sha256": "c" * 64,
            "training_authorized": True,
            "promotion_authorized": False,
            "automatic_next_job": None,
        }
        openings = {
            "records": 500,
            "unique_records": 500,
            "overlap_records": 0,
            "generator_seed": OPENING_SEED,
            "sha256": OPENING_SHA,
            "excluded_sources": {
                "/tmp/prior-turnover-confirmation.fen": 1000,
            },
        }
        preflight["evaluation_openings"] = {
            "seed": OPENING_SEED,
            "sha256": OPENING_SHA,
            "manifest": openings,
        }
        write(paths["preflight"], preflight)
        write(
            paths["training"],
            {
                "verdict": "REPLAY25_TRAINING_SCREEN_READY",
                "experiment_variant": "REPLAY25_RECENCY75",
                "parent": "F2M",
                "parent_model_sha256": F2M_MODEL_SHA,
                "training_records": 2_000_000,
                "training_corpus_sha256": "b" * 64,
                "training_meta_sha256": "c" * 64,
                "historical_replay_records": 500_000,
                "fresh_records": 1_500_000,
                "temporal_distribution_records": {
                    "fresh_m2": 1_500_000,
                    "parent_f2m": 500_000,
                },
                "new_generation_performed": False,
                "external_teacher_inputs": 0,
                "evaluation_authorized": True,
                "promotion_authorized": False,
                "automatic_next_job": None,
            },
        )
        write(
            paths["turnover-training"],
            {
                "verdict": "M2_TRAINING_SCREEN_READY",
                "experiment_variant": "TURNOVER_1_1",
                "model_sha256": TURNOVER_MODEL_SHA,
                "historical_replay_records": 1_000_000,
                "fresh_records": 1_000_000,
                "new_generation_performed": False,
            },
        )
        write(
            paths["turnover-evaluation"],
            {
                "verdict": "TURNOVER_DIRECTIONAL_CONFIRMATION_REVIEW",
                "training_summary": {"model_sha256": TURNOVER_MODEL_SHA},
            },
        )
        write(
            paths["turnover-confirmation"],
            {
                "verdict": "TURNOVER_EFFECT_CONFIRMED_HUMAN_REVIEW",
                "all_guardrails_pass": True,
                "previous_evaluation_certificate": {
                    "model_sha256": TURNOVER_MODEL_SHA,
                },
                "promotion_authorized": False,
                "automatic_next_job": None,
            },
        )
        write(
            paths["m2-training"],
            {
                "verdict": "M2_TRAINING_SCREEN_READY",
                "model_sha256": M2_MODEL_SHA,
                "fresh_only": True,
                "training_records": 2_000_000,
            },
        )
        m2_force = {
            "q00_vs_GEN2": force(0.56, 0.53, 0.59),
            "native_vs_GEN2": force(0.58, 0.55, 0.61),
        }
        write(
            paths["m2-evaluation"],
            {
                "verdict": "M2_PLATEAU_OR_REGRESSION_REVIEW",
                "all_guardrails_pass": True,
                "training_summary": {"model_sha256": M2_MODEL_SHA},
                "force": m2_force,
            },
        )
        write(paths["openings"], openings)

        rates = {
            "M2": m2,
            "TURNOVER": turnover,
            "F2M": f2m,
            "GEN2": (0.58, 0.55, 0.61),
        }
        for view in ("q00", "native"):
            for opponent, values in rates.items():
                write(
                    force_dir / f"force-{view}-REPLAY25-vs-{opponent}.json",
                    force(*values),
                )
        baseline = ["win"] * 294 + ["loss"] * 6
        candidate = ["win"] * 295 + ["loss"] * 5
        for stratum in ("p3_mince", "p4_egal"):
            write(conv_dir / f"REPLAY25-{stratum}.json", conversion(candidate))
            for control in ("M2", "TURNOVER", "F2M"):
                write(conv_dir / f"{control}-{stratum}.json", conversion(baseline))
        write(cov_dir / "REPLAY25-coverage.json", coverage(210_000, 28_100))
        write(cov_dir / "M2-coverage.json", coverage(207_000, 27_500))
        write(cov_dir / "TURNOVER-coverage.json", coverage(210_000, 28_000))
        write(cov_dir / "F2M-coverage.json", coverage(204_000, 27_400))
        return force_dir, conv_dir, cov_dir, paths

    def build(self, prepared):
        force_dir, conv_dir, cov_dir, paths = prepared
        return build_evaluation(
            force_dir=force_dir,
            conversion_dir=conv_dir,
            coverage_dir=cov_dir,
            training_summary_path=paths["training"],
            preflight_path=paths["preflight"],
            turnover_training_path=paths["turnover-training"],
            turnover_evaluation_path=paths["turnover-evaluation"],
            turnover_confirmation_path=paths["turnover-confirmation"],
            m2_training_path=paths["m2-training"],
            m2_evaluation_path=paths["m2-evaluation"],
            opening_manifest_path=paths["openings"],
            expected_opening_seed=OPENING_SEED,
            expected_opening_sha256=OPENING_SHA,
            bootstrap_samples=2_000,
        )

    def test_champion_requires_all_three_controls_in_both_views(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.build(self.prepare(
                Path(tmp),
                m2=(0.56, 0.53, 0.59),
                turnover=(0.55, 0.52, 0.58),
                f2m=(0.55, 0.52, 0.58),
            ))
        self.assertEqual(result["verdict"], CHAMPION_REVIEW)
        self.assertFalse(result["promotion_authorized"])

    def test_causal_better_allows_f2m_equivalence(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.build(self.prepare(
                Path(tmp),
                m2=(0.56, 0.53, 0.59),
                turnover=(0.55, 0.52, 0.58),
                f2m=(0.51, 0.48, 0.54),
            ))
        self.assertEqual(result["verdict"], CAUSAL_BETTER)

    def test_directional_requires_positive_m2_and_turnover(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.build(self.prepare(
                Path(tmp),
                m2=(0.52, 0.49, 0.55),
                turnover=(0.51, 0.48, 0.54),
                f2m=(0.51, 0.48, 0.54),
            ))
        self.assertEqual(result["verdict"], DIRECTIONAL)

    def test_flat_result_closes_the_dose(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.build(self.prepare(
                Path(tmp),
                m2=(0.49, 0.46, 0.52),
                turnover=(0.49, 0.46, 0.52),
                f2m=(0.49, 0.46, 0.52),
            ))
        self.assertEqual(result["verdict"], CLOSED)

    def test_training_dose_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            prepared = self.prepare(
                Path(tmp),
                m2=(0.52, 0.49, 0.55),
                turnover=(0.51, 0.48, 0.54),
                f2m=(0.51, 0.48, 0.54),
            )
            training = prepared[3]["training"]
            value = json.loads(training.read_text(encoding="utf-8"))
            value["fresh_records"] -= 1
            write(training, value)
            with self.assertRaisesRegex(ValueError, "training contract"):
                self.build(prepared)

    def test_opening_manifest_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            prepared = self.prepare(
                Path(tmp),
                m2=(0.52, 0.49, 0.55),
                turnover=(0.51, 0.48, 0.54),
                f2m=(0.51, 0.48, 0.54),
            )
            openings = prepared[3]["openings"]
            value = json.loads(openings.read_text(encoding="utf-8"))
            value["overlap_records"] = 1
            write(openings, value)
            with self.assertRaisesRegex(ValueError, "opening-pool"):
                self.build(prepared)


if __name__ == "__main__":
    unittest.main()

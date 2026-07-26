import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools.l3_turnover_l2_evaluation import (
    DIRECTIONAL,
    F2M_MODEL_SHA,
    LEAD,
    MULTIPLE,
    NO_LEAD,
    TURNOVER_CODE_SHA,
    TURNOVER_CORPUS_SHA,
    TURNOVER_META_SHA,
    TURNOVER_MODEL_SHA,
    build_evaluation,
)


OPENING_SEED = 1_836_313
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
        "complete": True,
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


class TurnoverL2EvaluationTests(unittest.TestCase):
    def prepare(
        self,
        root: Path,
        rates: dict[str, tuple[float, float, float]],
    ) -> dict[str, Path]:
        force_dir = root / "force"
        conversion_dir = root / "conversion"
        force_dir.mkdir()
        conversion_dir.mkdir()
        paths = {
            name: root / f"{name}.json"
            for name in (
                "training",
                "preflight",
                "turnover",
                "confirmation",
                "openings",
            )
        }
        openings = {
            "records": 500,
            "unique_records": 500,
            "overlap_records": 0,
            "generator_seed": OPENING_SEED,
            "sha256": OPENING_SHA,
            "excluded_sources": {"/tmp/prior-replay25.fen": 500},
        }
        preflight = {
            "verdict": "TURNOVER_L2_PREFLIGHT_READY",
            "code_sha": "b" * 40,
            "experiment_variant": "TURNOVER_1_1_L2_SCREEN",
            "jnnw_sha256": TURNOVER_CORPUS_SHA,
            "jsm_sha256": TURNOVER_META_SHA,
            "l2_levels": [1e-5, 3e-5, 1e-4],
            "control_l2": 3e-5,
            "control_source_code_sha": TURNOVER_CODE_SHA,
            "training_authorized": True,
            "promotion_authorized": False,
            "automatic_next_job": None,
            "evaluation_openings": {
                "seed": OPENING_SEED,
                "sha256": OPENING_SHA,
                "manifest": openings,
            },
        }
        training = {
            "verdict": "TURNOVER_L2_TRAINING_SCREEN_READY",
            "experiment_variant": "TURNOVER_1_1_L2_SCREEN",
            "parent": "F2M",
            "parent_model_sha256": F2M_MODEL_SHA,
            "control": {
                "model_sha256": TURNOVER_MODEL_SHA,
                "l2": 3e-5,
                "source_code_sha": TURNOVER_CODE_SHA,
            },
            "arms": {
                "L2_1E5": {
                    "l2": 1e-5,
                    "model_sha256": "1" * 64,
                    "optimizer": {"success": True},
                },
                "L2_1E4": {
                    "l2": 1e-4,
                    "model_sha256": "2" * 64,
                    "optimizer": {"success": True},
                },
            },
            "training_records": 2_000_000,
            "training_corpus_sha256": TURNOVER_CORPUS_SHA,
            "training_meta_sha256": TURNOVER_META_SHA,
            "historical_replay_records": 1_000_000,
            "fresh_records": 1_000_000,
            "new_generation_performed": False,
            "external_teacher_inputs": 0,
            "evaluation_authorized": True,
            "promotion_authorized": False,
            "automatic_next_job": None,
            "preflight_job": "home-0984",
            "preflight_code_sha": preflight["code_sha"],
        }
        turnover = {
            "experiment_variant": "TURNOVER_1_1",
            "code_sha": TURNOVER_CODE_SHA,
            "model_sha256": TURNOVER_MODEL_SHA,
            "training_corpus_sha256": TURNOVER_CORPUS_SHA,
            "training_meta_sha256": TURNOVER_META_SHA,
        }
        confirmation = {
            "verdict": "TURNOVER_EFFECT_CONFIRMED_HUMAN_REVIEW",
            "all_guardrails_pass": True,
            "promotion_authorized": False,
            "automatic_next_job": None,
        }
        for name, value in (
            ("training", training),
            ("preflight", preflight),
            ("turnover", turnover),
            ("confirmation", confirmation),
            ("openings", openings),
        ):
            write(paths[name], value)

        for arm in ("L2_1E5", "L2_1E4"):
            for view in ("q00", "native"):
                value = rates[f"{arm}_{view}"]
                write(
                    force_dir / f"force-{view}-{arm}-vs-TURNOVER.json",
                    force(*value),
                )
            if all(rates[f"{arm}_{view}"][0] > 0.5 for view in ("q00", "native")):
                for opponent in ("F2M", "GEN2"):
                    for view in ("q00", "native"):
                        write(
                            force_dir / f"force-{view}-{arm}-vs-{opponent}.json",
                            force(0.55, 0.52, 0.58),
                        )
                for stratum in ("p3_mince", "p4_egal"):
                    write(conversion_dir / f"{arm}-{stratum}.json", conversion(294))
                    write(
                        conversion_dir / f"TURNOVER-{stratum}.json",
                        conversion(294),
                    )
        return {
            **paths,
            "force_dir": force_dir,
            "conversion_dir": conversion_dir,
        }

    def evaluate(self, paths: dict[str, Path]) -> dict:
        return build_evaluation(
            force_dir=paths["force_dir"],
            conversion_dir=paths["conversion_dir"],
            training_summary_path=paths["training"],
            preflight_path=paths["preflight"],
            turnover_training_path=paths["turnover"],
            turnover_confirmation_path=paths["confirmation"],
            opening_manifest_path=paths["openings"],
            expected_opening_seed=OPENING_SEED,
            expected_opening_sha256=OPENING_SHA,
            bootstrap_samples=100,
        )

    def test_no_lead_closes_without_secondary_cells(self):
        rates = {
            "L2_1E5_q00": (0.49, 0.46, 0.52),
            "L2_1E5_native": (0.51, 0.48, 0.54),
            "L2_1E4_q00": (0.48, 0.45, 0.51),
            "L2_1E4_native": (0.49, 0.46, 0.52),
        }
        with tempfile.TemporaryDirectory() as tmp:
            result = self.evaluate(self.prepare(Path(tmp), rates))
        self.assertEqual(result["verdict"], NO_LEAD)
        self.assertEqual(result["recommended_l2_arm"], "L2_3E5_CONTROL")
        self.assertEqual(result["eligible_for_guard_cells"], [])

    def test_one_directional_arm_requests_confirmation(self):
        rates = {
            "L2_1E5_q00": (0.52, 0.49, 0.55),
            "L2_1E5_native": (0.51, 0.48, 0.54),
            "L2_1E4_q00": (0.48, 0.45, 0.51),
            "L2_1E4_native": (0.49, 0.46, 0.52),
        }
        with tempfile.TemporaryDirectory() as tmp:
            result = self.evaluate(self.prepare(Path(tmp), rates))
        self.assertEqual(result["verdict"], DIRECTIONAL)
        self.assertEqual(result["recommended_l2_arm"], "L2_1E5")

    def test_one_confirmed_arm_is_a_lead(self):
        rates = {
            "L2_1E5_q00": (0.55, 0.52, 0.58),
            "L2_1E5_native": (0.55, 0.52, 0.58),
            "L2_1E4_q00": (0.48, 0.45, 0.51),
            "L2_1E4_native": (0.49, 0.46, 0.52),
        }
        with tempfile.TemporaryDirectory() as tmp:
            result = self.evaluate(self.prepare(Path(tmp), rates))
        self.assertEqual(result["verdict"], LEAD)
        self.assertEqual(result["recommended_l2_arm"], "L2_1E5")

    def test_two_confirmed_arms_require_direct_comparison(self):
        rates = {
            f"{arm}_{view}": (0.55, 0.52, 0.58)
            for arm in ("L2_1E5", "L2_1E4")
            for view in ("q00", "native")
        }
        with tempfile.TemporaryDirectory() as tmp:
            result = self.evaluate(self.prepare(Path(tmp), rates))
        self.assertEqual(result["verdict"], MULTIPLE)
        self.assertIsNone(result["recommended_l2_arm"])

    def test_rejects_unconverged_arm(self):
        rates = {
            f"{arm}_{view}": (0.49, 0.46, 0.52)
            for arm in ("L2_1E5", "L2_1E4")
            for view in ("q00", "native")
        }
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.prepare(Path(tmp), rates)
            training = json.loads(paths["training"].read_text())
            training["arms"]["L2_1E5"]["optimizer"]["success"] = False
            write(paths["training"], training)
            with self.assertRaisesRegex(ValueError, "invalid converged"):
                self.evaluate(paths)


if __name__ == "__main__":
    unittest.main()

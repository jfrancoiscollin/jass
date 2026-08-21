"""Contracts for the REPLAY25 native-vs-context30 target experiment."""

from importlib import util
from pathlib import Path
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relative: str):
    spec = util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = _load("l3_conditional_targets_for_replay_test", "jobs/tools/l3_conditional_targets.py")
TARGETS = _load("l3_replay_context30_targets_tested", "jobs/tools/l3_replay_context30_targets.py")
READOUT = _load("l3_replay_context30_target_readout_tested", "jobs/tools/l3_replay_context30_target_readout.py")


class ReplayContext30TargetTest(unittest.TestCase):
    def _game_ids_covering_folds(self, per_fold: int = 3) -> list[int]:
        selected: dict[int, list[int]] = {fold: [] for fold in range(5)}
        for candidate in range(1, 100_000):
            fold = int(BASE.game_folds(np.asarray([candidate], dtype=np.uint64), 5, 20260811)[0])
            if len(selected[fold]) < per_fold:
                selected[fold].append(candidate)
            if all(len(values) == per_fold for values in selected.values()):
                break
        self.assertTrue(all(len(values) == per_fold for values in selected.values()))
        return [value for fold in range(5) for value in selected[fold]]

    def test_train_only_adapter_matches_historical_train_prefix_exactly(self) -> None:
        rng = np.random.default_rng(552)
        train_games = self._game_ids_covering_folds()
        game_ids = np.repeat(np.asarray(train_games, dtype=np.uint64), 2)
        contexts = rng.normal(size=(len(game_ids), 11)).astype(np.float64)
        outcomes = np.resize(np.asarray([-1.0, 0.0, 1.0]), len(game_ids)).astype(np.float64)

        holdout_games = np.asarray([900_001, 900_002], dtype=np.uint64)
        holdout_ids = np.repeat(holdout_games, 2)
        full_contexts = np.concatenate((contexts, rng.normal(size=(4, 11))), axis=0)
        full_outcomes = np.concatenate((outcomes, np.asarray([1.0, 0.0, -1.0, 0.0])))
        full_games = np.concatenate((game_ids, holdout_ids))

        historical, _, _ = BASE.cross_fitted_predictions(
            full_contexts,
            full_outcomes,
            full_games,
            len(contexts),
            group_ids=full_games,
            group_name="game_id",
            row_weighting="uniform",
            components=BASE.CONTEXT_SCHEMAS["ctx1-legacy-120"],
            require_convergence=False,
            fold_count=5,
            fold_seed=20260811,
            ridge=1e-4,
            max_iterations=50,
            tolerance=1e-8,
            line_search_steps=20,
        )
        adapted, mapping = TARGETS.train_only_oof_predictions(
            contexts, outcomes, game_ids
        )
        np.testing.assert_array_equal(adapted, historical[: len(contexts)])

        historical_targets = np.asarray(
            ((0.70 * outcomes + 0.30 * historical[: len(contexts)]) + 1.0) * 0.5,
            dtype=np.float32,
        )
        adapted_targets = np.asarray(
            ((0.70 * outcomes + 0.30 * adapted) + 1.0) * 0.5,
            dtype=np.float32,
        )
        np.testing.assert_array_equal(adapted_targets, historical_targets)
        self.assertFalse(mapping["adapter"]["synthetic_row_used_in_oof_training"])
        self.assertFalse(mapping["adapter"]["synthetic_row_included_in_output_targets"])
        self.assertTrue(mapping["adapter"]["historical_train_recipe_unchanged"])

    def test_force_classification_requires_two_pool_replication(self) -> None:
        positive = {
            "pool_rates": [0.51, 0.52],
            "inter_pool_compatible_95": True,
            "ci_low": 0.505,
            "ci_high": 0.525,
            "probability_rate_gt_half": 0.99,
        }
        negative = {
            "pool_rates": [0.49, 0.48],
            "inter_pool_compatible_95": True,
            "ci_low": 0.475,
            "ci_high": 0.495,
            "probability_rate_gt_half": 0.01,
        }
        mixed = {
            "pool_rates": [0.51, 0.49],
            "inter_pool_compatible_95": True,
            "ci_low": 0.499,
            "ci_high": 0.511,
            "probability_rate_gt_half": 0.70,
        }
        self.assertEqual(READOUT.classify(positive), "ESTABLISHED_POSITIVE")
        self.assertEqual(READOUT.classify(negative), "ESTABLISHED_NEGATIVE")
        self.assertEqual(READOUT.classify(mixed), "NOT_ESTABLISHED")

    def test_template_locks_target_only_scope(self) -> None:
        text = (ROOT / "jobs/templates/l3-replay-context30-target-gate-v1.sh").read_text(
            encoding="utf-8"
        )
        required = (
            "B_REPLAY25_CONTEXT30",
            "B_REPLAY25_NATIVE",
            "CONTEXT_30_ALIGNED_alpha_0.30",
            "--sample-weights",
            "--prior-mean \"$W/curriculum.pjtw\"",
            "NOPEN=3000",
            "BOOTSTRAP=200000",
            "historical_exclusion_count",
            "REFITS__1",
            "NEW_SELFPLAY__0",
            "FROZEN_COHORTS_READ__0",
            "PROMOTION_AUTHORIZED__FALSE",
        )
        for token in required:
            self.assertIn(token, text)
        self.assertNotIn("--gen-selfplay", text)
        self.assertNotIn("PROMOTION_AUTHORIZED__TRUE", text)


if __name__ == "__main__":
    unittest.main()

"""Contracts for the REPLAY25 native-vs-context30 target experiment."""

from importlib import util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "jobs/templates/l3-replay-context30-target-gate-v1.sh"
V2 = ROOT / "jobs/templates/l3-replay-context30-target-gate-v2.sh"


def _load(name: str, relative: str):
    spec = util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = _load("l3_conditional_targets_for_replay_test", "jobs/tools/l3_conditional_targets.py")
# The train-only adapter deliberately imports the historical builder by its
# runtime module name. Register the already loaded test instance under that
# name so the unit test exercises the same dependency topology as the job.
sys.modules["l3_conditional_targets"] = BASE
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

    def test_v1_locks_target_only_scope(self) -> None:
        text = V1.read_text(encoding="utf-8")
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
        # The renderer contains each prohibited token exactly once in its own
        # fail-closed scanner; it must not contain an executable occurrence.
        self.assertIn("if forbidden in text:", text)
        self.assertEqual(text.count('"--gen-selfplay"'), 1)
        self.assertEqual(text.count('"PROMOTION_AUTHORIZED__TRUE"'), 1)

    def test_v2_is_only_a_pinned_render_validator(self) -> None:
        text = V2.read_text(encoding="utf-8")
        for token in (
            'EXPECTED_V1_BLOB="b0f32aae0c4b8326568a694b981ef1abd300e82d"',
            "JASS_REPLAY_CONTEXT30_RENDER_ONLY",
            '"technical_change_only": True',
            '"scientific_protocol_changed": False',
            '"runtime_default_changed": False',
            '"refits": 1',
            '"new_selfplay": 0',
            '"automatic_promotion": False',
            "inner_generated_script_forbidden_scan_preserved",
            'exec bash "$PATCHED"',
        ):
            self.assertIn(token, text)

    def test_complete_two_stage_renderer_produces_locked_final_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = root / "result"
            artefacts = root / "artefacts"
            result.mkdir()
            artefacts.mkdir()
            env = os.environ.copy()
            env.update(
                {
                    "JASS_CODE_DIR": str(ROOT),
                    "JASS_RESULT_DIR": str(result),
                    "JASS_ARTEFACT_DIR": str(artefacts),
                    "JASS_REPLAY_CONTEXT30_RENDER_ONLY": "1",
                }
            )
            completed = subprocess.run(
                ["bash", str(V2)],
                cwd=ROOT,
                env=env,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertIn(completed.returncode, (0, 1))
            rendered = artefacts / "replay-context30-rendered.sh"
            generated = result / "l3-replay-context30-target-gate-v1.generated.sh"
            final = rendered if rendered.is_file() else generated
            self.assertTrue(final.is_file())
            if completed.returncode != 0:
                self.assertFalse(rendered.is_file())
                self.assertTrue(generated.is_file())
            subprocess.run(["bash", "-n", str(final)], check=True)
            text = final.read_text(encoding="utf-8")
            for token in (
                'NOPEN=3000',
                'CANDIDATES=40000',
                'BOOTSTRAP=200000',
                'POOL_SEED_1=2026082211',
                'POOL_SEED_2=2026082212',
                'B_REPLAY25_CONTEXT30',
                'B_REPLAY25_NATIVE',
                'CONTEXT_30_ALIGNED_alpha_0.30',
                '--target external',
                '--sample-weights',
                '--prior-mean "$W/curriculum.pjtw"',
                '--pattern-a "$W/B_C30.pjtw" --pattern-b "$W/B_NATIVE.pjtw"',
                'GAMES_TOTAL__24000',
                'REFITS__1',
                'NEW_SELFPLAY__0',
                'FROZEN_COHORTS_READ__0',
                'PROMOTION_AUTHORIZED__FALSE',
            ):
                self.assertIn(token, text)
            self.assertEqual(text.count('pattern_jass/tools/train_stream_exact.py \\'), 1)
            for forbidden in (
                "stage sequential-four-arm-fits",
                "fit_arm A ",
                "--gen-selfplay",
                "PROMOTION_AUTHORIZED__TRUE",
            ):
                self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()

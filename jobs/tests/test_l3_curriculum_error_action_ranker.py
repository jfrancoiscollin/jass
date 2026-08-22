from pathlib import Path
import hashlib
import importlib.util
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "l3_curriculum_error_action_ranker",
    ROOT / "jobs" / "tools" / "l3_curriculum_error_action_ranker.py",
)
assert SPEC and SPEC.loader
R = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R)


QUIET = "1-2"
CAPTURE = "3x4 captures=7"


def image(action: str) -> str:
    return R.source._mapped_image_action(action)


def profile(index: int, *, error: bool) -> dict:
    # The capture gradually recovers versus the quiet baseline.  The exact
    # image carries byte-for-byte equivalent mapped action trajectories.
    rows = {}
    for depth in R.FEATURE_DEPTHS:
        capture = -70.0 + 18.0 * (depth - 6) + (index % 3)
        quiet = 0.0
        rows[str(depth)] = {
            "moves": [
                {"action": QUIET, "score": quiet},
                {"action": CAPTURE, "score": capture},
            ]
        }
    image_rows = {
        depth: {
            "moves": [
                {"action": image(QUIET), "score": item["moves"][0]["score"]},
                {"action": image(CAPTURE), "score": item["moves"][1]["score"]},
            ]
        }
        for depth, item in rows.items()
    }
    return {
        "source": {
            "opening_id": f"opening-{index}-{'e' if error else 'c'}",
            "exact_state_key": f"state-{index}-{'e' if error else 'c'}",
        },
        "trace": {"original": {"depths": rows}, "exact_image": {"depths": image_rows}},
    }


def entry(index: int, *, error: bool) -> dict:
    values = (
        {QUIET: {"root_cp": 0.0}, CAPTURE: {"root_cp": 120.0}}
        if error
        else {QUIET: {"root_cp": 5.0}, CAPTURE: {"root_cp": 0.0}}
    )
    return {
        "profile": profile(index, error=error),
        "judged": {
            "action_values": values,
            "exact_teacher_action": CAPTURE if error else QUIET,
        },
    }


def pair(index: int) -> dict:
    return {"pair_id": index, "error": entry(index, error=True), "control": entry(index, error=False)}


class ActionRankerTests(unittest.TestCase):
    def test_source_loader_counts_only_sealed_splits(self):
        pairs = {
            "schema": R.source.SCHEMA_PAIRS,
            "matching_passed": True,
            "matched_pairs": 2,
            "pairs": [
                {"pair_id": 0, "split": "discovery"},
                {"pair_id": 1, "split": "confirm"},
            ],
        }
        digest = hashlib.sha256(R._canonical(pairs)).hexdigest()
        shards = []
        for shard in range(16):
            shards.append(
                {
                    "schema": R.source.SCHEMA_ATLAS_SHARD,
                    "shard": shard,
                    "nshards": 16,
                    "max_pairs": 0,
                    "pairs_sha256": digest,
                    "champion_sha256": "champion",
                    "jass_sha256": "jass",
                    "search_params_sha256": "search",
                    "rows": ([{"pair_id": shard}] if shard < 2 else []),
                }
            )

        _, _, _, counts = R._load_source(pairs, shards)

        self.assertEqual(counts["pairs_by_split"], {"discovery": 1, "confirm": 1})

    def test_source_loader_rejects_unsealed_split(self):
        pairs = {
            "schema": R.source.SCHEMA_PAIRS,
            "matching_passed": True,
            "matched_pairs": 1,
            "pairs": [{"pair_id": 0, "split": "peek"}],
        }
        digest = hashlib.sha256(R._canonical(pairs)).hexdigest()
        shards = [
            {
                "schema": R.source.SCHEMA_ATLAS_SHARD,
                "shard": shard,
                "nshards": 16,
                "max_pairs": 0,
                "pairs_sha256": digest,
                "champion_sha256": "champion",
                "jass_sha256": "jass",
                "search_params_sha256": "search",
                "rows": ([{"pair_id": 0}] if shard == 0 else []),
            }
            for shard in range(16)
        ]

        with self.assertRaisesRegex(ValueError, "split drift"):
            R._load_source(pairs, shards)

    def test_feature_contract_and_exact_image_equivariance(self):
        raw, scores = R._raw_features(profile(0, error=True), image=False)
        transformed, image_scores = R._raw_features(profile(0, error=True), image=True)
        self.assertEqual(set(raw), {QUIET, CAPTURE})
        self.assertEqual(scores, image_scores)
        self.assertEqual(len(R.FEATURE_NAMES), 20)
        for action in raw:
            np.testing.assert_allclose(raw[action], transformed[action])

    def test_pairwise_residual_ranker_repairs_synthetic_error_and_abstains_on_control(self):
        rows = [pair(index) for index in range(32)]
        model = R._fit(rows, alpha=1.0)
        repaired = R._decision(rows[0]["error"], model, threshold=5.0, margin_band=100.0)
        control = R._decision(rows[0]["control"], model, threshold=1_000.0, margin_band=100.0)
        self.assertGreater(repaired["improvement_cp"], 0.0)
        self.assertTrue(repaired["changed_pair"])
        self.assertFalse(control["changed_pair"])
        self.assertEqual(control["improvement_cp"], 0.0)
        self.assertLessEqual(max(abs(x) for x in model["coef"]), 1_000.0)

    def test_sham_permutation_is_deterministic_and_non_identity(self):
        values = {QUIET: 0.0, CAPTURE: 120.0, "5-6": 30.0}
        left = R._permuted_values(values, seed=7, state_key="a")
        right = R._permuted_values(values, seed=7, state_key="a")
        self.assertEqual(left, right)
        self.assertEqual(sorted(left.values()), sorted(values.values()))

    def test_component_split_keeps_shared_opening_atomic(self):
        rows = [pair(index) for index in range(40)]
        rows[1]["error"]["profile"]["source"]["opening_id"] = rows[0]["error"]["profile"]["source"]["opening_id"]
        fit, validation, manifest = R._inner_split(rows, seed=2026082235)
        owner = {row["pair_id"]: "fit" for row in fit} | {row["pair_id"]: "validation" for row in validation}
        self.assertEqual(owner[0], owner[1])
        self.assertEqual(manifest["overlap"], 0)

    def test_correction_is_hard_capped(self):
        model = {
            "mean": [0.0] * len(R.FEATURE_NAMES),
            "scale": [1.0] * len(R.FEATURE_NAMES),
            "coef": [1_000.0] * len(R.FEATURE_NAMES),
        }
        self.assertEqual(R._correction(model, np.ones(len(R.FEATURE_NAMES))), R.CORRECTION_CAP_CP)


if __name__ == "__main__":
    unittest.main()

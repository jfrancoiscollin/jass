import copy
import unittest

from jobs.tools import l3_curriculum_error_loss_first_crossfit as screen


TOTAL = 8


def _row(pool: int, ordinal: int, role: str, *, gradient: float = 1.0) -> dict:
    error = role == "error"
    baseline = {"a": 0.0, "b": 20.0} if error else {"a": 20.0, "b": 0.0}
    return {
        "accepted": True, "label": role, "pool": pool,
        "opening_id": f"p{pool}-{role}-o{ordinal}",
        "game_uid": f"p{pool}-{role}-g{ordinal}",
        "exact_state_key": f"p{pool}-{role}-s{ordinal}",
        "legal_actions": ["a", "b"], "teacher_action": "a",
        "historical_action": "b" if error else "a",
        "baseline_shallow_scores_cp": {
            "symmetrised": dict(baseline), "original": dict(baseline),
            "exact_image": dict(baseline),
        },
        "listwise_bounded_utility": {"a": 0.0, "b": -100.0},
        "comparisons": [{
            "teacher": "a", "sibling": "b", "teacher_margin_cp": 100.0,
            "bounded_margin_cp": 100.0, "pair_weight": 1.0,
            "baseline_shallow_margin_cp": baseline["a"] - baseline["b"],
            "baseline_original_margin_cp": baseline["a"] - baseline["b"],
            "baseline_exact_image_margin_cp": baseline["a"] - baseline["b"],
            "gradient": {"0": gradient}, "original_gradient": {"0": gradient},
            "exact_image_gradient": {"0": gradient},
        }],
        "teacher_details": {"12": {
            "original_values_cp": {"a": 100.0, "b": 0.0},
            "exact_image_values_cp": {"a": 100.0, "b": 0.0},
        }},
    }


def _payload(count: int = 16) -> dict:
    pairs = []
    for pool in (1, 2):
        for ordinal in range(count):
            pairs.append({
                "pair_id": (pool - 1) * count + ordinal, "pool": pool,
                "matching_stratum": "opening|men|quiet|b2",
                "error": _row(pool, ordinal, "error"),
                "control": _row(pool, ordinal, "control"),
            })
    return {
        "schema": screen.PAIR_SCHEMA, "source_verdict": screen.SOURCE_VERDICT,
        "pairs": pairs, "opening_game_canonical_overlap": 0,
    }


def _labels(count: int = 16) -> dict:
    return {
        "schema": screen.LABEL_SCHEMA, "verdict": screen.SOURCE_VERDICT,
        "passed": True, "matched_pairs": 2 * count,
        "anchored_local_refit_authorized": False,
        "production_model_authorized": False,
        "strength_gate_authorized": False,
        "promotion_authorized": False,
        "automatic_continuation": False,
    }


class LossFirstCrossfitTests(unittest.TestCase):
    def test_discovery_requires_replicated_sign(self) -> None:
        by_pool = screen.load_pairs(_payload(), total=TOTAL)
        discovery = screen.discover(by_pool[1])
        self.assertEqual(discovery["selected_buckets"], [0])
        self.assertEqual(discovery["selected"][0]["error_openings"], 16)
        inconsistent = copy.deepcopy(_payload())
        for row in inconsistent["pairs"]:
            if row["pool"] == 1 and row["pair_id"] % 2:
                for key in ("gradient", "original_gradient", "exact_image_gradient"):
                    row["error"]["comparisons"][0][key]["0"] = -1.0
        by_pool = screen.load_pairs(inconsistent, total=TOTAL)
        self.assertEqual(screen.discover(by_pool[1])["selected_buckets"], [])

    def test_real_crossfit_corrects_errors_without_moving_controls(self) -> None:
        by_pool = screen.load_pairs(_payload(), total=TOTAL)
        result = screen._crossfit(by_pool)
        self.assertGreater(result["selected_coordinate_cosine"], 0.99)
        for pool in (1, 2):
            heldout = result["heldout"][str(pool)]
            self.assertGreater(heldout["error_teacher_top_hit_gain"], 0.0)
            self.assertGreater(heldout["stable_error_50cp_rate_reduction"], 0.0)
            self.assertGreaterEqual(heldout["control_teacher_top_hit_gain"], 0.0)
            self.assertEqual(heldout["orientation_symmetry_fraction"], 1.0)

    def test_label_sham_is_deterministic_and_target_only(self) -> None:
        state = screen.load_pairs(_payload(), total=TOTAL)[1][0]["error"]
        before = copy.deepcopy(state["vectors"])
        first = screen._target_utilities(state, 123)
        second = screen._target_utilities(state, 123)
        self.assertEqual(first, second)
        self.assertCountEqual(first.values(), state["utilities"].values())
        self.assertEqual(state["vectors"], before)

    def test_run_never_authorizes_production_or_strength(self) -> None:
        report, models = screen.run(
            _labels(), _payload(), labels_sha="a" * 64, pairs_sha="b" * 64,
            bootstrap_samples=100, bootstrap_seed=screen._seed("boot"),
            sham_replicates=10, sham_seed=screen._seed("sham"), total_buckets=TOTAL,
        )
        self.assertFalse(report["production_model_authorized"])
        self.assertFalse(report["strength_gate_authorized"])
        self.assertFalse(report["promotion_authorized"])
        self.assertEqual(report["pattern_eval_fits"], 0)
        self.assertEqual(report["strength_games"], 0)
        self.assertFalse(models["authorized_for_production"])
        self.assertFalse(report["gates"]["exactly_1000_opening_cluster_label_shams"])

    def test_pool_leakage_fails_closed(self) -> None:
        payload = _payload()
        payload["pairs"][16]["error"]["opening_id"] = payload["pairs"][0]["error"]["opening_id"]
        with self.assertRaisesRegex(ValueError, "cross-pool"):
            screen.load_pairs(payload, total=TOTAL)


if __name__ == "__main__":
    unittest.main()

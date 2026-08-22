from __future__ import annotations

import unittest

from jobs.tools import l3_curriculum_error_residual_atlas as residual


IDENTITY = "a" * 64


def decision(label: str, values: dict[int, float], pair_id: int) -> dict:
    return {
        "label": label,
        "source": {"opening_id": f"o-{pair_id}-{label}", "fen": "W:W31:B20"},
        "teacher_action": "31-27",
        "rival_action": "31-26",
        "rival_mode": "historical_action" if label == "error" else "exact_runner_up",
        "forced_single_action": False,
        "historical_regret_cp": 80.0 if label == "error" else 0.0,
        "orientation_cosine": 1.0,
        "gradient": [
            {
                "coordinate": coordinate,
                "value": value,
                "representative_full_column": coordinate,
            }
            for coordinate, value in sorted(values.items())
        ],
    }


def forced_control(pair_id: int) -> dict:
    row = decision("control", {}, pair_id)
    row.update({
        "rival_action": None,
        "rival_mode": "forced_single_legal_action",
        "forced_single_action": True,
        "orientation_cosine": None,
    })
    return row


def make_shards(*, null: bool = False) -> list[dict]:
    shards = []
    for shard_id in range(2):
        rows = []
        for pair_id in range(80):
            if pair_id % 2 != shard_id:
                continue
            split = "discovery" if pair_id < 40 else "confirm"
            sign = -1.0 if null and pair_id % 2 == 0 else 1.0
            rows.append(
                {
                    "pair_id": pair_id,
                    "split": split,
                    "error": decision("error", {10: sign, 11: sign, 12: sign}, pair_id),
                    "control": decision("control", {}, pair_id),
                }
            )
        shards.append(
            {
                "schema": residual.SCHEMA_SHARD,
                "champion_sha256": IDENTITY,
                "source_jass_sha256": "d" * 64,
                "jass_sha256": "b" * 64,
                "search_params_sha256": "c" * 64,
                "shard": shard_id,
                "nshards": 2,
                "max_pairs": 0,
                "rows": rows,
            }
        )
    return shards


class CurriculumErrorResidualAtlasTests(unittest.TestCase):
    def test_sparse_vector_math(self) -> None:
        self.assertEqual(
            residual._subtract({1: 0.8, 2: 0.2}, {1: 0.3, 3: 0.5}, sign=-1.0),
            {1: -0.5, 2: -0.2, 3: 0.5},
        )
        self.assertAlmostEqual(
            residual._cosine({1: 1.0, 2: 1.0}, {1: 1.0, 2: 1.0}), 1.0
        )

    def test_single_legal_action_is_a_certified_forced_control(self) -> None:
        rival, mode = residual._rival(
            {
                "exact_teacher_action": "31-27",
                "historical_action": "31-27",
                "action_values": {"31-27": {"twice_root_cp": 0}},
            },
            label="control",
        )
        self.assertIsNone(rival)
        self.assertEqual(mode, "forced_single_legal_action")

    def test_confirmed_fixed_direction_authorizes_region(self) -> None:
        report, region = residual.aggregate(
            make_shards(),
            min_discovery_hits=6,
            min_region_buckets=2,
            max_region_buckets=8,
            min_orientation_cosine=0.0,
            min_coordinate_replication=0.70,
            bootstrap_samples=2000,
            permutation_samples=2000,
            seed=17,
        )
        self.assertTrue(report["passed"])
        self.assertEqual(
            report["verdict"], "JASS_CURRICULUM_ERROR_RESIDUAL_REGION_CONFIRMED"
        )
        self.assertEqual(report["selected_canonical_buckets"], 3)
        self.assertEqual(region["pattern_columns_full"], [10, 11, 12])
        self.assertTrue(region["fit_authorized"])
        self.assertFalse(region["promotion_authorized"])

    def test_forced_control_is_excluded_without_fabricated_zero_pair(self) -> None:
        shards = make_shards()
        forced_pair = next(
            row for shard in shards for row in shard["rows"] if row["pair_id"] == 40
        )
        forced_pair["control"] = forced_control(40)
        report, _region = residual.aggregate(
            shards,
            min_discovery_hits=6,
            min_region_buckets=2,
            max_region_buckets=8,
            min_orientation_cosine=0.0,
            min_coordinate_replication=0.70,
            bootstrap_samples=1000,
            permutation_samples=1000,
            seed=23,
        )
        self.assertTrue(report["passed"])
        forced = report["forced_controls"]
        self.assertEqual(forced["total"], 1)
        self.assertEqual(forced["informative_confirm_pairs"], 39)
        self.assertTrue(forced["excluded_from_control_and_paired_statistics"])
        self.assertEqual(report["confirm"]["control_projection"]["n"], 39)
        self.assertEqual(report["confirm"]["paired_error_minus_control"]["n"], 39)

    def test_excess_forced_controls_fail_closed(self) -> None:
        shards = make_shards()
        for pair_id in (40, 41, 42, 43, 44):
            pair = next(
                row for shard in shards for row in shard["rows"] if row["pair_id"] == pair_id
            )
            pair["control"] = forced_control(pair_id)
        report, region = residual.aggregate(
            shards,
            min_discovery_hits=6,
            min_region_buckets=2,
            max_region_buckets=8,
            min_orientation_cosine=0.0,
            min_coordinate_replication=0.70,
            bootstrap_samples=500,
            permutation_samples=500,
            seed=29,
        )
        self.assertFalse(report["passed"])
        self.assertFalse(report["gates"]["forced_control_fraction_le_0_05"])
        self.assertFalse(report["gates"]["informative_confirm_pair_fraction_ge_0_95"])
        self.assertEqual(region["pattern_columns_full"], [])

    def test_unstable_discovery_direction_fails_closed(self) -> None:
        report, region = residual.aggregate(
            make_shards(null=True),
            min_discovery_hits=6,
            min_region_buckets=2,
            max_region_buckets=8,
            min_orientation_cosine=0.0,
            min_coordinate_replication=0.70,
            bootstrap_samples=500,
            permutation_samples=500,
            seed=19,
        )
        self.assertFalse(report["passed"])
        self.assertIsNone(report["next_stage"])
        self.assertEqual(region["pattern_columns_full"], [])
        self.assertFalse(region["fit_authorized"])


if __name__ == "__main__":
    unittest.main()

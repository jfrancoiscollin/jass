from __future__ import annotations

import unittest

from jobs.tools import l3_curriculum_error_conditional_discovery_screen as screen


def decision(label: str, pair_id: int, *, stratum: str = "midgame|kings|quiet", cosine: float = 1.0) -> dict:
    return {
        "label": label, "source": {"opening_id": f"{label}-{pair_id}",
        "exact_state_key": f"{label}-state-{pair_id}", "stratum": stratum},
        "informative_ranking": True, "reclassified_exact_non_error": False,
        "forced_single_action": False, "orientation_cosine": cosine,
        "gradient": [{"coordinate": 7 if label == "error" else 9, "value": 1.0,
                      "representative_full_column": 7 if label == "error" else 9}],
    }


def pair(pair_id: int, split: str = "discovery", **kwargs) -> dict:
    return {"pair_id": pair_id, "split": split,
            "error": decision("error", pair_id, **kwargs),
            "control": decision("control", pair_id, **kwargs)}


class CurriculumErrorConditionalDiscoveryScreenTests(unittest.TestCase):
    def test_outer_confirmation_is_not_dereferenced(self) -> None:
        report = {
            "schema": screen.residual.SCHEMA_REPORT,
            "verdict": "JASS_CURRICULUM_ERROR_RESIDUAL_REGION_NOT_ESTABLISHED",
            "pairs": 353,
            "informative_error_pairs": 290,
            "reclassified_exact_non_errors": {"total": 63},
            "all_splits": {"discovery": 1, "confirm": 352},
            "champion_sha256": "champion",
            "jass_sha256": "jass",
            "search_params_sha256": "search",
        }
        rows = [pair(0)] + [
            {"pair_id": pair_id, "split": "confirm", "error": None, "control": None}
            for pair_id in range(1, 353)
        ]
        shards = [{
            "schema": screen.residual.SCHEMA_SHARD,
            "shard": 0,
            "nshards": 1,
            "champion_sha256": "champion",
            "jass_sha256": "jass",
            "search_params_sha256": "search",
            "rows": rows,
        }]
        discovery = screen._load(shards, report)
        eligible, _ = screen._informative_symmetric(discovery)
        self.assertEqual([row["pair_id"] for row in eligible], [0])

    def test_orientation_and_pair_stratum_filter_is_strict(self) -> None:
        rows = [pair(0), pair(1, cosine=-0.1), pair(2)]
        rows[2]["control"]["source"]["stratum"] = "opening|no_kings|capture"
        eligible, counts = screen._informative_symmetric(rows)
        self.assertEqual([row["pair_id"] for row in eligible], [0])
        self.assertEqual(counts["orientation_unstable"], 1)
        self.assertEqual(counts["stratum_mismatch"], 1)

    def test_component_split_keeps_shared_state_and_pair_atomic(self) -> None:
        rows = [pair(index) for index in range(40)]
        rows[1]["error"]["source"]["exact_state_key"] = rows[0]["control"]["source"]["exact_state_key"]
        fit, validation, audit = screen._inner_split(rows, seed=17)
        side = {row["pair_id"]: "fit" for row in fit} | {row["pair_id"]: "validation" for row in validation}
        self.assertEqual(side[0], side[1])
        self.assertEqual(audit["overlap"], 0)

    def test_fixed_candidate_family_contains_conditional_views(self) -> None:
        self.assertEqual(
            screen._views("midgame|kings|capture"),
            ("ALL", "PHASE=midgame", "TACTICAL=capture", "KINGS=kings",
             "PHASE=midgame|TACTICAL=capture", "PHASE=midgame|KINGS=kings",
             "FULL=midgame|kings|capture"),
        )

    def test_direction_is_fit_only_and_sparse(self) -> None:
        rows = [pair(index) for index in range(20)]
        direction, selected = screen._direction(rows, total=100, min_hits=4, max_buckets=4)
        self.assertEqual(set(direction), {7})
        self.assertEqual(selected[0]["fit_hits"], 20)


if __name__ == "__main__":
    unittest.main()

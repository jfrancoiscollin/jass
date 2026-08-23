from pathlib import Path
import importlib.util
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "l3_curriculum_error_paired_coverage_screen",
    ROOT / "jobs" / "tools" / "l3_curriculum_error_paired_coverage_screen.py",
)
assert SPEC and SPEC.loader
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)


QUIET = "1-2"
OTHER = "3x4 captures=7"


def profile(index: int, margin: float, *, role: str) -> dict:
    rows = {
        str(depth): {
            "moves": [
                {"action": QUIET, "score": 0.0},
                {"action": OTHER, "score": -margin},
            ]
        }
        for depth in C.ranker.FEATURE_DEPTHS
    }
    image_rows = {
        depth: {
            "moves": [
                {
                    "action": C.source._mapped_image_action(row["action"]),
                    "score": row["score"],
                }
                for row in item["moves"]
            ]
        }
        for depth, item in rows.items()
    }
    return {
        "source": {
            "opening_id": f"opening-{index}-{role}",
            "game_uid": f"game-{index}-{role}",
            "exact_state_key": f"state-{index}-{role}",
        },
        "trace": {"original": {"depths": rows}, "exact_image": {"depths": image_rows}},
    }


def pair(index: int, *, split: str = "discovery") -> dict:
    # Everything lies below the failed absolute 50 cp boundary.  The relative
    # band must still obtain deterministic, non-trivial coverage.
    margin = float(index % 49 + 1)
    return {
        "pair_id": index,
        "split": split,
        "error": profile(index, margin, role="error"),
        "control": profile(index, margin, role="control"),
    }


def payload() -> dict:
    discovery = [pair(index) for index in range(128)]
    confirm = [pair(128 + index, split="confirm") for index in range(32)]
    return {
        "schema": C.source.SCHEMA_PAIRS,
        "matching_passed": True,
        "matched_pairs": len(discovery) + len(confirm),
        "pairs_by_split": {"discovery": len(discovery), "confirm": len(confirm)},
        "pairs": discovery + confirm,
        "opening_overlap": 0,
        "maximum_cardinality_matching": True,
    }


class PairedCoverageScreenTests(unittest.TestCase):
    def test_relative_band_passes_with_target_free_broad_support(self):
        report = C.run(payload())
        self.assertEqual(report["verdict"], C.READY)
        self.assertTrue(report["passed"])
        self.assertEqual(report["exact_action_value_reads"], 0)
        self.assertEqual(report["outer_confirm_profile_rows_examined"], 0)
        self.assertFalse(report["residual_fit_authorized"])
        self.assertLess(report["fixed_gate"]["lower_margin_cp"], report["fixed_gate"]["upper_margin_cp"])
        for role in ("error", "control"):
            self.assertGreaterEqual(report["feature_audit_metrics"]["roles"][role]["eligible"], 8)

    def test_action_value_payload_is_rejected_before_screening(self):
        rows = payload()
        rows["pairs"][0]["error"]["action_values"] = {QUIET: {"root_cp": 1}}
        with self.assertRaisesRegex(ValueError, "contains action targets"):
            C.run(rows)

    def test_confirm_profile_payload_is_not_examined(self):
        rows = payload()
        rows["pairs"][-1]["error"]["action_values"] = {QUIET: {"root_cp": 999}}
        report = C.run(rows)
        self.assertEqual(report["verdict"], C.READY)
        self.assertEqual(report["outer_confirm_profile_rows_examined"], 0)
        self.assertEqual(report["outer_confirm_action_value_reads"], 0)

    def test_opening_game_and_state_components_are_atomic(self):
        rows = [pair(index) for index in range(40)]
        rows[1]["error"]["source"]["game_uid"] = rows[0]["control"]["source"]["game_uid"]
        fit, audit, _manifest = C._split(rows, seed=C.SPLIT_SEED)
        owner = {row["pair_id"]: "fit" for row in fit} | {row["pair_id"]: "audit" for row in audit}
        self.assertEqual(owner[0], owner[1])
        fit_ids, audit_ids = C._identity_sets(fit), C._identity_sets(audit)
        self.assertEqual({key: len(fit_ids[key] & audit_ids[key]) for key in fit_ids}, {
            "opening_id": 0,
            "game_uid": 0,
            "exact_state_key": 0,
        })

    def test_exact_image_legal_set_drift_is_rejected(self):
        rows = payload()
        moves = rows["pairs"][0]["error"]["trace"]["exact_image"]["depths"]["9"]["moves"]
        moves.pop()
        with self.assertRaisesRegex(ValueError, "legal action set drift"):
            C.run(rows)


if __name__ == "__main__":
    unittest.main()

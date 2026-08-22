#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from jobs.tools import l3_curriculum_error_learning as learning


START = "W:W31-50:B1-20"
ALT = "W:W26,31-49:B1-19,25"


class CurriculumErrorLearningTests(unittest.TestCase):
    def test_prepare_rejects_a_copied_game(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = {
                "game_id": 1,
                "opening_id": "same-opening",
                "opening": START,
                "jass_is_white": True,
                "jass_score": 0.0,
                "moves": ["31-26"],
                "fens": [START, "B:W26,32-50:B1-20"],
            }
            for name in ("game-001.json", "game-002.json"):
                (root / name).write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "duplicate game identity"):
                learning.prepare_games([root], split_seed=17)

    def test_prepare_rejects_a_state_transposition_across_splits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wanted = {"discovery": None, "confirm": None}
            for value in range(100):
                split = learning._split(str(value), 17)
                if wanted[split] is None:
                    wanted[split] = value
                if all(item is not None for item in wanted.values()):
                    break
            for index, (split, opening_id) in enumerate(wanted.items(), 1):
                payload = {
                    "game_id": index,
                    "opening_id": opening_id,
                    "opening": START,
                    "jass_is_white": True,
                    "jass_score": 0.0 if split == "discovery" else 1.0,
                    "moves": ["31-26"],
                    "fens": [START, "B:W26,32-50:B1-20"],
                }
                (root / f"game-{index:03d}.json").write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "cross discovery/confirm"):
                learning.prepare_games([root], split_seed=17)

    def test_prepare_keeps_all_champion_turns_and_splits_by_opening(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wanted = {"discovery": None, "confirm": None}
            for value in range(100):
                split = learning._split(str(value), 17)
                if wanted[split] is None:
                    wanted[split] = value
                if all(item is not None for item in wanted.values()):
                    break
            for index, (split, opening_id) in enumerate(wanted.items(), 1):
                if index == 1:
                    fens = [START, "B:W26,32-50:B1-20", ALT, START]
                else:
                    fens = [
                        "W:W21-40:B1-20",
                        "B:W22-40:B1-20",
                        "W:W22-40:B2-20",
                        "B:W23-40:B2-20",
                    ]
                payload = {
                    "game_id": index,
                    "opening_id": opening_id,
                    "opening": fens[0],
                    "jass_is_white": True,
                    "jass_score": 0.0 if split == "discovery" else 1.0,
                    "moves": ["31-26", "20-24", "32-27"],
                    "fens": fens,
                }
                (root / f"game-{index:03d}.json").write_text(json.dumps(payload))
            report = learning.prepare_games([root], split_seed=17)
            self.assertEqual(report["decisions"], 4)
            by_opening: dict[str, set[str]] = {}
            for row in report["rows"]:
                by_opening.setdefault(row["opening_id"], set()).add(row["split"])
            self.assertTrue(all(len(splits) == 1 for splits in by_opening.values()))
            self.assertEqual(set(report["games_by_outcome"]), {"loss", "win"})

    def test_aggregate_confirms_region_on_sealed_openings(self) -> None:
        rows = []
        ordinal = 0
        for split in ("discovery", "confirm"):
            for kind, fen, outcome, regret in (
                ("error", START, "loss", 120),
                ("control", ALT, "win", 0),
            ):
                for index in range(12):
                    rows.append(
                        {
                            "ordinal": ordinal,
                            "game_uid": f"{split}-{kind}-{index}",
                            "opening_id": f"{split}-{kind}-{index}",
                            "split": split,
                            "outcome": outcome,
                            "ply": 10,
                            "fen": fen,
                            "actual_move": "31-26",
                            "stratum": "midgame|no_kings|quiet",
                            "move_differs": kind == "error",
                            "regret_cp": regret,
                            **(
                                {
                                    "exact_symmetry": {
                                        "score_delta": 0,
                                        "original_static_score": 1,
                                        "image_static_score": 1,
                                    }
                                }
                                if ordinal == 0
                                else {}
                            ),
                        }
                    )
                    ordinal += 1
        selection = {
            "schema": learning.SCHEMA_SELECTION,
            "decisions": len(rows),
            "rows": [{"ordinal": index} for index in range(len(rows))],
        }
        selection_sha = hashlib.sha256(learning._canonical(selection)).hexdigest()
        shard = {
            "schema": learning.SCHEMA_SHARD,
            "selection_sha256": selection_sha,
            "champion_sha256": "a" * 64,
            "jass_sha256": "c" * 64,
            "search_params_sha256": "d" * 64,
            "shard": 0,
            "nshards": 1,
            "teacher_depth": 10,
            "judge_depth": 12,
            "max_rows": 0,
            "rows": rows,
        }
        report, region, seeds = learning.aggregate(
            selection,
            [shard],
            min_regret_cp=50,
            max_control_regret_cp=10,
            min_error_openings=8,
            min_discovery_hits=4,
            discovery_risk_ratio=1.5,
            confirm_risk_ratio=1.5,
            min_confirmed_buckets=1,
            max_region_buckets=32,
            match_seed=19,
        )
        self.assertTrue(report["fit_authorized"])
        self.assertEqual(report["loss_error_openings"], 24)
        self.assertGreaterEqual(report["confirmed_buckets"], 1)
        self.assertTrue(region["fit_authorized"])
        self.assertEqual(region["extras"], [])
        self.assertEqual(seeds[:4], b"JNNW")
        self.assertEqual(struct.unpack_from("<I", seeds, 4)[0], 24)
        self.assertEqual(len(seeds), 8 + 24 * 38)

    def test_aggregate_refuses_terminal_loss_without_regret(self) -> None:
        selection = {"schema": learning.SCHEMA_SELECTION, "decisions": 2, "rows": []}
        digest = hashlib.sha256(learning._canonical(selection)).hexdigest()
        rows = [
            {
                "ordinal": index,
                "game_uid": f"g{index}",
                "opening_id": f"o{index}",
                "split": "discovery" if index == 0 else "confirm",
                "outcome": "loss",
                "ply": 2,
                "fen": START,
                "stratum": "opening|no_kings|quiet",
                "move_differs": False,
                "regret_cp": 0,
                **({"exact_symmetry": {"score_delta": 0}} if index == 0 else {}),
            }
            for index in range(2)
        ]
        shard = {
            "schema": learning.SCHEMA_SHARD,
            "selection_sha256": digest,
            "champion_sha256": "b" * 64,
            "jass_sha256": "c" * 64,
            "search_params_sha256": "d" * 64,
            "shard": 0,
            "nshards": 1,
            "teacher_depth": 10,
            "judge_depth": 12,
            "max_rows": 0,
            "rows": rows,
        }
        report, region, _seeds = learning.aggregate(
            selection,
            [shard],
            min_regret_cp=50,
            max_control_regret_cp=10,
            min_error_openings=1,
            min_discovery_hits=1,
            discovery_risk_ratio=1.0,
            confirm_risk_ratio=1.0,
            min_confirmed_buckets=1,
            max_region_buckets=8,
            match_seed=1,
        )
        self.assertFalse(report["fit_authorized"])
        self.assertEqual(report["loss_error_openings"], 0)
        self.assertFalse(region["fit_authorized"])

    def test_error_inference_has_one_vote_per_opening(self) -> None:
        rows = [
            {
                "opening_id": "paired-opening",
                "game_uid": f"g{index}",
                "regret_cp": regret,
                "ply": ply,
            }
            for index, (regret, ply) in enumerate(((80, 12), (120, 8), (120, 20)))
        ]
        selected = learning._one_per_opening(rows)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["ply"], 20)

    def test_control_opening_must_be_clean_on_every_observed_decision(self) -> None:
        error = {
            "opening_id": "error",
            "game_uid": "error-game",
            "split": "discovery",
            "stratum": "midgame|no_kings|quiet",
            "outcome": "loss",
            "regret_cp": 100,
            "ply": 10,
        }
        rows = [error] + [
            {
                "opening_id": "dirty-control",
                "game_uid": "control-game",
                "split": "discovery",
                "stratum": "midgame|no_kings|quiet",
                "outcome": "win",
                "regret_cp": regret,
                "ply": ply,
            }
            for regret, ply in ((0, 8), (40, 12))
        ]
        controls = learning._matched_controls(
            [error], rows, seed=1, max_control_regret=10
        )
        self.assertEqual(controls, [])


if __name__ == "__main__":
    unittest.main()

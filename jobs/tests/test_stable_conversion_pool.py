#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import gzip
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "tools/stable_conversion_pool.py"
SPEC = importlib.util.spec_from_file_location("stable_conversion_pool", MODULE)
SCP = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = SCP
SPEC.loader.exec_module(SCP)


class FakeJass:
    def __init__(self, children: dict[bytes, list[dict]],
                 legal_overrides: dict[bytes, str] | None = None):
        self._children = children
        self._legal_overrides = legal_overrides or {}

    def children(self, fens):
        return [self._children.get(SCP.parse_fen(fen).key(), []) for fen in fens]

    def legal(self, fens):
        return [self._legal_overrides.get(SCP.parse_fen(fen).key(), "31>26")
                for fen in fens]


def make_trajectory(game: int, move: str, child: str) -> dict:
    opening = SCP.START_FEN
    fens = [opening, child]
    moves = [move]
    return {
        "schema": 1,
        "source_game_id": f"game-{game}",
        "game_index": game,
        "shard": 0,
        "seed_source": "ONP",
        "opening": opening,
        "outcome": "D",
        "reason": "ply cap",
        "fens": fens,
        "moves": moves,
        "trajectory_hash": SCP.trajectory_digest(opening, fens, moves),
    }


class StableConversionPoolTests(unittest.TestCase):
    def setUp(self):
        self.children = [
            "W:W31,32,33,34:B1,2",
            "B:W31,32,33,34:B1,2",
            "W:W31,32:B1,2,3,4",
            "B:W31,32:B1,2,3,4",
        ]
        self.moves = ["31-26", "32-27", "33-28", "34-29"]

    def write_trajectories(self, root: Path) -> Path:
        path = root / "trajectories.jsonl"
        rows = [make_trajectory(i, move, child)
                for i, (move, child) in enumerate(zip(self.moves, self.children), start=1)]
        path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        return path

    def fake_engine(self, *, legal_overrides=None) -> FakeJass:
        root_key = SCP.parse_fen(SCP.START_FEN).key()
        children = [{"move": move, "capture": False, "fen": fen}
                    for move, fen in zip(self.moves, self.children)]
        return FakeJass({root_key: children}, legal_overrides)

    def build_args(self, root: Path, trajectory: Path):
        return SCP.build_parser().parse_args([
            "build", "--jass", "unused", "--trajectory", str(trajectory),
            "--max-positions", "4", "--out-pool", str(root / "pool.fen"),
            "--out-proof", str(root / "proof.jsonl"),
            "--manifest", str(root / "manifest.json"),
        ])

    def write_corpus(self, root: Path, *, seeded_index: int | None = None,
                     opening_ids: list[int] | None = None):
        records = []
        metadata = []
        for index, fen in enumerate(self.children):
            records.append(SCP.parse_fen(fen).key() + struct.pack("<ib", 0, 0))
            metadata.append(struct.pack(
                "<QQB", 100 + index,
                (opening_ids[index] if opening_ids else 1000 + index),
                1 if index == seeded_index else 0,
            ))
        data, meta = root / "source.jnnw.gz", root / "source.jsm.gz"
        with gzip.open(data, "wb") as handle:
            handle.write(b"JNNW" + struct.pack("<I", len(records)) + b"".join(records))
        with gzip.open(meta, "wb") as handle:
            handle.write(b"JSM1" + struct.pack("<I", len(metadata)) + b"".join(metadata))
        return data, meta

    def test_fen_parser_expands_ranges_and_measures_exact_two_men(self):
        board = SCP.parse_fen("W:W31-34,K40:B1-2,K10")
        facts = SCP.material_facts(board)
        self.assertEqual(facts["white_men"], 4)
        self.assertEqual(facts["black_men"], 2)
        self.assertEqual(facts["king_gap"], 0)
        self.assertEqual(facts["value_gap"], 2)
        self.assertEqual(SCP.parse_fen(board.fen()).key(), board.key())

    def test_build_and_independent_audit_publish_balanced_proofs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            trajectory = self.write_trajectories(root)
            engine = self.fake_engine()
            args = self.build_args(root, trajectory)
            self.assertEqual(SCP.build_pool(args, engine), 0)

            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["gate_ready"])
            self.assertEqual(manifest["selected_positions"], 4)
            self.assertEqual(manifest["selected_source_games"], 4)
            self.assertEqual(set(manifest["selected_cells"].values()), {1})
            self.assertEqual(manifest["trajectory_plies_verified"], 4)

            proofs = [json.loads(line) for line in
                      (root / "proof.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(proofs), 4)
            self.assertTrue(all(row["stability"]["quiet_white"] for row in proofs))
            self.assertTrue(all(row["stability"]["quiet_black"] for row in proofs))
            self.assertTrue(all(
                row["stability"]["scope"] == "all_legal_first_plies_only"
                and row["stability"]["certifies_theoretical_win"] is False
                for row in proofs
            ))
            self.assertTrue(all(
                row["provenance"]["source_outcome_not_used_for_selection"]
                for row in proofs
            ))
            self.assertTrue(all(row["material"]["value_gap"] == 2 for row in proofs))

            audit_args = SCP.build_parser().parse_args([
                "audit", "--jass", "unused", "--trajectory", str(trajectory),
                "--pool", str(root / "pool.fen"),
                "--proof", str(root / "proof.jsonl"),
                "--manifest", str(root / "audit.json"),
            ])
            self.assertEqual(SCP.audit_pool(audit_args, engine), 0)
            audit = json.loads((root / "audit.json").read_text(encoding="utf-8"))
            self.assertTrue(audit["audit_pass"])
            self.assertEqual(audit["positions"], 4)
            self.assertEqual(
                audit["stability_scope"], "all_legal_first_plies_only"
            )
            self.assertFalse(audit["certifies_theoretical_win"])

    def test_capture_for_either_colour_makes_pool_not_gate_ready(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            trajectory = self.write_trajectories(root)
            tactical = SCP.parse_fen(self.children[0]).with_stm("B").key()
            engine = self.fake_engine(legal_overrides={tactical: "1>12*7"})
            args = self.build_args(root, trajectory)
            self.assertEqual(SCP.build_pool(args, engine), 2)
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["gate_ready"])
            self.assertEqual(manifest["selected_positions"], 0)
            # The same board occurs with both STMs in this fixture.  Auditing
            # both colours rejects both records when Black has a capture.
            self.assertEqual(manifest["rejected_stability"]["capture_available"], 2)

    def test_gzip_jnnw_jsm1_mode_uses_opening_as_unit_and_reaudits_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data, meta = self.write_corpus(root)
            args = SCP.build_parser().parse_args([
                "build", "--jass", "unused", "--corpus", str(data), str(meta),
                "--max-positions", "4", "--out-pool", str(root / "pool.fen"),
                "--out-proof", str(root / "proof.jsonl"),
                "--manifest", str(root / "manifest.json"),
            ])
            engine = self.fake_engine()
            self.assertEqual(SCP.build_pool(args, engine), 0)
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_mode"], "jnnw_jsm1_unseeded_selfplay")
            self.assertEqual(manifest["selected_opening_ids"], 4)
            self.assertIsNone(manifest["trajectory_plies_verified"])
            self.assertEqual(manifest["inputs"][0]["seeded_records"], 0)

            proofs = [json.loads(line) for line in
                      (root / "proof.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertTrue(all(
                proof["provenance"]["kind"] == "jnnw_jsm1_unseeded_selfplay"
                for proof in proofs
            ))
            self.assertEqual(
                {proof["provenance"]["source_opening_id"] for proof in proofs},
                {1000, 1001, 1002, 1003},
            )

            audit_args = SCP.build_parser().parse_args([
                "audit", "--jass", "unused", "--corpus", str(data), str(meta),
                "--pool", str(root / "pool.fen"),
                "--proof", str(root / "proof.jsonl"),
                "--manifest", str(root / "audit.json"),
            ])
            self.assertEqual(SCP.audit_pool(audit_args, engine), 0)
            audit = json.loads((root / "audit.json").read_text(encoding="utf-8"))
            self.assertTrue(audit["standard_selfplay_jsm1_seeded_zero"])
            self.assertEqual(audit["source_opening_ids"], 4)

    def test_corpus_mode_hard_fails_if_any_jsm1_row_is_seeded(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data, meta = self.write_corpus(root, seeded_index=2)
            args = SCP.build_parser().parse_args([
                "build", "--jass", "unused", "--corpus", str(data), str(meta),
                "--max-positions", "4", "--out-pool", str(root / "pool.fen"),
                "--out-proof", str(root / "proof.jsonl"),
                "--manifest", str(root / "manifest.json"),
            ])
            with self.assertRaisesRegex(ValueError, "not standard-only"):
                SCP.build_pool(args, self.fake_engine())

    def test_corpus_selection_never_uses_two_records_from_one_opening(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            data, meta = self.write_corpus(
                root, opening_ids=[1000, 1000, 1002, 1003]
            )
            args = SCP.build_parser().parse_args([
                "build", "--jass", "unused", "--corpus", str(data), str(meta),
                "--max-positions", "4", "--out-pool", str(root / "pool.fen"),
                "--out-proof", str(root / "proof.jsonl"),
                "--manifest", str(root / "manifest.json"),
            ])
            self.assertEqual(SCP.build_pool(args, self.fake_engine()), 2)
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["gate_ready"])
            self.assertEqual(manifest["selected_positions"], 0)

    def test_balancer_reroutes_a_shared_opening_out_of_a_rare_cell(self):
        def source(record, opening):
            return SCP.CorpusSource(
                "data", "d" * 64, "meta", "m" * 64,
                record, 100 + record, opening, 0,
            )

        def candidate(fen, src):
            board = SCP.parse_fen(fen)
            facts = SCP.material_facts(board)
            low, high = sorted((facts["white_pieces"], facts["black_pieces"]))
            return SCP.Candidate(
                board, src, -1, facts["advantaged"], low, high,
            )

        # opening 1 is the only source for cell B but also has a candidate in
        # cell A. opening 2 can fill A. The old greedy selector could consume
        # opening 1 in A and incorrectly report that no balanced pool exists.
        a_shared = candidate("W:W31,32,33,34:B1,2", source(1, 1))
        b_rare = candidate("B:W31,32,33,34:B1,2", source(2, 1))
        a_fallback = candidate("W:W30,32,33,34:B1,2", source(3, 2))
        c = candidate("W:W31,32:B1,2,3,4", source(4, 3))
        d = candidate("B:W31,32:B1,2,3,4", source(5, 4))
        seed = next(value for value in range(1000)
                    if SCP._rank(a_shared, value) < SCP._rank(a_fallback, value))

        selected, counts, target = SCP.select_balanced(
            [a_shared, b_rare, a_fallback, c, d],
            piece_pairs=set(), max_positions=4, seed=seed,
        )

        self.assertEqual(target, 1)
        self.assertEqual(len(selected), 4)
        self.assertEqual(set(counts.values()), {1})
        self.assertEqual(len({row.source_key for row in selected}), 4)
        self.assertIn(b_rare.position_id, {row.position_id for row in selected})

    def test_top3_contract_creates_twelve_exactly_balanced_cells(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            records, metadata = [], []
            index = 0
            for low, high in ((16, 18), (17, 19), (18, 20)):
                for advantaged in ("W", "B"):
                    for stm in ("W", "B"):
                        white_n = high if advantaged == "W" else low
                        black_n = high if advantaged == "B" else low
                        white = ",".join(str(square) for square in range(21, 21 + white_n))
                        black = ",".join(str(square) for square in range(1, 1 + black_n))
                        board = SCP.parse_fen(f"{stm}:W{white}:B{black}")
                        records.append(board.key() + struct.pack("<ib", 0, 0))
                        metadata.append(struct.pack("<QQB", 500 + index, 5000 + index, 0))
                        index += 1
            data, meta = root / "top3.jnnw.gz", root / "top3.jsm.gz"
            with gzip.open(data, "wb") as handle:
                handle.write(b"JNNW" + struct.pack("<I", 12) + b"".join(records))
            with gzip.open(meta, "wb") as handle:
                handle.write(b"JSM1" + struct.pack("<I", 12) + b"".join(metadata))
            args = SCP.build_parser().parse_args([
                "build", "--jass", "unused", "--corpus", str(data), str(meta),
                "--piece-pair", "16:18", "--piece-pair", "17:19",
                "--piece-pair", "18:20", "--max-positions", "12",
                "--out-pool", str(root / "pool.fen"),
                "--out-proof", str(root / "proof.jsonl"),
                "--manifest", str(root / "manifest.json"),
            ])
            self.assertEqual(SCP.build_pool(args, self.fake_engine()), 0)
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["selected_cells"]), 12)
            self.assertEqual(set(manifest["selected_cells"].values()), {1})

    def test_illegal_source_transition_is_rejected_before_pooling(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            trajectory = self.write_trajectories(root)
            engine = self.fake_engine()
            root_key = SCP.parse_fen(SCP.START_FEN).key()
            engine._children[root_key] = engine._children[root_key][1:]
            with self.assertRaisesRegex(ValueError, "illegal/desynchronised trajectory"):
                SCP.build_pool(self.build_args(root, trajectory), engine)


if __name__ == "__main__":
    unittest.main()

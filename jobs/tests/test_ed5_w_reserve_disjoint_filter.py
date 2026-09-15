from __future__ import annotations

from pathlib import Path
import struct
import tempfile
import unittest

from jobs.tools import ed4_fresh_w_source_stage as base
from jobs.tools import ed5_fresh_w_source_disjoint_filter_stage as repair


def record(square: int, stm: int = 0) -> bytes:
    raw = bytearray(base.JNNW_REC)
    struct.pack_into("<4Q", raw, 0, 1 << square, 0, 0, 0)
    raw[32] = stm
    raw[33:38] = b"\0" * 5
    return bytes(raw)


def rows_for_openings(openings: int) -> list[dict]:
    rows: list[dict] = []
    raw_index = 0
    for opening in range(openings):
        for game_slot in range(base.GAMES_PER_OPENING):
            game_id = 1000 + opening * 10 + game_slot
            for ply in range(base.ROWS_PER_GAME):
                rows.append({
                    "raw_row_index": raw_index,
                    "game_id": game_id,
                    "opening_id": 100 + opening,
                    "seeded": 0,
                    "ply": ply,
                    "game_plies": base.ROWS_PER_GAME,
                    "last_eps_ply": 0,
                    "flags": 0,
                })
                raw_index += 1
    return rows


def write_jnnw(path: Path, count: int) -> list[bytes]:
    recs = [record(i % 49, (i // 49) % 2) for i in range(count)]
    path.write_bytes(b"JNNW" + struct.pack("<I", count) + b"".join(recs))
    return recs


class Ed5WReserveDisjointFilterTests(unittest.TestCase):
    def test_skips_colliding_opening_and_preserves_shape_and_order(self) -> None:
        rows = rows_for_openings(3)
        with tempfile.TemporaryDirectory() as tmp:
            jnnw = Path(tmp) / "safe-full.jnnw"
            recs = write_jnnw(jnnw, len(rows))
            forbidden = {base.canonical_position(recs[0])}
            selected, groups, support = repair.select_rows_with_forbidden(
                rows, jnnw, 2, forbidden
            )
        self.assertEqual(selected, list(range(16, 48)))
        self.assertEqual(len(groups), 32)
        self.assertEqual({row["opening_id"] for row in groups}, {101, 102})
        self.assertEqual(support["selected_openings"], 2)
        self.assertEqual(support["selected_games"], 4)
        self.assertEqual(support["selected_positions"], 32)
        self.assertEqual(support["forbidden_openings_skipped"], 1)
        self.assertEqual(support["forbidden_selected_rows_seen"], 1)

    def test_insufficient_after_exclusion_fails_closed(self) -> None:
        rows = rows_for_openings(2)
        with tempfile.TemporaryDirectory() as tmp:
            jnnw = Path(tmp) / "safe-full.jnnw"
            recs = write_jnnw(jnnw, len(rows))
            forbidden = {base.canonical_position(recs[0])}
            with self.assertRaises(base.SupportInsufficient) as ctx:
                repair.select_rows_with_forbidden(rows, jnnw, 2, forbidden)
        self.assertEqual(ctx.exception.report["forbidden_openings_skipped"], 1)
        self.assertEqual(ctx.exception.report["required_paired_openings"], 2)

    def test_nonzero_target_bytes_fail_closed(self) -> None:
        rows = rows_for_openings(1)
        with tempfile.TemporaryDirectory() as tmp:
            jnnw = Path(tmp) / "safe-full.jnnw"
            recs = list(write_jnnw(jnnw, len(rows)))
            bad = bytearray(recs[0])
            bad[33] = 1
            recs[0] = bytes(bad)
            jnnw.write_bytes(b"JNNW" + struct.pack("<I", len(recs)) + b"".join(recs))
            with self.assertRaisesRegex(ValueError, "target_bytes_nonzero"):
                repair.select_rows_with_forbidden(rows, jnnw, 1, set())


if __name__ == "__main__":
    unittest.main()

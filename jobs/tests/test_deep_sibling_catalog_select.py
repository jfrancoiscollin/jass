from __future__ import annotations

import hashlib
import sqlite3
import unittest

from jobs.tools import deep_sibling_catalog_select as base
from jobs.tools import deep_sibling_catalog_select_runner as runner
from jobs.tools.tb_frontier_symmetry_dedup import canonical_fingerprint, symmetric_fingerprint


class DeepSiblingSelectionTests(unittest.TestCase):
    def test_frozen_phase_quotas_and_bounds(self):
        self.assertEqual(base.PHASES, {
            "P0": (30, 40, 2000),
            "P1": (20, 29, 2000),
            "P2": (12, 19, 2000),
            "P3": (9, 11, 2000),
        })
        for p in range(30, 41): self.assertEqual(base.phase_for(p), "P0")
        for p in range(20, 30): self.assertEqual(base.phase_for(p), "P1")
        for p in range(12, 20): self.assertEqual(base.phase_for(p), "P2")
        for p in range(9, 12): self.assertEqual(base.phase_for(p), "P3")
        with self.assertRaises(ValueError): base.phase_for(8)
        with self.assertRaises(ValueError): base.phase_for(41)

    def test_frozen_hash_rules(self):
        fp = "0000000000001:0000000000000:0000000000002:0000000000000:0"
        self.assertEqual(
            base.sample_hash(fp),
            "7cba5b9fed318abb13f8c6d7d7f2f72831e5a0b2bd488d452e06b9496169579c",
        )
        identity = "sha256:" + "a" * 64
        self.assertEqual(base.source_bucket(identity), 0)
        expected = int.from_bytes(hashlib.sha256(f"2026083102:{identity}".encode()).digest()[:8], "little") % 5
        self.assertEqual(expected, 0)

    def test_selector_uses_same_historical_symmetry(self):
        fp = "0000000000001:0000000000000:0000000000002:0000000000000:0"
        sym = symmetric_fingerprint(fp)
        self.assertEqual(canonical_fingerprint(fp), canonical_fingerprint(sym))

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(":memory:")
        base.init_db(db)
        return db

    def _add(self, db: sqlite3.Connection, bucket: int, path: str, raw_fp: str):
        return runner.merge_occurrence(
            db,
            canonical="canon", phase="P1", hash_key="hash", rec=b"\0" * 38,
            raw_fp=raw_fp, stm=0 if bucket else 1, pieces=24, legal_moves=3,
            source_identity=f"source-{bucket}-{path}", bucket=bucket,
            candidate_id=f"cid-{path}", source_path=path, source_row_index=7,
        )

    def test_cross_partition_duplicate_holdout_wins(self):
        db = self._db()
        self._add(db, 2, "z-train", "train-fp")
        inserted, new_cross = self._add(db, 0, "a-holdout", "holdout-fp")
        self.assertFalse(inserted)
        self.assertTrue(new_cross)
        row = db.execute(
            "SELECT has_holdout,cross_partition,source_bucket,raw_fp,occurrence_count FROM parents WHERE canonical='canon'"
        ).fetchone()
        self.assertEqual(row, (1, 1, 0, "holdout-fp", 2))

    def test_holdout_win_is_order_independent(self):
        for reverse in (False, True):
            db = self._db()
            seq = [(0, "h", "holdout-fp"), (3, "t", "train-fp")]
            if reverse: seq.reverse()
            for bucket, path, fp in seq: self._add(db, bucket, path, fp)
            row = db.execute(
                "SELECT has_holdout,cross_partition,source_bucket,raw_fp,occurrence_count FROM parents WHERE canonical='canon'"
            ).fetchone()
            self.assertEqual(row, (1, 1, 0, "holdout-fp", 2))


if __name__ == "__main__":
    unittest.main()

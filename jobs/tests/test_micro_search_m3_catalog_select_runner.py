from __future__ import annotations

import csv
import importlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest


class MicroSearchM3SelectorTests(unittest.TestCase):
    def test_preregistered_quotas_and_exclusions(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            canon = root / "prior.tsv"
            with canon.open("w", newline="", encoding="utf-8") as handle:
                wr = csv.DictWriter(handle, fieldnames=["canonical_fingerprint"], delimiter="\t")
                wr.writeheader()
                wr.writerow({"canonical_fingerprint": "deadbeef"})
            force = root / "force"
            force.mkdir()
            (force / "p1.fen").write_text("W:W31,32:B1,2\n", encoding="utf-8")
            report = root / "report.json"

            old = dict(os.environ)
            os.environ["JASS_M3_EXCLUDE_CANON_TSVS"] = str(canon)
            os.environ["JASS_M3_FORCE_FEN_DIR"] = str(force)
            os.environ["JASS_M3_EXCLUSION_REPORT"] = str(report)
            try:
                mod = importlib.import_module("jobs.tools.micro_search_m3_catalog_select_runner")
                self.assertEqual(
                    {k: v[2] for k, v in mod.M3_PHASES.items()},
                    {"P0": 25000, "P1": 25000, "P2": 25000, "P3": 25000},
                )
                self.assertIn("deadbeef", mod.BLOCK_CANON)
                self.assertEqual(len(mod.BLOCK_EXACT), 1)

                db = sqlite3.connect(":memory:")
                mod.base.init_db(db)
                rec = b"\0" * 38
                # Canonical-blocked row never enters the selection DB.
                got = mod.merge_occurrence(
                    db,
                    canonical="deadbeef",
                    phase="P0",
                    hash_key="00",
                    rec=rec,
                    raw_fp="1:0:0:2:0",
                    stm=0,
                    pieces=32,
                    legal_moves=2,
                    source_identity="s",
                    bucket=1,
                    candidate_id="c",
                    source_path="p",
                    source_row_index=0,
                )
                self.assertEqual(got, (False, False))
                self.assertEqual(db.execute("SELECT COUNT(*) FROM parents").fetchone()[0], 0)

                # Force exact row is blocked independently of its canonical id.
                stm, wm, wk, bm, bk = next(iter(mod.BLOCK_EXACT))
                raw_fp = f"{wm:x}:{wk:x}:{bm:x}:{bk:x}:{stm}"
                got = mod.merge_occurrence(
                    db,
                    canonical="not-blocked-canonical",
                    phase="P0",
                    hash_key="01",
                    rec=rec,
                    raw_fp=raw_fp,
                    stm=stm,
                    pieces=32,
                    legal_moves=2,
                    source_identity="s",
                    bucket=1,
                    candidate_id="c",
                    source_path="p",
                    source_row_index=1,
                )
                self.assertEqual(got, (False, False))
                self.assertEqual(db.execute("SELECT COUNT(*) FROM parents").fetchone()[0], 0)

                # An unblocked row uses the audited 17-column insert path.
                got = mod.merge_occurrence(
                    db,
                    canonical="allowed",
                    phase="P0",
                    hash_key="02",
                    rec=rec,
                    raw_fp="1:0:2:0:0",
                    stm=0,
                    pieces=32,
                    legal_moves=2,
                    source_identity="s",
                    bucket=1,
                    candidate_id="c",
                    source_path="p",
                    source_row_index=2,
                )
                self.assertEqual(got, (True, False))
                self.assertEqual(db.execute("SELECT COUNT(*) FROM parents").fetchone()[0], 1)

                mod._write_exclusion_report()
                payload = json.loads(report.read_text(encoding="utf-8"))
                self.assertEqual(payload["selection_seed"], 2026090210)
                self.assertFalse(payload["source_labels_read"])
                self.assertEqual(payload["teacher_scores_read"], 0)
                self.assertEqual(payload["fits"], 0)
                self.assertEqual(payload["strength_games"], 0)
            finally:
                os.environ.clear()
                os.environ.update(old)


if __name__ == "__main__":
    unittest.main()

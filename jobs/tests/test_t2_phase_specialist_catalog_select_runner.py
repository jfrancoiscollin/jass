from __future__ import annotations

import csv
import importlib
import json
import os
from pathlib import Path
import tempfile
import unittest


class T2FreshSelectorTests(unittest.TestCase):
    def test_frozen_t2_quotas_seed_and_zero_read_contract(self) -> None:
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
                mod = importlib.import_module("jobs.tools.t2_phase_specialist_catalog_select_runner")
                self.assertEqual(mod.T2_SELECTION_SEED, 2026090610)
                self.assertEqual(
                    {k: v[2] for k, v in mod.T2_PHASES.items()},
                    {"P0": 2000, "P1": 2000, "P2": 2000, "P3": 2000},
                )
                self.assertEqual(mod.m3.base.PHASES, mod.T2_PHASES)
                self.assertIn("deadbeef", mod.m3.BLOCK_CANON)
                self.assertEqual(len(mod.m3.BLOCK_EXACT), 1)
                mod._write_exclusion_report()
                payload = json.loads(report.read_text(encoding="utf-8"))
                self.assertEqual(payload["schema"], "jass.t2_phase_specialist_exclusions.v1")
                self.assertEqual(payload["selection_seed"], 2026090610)
                self.assertEqual(payload["phase_quotas"], {"P0": 2000, "P1": 2000, "P2": 2000, "P3": 2000})
                for key in ("teacher_scores_read", "t2_scores_read", "d1_scores_read", "q1_label_reads", "q1_score_reads", "fits", "strength_games"):
                    self.assertEqual(payload[key], 0)
                self.assertFalse(payload["source_labels_read"])
                self.assertFalse(payload["promotion_authorized"])
            finally:
                os.environ.clear()
                os.environ.update(old)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from jobs.tools import l3_curriculum_repair_corpus_audit as audit


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


class RepairCorpusAuditTests(unittest.TestCase):
    def test_exact_seed_lineage_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lineage = {
                "schema": audit.SCHEMA_SEEDS,
                "rows": [{"record_index": 0}, {"record_index": 1}],
            }
            seed_report = {
                "schema": audit.SCHEMA_SEEDS,
                "verdict": "JASS_CURRICULUM_REPAIR_SEEDS_READY",
                "generation_authorized": True,
                "champion_sha256": "a" * 64,
                "seed_positions": 2,
                "lineage_sha256": hashlib.sha256(canonical(lineage)).hexdigest(),
            }
            data = root / "repair.jnnw"
            meta = root / "repair.jsm"
            usage = root / "repair.jssu"
            data.write_bytes(b"JNNW" + struct.pack("<I", 2) + b"\0" * 37 + b"\xff" + b"\0" * 37 + b"\1")
            rows = (
                audit.JSM2.pack(10, 1, 1, 0, 1, 0xFFFF, -1, 0)
                + audit.JSM2.pack(11, 2, 1, 0, 1, 0xFFFF, 1, 0)
            )
            meta.write_bytes(b"JSM2" + struct.pack("<I", 2) + rows)
            usage.write_text("JSSU1\topening_id\tseed_index\n1\t0\n2\t1\n", encoding="utf-8")
            old = audit.TARGET_RECORDS
            audit.TARGET_RECORDS = 2
            try:
                report = audit.audit(
                    data=data,
                    meta=meta,
                    seed_usage=usage,
                    seed_report=seed_report,
                    lineage=lineage,
                    generator_log=(
                        "LABELHYG label_score_searches=0\n"
                        "EXPLORATION split_selfplay_rngs=1 openings=2 seeded_openings=2 "
                        "standard_openings=0 seed_catalogue_positions=2 seed_frac=100 "
                        "seed_without_replacement=1 seed_unique_used=2 seed_reuses=0 "
                        "seed_usage_rows=2 games=2\n"
                    ),
                    champion_sha256="a" * 64,
                    source_job="source",
                    source_attempt="attempt",
                    source_code_sha="b" * 64,
                )
            finally:
                audit.TARGET_RECORDS = old
            self.assertEqual(report["verdict"], "JASS_CURRICULUM_REPAIR_CORPUS_READY")
            self.assertEqual(report["seed_reuses"], 0)
            self.assertTrue(report["all_rows_seeded"])

    def test_reused_seed_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            usage = Path(tmp) / "usage.tsv"
            usage.write_text("JSSU1\topening_id\tseed_index\n1\t0\n2\t0\n", encoding="utf-8")
            parsed = audit._parse_usage(usage)
            self.assertNotEqual(len(set(parsed.values())), len(parsed))

    def test_counted_file_rejects_truncation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.jnnw"
            path.write_bytes(b"JNNW" + struct.pack("<I", 1))
            with self.assertRaisesRegex(ValueError, "size"):
                audit._counted_file(path, b"JNNW", 38)


if __name__ == "__main__":
    unittest.main()

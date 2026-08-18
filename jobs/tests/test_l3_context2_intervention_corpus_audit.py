# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

from jobs.tools.l3_conditional_targets import JNNW_DTYPE
from jobs.tools.l3_context2_intervention_corpus_audit import audit


def write_corpus(path: Path, outcomes: list[int]) -> None:
    rows = np.zeros(len(outcomes), dtype=JNNW_DTYPE)
    rows["wdl"] = outcomes
    path.write_bytes(struct.pack("<4sI", b"JNNW", len(rows)) + rows.tobytes())


class Context2InterventionCorpusAuditTests(unittest.TestCase):
    def test_round_trip_accepts_exact_balanced_union(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            quotas = {"BASE": 6, "ROP16": 6, "EPS16": 6, "DECAY120": 6, "TOPK3M30": 6, "DEPTH10": 6}
            cells = {}
            outcomes = [-1, -1, 0, 0, 1, 1]
            for name in quotas:
                path = root / f"{name}.jnnw"
                write_corpus(path, outcomes)
                cells[name] = path
            unified = root / "unified.jnnw"
            write_corpus(unified, outcomes * len(quotas))
            payload = audit(
                cells=cells,
                unified=unified,
                code_sha="a" * 40,
                fresh_seed=123,
                expected_quotas=quotas,
            )
            self.assertEqual(payload["records"], 36)
            self.assertEqual(payload["relative_draw_shift_vs_base"], 0.0)
            self.assertEqual(payload["wdl_side_skew"], 0.0)

    def test_refuses_record_count_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            quotas = {"BASE": 3, "ROP16": 3, "EPS16": 3, "DECAY120": 3, "TOPK3M30": 3, "DEPTH10": 3}
            cells = {}
            for name in quotas:
                path = root / f"{name}.jnnw"
                write_corpus(path, [-1, 0, 1])
                cells[name] = path
            write_corpus(cells["EPS16"], [-1, 1])
            unified = root / "unified.jnnw"
            write_corpus(unified, [-1, 0, 1] * len(quotas))
            with self.assertRaisesRegex(ValueError, "EPS16: 2 records != 3"):
                audit(
                    cells=cells,
                    unified=unified,
                    code_sha="a" * 40,
                    fresh_seed=123,
                    expected_quotas=quotas,
                )


if __name__ == "__main__":
    unittest.main()

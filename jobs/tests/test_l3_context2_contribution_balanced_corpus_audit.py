#!/usr/bin/env python3
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

from jobs.tools.l3_conditional_targets import JNNW_DTYPE
from jobs.tools.l3_context2_contribution_balanced_corpus_audit import (
    CELL_NAMES,
    audit,
)


def write_corpus(path: Path, outcomes: list[int]) -> None:
    rows = np.zeros(len(outcomes), dtype=JNNW_DTYPE)
    rows["wdl"] = outcomes
    path.write_bytes(struct.pack("<4sI", b"JNNW", len(rows)) + rows.tobytes())


class ContributionBalancedCorpusAuditTests(unittest.TestCase):
    def fixture(self, root: Path, outcomes: list[int]) -> dict[str, Path]:
        cells = {}
        for name in CELL_NAMES:
            path = root / f"{name}.jnnw"
            write_corpus(path, outcomes)
            cells[name] = path
        return cells

    def test_preflight_and_complete_corpus_pass_exact_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outcomes = [-1, -1, 0, 0, 1, 1]
            cells = self.fixture(root, outcomes)
            preflight = audit(
                cells=cells,
                expected_per_cell=6,
                code_sha="a" * 40,
                fresh_seed=7,
                seed_source="run/attempt",
            )
            self.assertEqual(
                preflight["verdict"],
                "JASS_CONTEXT2_CONTRIBUTION_BALANCED_PREFLIGHT_PASSED",
            )
            unified = root / "unified.jnnw"
            write_corpus(unified, outcomes * len(CELL_NAMES))
            complete = audit(
                cells=cells,
                expected_per_cell=6,
                code_sha="a" * 40,
                fresh_seed=7,
                seed_source="run/attempt",
                unified=unified,
            )
            self.assertEqual(complete["records"], 36)
            self.assertTrue(complete["guards"]["all_cell_wdl_guards_passed"])

    def test_rejects_cell_count_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cells = self.fixture(root, [-1, 0, 1])
            write_corpus(cells["center_presence"], [-1, 1])
            with self.assertRaisesRegex(ValueError, "center_presence: 2 records"):
                audit(
                    cells=cells,
                    expected_per_cell=3,
                    code_sha="b" * 40,
                    fresh_seed=8,
                    seed_source="run/attempt",
                )

    def test_rejects_wdl_skew_and_draw_shift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cells = self.fixture(root, [-1, 0, 1] * 100)
            write_corpus(cells["blocked_man"], [-1] * 120 + [0] * 60 + [1] * 120)
            with self.assertRaisesRegex(ValueError, "draw shift"):
                audit(
                    cells=cells,
                    expected_per_cell=300,
                    code_sha="c" * 40,
                    fresh_seed=9,
                    seed_source="run/attempt",
                )
            write_corpus(cells["blocked_man"], [-1] * 99 + [0] * 94 + [1] * 107)
            with self.assertRaisesRegex(ValueError, "side skew"):
                audit(
                    cells=cells,
                    expected_per_cell=300,
                    code_sha="c" * 40,
                    fresh_seed=9,
                    seed_source="run/attempt",
                )


if __name__ == "__main__":
    unittest.main()

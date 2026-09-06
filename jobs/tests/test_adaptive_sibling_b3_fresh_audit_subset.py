from __future__ import annotations

import hashlib
import unittest

from jobs.tools import adaptive_sibling_b2_select as selector
from jobs.tools import adaptive_sibling_b3_fresh_audit_subset as subject


class FreshB3AuditSubsetTests(unittest.TestCase):
    def _parents(self):
        parents = []
        parent_id = 0
        for cell in selector.CELL_ORDER:
            phase, stm_text = cell.split("_stm")
            stm = int(stm_text)
            lo, _hi = selector.PHASES[phase]
            for local in range(500):
                canonical = f"{parent_id:013x}:0000000000000:0000000000000:0000000000000:{stm}"
                parents.append(subject.Parent(
                    source_parent_id=parent_id,
                    canonical_fingerprint=canonical,
                    raw_fingerprint=canonical,
                    parent_stm=stm,
                    pieces=lo,
                    legal_moves=2,
                    phase=phase,
                    source_shard=local % 16,
                    source_row_index=local,
                    source_selection_hash=hashlib.sha256(f"source:{canonical}".encode()).hexdigest(),
                    audit_selection_hash=subject.audit_hash(canonical),
                    record=b"\0" * subject.RECORD_SIZE,
                ))
                parent_id += 1
        return parents

    def test_frozen_constants(self) -> None:
        self.assertEqual(subject.AUDIT_SEED, 2026110817)
        self.assertEqual(subject.AUDIT_PARENTS, 1000)
        self.assertEqual(subject.AUDIT_PER_CELL, 125)
        self.assertEqual(subject.VERDICT, "B3_FRESH_AUDIT_SUBSET_SEALED_V1")

    def test_selects_lowest_125_per_cell(self) -> None:
        parents = self._parents()
        selected = subject.select_subset(parents)
        self.assertEqual(len(selected), 1000)
        self.assertEqual(len({p.canonical_fingerprint for p in selected}), 1000)
        for cell in selector.CELL_ORDER:
            actual = [p for p in selected if p.cell == cell]
            expected = sorted([p for p in parents if p.cell == cell], key=lambda p: p.audit_order)[:125]
            self.assertEqual(actual, expected)

    def test_selection_does_not_use_source_selection_hash(self) -> None:
        parents = self._parents()
        baseline = [p.source_parent_id for p in subject.select_subset(parents)]
        mutated = [subject.Parent(
            **{**p.__dict__, "source_selection_hash": "f" * 64}
        ) for p in parents]
        self.assertEqual(baseline, [p.source_parent_id for p in subject.select_subset(mutated)])


if __name__ == "__main__":
    unittest.main()

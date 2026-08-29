import hashlib
import unittest

from jobs.tools.scan_ceiling_select import Candidate
from jobs.tools.search_semantics_discovery_select import (
    DEEP_DOMAIN, DEEP_PER_PHASE, PER_PHASE, SELECTION_DOMAIN,
    SELECTION_SEED, SUBSET_HASH_SEED, frozen_hash, select,
)


class DiscoveryASelectorTest(unittest.TestCase):
    def candidate(self, phase: str, i: int) -> Candidate:
        pieces = {"P0": 35, "P1": 25, "P2": 15, "P3": 10}[phase]
        identity = f"{phase}-canonical-{i:04d}"
        return Candidate(identity, identity, b"", i & 1, pieces, 2 + i % 15,
                         phase, i % 16, i, "ignored", "ignored")

    def test_frozen_hash_has_no_hidden_separator(self):
        identity = "abc"
        self.assertEqual(
            frozen_hash(SELECTION_DOMAIN, SELECTION_SEED, identity),
            hashlib.sha256((SELECTION_DOMAIN + str(SELECTION_SEED) + identity).encode()).hexdigest(),
        )

    def test_exact_phase_quotas_and_deep_nested(self):
        unique = {}
        for phase in ("P0", "P1", "P2", "P3"):
            for i in range(160):
                c = self.candidate(phase, i)
                unique[c.canonical] = c
        chosen, deep, available = select(unique)
        self.assertEqual(len(chosen), 4 * PER_PHASE)
        self.assertEqual(len(deep), 4 * DEEP_PER_PHASE)
        for phase in ("P0", "P1", "P2", "P3"):
            phase_chosen = [c for c in chosen if c.phase == phase]
            self.assertEqual(len(phase_chosen), 128)
            expected = sorted(
                phase_chosen,
                key=lambda c: (frozen_hash(DEEP_DOMAIN, SUBSET_HASH_SEED, c.canonical), c.canonical),
            )[:32]
            self.assertEqual({c.canonical for c in expected}, {c.canonical for c in phase_chosen if c.canonical in deep})
            self.assertEqual(available[phase], 160)

    def test_insufficient_support_is_terminal_selection_error(self):
        unique = {}
        for phase in ("P0", "P1", "P2", "P3"):
            limit = 127 if phase == "P3" else 128
            for i in range(limit):
                c = self.candidate(phase, i)
                unique[c.canonical] = c
        with self.assertRaisesRegex(ValueError, "support insufficient"):
            select(unique)


if __name__ == "__main__":
    unittest.main()

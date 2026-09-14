from __future__ import annotations

from pathlib import Path
import struct
import tempfile
import unittest

from jobs.tools import ed4_fresh_dws_disjointness_stage as d


def record(square: int, stm: int = 0) -> bytes:
    raw = bytearray(38)
    raw[:8] = struct.pack('<Q', 1 << square)
    raw[32] = stm
    raw[33:38] = b'\0' * 5
    return bytes(raw)


def jnnw(path: Path, rows: list[bytes]) -> None:
    path.write_bytes(b'JNNW' + struct.pack('<I', len(rows)) + b''.join(rows))


class FreshDWSDisjointnessTests(unittest.TestCase):
    def test_pairwise_disjoint_sets_pass(self):
        result = d.pairwise_report({'a', 'b'}, {'c'}, {'d', 'e'})
        self.assertTrue(result['pairwise_disjoint'])
        self.assertEqual(result['counts'], {'D': 2, 'W': 1, 'S': 2})
        self.assertEqual(result['overlaps']['D_W']['count'], 0)
        self.assertEqual(result['overlaps']['D_S']['count'], 0)
        self.assertEqual(result['overlaps']['W_S']['count'], 0)

    def test_any_cross_block_duplicate_fails(self):
        result = d.pairwise_report({'a', 'same'}, {'same', 'w'}, {'s'})
        self.assertFalse(result['pairwise_disjoint'])
        self.assertEqual(result['overlaps']['D_W']['count'], 1)
        self.assertEqual(result['overlaps']['D_S']['count'], 0)
        self.assertEqual(result['overlaps']['W_S']['count'], 0)

    def test_canonical_set_never_accepts_target_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'x.jnnw'
            good = record(2)
            bad = bytearray(record(3)); bad[37] = 1
            jnnw(path, [good, bytes(bad)])
            with self.assertRaisesRegex(ValueError, 'target_bytes_nonzero'):
                d.canonical_set(path)

    def test_canonical_digest_matches_unique_identity_contract(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'x.jnnw'
            jnnw(path, [record(2), record(3), record(2)])
            identities = d.canonical_set(path)
            self.assertEqual(len(identities), 2)
            self.assertEqual(d.digest_identities(identities), d.digest_identities(set(identities)))

    def test_overlap_digest_is_stable_and_empty_is_explicit(self):
        self.assertEqual(d.overlap_digest(set()),
                         'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')
        self.assertEqual(d.overlap_digest({'b', 'a'}), d.overlap_digest({'a', 'b'}))


if __name__ == '__main__':
    unittest.main()

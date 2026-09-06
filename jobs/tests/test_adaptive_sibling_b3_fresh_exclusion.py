from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from jobs.tools import adaptive_sibling_b3_fresh_exclusion as subject
from jobs.tools.adaptive_sibling_b2_exclusions import canonical_json_bytes, sha256_file


def fp(offset: int) -> str:
    return f"{1 << offset:013x}:0000000000000:{1 << (49-offset):013x}:0000000000000:0"


class B3FreshExclusionTests(unittest.TestCase):
    def test_canonical_lines_rejects_noncanonical_and_accepts_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ids.txt"
            values = sorted({subject.canonical_fingerprint(fp(i)) for i in range(3)})
            path.write_text("\n".join(values) + "\n", encoding="ascii")
            self.assertEqual(subject.canonical_lines(path, expected_count=3, require_sorted=True), values)

    def test_combine_requires_disjoint_exact_cardinality(self):
        a = subject.canonical_fingerprint(fp(1))
        b = subject.canonical_fingerprint(fp(2))
        c = subject.canonical_fingerprint(fp(3))
        with mock.patch.object(subject, "COMBINED_COUNT", 3):
            combined, overlap = subject.combine([a, b], [c])
            self.assertEqual(overlap, 0)
            self.assertEqual(combined, sorted([a, b, c]))
            with self.assertRaises(subject.StageError):
                subject.combine([a, b], [b])

    def test_verify_b2_authenticates_publication_and_identities(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identities = root / "ordered-identities.txt"
            values = [subject.canonical_fingerprint(fp(4)), subject.canonical_fingerprint(fp(5))]
            identities.write_text("\n".join(values) + "\n", encoding="ascii")
            desc = subject.descriptor(
                identities,
                rows=2,
                serialization="canonical_fingerprint_ascii, one per line, LF terminated",
            )
            publication = {
                "schema": "jass.adaptive_sibling_b2_source_selection_publication.v1",
                "verdict": "B2_SOURCE_SELECTION_LOCAL_SEAL_COMPLETE",
                "selection": {
                    "parents": 2,
                    "forbidden_overlap": 0,
                    "target_blind": True,
                    "ordered_identities": desc,
                },
            }
            pub = root / "source-selection-publication.json"
            pub.write_bytes(canonical_json_bytes(publication))
            with mock.patch.object(subject, "B2_COUNT", 2), \
                 mock.patch.dict(subject.B2, {"publication_sha256": sha256_file(pub)}):
                self.assertEqual(subject.verify_b2(pub, identities), values)

    def test_summary_side_effects_are_zero_by_contract(self):
        self.assertEqual(subject.VERDICT, "B3_FRESH_EXCLUSION_PREPARATION_COMPLETE")
        self.assertEqual(subject.COMBINED_COUNT, 227317)
        self.assertEqual(subject.B2["publication_sha256"],
                         "e61339f1edba4f22e29a9b02b1d1708d426a27626b0f58ea789ea6c5f946cca1")


if __name__ == "__main__":
    unittest.main()

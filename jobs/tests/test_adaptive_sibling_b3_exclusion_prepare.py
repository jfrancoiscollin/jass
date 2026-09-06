from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from jobs.tools import adaptive_sibling_b3_exclusion_prepare as tool


class B3FreshExclusionPrepareTests(unittest.TestCase):
    def test_combined_union_is_sorted_unique_and_rejects_cross_overlap(self) -> None:
        historical = ["h2", "h1"]
        b2 = ["b2", "b1"]
        with mock.patch.object(tool, "HISTORICAL_UNIQUE", 2), \
             mock.patch.object(tool, "B2_PARENTS", 2), \
             mock.patch.object(tool, "EXPECTED_COMBINED_UNIQUE", 4):
            raw, counts = tool.build_combined_union(historical, b2)
            self.assertEqual(raw, b"b1\nb2\nh1\nh2\n")
            self.assertEqual(counts, {
                "historical_unique": 2,
                "b2_unique": 2,
                "cross_overlap": 0,
                "combined_unique": 4,
            })
            with self.assertRaisesRegex(tool.ExclusionPrepareError, "overlap"):
                tool.build_combined_union(["same", "h"], ["same", "b"])

    def test_b2_publication_authenticates_exact_ordered_identity_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            identities = root / "ordered-identities.txt"
            identities.write_bytes(b"x\n")
            with mock.patch.object(tool, "B2_PARENTS", 1):
                descriptor = {
                    "local_name": identities.name,
                    "sha256": tool.sha256_file(identities),
                    "size_bytes": identities.stat().st_size,
                    "rows": 1,
                    "serialization": "canonical_fingerprint_ascii, one per line, LF terminated",
                }
                receipt = {
                    "schema": "jass.adaptive_sibling_b2_source_selection_publication.v1",
                    "status": "VALID",
                    "verdict": "B2_SOURCE_SELECTION_LOCAL_SEAL_COMPLETE",
                    "implementation": {"commit": tool.B2_CODE},
                    "selection": {
                        "parents": 1,
                        "forbidden_overlap": 0,
                        "target_blind": True,
                        "ordered_identities": descriptor,
                    },
                }
                self.assertEqual(tool.validate_b2_publication(receipt, identities), descriptor)
                receipt["selection"]["forbidden_overlap"] = 1
                with self.assertRaisesRegex(tool.ExclusionPrepareError, "exclusion"):
                    tool.validate_b2_publication(receipt, identities)

    def test_canonical_json_roundtrip_is_compact_ascii_lf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "v.json"
            value = {"z": 1, "a": "é"}
            path.write_bytes(tool.canonical_json(value))
            self.assertEqual(tool.read_canonical_json(path), value)
            self.assertEqual(path.read_bytes(), b'{"a":"\\u00e9","z":1}\n')


if __name__ == "__main__":
    unittest.main()

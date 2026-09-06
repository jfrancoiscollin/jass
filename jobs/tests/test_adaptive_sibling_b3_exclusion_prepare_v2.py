from __future__ import annotations

import tempfile
from pathlib import Path
import unittest
from unittest import mock

from jobs.tools import adaptive_sibling_b3_exclusion_prepare as base
from jobs.tools import adaptive_sibling_b3_exclusion_prepare_v2 as tool


class B3FreshExclusionPrepareV2Tests(unittest.TestCase):
    def test_run_binds_union_and_manifest_identities(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work = root / "work"
            artifacts = root / "artifacts"
            artifacts.mkdir()
            union = artifacts / "b3-fresh-exclusion-union.txt"
            manifest = artifacts / "b3-fresh-exclusion-manifest.json"
            summary = artifacts / "scientific-summary.json"
            union.write_bytes(b"a\n")
            manifest_obj = {
                "union": {
                    "sha256": base.sha256_file(union),
                    "unique_canonical": 1,
                }
            }
            manifest.write_bytes(base.canonical_json(manifest_obj))
            summary.write_bytes(base.canonical_json({"state": "completed"}))

            with mock.patch.object(base, "EXPECTED_COMBINED_UNIQUE", 1), \
                 mock.patch.object(base, "run", return_value={"state": "completed"}):
                result = tool.run(work, artifacts)

            self.assertEqual(result["exclusion_union_sha256"], base.sha256_file(union))
            self.assertEqual(result["exclusion_manifest_sha256"], base.sha256_file(manifest))
            self.assertEqual(result, base.read_canonical_json(summary))

    def test_run_fails_closed_on_union_manifest_divergence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            (artifacts / "b3-fresh-exclusion-union.txt").write_bytes(b"a\n")
            (artifacts / "b3-fresh-exclusion-manifest.json").write_bytes(
                base.canonical_json({"union": {"sha256": "0" * 64, "unique_canonical": 1}})
            )
            (artifacts / "scientific-summary.json").write_bytes(
                base.canonical_json({"state": "completed"})
            )
            with mock.patch.object(base, "EXPECTED_COMBINED_UNIQUE", 1), \
                 mock.patch.object(base, "run", return_value={"state": "completed"}):
                with self.assertRaisesRegex(tool.SummaryReceiptError, "SHA"):
                    tool.run(root / "work", artifacts)


if __name__ == "__main__":
    unittest.main()

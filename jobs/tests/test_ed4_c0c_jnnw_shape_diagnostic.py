from __future__ import annotations

# Keep this suite on an ordinary branch commit after the incident-register bot
a# autofeeds TI-043 so the required PR checks run against the final head.
import gzip
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

from jobs.tools import ed4_c0c_jnnw_shape_diagnostic_stage as stage


def jnnw(count: int, body: bytes, trailing: bytes = b"") -> bytes:
    return b"JNNW" + struct.pack("<I", count) + body + trailing


class JnnwShapeDiagnosticTests(unittest.TestCase):
    def test_valid_envelope_does_not_decode_records(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.jnnw"
            p.write_bytes(jnnw(2, b"x" * (2 * stage.REC)))
            got = stage.inspect_jnnw_envelope(p, False)
            self.assertEqual(got["state"], "valid")
            self.assertEqual(got["declared_count"], 2)

    def test_exact_trailing_byte_reproduces_1907_token(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.jnnw"
            p.write_bytes(jnnw(1, b"x" * stage.REC, b"!"))
            got = stage.inspect_jnnw_envelope(p, False)
            self.assertEqual(got["reason"], "jnnw_trailing_bytes")
            self.assertEqual(got["declared_body_bytes"], stage.REC)

    def test_truncated_and_bad_header_remain_distinct(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            truncated = root / "truncated.jnnw"
            truncated.write_bytes(jnnw(2, b"x" * stage.REC))
            self.assertEqual(stage.inspect_jnnw_envelope(truncated, False)["reason"], "jnnw_truncated")
            bad = root / "bad.jnnw"
            bad.write_bytes(b"NOPE" + b"\0" * 4)
            self.assertEqual(stage.inspect_jnnw_envelope(bad, False)["reason"], "jnnw_header")

    def test_gzip_trailing_byte_is_detected_after_decompression(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.jnnw.gz"
            with gzip.open(p, "wb") as f:
                f.write(jnnw(1, b"x" * stage.REC, b"!"))
            self.assertEqual(stage.inspect_jnnw_envelope(p, True)["reason"], "jnnw_trailing_bytes")

    def test_main_publishes_only_structural_diagnostic_counters(self):
        fake_diag = {
            "first_failure": {
                "job_id": "job", "attempt_id": "attempt", "path": "x.jnnw",
                "kind": "jnnw", "sha256": "a" * 64, "size_bytes": 47,
                "state": "invalid", "reason": stage.EXPECTED_FAILURE_TOKEN,
                "declared_count": 1, "declared_body_bytes": 38, "consumed_body_bytes": 38,
            },
            "jnnw_files_checked": 1,
            "candidate_payload_reads": 1,
            "candidate_payload_bytes_read": 47,
            "candidate_inventories_authenticated": 1,
            "zero_size_jnnw_skipped": 0,
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            art = root / "art"
            with mock.patch.object(stage, "fetch_parent_metadata", return_value=({}, {})), \
                 mock.patch.object(stage, "find_first_jnnw_failure", return_value=fake_diag), \
                 mock.patch.dict(os.environ, {
                     "JASS_ARTEFACT_DIR": str(art),
                     "JASS_RESULT_DIR": str(root / "result"),
                     "LAUNCH_MODE": "rehearsal",
                 }):
                self.assertEqual(stage.main(), 0)
            summary = json.loads((art / "scientific-summary.json").read_text())
            self.assertEqual(summary["first_failure"]["reason"], stage.EXPECTED_FAILURE_TOKEN)
            for key in ("record_fields_decoded", "position_identity_reads", "target_fields_decoded",
                        "target_reads", "score_reads", "wdl_reads", "qvalue_reads", "model_reads",
                        "teacher_calls", "search_calls", "fits", "games", "alpha_spent"):
                self.assertEqual(summary[key], 0, key)
            self.assertFalse(summary["confirmation_authorized"])
            self.assertFalse(summary["automatic_continuation"])
            self.assertIsNone(summary["scientific_verdict"])
            evidence = json.loads((art / "execution-evidence.json").read_text())
            self.assertEqual(evidence["state"], "completed")
            self.assertEqual(evidence["completed_phases"], stage.PHASES)

    def test_main_rejects_a_different_failure_token(self):
        fake = {"first_failure": {"reason": "jnnw_truncated"}}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            art = root / "art"
            with mock.patch.object(stage, "fetch_parent_metadata", return_value=({}, {})), \
                 mock.patch.object(stage, "find_first_jnnw_failure", return_value=fake), \
                 mock.patch.dict(os.environ, {
                     "JASS_ARTEFACT_DIR": str(art),
                     "JASS_RESULT_DIR": str(root / "result"),
                     "LAUNCH_MODE": "rehearsal",
                 }):
                self.assertEqual(stage.main(), 2)
            summary = json.loads((art / "scientific-summary.json").read_text())
            self.assertEqual(summary["state"], "failed")
            self.assertFalse(summary["confirmation_authorized"])


if __name__ == "__main__":
    unittest.main()

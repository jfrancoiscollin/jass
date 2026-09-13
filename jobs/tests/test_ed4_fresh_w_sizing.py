from __future__ import annotations

import json
from pathlib import Path
import struct
import tempfile
import unittest

from jobs.tools import ed4_fresh_w_sizing_stage as w


class FreshWSizingTests(unittest.TestCase):
    def test_sanitizers_never_publish_wdl_or_game_result(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            jnnw = root / "raw.jnnw"
            raw = bytearray(b"JNNW" + struct.pack("<I", 4))
            for i, label in enumerate((-1, 0, 1, -1)):
                rec = bytearray(38)
                rec[32] = i % 2
                rec[37] = label & 0xFF
                raw.extend(rec)
            jnnw.write_bytes(raw)

            jsm = root / "raw.jsm2"
            meta = bytearray(b"JSM2" + struct.pack("<I", 4))
            rows = [
                (10, 100, 0, 0, 2, 0xFFFF, 1, 0),
                (10, 100, 0, 1, 2, 0xFFFF, 1, 0),
                (11, 100, 0, 0, 2, 0xFFFF, -1, 0),
                (11, 100, 0, 1, 2, 0xFFFF, -1, 0),
            ]
            for game, opening, seeded, ply, plies, last_eps, outcome, flags in rows:
                meta.extend(struct.pack("<QQBHHHbB", game, opening, seeded, ply, plies,
                                        last_eps, outcome, flags))
            jsm.write_bytes(meta)

            safe_jnnw = root / "safe.jnnw"
            safe_jsm = root / "safe.jsm2"
            self.assertEqual(w.sanitize_jnnw(jnnw, safe_jnnw), 4)
            report = w.sanitize_and_summarize_jsm2(jsm, safe_jsm)
            self.assertEqual(report["independent_games"], 2)
            self.assertEqual(report["independent_openings"], 1)
            self.assertFalse(report["game_result_parsed"])

            jraw = safe_jnnw.read_bytes()
            self.assertTrue(all(jraw[8 + i * 38 + 37] == 0 for i in range(4)))
            mraw = safe_jsm.read_bytes()
            self.assertTrue(all(mraw[8 + i * 25 + 23] == 0 for i in range(4)))
            self.assertNotIn("outcome", json.dumps(report).lower())

    def test_invalid_reserved_jsm2_flags_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "x.jsm2"
            path.write_bytes(b"JSM2" + struct.pack("<I", 1) +
                             struct.pack("<QQBHHHbB", 1, 2, 0, 0, 1, 0xFFFF, 1, 0x04))
            with self.assertRaisesRegex(ValueError, "jsm2_flags"):
                w.sanitize_and_summarize_jsm2(path, root / "safe.jsm2")

    def test_preregistered_constants_are_frozen(self):
        self.assertEqual(w.SEED, 202609120402)
        self.assertEqual(w.RECORD_TARGET, 4096)
        self.assertEqual(w.CURRICULUM_SHA,
                         "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1")


if __name__ == "__main__":
    unittest.main()

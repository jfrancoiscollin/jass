#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools" / "apply_label_policy.py"
SPEC = importlib.util.spec_from_file_location("apply_label_policy", MODULE)
M = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(M)


def record(wdl: int, marker: int = 1) -> bytearray:
    raw = bytearray(38)
    struct.pack_into("<Q", raw, 0, marker)
    raw[32] = 0
    struct.pack_into("<b", raw, 37, wdl)
    return raw


class ApplyLabelPolicyTests(unittest.TestCase):
    def test_source_tag_does_not_grant_certificate(self):
        original = [record(1)]
        deep = [record(0)]
        out, manifest = M.merge_policy(original, deep, bytes([1]), [None])
        self.assertEqual(struct.unpack_from("<b", out[0], 37)[0], 0)
        self.assertEqual(manifest["protected_tip"], 0)
        self.assertEqual(manifest["by_final_source"]["DEEP_RELABEL"], 1)

    def test_verified_cert_proof_blocks_draw_band(self):
        cert = {
            "oracle_tier": "CERT_PROOF",
            "proof_type": "pv_to_tb",
            "proof_validated": True,
            "blocks_draw_band": True,
            "result_wdl": 1,
        }
        out, manifest = M.merge_policy(
            [record(1)], [record(0)], bytes([1]), [cert], min_protected_tip_rate=1.0
        )
        self.assertEqual(struct.unpack_from("<b", out[0], 37)[0], 1)
        self.assertEqual(manifest["protected_tip_rate"], 1.0)

    def test_search_stable_does_not_block(self):
        cert = {
            "oracle_tier": "SEARCH_STABLE",
            "proof_type": "search_stable",
            "proof_validated": False,
            "blocks_draw_band": False,
            "result_wdl": 1,
        }
        out, manifest = M.merge_policy([record(1)], [record(0)], bytes([2]), [cert])
        self.assertEqual(struct.unpack_from("<b", out[0], 37)[0], 0)
        self.assertEqual(manifest["protected_tip"], 0)

    def test_invalid_blocking_claim_fails(self):
        cert = {
            "oracle_tier": "SEARCH_STABLE",
            "proof_type": "search_stable",
            "proof_validated": False,
            "blocks_draw_band": True,
            "result_wdl": 1,
        }
        with self.assertRaises(ValueError):
            M.merge_policy([record(1)], [record(0)], bytes([1]), [cert])

    def test_position_misalignment_fails(self):
        with self.assertRaises(ValueError):
            M.merge_policy([record(1, 1)], [record(0, 2)], bytes([0]), [None])

    def test_threshold_fails_closed(self):
        with self.assertRaises(ValueError):
            M.merge_policy(
                [record(1)], [record(0)], bytes([1]), [None], min_protected_tip_rate=0.9
            )

    def test_jnnw_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.jnnw"
            M.write_jnnw(path, [record(1), record(-1, 2)])
            values = M.read_jnnw(path)
            self.assertEqual(len(values), 2)
            self.assertEqual(struct.unpack_from("<b", values[1], 37)[0], -1)


if __name__ == "__main__":
    unittest.main()

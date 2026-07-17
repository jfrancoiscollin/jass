#!/usr/bin/env python3
"""Tests §11.4 — garde cache×processus + audit MTC."""
from __future__ import annotations
import importlib.util, os, tempfile, unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
def _load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
CG = _load("cache_guard"); MT = _load("mtc_audit")


class CacheGuardTests(unittest.TestCase):
    def test_0723_config_rejected(self):
        # 16 × 2048 = 32768 Mo sur box 32 Go → refusé
        rep = CG.check(2048, 16, 32000)
        self.assertFalse(rep["ok"]); self.assertEqual(rep["aggregate_mb"], 32768)

    def test_fixed_config_ok(self):
        # 16 × 512 = 8192 Mo → OK
        rep = CG.check(512, 16, 32000)
        self.assertTrue(rep["ok"]); self.assertEqual(rep["aggregate_mb"], 8192)

    def test_hard_cap_enforced(self):
        # même sous 30% de réserve, le hard-cap 24Go borne
        rep = CG.check(2000, 16, 128000, reserve_frac=0.0, hard_cap_mb=24576)
        self.assertFalse(rep["ok"])   # 32000 > 24576

    def test_suggestion_present(self):
        rep = CG.check(2048, 16, 32000)
        self.assertTrue(any("suggestion" in r for r in rep["reasons"]))


class MtcAuditTests(unittest.TestCase):
    def test_missing_env_fails(self):
        old = os.environ.pop("JASS_EGDB_MTC_PATH", None)
        try:
            rep = MT.audit(512, 16, 32000)
            self.assertFalse(rep["audit_ok"])
            self.assertFalse(rep["mtc_active"])
        finally:
            if old is not None: os.environ["JASS_EGDB_MTC_PATH"] = old

    def test_present_readable_env_ok(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td); (d / "db2.idx_mtc").write_bytes(b"fixture")
            os.environ["JASS_EGDB_MTC_PATH"] = str(d)
            try:
                rep = MT.audit(
                    512, 16, 32000, smoke_ok=True, require_smoke=True,
                    smoke_procs=2,
                )
                self.assertTrue(rep["mtc_active"]); self.assertTrue(rep["mtc_readable"])
                self.assertTrue(rep["audit_ok"])
                self.assertEqual(rep["mtc_entries"], 1)
                self.assertEqual(rep["mtc_total_bytes"], 7)
                self.assertEqual(len(rep["mtc_inventory_sha256"]), 64)
                self.assertEqual(rep["audit_level"], "complete")
                self.assertEqual(rep["concurrent_smoke_procs"], 2)
            finally:
                os.environ.pop("JASS_EGDB_MTC_PATH", None)

    def test_required_smoke_cannot_be_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td); (d / "db2.idx_mtc").write_bytes(b"fixture")
            os.environ["JASS_EGDB_MTC_PATH"] = str(d)
            try:
                rep = MT.audit(
                    512, 16, 32000, smoke_ok=None, require_smoke=True,
                    smoke_procs=2,
                )
                self.assertFalse(rep["audit_ok"])
                self.assertIn("requis", " ".join(rep["reasons"]))
            finally:
                os.environ.pop("JASS_EGDB_MTC_PATH", None)

    def test_required_smoke_records_real_concurrency(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td); (d / "db2.idx_mtc").write_bytes(b"fixture")
            os.environ["JASS_EGDB_MTC_PATH"] = str(d)
            try:
                rep = MT.audit(
                    512, 16, 32000, smoke_ok=True, require_smoke=True,
                    smoke_procs=1,
                )
                self.assertFalse(rep["audit_ok"])
                self.assertIn("deux processus", " ".join(rep["reasons"]))
            finally:
                os.environ.pop("JASS_EGDB_MTC_PATH", None)

    def test_empty_mtc_directory_fails(self):
        with tempfile.TemporaryDirectory() as td:
            os.environ["JASS_EGDB_MTC_PATH"] = td
            try:
                rep = MT.audit(512, 16, 32000, smoke_ok=True)
                self.assertFalse(rep["audit_ok"])
                self.assertEqual(rep["mtc_entries"], 0)
            finally:
                os.environ.pop("JASS_EGDB_MTC_PATH", None)

    def test_bad_cache_fails_audit(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td); (d / "db2.idx_mtc").write_bytes(b"fixture")
            os.environ["JASS_EGDB_MTC_PATH"] = str(d)
            try:
                rep = MT.audit(2048, 16, 32000, smoke_ok=True)   # cache trop gros
                self.assertFalse(rep["audit_ok"])
            finally:
                os.environ.pop("JASS_EGDB_MTC_PATH", None)

    def test_recorded_audit_verifies_same_host_path_and_inventory(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td); target = d / "db2.idx_mtc"; target.write_bytes(b"fixture")
            os.environ["JASS_EGDB_MTC_PATH"] = str(d)
            try:
                recorded = MT.audit(
                    512, 16, 32000, smoke_ok=True, require_smoke=True,
                    smoke_procs=2,
                )
                verified = MT.verify_recorded_audit(
                    recorded, str(d), expected_host=recorded["host"]
                )
                self.assertTrue(verified["verification_ok"])
                target.write_bytes(b"changed-size")
                changed = MT.verify_recorded_audit(
                    recorded, str(d), expected_host=recorded["host"]
                )
                self.assertFalse(changed["verification_ok"])
                self.assertIn("inventory differs", " ".join(changed["reasons"]))
            finally:
                os.environ.pop("JASS_EGDB_MTC_PATH", None)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests §11.4 — garde cache×processus + audit MTC."""
from __future__ import annotations
import importlib.util, os, unittest
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
        d = Path("/tmp/p0/_mtc_fixture"); d.mkdir(parents=True, exist_ok=True)
        os.environ["JASS_EGDB_MTC_PATH"] = str(d)
        try:
            rep = MT.audit(512, 16, 32000, smoke_ok=True)
            self.assertTrue(rep["mtc_active"]); self.assertTrue(rep["mtc_readable"])
            self.assertTrue(rep["audit_ok"])
        finally:
            os.environ.pop("JASS_EGDB_MTC_PATH", None)

    def test_bad_cache_fails_audit(self):
        d = Path("/tmp/p0/_mtc_fixture"); d.mkdir(parents=True, exist_ok=True)
        os.environ["JASS_EGDB_MTC_PATH"] = str(d)
        try:
            rep = MT.audit(2048, 16, 32000, smoke_ok=True)   # cache trop gros
            self.assertFalse(rep["audit_ok"])
        finally:
            os.environ.pop("JASS_EGDB_MTC_PATH", None)


if __name__ == "__main__":
    unittest.main()

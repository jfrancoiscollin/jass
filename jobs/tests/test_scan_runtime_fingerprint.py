#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "jobs/tools/scan_runtime_fingerprint.py"
SPEC = importlib.util.spec_from_file_location("scan_runtime_fingerprint", MODULE)
SRF = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = SRF
SPEC.loader.exec_module(SRF)
CALIBRATE_MODULE = ROOT / "jobs/tools/calibrate_vs_scan.py"
CALIBRATE_SPEC = importlib.util.spec_from_file_location(
    "scan_runtime_fingerprint_calibrate", CALIBRATE_MODULE,
)
CALIBRATE = importlib.util.module_from_spec(CALIBRATE_SPEC)
assert CALIBRATE_SPEC.loader is not None
sys.modules[CALIBRATE_SPEC.name] = CALIBRATE
CALIBRATE_SPEC.loader.exec_module(CALIBRATE)


class ScanRuntimeFingerprintTests(unittest.TestCase):
    def test_fingerprint_and_runtime_adapter_share_the_exact_hub_contract(self):
        self.assertEqual(
            SRF.HUB_PARAMS, dict(CALIBRATE.ScanEngine.RUNTIME_PARAMS),
        )

    def make_runtime(self, root: Path) -> None:
        (root / "data").mkdir(parents=True)
        (root / "scan_linux").write_bytes(b"scan-binary")
        (root / "scan.ini").write_text("variant = normal\n", encoding="utf-8")
        with (root / "data/eval").open("wb") as handle:
            handle.seek(SRF.SCAN_EVAL_BYTES - 1)
            handle.write(b"\0")

    def test_manifest_is_deterministic_and_covers_only_active_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_runtime(root)
            first = SRF.build_manifest(root)
            second = SRF.build_manifest(root)
            self.assertEqual(first, second)
            self.assertEqual(
                [row["path"] for row in first["active_files"]],
                ["scan_linux", "scan.ini", "data/eval"],
            )
            self.assertEqual(first["hub_params"], SRF.HUB_PARAMS)
            payload = {key: value for key, value in first.items()
                       if key != "runtime_sha256"}
            expected = SRF.hashlib.sha256(SRF.canonical_bytes(payload)).hexdigest()
            self.assertEqual(first["runtime_sha256"], expected)

    def test_bad_eval_size_and_missing_ini_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_runtime(root)
            (root / "data/eval").write_bytes(b"short")
            with self.assertRaisesRegex(ValueError, "expected 8503280"):
                SRF.build_manifest(root)
            (root / "data/eval").unlink()
            with self.assertRaisesRegex(ValueError, "missing active"):
                SRF.build_manifest(root)

    def test_cli_writes_manifest_and_prints_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_runtime(root)
            output = root / "manifest.json"
            self.assertEqual(SRF.main([
                "--scan-dir", str(root), "--output", str(output),
            ]), 0)
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8"))["runtime_sha256"],
                SRF.build_manifest(root)["runtime_sha256"],
            )


if __name__ == "__main__":
    unittest.main()

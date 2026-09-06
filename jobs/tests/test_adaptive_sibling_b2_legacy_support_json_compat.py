from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from jobs.tools import adaptive_sibling_b2_legacy_support_json_compat as compat
from jobs.tools import adaptive_sibling_b2_readout as readout


ROOT = Path(__file__).resolve().parents[2]


class LegacySupportJsonCompatTests(unittest.TestCase):
    def tearDown(self) -> None:
        compat.uninstall()

    def test_allowed_pretty_json_is_accepted_without_rewriting_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "verified-historical.json"
            raw = (json.dumps({"schema": "legacy", "ok": True}, indent=2, sort_keys=True)
                   + "\n").encode("utf-8")
            path.write_bytes(raw)
            with self.assertRaisesRegex(readout.ReadoutError, "non-canonical JSON"):
                readout.read_canonical_json(path)
            compat.install()
            value, accepted_raw = readout.read_canonical_json(path)
            self.assertEqual(value, {"ok": True, "schema": "legacy"})
            self.assertEqual(accepted_raw, raw)
            self.assertEqual(path.read_bytes(), raw)

    def test_disallowed_pretty_json_remains_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "scientific-summary.json"
            path.write_text(json.dumps({"ok": True}, indent=2) + "\n", encoding="utf-8")
            compat.install()
            with self.assertRaisesRegex(readout.ReadoutError, "non-canonical JSON"):
                readout.read_canonical_json(path)

    def test_duplicate_keys_remain_rejected_for_allowed_legacy_name(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source-manifest.json"
            path.write_bytes(b'{"a":1,"a":2}\n')
            compat.install()
            with self.assertRaisesRegex(readout.ReadoutError, "duplicate JSON key"):
                readout.read_canonical_json(path)

    def test_canonical_allowed_json_still_uses_frozen_parser(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "legacy-terminal-summary.json"
            raw = readout.canonical_json_bytes({"ok": True, "schema": "legacy"})
            path.write_bytes(raw)
            compat.install()
            value, accepted_raw = readout.read_canonical_json(path)
            self.assertEqual(value, {"ok": True, "schema": "legacy"})
            self.assertEqual(accepted_raw, raw)

    def test_v3_script_entrypoint_resolves_repo_package_without_pythonpath(self):
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            [
                sys.executable,
                "jobs/tools/adaptive_sibling_b2_statistical_completion_recovery_v3.py",
                "--help",
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--work-dir", proc.stdout)
        self.assertIn("--artifact-dir", proc.stdout)


if __name__ == "__main__":
    unittest.main()

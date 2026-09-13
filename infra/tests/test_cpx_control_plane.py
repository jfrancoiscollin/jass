from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("cpx_control_plane", ROOT / "infra/cpx_control_plane.py")
assert SPEC and SPEC.loader
cp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cp)


class ControlPlaneTests(unittest.TestCase):
    def test_only_transient_jass_units_are_killable(self):
        self.assertIsNotNone(cp.JOB_UNIT_RE.fullmatch("jass-job-0123456789abcdefabcd.service"))
        for bad in (
            "jass-runner-v3.service",
            "ssh.service",
            "jass-job-../../ssh.service",
            "jass-job-deadbeef.service",
            "jass-job-0123456789abcdefabcd.timer",
        ):
            self.assertIsNone(cp.JOB_UNIT_RE.fullmatch(bad), bad)

    def test_token_minimum_length(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "token"
            p.write_text("short\n")
            with self.assertRaises(RuntimeError):
                cp.read_token(p)
            p.write_text("x" * 32 + "\n")
            self.assertEqual(cp.read_token(p), "x" * 32)

    def test_reboot_is_disabled_by_default_in_unit(self):
        text = (ROOT / "infra/jass-control-plane.service").read_text()
        self.assertIn("Environment=JASS_CONTROL_ALLOW_REBOOT=0", text)
        self.assertIn("Environment=JASS_CONTROL_BIND=127.0.0.1", text)

    def test_no_arbitrary_exec_endpoint(self):
        text = (ROOT / "infra/cpx_control_plane.py").read_text()
        self.assertNotIn('/v1/exec', text)
        self.assertNotIn('/v1/shell', text)
        self.assertIn('/v1/runner/restart', text)
        self.assertIn('/v1/job/kill', text)


if __name__ == "__main__":
    unittest.main()

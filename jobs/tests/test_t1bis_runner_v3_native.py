#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FETCHER = ROOT / "jobs/tools/fetch_t1bis_inputs.py"
FULL = ROOT / "jobs/templates/t1bis-adj-g1-runner-v3-native.sh"
SMOKE = ROOT / "jobs/templates/t1bis-adj-g1-runner-v3-smoke.sh"


class NativeT1BisTest(unittest.TestCase):
    def fake_rclone(self, root: Path) -> Path:
        path = root / "rclone"
        path.write_text(
            """#!/usr/bin/env python3
import shutil,sys
from pathlib import Path
cmd=sys.argv[1]
if cmd=='cat':
    sys.stdout.buffer.write(Path(sys.argv[2]).read_bytes())
elif cmd=='copyto':
    src,dst=Path(sys.argv[2]),Path(sys.argv[3])
    dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(src,dst)
else:
    print('unsupported '+cmd,file=sys.stderr); raise SystemExit(9)
""",
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

    def build_remote(self, root: Path) -> Path:
        prefix = root / "inputs/t1bis-adj-g1/v1"
        files = prefix / "files"
        files.mkdir(parents=True)
        roles = {
            "parent_pattern": "parent.pjtw.gz",
            "fixed_pattern": "fixed.pjtw.gz",
            "gen2_pattern": "gen2.pjtw.gz",
            "seed_corpus": "seeds.jnnw.gz",
            "g1_pool": "g1_pool.fen",
            "conversion_gauge": "gauge.fen",
        }
        objects = []
        for index, (role, name) in enumerate(roles.items(), 1):
            payload = (f"payload-{index}-{role}\n").encode()
            target = files / name
            target.write_bytes(payload)
            objects.append({
                "role": role,
                "target_name": name,
                "remote": str(target),
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "source_commit": "a" * 40,
                "source_blob": "b" * 40,
            })
        manifest = {
            "schema": 1,
            "dataset": "t1bis-adj-g1-inputs",
            "version": "v1",
            "source_commit": "a" * 40,
            "objects": objects,
        }
        raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
        (prefix / "manifest.json").write_bytes(raw)
        success = {
            "state": "completed",
            "dataset": "t1bis-adj-g1-inputs",
            "version": "v1",
            "manifest_sha256": hashlib.sha256(raw).hexdigest(),
            "manifest_size_bytes": len(raw),
            "object_count": len(objects),
        }
        (prefix / "_SUCCESS").write_text(json.dumps(success), encoding="utf-8")
        return prefix

    def test_fetcher_accepts_verified_set_and_rejects_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            prefix = self.build_remote(root)
            rclone = self.fake_rclone(root)
            out = root / "out"
            subprocess.run([
                sys.executable, str(FETCHER),
                "--rclone-bin", str(rclone),
                "--remote-prefix", str(prefix),
                "--out-dir", str(out),
            ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            report = json.loads((out / "verified-inputs.json").read_text())
            self.assertEqual(report["state"], "verified")
            self.assertEqual(len(report["objects"]), 6)

            (prefix / "files/gauge.fen").write_text("tampered", encoding="utf-8")
            failed = subprocess.run([
                sys.executable, str(FETCHER),
                "--rclone-bin", str(rclone),
                "--remote-prefix", str(prefix),
                "--out-dir", str(root / "out2"),
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertNotEqual(failed.returncode, 0)

    def test_launchers_are_native_and_shell_valid(self) -> None:
        for script in (FULL, SMOKE):
            subprocess.run(["bash", "-n", str(script)], check=True)
        text = FULL.read_text(encoding="utf-8")
        blocked = [
            "/" + "/".join(("root", "jass")),
            "origin/" + "".join(("ma", "in")),
            "HEAD:" + "".join(("ma", "in")),
            "refs/heads/" + "".join(("ma", "in")),
            "replace_once",
            "t1bis-adj-g1-v2.sh",
        ]
        for token in blocked:
            self.assertNotIn(token, text)
        self.assertIn("fetch_t1bis_inputs.py", text)
        self.assertIn('GAMES="${GAMES:-300}"', text)
        self.assertIn('PLAYD="${PLAYD:-10}"', text)
        self.assertIn('ARB_DEPTH="${ARB_DEPTH:-14}"', text)
        self.assertIn('ANCHOR="${ANCHOR:-0.05}"', text)
        self.assertIn('CONV_DEPTH="${CONV_DEPTH:-10}"', text)
        self.assertIn('NOPEN="${NOPEN:-300}"', text)
        self.assertIn('DEPTH="${DEPTH:-9}"', text)


if __name__ == "__main__":
    unittest.main()

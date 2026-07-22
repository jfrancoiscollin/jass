#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs/tools/validate_opening_pool.py"


def invoke(pool: Path, exclude: Path, expected: int, out: Path, check: bool = True):
    return subprocess.run([
        sys.executable, str(TOOL), "--pool", str(pool), "--expected", str(expected),
        "--exclude", str(exclude), "--generator-seed", "271828", "--out", str(out),
    ], check=check, capture_output=True, text=True)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pool = root / "pool.fen"
        exclude = root / "exclude.fen"
        out = root / "manifest.json"
        pool.write_text("# generated\nW:W31:B20 # a\nB:W32:B19 # b\n")
        exclude.write_text("# old\nW:W33:B18\n")
        invoke(pool, exclude, 2, out)
        payload = json.loads(out.read_text())
        assert payload["records"] == 2
        assert payload["overlap_records"] == 0

        exclude.write_text("W:W31:B20\n")
        assert invoke(pool, exclude, 2, out, check=False).returncode != 0
        pool.write_text("W:W31:B20\nW:W31:B20\n")
        exclude.write_text("")
        assert invoke(pool, exclude, 2, out, check=False).returncode != 0
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

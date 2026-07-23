#!/usr/bin/env python3
from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/blend_pjtw.py"
HDR = (0x57544A50, 3, 1000, 2, 1)


def write_model(path: Path, weights: list[int], header=HDR) -> None:
    path.write_bytes(struct.pack("<5I", *header) + struct.pack(f"<{len(weights)}i", *weights))


def read_weights(path: Path) -> list[int]:
    raw = path.read_bytes()[20:]
    return list(struct.unpack(f"<{len(raw)//4}i", raw))


def read_header(path: Path) -> tuple[int, int, int, int, int]:
    return struct.unpack("<5I", path.read_bytes()[:20])


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        a, b, out, report = (root / name for name in ("a.pjtw", "b.pjtw", "out.pjtw", "report.json"))
        write_model(a, [0, 8, -8, 20, 100, -100])
        write_model(b, [8, 0, 8, -20, -100, 100])
        subprocess.run([sys.executable, str(TOOL), "--parent-a", str(a), "--parent-b", str(b),
                        "--alpha-a", "0.75", "--out", str(out), "--report", str(report)], check=True)
        assert read_weights(out) == [2, 6, -4, 10, 50, -50]
        payload = json.loads(report.read_text())
        assert payload["alpha_a"] == 0.75 and payload["alpha_b"] == 0.25

        selfdesc = (0x57544A50, 3 | 0x200, 1000, 2, 1)
        write_model(a, [0, 8, -8, 20, 100, -100], header=selfdesc)
        write_model(b, [8, 0, 8, -20, -100, 100], header=selfdesc)
        subprocess.run([sys.executable, str(TOOL), "--parent-a", str(a), "--parent-b", str(b),
                        "--alpha-a", "0.25", "--out", str(out)], check=True)
        assert read_header(out) == selfdesc
        assert read_weights(out) == [6, 2, 4, -10, -50, 50]

        bad = root / "bad.pjtw"
        write_model(bad, [1] * 8, header=(0x57544A50, 3, 1000, 3, 1))
        rc = subprocess.run([sys.executable, str(TOOL), "--parent-a", str(a), "--parent-b", str(bad),
                             "--alpha-a", "0.5", "--out", str(out)]).returncode
        assert rc != 0
        write_model(bad, [1] * 6, header=(0x57544A50, 4 | 0x200, 1000, 2, 1))
        rc = subprocess.run([sys.executable, str(TOOL), "--parent-a", str(a), "--parent-b", str(bad),
                             "--alpha-a", "0.5", "--out", str(out)]).returncode
        assert rc != 0
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs/tools/l3_pure_meta_blend.py"


def gate(rate: float, n: int = 400) -> dict:
    wins = round(rate * n)
    return {"wins_a": wins, "draws": 0, "wins_b": n - wins, "n": n, "rate": wins / n}


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for alpha, c0, p1 in ((0.25, 0.48, 0.54), (0.5, 0.52, 0.53), (0.75, 0.51, 0.55)):
            tag = f"c0w{round(alpha*1000):04d}"
            (root / f"screen-{tag}-vs-c0.json").write_text(json.dumps(gate(c0)))
            (root / f"screen-{tag}-vs-p1.json").write_text(json.dumps(gate(p1)))
        selection = root / "selection.json"
        subprocess.run([sys.executable, str(TOOL), "select", "--screen-dir", str(root),
                        "--alphas", "0.25", "0.5", "0.75", "--out", str(selection)], check=True)
        assert json.loads(selection.read_text())["selected"]["alpha_c0"] == 0.5
        paths = []
        for name in ("d-c0", "t-c0", "d-p1", "t-p1"):
            path = root / f"{name}.json"
            path.write_text(json.dumps(gate(0.56, 800)))
            paths.append(path)
        verdict = root / "verdict.json"
        summary = root / "summary.json"
        subprocess.run([sys.executable, str(TOOL), "confirm", "--selection", str(selection),
                        "--depth-vs-c0", str(paths[0]), "--movetime-vs-c0", str(paths[1]),
                        "--depth-vs-p1", str(paths[2]), "--movetime-vs-p1", str(paths[3]),
                        "--out", str(verdict), "--summary-out", str(summary)], check=True)
        assert json.loads(verdict.read_text())["decision"] == "META_SUPERIOR_TO_BOTH"
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

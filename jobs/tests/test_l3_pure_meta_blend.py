#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs/tools/l3_pure_meta_blend.py"
TEMPLATE = ROOT / "jobs/templates/l3-pure-c0-p1-meta-blend-v1.sh"
HOME_WRAPPER = (
    ROOT
    / "jobs/prepared/l3-pure-c0-p1-meta-blend-20260723"
    / "home-0923-l3-pure-c0-p1-meta-blend-v1.sh"
)


def gate(rate: float, n: int = 400) -> dict:
    wins = round(rate * n)
    return {"wins_a": wins, "draws": 0, "wins_b": n - wins, "n": n, "rate": wins / n}


def main() -> int:
    template = TEMPLATE.read_text()
    wrapper = HOME_WRAPPER.read_text()
    assert 'requires >=16 CPUs' in template
    assert 'requires >=14 GiB RAM' in template
    assert 'git show "$EXPECTED_CODE_SHA:$src"' in template
    assert 'grep -q "g_emasks" src/scan_eval.cpp' in template
    assert template.count('grep -q "has_any_capture"') == 2
    assert 'report.get("n") != expected' in template
    assert 'die "$label incomplete"' in template
    assert 'expected_games="$((2 * expected_openings))"' in template
    assert '"$SCREEN_NOPEN" --depth "$SCREEN_DEPTH"' in template
    assert '"$CONFIRM_NOPEN" --movetime "$MOVETIME"' in template
    assert "home-0923-l3-pure-c0-p1-meta-blend-v1" in wrapper
    assert "20260718T104245Z-8fc4eacb" in wrapper
    assert "20260719T175711Z-337ccbdc" in wrapper
    assert "PAR_GATE=12" in wrapper
    assert "SHARD_TIMEOUT=1800 GATE_TIMEOUT=2700" in wrapper
    assert "timeout --signal=TERM --kill-after=30 5400" in wrapper
    assert 'timeout "$GATE_TIMEOUT"' in template
    assert '--timeout "$SHARD_TIMEOUT"' in template

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

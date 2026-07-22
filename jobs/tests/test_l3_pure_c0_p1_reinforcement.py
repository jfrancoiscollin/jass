#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs/tools/l3_pure_c0_p1_reinforcement.py"
TEMPLATE = ROOT / "jobs/templates/l3-pure-c0-p1-reinforcement-v1.sh"
Q00 = "a=1,b=2"


def report(rate_side: str) -> dict:
    if rate_side == "p1":
        wins, draws, losses = 500, 700, 336
    elif rate_side == "c0":
        wins, draws, losses = 336, 700, 500
    else:
        wins, draws, losses = 418, 700, 418
    n = wins + draws + losses
    rate = (wins + 0.5 * draws) / n
    return {
        "wins_a": wins,
        "draws": draws,
        "wins_b": losses,
        "n": n,
        "rate": rate,
        "ci_low": rate - 0.01,
        "ci_high": rate + 0.01,
        "elo": 0.0,
        "complete": True,
        "search_params_a": Q00,
        "search_params_b": Q00,
    }


def run_case(depth_side: str, time_side: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        depth = report(depth_side)
        depth["depth"] = 9
        depth["movetime"] = None
        timed = report(time_side)
        timed["depth"] = None
        timed["movetime"] = 0.3
        (root / "d.json").write_text(json.dumps(depth))
        (root / "t.json").write_text(json.dumps(timed))
        subprocess.run([
            sys.executable, str(TOOL),
            "--q00-depth", str(root / "d.json"),
            "--q00-movetime", str(root / "t.json"),
            "--out", str(root / "out.json"),
            "--summary-out", str(root / "summary.json"),
        ], check=True)
        return json.loads((root / "out.json").read_text())


def main() -> int:
    assert run_case("p1", "p1")["recommended_parent"] == "P1_0842_G4"
    assert run_case("c0", "c0")["recommended_parent"] == "C0_A_G3"
    assert run_case("p1", "c0")["recommended_parent"] == "UNRESOLVED"
    assert run_case("flat", "flat")["recommended_parent"] == "UNRESOLVED"
    template = TEMPLATE.read_text()
    assert '--gen-opening-pool "$NOPEN"' in template
    assert "validate_opening_pool.py" in template
    assert "--exclude data/dilf_combinations.fen" in template
    assert "seen<=300" not in template
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

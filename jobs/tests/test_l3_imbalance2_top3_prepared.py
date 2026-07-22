#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "jobs/templates/l3-imbalance2-top3-selfplay-v1.sh"
WRAPPER = ROOT / "jobs/prepared/l3-imbalance2-top3-20260721/ccx33-l3-imbalance2-top3-selfplay-p1.sh"
PLAN = ROOT / "docs/L3_IMBALANCE2_TOP3_SELFPLAY_PLAN.md"


def main() -> int:
    for path in (RUNNER, WRAPPER, PLAN):
        assert path.exists(), path
    subprocess.run(["bash", "-n", str(RUNNER)], check=True)
    subprocess.run(["bash", "-n", str(WRAPPER)], check=True)
    runner = RUNNER.read_text(encoding="utf-8")
    wrapper = WRAPPER.read_text(encoding="utf-8")
    assert "for low in 16 17 18" in runner
    assert "source_records=$FRESH selfplay_only=1" in runner
    assert "static --low" not in runner
    assert "JASS_EGDB=ON" not in runner
    assert "IMBALANCE2_REWEIGHT_POLICY=role-aware-v2" in runner
    assert "run_eval g0" in runner and 'FINAL_MODEL="g${GENERATIONS}"' in runner
    assert 'SEED_CLEAN="${SEED_CLEAN:-0}"' in runner
    assert "--quiet-only --sample-initial" in runner
    assert "TOP3_SPECIALIZATION_SIGNAL" in runner
    assert "promotion_authorized':False" in runner
    assert "FRESH=500000" in wrapper
    assert "SEED_CLEAN" not in wrapper
    assert "PAR_GEN=6" in wrapper
    assert "EVAL_PER_STRATUM=64" in wrapper
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

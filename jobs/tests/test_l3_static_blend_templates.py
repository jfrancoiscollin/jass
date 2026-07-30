#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "jobs/templates/l3-pure-reverse-seed-static-blend-build-v1.sh"
READOUT = (
    ROOT / "jobs/templates/l3-pure-reverse-seed-static-blend-readout-v1.sh"
)


def main() -> int:
    build = BUILD.read_text(encoding="utf-8")
    readout = READOUT.read_text(encoding="utf-8")

    for token in (
        'ALPHA_CHAMPION="${ALPHA_CHAMPION:-0.5}"',
        "L3_PURE_REVERSE_SEED_ABOVE_MATCHED_CONTROL_IC95",
        "--alpha-a \"$ALPHA_CHAMPION\"",
        'MAX_STATIC_RESIDUAL="${MAX_STATIC_RESIDUAL:-8.0}"',
        "--max-abs-residual \"$MAX_STATIC_RESIDUAL\"",
        '"single_factor": "static_pjtw_weight_blend"',
        '"training_records": 0',
        '"self_play_games": 0',
        "PROMOTION_AUTHORIZED__FALSE",
        "AUTOMATIC_NEXT_JOB__NULL",
    ):
        assert token in build, token

    for token in (
        'NOPEN="${NOPEN:-1500}"',
        'OPENING_SEED="${OPENING_SEED:-1105001}"',
        "--exclude \"$IN/prior-topk-openings.fen\"",
        "--exclude \"$IN/prior-hard-openings.fen\"",
        "--exclude \"$IN/prior-reverse-openings.fen\"",
        "--exclude \"$IN/prior-failed-x2-openings.fen\"",
        "force-$view-BLEND50-vs-TURNOVER.json",
        "--depth \"$FORCE_DEPTH\"",
        "--movetime \"$MOVETIME\"",
        "promotion=false automatic_next_job=null",
    ):
        assert token in readout, token

    assert "alpha_selected_on_force_pool" not in build
    assert "FULL_RUN_APPROVED" in build and "SCIENTIFIC_GO" in build
    assert "FULL_RUN_APPROVED" in readout and "SCIENTIFIC_GO" in readout
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

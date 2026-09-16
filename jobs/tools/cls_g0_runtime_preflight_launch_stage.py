#!/usr/bin/env python3
"""Launch-V2 wrapper for CLS-G0 CURRICULUM identity tooling preflight."""
from __future__ import annotations

import os
from pathlib import Path
import sys

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools import cls_g0_runtime_preflight_stage as stage  # noqa: E402
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json  # noqa: E402

PHASES = ["execute-g0-identity-preflight"]


def main() -> int:
    mode = os.environ.get("LAUNCH_MODE", "")
    art = Path(os.environ["JASS_ARTEFACT_DIR"])
    result = Path(os.environ["JASS_RESULT_DIR"])
    art.mkdir(parents=True, exist_ok=True)
    evidence = StageEvidence(art, mode)
    try:
        evidence.begin(PHASES[0])
        summary = stage.run_stage(result / "cls-g0-runtime-preflight-work", art)
        evidence.value["actual_side_effects"].update({
            "fits": 0,
            "new_scan_searches": 0,
            "new_jass_searches": int(summary["new_jass_searches"]),
            "strength_games": 0,
            "selfplay_games": 0,
            "promotions": 0,
            "bakes": 0,
            "test_target_reads": 0,
        })
        evidence.complete()
        evidence.finish()
        return 0
    except BaseException as exc:
        evidence.fail(exc)
        atomic_json(art / "scientific-summary.json", {
            "schema": stage.SCHEMA,
            "state": "failed",
            "terminal": stage.TECHNICAL_TERMINAL,
            "scientific_verdict": None,
            "classification": "TECHNICAL",
            "error_type": type(exc).__name__,
            "target_reads": 0,
            "candidate_reads": 0,
            "control_evaluations": 0,
            "new_jass_searches": evidence.value["actual_side_effects"]["new_jass_searches"],
            "new_scan_searches": 0,
            "fits": 0,
            "strength_games": 0,
            "alpha_spent": 0,
            "promotions": 0,
            "bakes": 0,
        })
        print(f"CLS-G0 TECHNICAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

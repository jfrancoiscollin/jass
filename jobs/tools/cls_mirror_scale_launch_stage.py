#!/usr/bin/env python3
"""Launch-V2 evidence wrapper for the frozen CLS-D mirror-scale diagnostic."""
from __future__ import annotations

import os
from pathlib import Path
import sys

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools import cls_mirror_scale_stage as stage  # noqa: E402
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json  # noqa: E402

PHASES = ["execute-cls-mirror-scale"]


def main() -> int:
    mode = os.environ.get("LAUNCH_MODE", "")
    art = Path(os.environ["JASS_ARTEFACT_DIR"])
    result = Path(os.environ["JASS_RESULT_DIR"])
    art.mkdir(parents=True, exist_ok=True)
    evidence = StageEvidence(art, mode)
    try:
        evidence.begin(PHASES[0])
        summary = stage.run_stage(result / "cls-mirror-scale-work", art)
        evidence.value["actual_side_effects"].update({
            "fits": 0,
            "new_scan_searches": int(summary["new_scan_searches"]),
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
            "new_scan_searches": evidence.value["actual_side_effects"]["new_scan_searches"],
            "fits": 0,
            "strength_games": 0,
            "selfplay_games": 0,
            "alpha_spent": 0,
            "promotions": 0,
            "bakes": 0,
        })
        print(f"CLS mirror TECHNICAL: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

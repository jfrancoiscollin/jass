#!/usr/bin/env python3
"""Target-blind MegaCorpus selector for T2 phase-specialist deep-fresh v1.

This is a thin wrapper around the already-audited M3 catalog selector. It keeps
its canonical/exact exclusion machinery and zero-label semantics, but freezes
the T2 confirmation quantities preregistered before fresh data are read:

* exactly 2,000 parents in each P0/P1/P2/P3 phase (8,000 total),
* sampling seed 2026090610 (passed by the control job),
* canonical exclusions supplied through JASS_M3_EXCLUDE_CANON_TSVS,
* force-pool exact exclusions supplied through JASS_M3_FORCE_FEN_DIR.

No teacher score, T2 score, D1 score, q1000/q50/q200 value or source label is
read by this selector.
"""
from __future__ import annotations

import atexit
import json
import os
from pathlib import Path

from jobs.tools import micro_search_m3_catalog_select_runner as m3

T2_SELECTION_SEED = 2026090610
T2_PHASES = {
    "P0": (30, 40, 2_000),
    "P1": (20, 29, 2_000),
    "P2": (12, 19, 2_000),
    "P3": (9, 11, 2_000),
}

# The imported M3 module has already loaded the exclusion inputs from the same
# environment and installed its audited merge_occurrence hook. Change only the
# preregistered phase quotas for this fresh T2 selection.
m3.M3_PHASES = dict(T2_PHASES)
m3.base.PHASES = dict(T2_PHASES)

# Replace only the reporting callback so the immutable receipt names the T2
# contract and its frozen seed/quotas. The base selection itself uses the
# --sample-seed argument supplied by the control job.
atexit.unregister(m3._write_exclusion_report)


def _write_exclusion_report() -> None:
    target = os.environ.get("JASS_M3_EXCLUSION_REPORT")
    if not target:
        return
    payload = {
        "schema": "jass.t2_phase_specialist_exclusions.v1",
        "selection_seed": T2_SELECTION_SEED,
        "phase_quotas": {name: quota for name, (_lo, _hi, quota) in T2_PHASES.items()},
        **m3.EVIDENCE,
        **m3.STATS,
        "source_labels_read": False,
        "teacher_scores_read": 0,
        "t2_scores_read": 0,
        "d1_scores_read": 0,
        "q1_label_reads": 0,
        "q1_score_reads": 0,
        "fits": 0,
        "strength_games": 0,
        "promotion_authorized": False,
    }
    Path(target).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


atexit.register(_write_exclusion_report)

if __name__ == "__main__":
    raise SystemExit(m3.base.main())

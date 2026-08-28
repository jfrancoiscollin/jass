#!/usr/bin/env python3
"""Preregistered M5 target-blind fresh transfer-confirmation selector.

This reuses the already-audited M3 MegaCorpus selector/exclusion machinery and
changes only the frozen M5 quantities from
L3_MICRO_SEARCH_TEACHER_TO_T_V1_20260827.md:

* exactly 1,000 parents in each P0/P1/P2/P3 phase (4,000 total),
* sampling hash seed supplied by control as 2026090220,
* exclusion set extended through the frozen M3 cohort,
* zero source labels / teacher scores during selection.
"""
from __future__ import annotations

import atexit
import json
import os
from pathlib import Path

from jobs.tools import micro_search_m3_catalog_select_runner as m3

M5_SELECTION_SEED = 2026090220
M5_PHASES = {
    "P0": (30, 40, 1_000),
    "P1": (20, 29, 1_000),
    "P2": (12, 19, 1_000),
    "P3": (9, 11, 1_000),
}

# Preserve the exact audited canonical/exact exclusion and representative
# semantics from M3.  Environment-backed exclusions are loaded by m3 at import
# time before this quota-only override.
m3.base.PHASES = dict(M5_PHASES)


def _write_m5_exclusion_report() -> None:
    target = os.environ.get("JASS_M5_EXCLUSION_REPORT")
    if not target:
        return
    payload = {
        "schema": "jass.micro_search_m5_exclusions.v1",
        "selection_seed": M5_SELECTION_SEED,
        "phase_quotas": {name: quota for name, (_lo, _hi, quota) in M5_PHASES.items()},
        **m3.EVIDENCE,
        **m3.STATS,
        "source_labels_read": False,
        "teacher_scores_read": 0,
        "fits": 0,
        "strength_games": 0,
        "promotion_authorized": False,
    }
    Path(target).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


atexit.register(_write_m5_exclusion_report)

if __name__ == "__main__":
    raise SystemExit(m3.base.main())

#!/usr/bin/env python3
"""Preregistered Joint T+D Q1 target-blind parent selector.

This is a quota/seed/report wrapper around the already-audited M3 selector and
its canonical/exact exclusion machinery.  Q1 changes only the quantities frozen
in L3_JOINT_TD_DEEP_FRESH_CONFIRMATION_V1_20260828.md:

* exactly 1,000 parents in each P0/P1/P2/P3 phase (4,000 total),
* canonical sampling seed 2026090420,
* environment-backed prior-cohort exclusions supplied by control,
* zero teacher/q1000/q50/q200 reads and zero model fits during selection.
"""
from __future__ import annotations

import atexit
import json
import os
from pathlib import Path
import sys

from jobs.tools import micro_search_m3_catalog_select_runner as m3

PREREG_SHA = "b280fc1f4878133a41168f4bbc6a537eec526cdc"
Q1_SELECTION_SEED = 2026090420
Q1_PHASES = {
    "P0": (30, 40, 1_000),
    "P1": (20, 29, 1_000),
    "P2": (12, 19, 1_000),
    "P3": (9, 11, 1_000),
}

# Preserve audited exact/canonical de-dup and exclusion semantics.  m3 loads all
# environment-backed exclusion inventories before this quota-only override.
m3.base.PHASES = dict(Q1_PHASES)


def _arg_value(name: str) -> str | None:
    try:
        i = sys.argv.index(name)
    except ValueError:
        return None
    return sys.argv[i + 1] if i + 1 < len(sys.argv) else None


def _write_q1_exclusion_report() -> None:
    target = os.environ.get("JASS_Q1_EXCLUSION_REPORT")
    if not target:
        return
    payload = {
        "schema": "jass.joint_td_q1_exclusions.v1",
        "prereg_sha": PREREG_SHA,
        "selection_seed": Q1_SELECTION_SEED,
        "phase_quotas": {name: quota for name, (_lo, _hi, quota) in Q1_PHASES.items()},
        **m3.EVIDENCE,
        **m3.STATS,
        "target_blind": True,
        "source_labels_read": False,
        "teacher_scores_read": 0,
        "q1000_scores_read": 0,
        "q50_scores_read": 0,
        "q200_scores_read": 0,
        "model_refits": 0,
        "strength_games": 0,
        "promotion_authorized": False,
    }
    Path(target).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


atexit.register(_write_q1_exclusion_report)

if __name__ == "__main__":
    if _arg_value("--sample-seed") != str(Q1_SELECTION_SEED):
        raise SystemExit(f"Q1 requires --sample-seed {Q1_SELECTION_SEED}")
    raise SystemExit(m3.base.main())

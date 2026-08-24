#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Schema adapter for the preregistered search-frontier regret screen."""
from __future__ import annotations

import pathlib
import sys

if __package__ in (None, ""):
    root = str(pathlib.Path(__file__).resolve().parents[2])
    if root not in sys.path:
        sys.path.insert(0, root)

from jobs.tools import l3_curriculum_search_frontier_regret_distillation as base

# The source corpus uses the canonical five-way phase taxonomy from
# l3_curriculum_error_learning._phase. This is schema plumbing only; it does
# not alter any preregistered statistical parameter or target.
base.CATEGORIES["phase"] = (
    "opening", "midgame", "late_midgame", "endgame", "deep_endgame"
)

if __name__ == "__main__":
    raise SystemExit(base.main())

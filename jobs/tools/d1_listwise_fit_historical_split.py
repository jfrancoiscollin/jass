#!/usr/bin/env python3
"""Compatibility entrypoint for the frozen CURRENT_2M historical split used by D1.

The D1 implementation accidentally assumed an exact 200,000-row holdout.  The
immutable CURRENT_2M manifest produced with holdout-mod=10 / seed=577215 has
199,204 holdout rows and 1,800,796 train rows.  This wrapper patches only those
operational cardinality constants before delegating to the already-frozen D1
fitter.  It does not change labels, objective terms, lambda, optimizer, model
class, or any scientific gate.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools import d1_listwise_fit as impl  # noqa: E402

HISTORICAL_HOLDOUT = 199_204
HISTORICAL_TRAIN = 1_800_796


def apply_historical_split() -> None:
    if impl.RECORDS != 2_000_000:
        raise RuntimeError("D1 CURRENT_2M record contract drift")
    impl.HOLDOUT = HISTORICAL_HOLDOUT
    impl.TRAIN = HISTORICAL_TRAIN


def main() -> int:
    apply_historical_split()
    return impl.main()


if __name__ == "__main__":
    raise SystemExit(main())

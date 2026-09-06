#!/usr/bin/env python3
"""Run the frozen D1 terminal readout with the immutable CURRENT_2M split counts."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools import d1_listwise_fit as fit_impl  # noqa: E402
from jobs.tools.d1_listwise_fit_historical_split import (  # noqa: E402
    HISTORICAL_HOLDOUT,
    HISTORICAL_TRAIN,
)

# d1_postfit_readout imports d1_listwise_fit and derives the expected holdout
# contract from that module.  Patch the historical cardinalities before import.
fit_impl.HOLDOUT = HISTORICAL_HOLDOUT
fit_impl.TRAIN = HISTORICAL_TRAIN

from jobs.tools import d1_postfit_readout as readout  # noqa: E402


def main() -> int:
    return readout.main()


if __name__ == "__main__":
    raise SystemExit(main())

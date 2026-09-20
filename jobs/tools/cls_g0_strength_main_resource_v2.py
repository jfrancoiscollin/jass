#!/usr/bin/env python3
"""New resource-only admission; original 2067 remains preparation-blocked."""
from __future__ import annotations
from pathlib import Path
import signal
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from jobs.tools import cls_g0_strength_main as base

PROJECTED_WORK_CEILING = 3000
ORIGINAL_SELECTION_SHA = "0a9497f68387b1e0b65a36a9d0da538e9cfd7932167c0d2b0f664e15b81c53c1"


def main() -> int:
    return base.main(projected_work_ceiling=PROJECTED_WORK_CEILING,
                     expected_selection_sha=ORIGINAL_SELECTION_SHA)


if __name__ == "__main__":
    def terminate(signum, frame):
        raise KeyboardInterrupt("TERMINATED")
    signal.signal(signal.SIGTERM, terminate)
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run ED4-FRESH W sizing and remove non-evidence scratch before publication.

The scientific stage writes all admissible outputs under JASS_ARTEFACT_DIR.
Its source/build tree and authenticated input copy live under JASS_RESULT_DIR
only as execution scratch.  runner-v3 publishes the entire result directory, so
leaving those trees behind needlessly turns a small metadata rehearsal into a
large object-store transfer.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools import ed4_fresh_w_sizing_stage as stage

SCRATCH_NAMES = ("work", "inputs")


def cleanup_result_scratch(result_dir: Path) -> None:
    for name in SCRATCH_NAMES:
        path = result_dir / name
        if path.is_symlink():
            path.unlink()
        elif path.exists():
            shutil.rmtree(path)
        if path.exists() or path.is_symlink():
            raise RuntimeError(f"scratch cleanup failed: {name}")


def main() -> int:
    result_dir = Path(os.environ["JASS_RESULT_DIR"])
    rc = stage.main()
    try:
        cleanup_result_scratch(result_dir)
    except Exception as exc:
        print(f"ED4 W sizing scratch cleanup failed: {type(exc).__name__}", file=sys.stderr)
        return 70
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

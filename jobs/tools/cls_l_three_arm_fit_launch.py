#!/usr/bin/env python3
"""Launch-V2 entrypoint for the frozen CLS-L three-arm fit stage."""
from __future__ import annotations

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
# Launch-V2 invokes this entrypoint by file path (``python jobs/tools/...py``).
# In that mode Python puts ``jobs/tools`` rather than the repository root on
# sys.path, so package imports under ``jobs`` would otherwise fail before the
# frozen stage can authenticate any scientific input.  Bootstrap only the
# repository import root; no scientific/runtime contract is changed.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools.cls_l_source_normalization_preflight_launch import (
    authenticated_code_sha,
    ensure_numeric_runtime,
)

SCRIPT = ROOT / "jobs" / "templates" / "l3-cls-l-three-arm-fit-v1.sh"


def main() -> int:
    if not SCRIPT.is_file():
        raise FileNotFoundError(SCRIPT)
    os.environ["EXPECTED_CODE_SHA"] = authenticated_code_sha()
    os.environ["JASS_L3_NUMERIC_VENV"] = str(ensure_numeric_runtime())
    os.execv("/usr/bin/bash", ["/usr/bin/bash", str(SCRIPT)])
    return 127


if __name__ == "__main__":
    raise SystemExit(main())

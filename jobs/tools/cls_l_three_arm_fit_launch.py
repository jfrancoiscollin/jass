#!/usr/bin/env python3
"""Launch-V2 entrypoint for the frozen CLS-L three-arm fit stage."""
from __future__ import annotations

import os
from pathlib import Path

from jobs.tools.cls_l_source_normalization_preflight_launch import (
    authenticated_code_sha,
    ensure_numeric_runtime,
)

ROOT = Path(__file__).resolve().parents[2]
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

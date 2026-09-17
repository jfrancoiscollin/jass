#!/usr/bin/env python3
"""Launch-V2 Python entrypoint for the frozen CLS-L normalization shell stage.

Launch-V2 fingerprints its command interpreter as the numerical runtime. The
scientific stage itself remains the existing immutable shell template; this thin
entrypoint exists only so the gate fingerprints /usr/bin/python3 rather than
trying to execute Python runtime-identification code through /usr/bin/bash.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "jobs" / "templates" / "l3-cls-l-source-normalization-preflight-v1.sh"


def main() -> int:
    if not SCRIPT.is_file():
        raise FileNotFoundError(SCRIPT)
    os.execv("/usr/bin/bash", ["/usr/bin/bash", str(SCRIPT)])
    return 127  # pragma: no cover - execv replaces the process on success.


if __name__ == "__main__":
    raise SystemExit(main())

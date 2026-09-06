#!/usr/bin/env python3
"""Run frozen B2 recovery v2 with legacy-support JSON formatting compatibility.

This wrapper changes no scientific computation. It only installs the narrowly
scoped immutable-support serialization compatibility established after technical
failure 1829, then delegates to the existing exact-zero-cost recovery v2.
"""
from __future__ import annotations

from pathlib import Path
import sys

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools import adaptive_sibling_b2_legacy_support_json_compat as legacy_support  # noqa: E402

legacy_support.install()

from jobs.tools import adaptive_sibling_b2_statistical_completion_recovery_v2 as recovery_v2  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(recovery_v2.main(sys.argv[1:]))

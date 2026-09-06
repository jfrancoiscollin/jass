#!/usr/bin/env python3
"""Run target-data B2 admissibility with the exact-zero-cost compatibility shim."""
from __future__ import annotations

import sys

from jobs.tools import adaptive_sibling_b2_exact_zero_cost_compat as compat

compat.install()

from jobs.tools import adaptive_sibling_b2_recovery_admissibility_preflight as preflight  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(preflight.main(sys.argv[1:]))

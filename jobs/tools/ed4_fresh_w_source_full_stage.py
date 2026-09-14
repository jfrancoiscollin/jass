#!/usr/bin/env python3
"""Launch-V2-compatible full-shape wrapper for ED4-FRESH W source.

Launch V2 permits only LAUNCH_MODE to differ between a rehearsal and the
production spec it admits. The original W source stage intentionally used a
small 4096-record / 32-opening rehearsal shape and a 40960-record / 512-opening
production shape, which makes their normalized specs different and therefore
cannot admit production.

This wrapper changes no W science. It makes *rehearsal mode* execute the exact
production source shape while retaining rehearsal evidence/side-effect
classification. Production mode is unchanged. Both modes therefore use the
same command, seed, record budget, source-selection rule, outputs and time
contract; only LAUNCH_MODE differs, as required by Launch V2. Outcomes remain
unread and target bytes remain zeroed by the underlying stage.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools import ed4_fresh_w_source_stage as base

_ORIGINAL_RUN = base.subprocess.run


def production_shape_contract() -> dict[str, int]:
    return {
        "record_budget": base.PRODUCTION_RECORD_BUDGETS[0],
        "opening_groups": base.PRODUCTION_OPENINGS,
        "positions": base.PRODUCTION_POSITIONS,
        "generator_timeout_seconds": 2100,
    }


def adjusted_timeout(command, timeout):
    """Raise only the generator's old small-rehearsal timeout to production's cap."""
    if isinstance(command, (list, tuple)) and "--gen-data-wdl" in command and timeout == 900:
        return production_shape_contract()["generator_timeout_seconds"]
    return timeout


def _run_with_full_rehearsal_timeout(*args, **kwargs):
    command = args[0] if args else kwargs.get("args")
    if "timeout" in kwargs:
        kwargs = dict(kwargs)
        kwargs["timeout"] = adjusted_timeout(command, kwargs["timeout"])
    return _ORIGINAL_RUN(*args, **kwargs)


def configure_full_rehearsal_shape() -> None:
    contract = production_shape_contract()
    base.REHEARSAL_RECORD_BUDGET = contract["record_budget"]
    base.REHEARSAL_OPENINGS = contract["opening_groups"]
    base.REHEARSAL_POSITIONS = contract["positions"]
    # Only the `--gen-data-wdl` call has a mode-dependent timeout in the base
    # stage. Keep every other subprocess timeout untouched.
    base.subprocess.run = _run_with_full_rehearsal_timeout


def main() -> int:
    configure_full_rehearsal_shape()
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())

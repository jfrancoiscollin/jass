#!/usr/bin/env python3
"""Signal-safe entrypoint for the ED2 controller (not its Scan workers)."""
from __future__ import annotations
from pathlib import Path
import signal
import sys
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))


def install_shutdown_handlers():
    def stop(signum, _frame):
        # Unwind role_search's finally block, which terminates all worker groups.
        # Ignore repeat termination while that bounded cleanup is in progress.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        raise SystemExit(128+signum)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)


def main():
    from jobs.tools.ed2_value_pipeline import main as controller
    install_shutdown_handlers()
    return controller()


if __name__=='__main__': raise SystemExit(main())

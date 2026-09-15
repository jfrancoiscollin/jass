#!/usr/bin/env python3
"""Run the frozen ED5 D/W/S historical barrier with an explicit current D source.

The original barrier default remains D1976 for reproducibility of 1985/1986.
After the authenticated pre-target D collision repair, the replacement D source
must be bound by immutable job/attempt/code identity just like W and S. This
wrapper changes only that source identity; all canonical/historical checks and
zero-target semantics remain delegated byte-for-byte to the existing barrier.
"""
from __future__ import annotations

from jobs.tools import ed5_fresh_dws_disjointness_stage as barrier


def main() -> int:
    barrier.D = barrier.identity_from_env("D")
    return barrier.main()


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "jobs/templates/l3-imbalance2-top3-selfplay-v1.sh"
ADAPTER = ROOT / "jobs/templates/l3-imbalance2-top3-selfplay-2m-v1.sh"
WRAPPER = ROOT / "jobs/prepared/l3-imbalance2-top3-2m-20260721/ccx33-l3-imbalance2-top3-selfplay-2m-p1.sh"


def main() -> int:
    base = BASE.read_text(encoding="utf-8")
    adapter = ADAPTER.read_text(encoding="utf-8")
    wrapper = WRAPPER.read_text(encoding="utf-8")
    assert 'FRESH="${FRESH:-500000}"' in base
    assert 'FRESH=2000000' in wrapper
    assert 'CHUNK=500000' in wrapper
    assert 'exec bash jobs/templates/l3-imbalance2-top3-selfplay-2m-v1.sh' in wrapper
    for token in (
        'FRESH="${FRESH:-2000000}"',
        'standard TOP3 requires 2000000 records and four generations',
        'corpus=2M/gen',
    ):
        assert token in adapter
    with tempfile.TemporaryDirectory() as tmp:
        # Static syntax gate; runtime expansion itself is fail-closed on exact replacements.
        subprocess.run(["bash", "-n", str(ADAPTER)], check=True)
        subprocess.run(["bash", "-n", str(WRAPPER)], check=True)
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

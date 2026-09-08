#!/usr/bin/env python3
"""Add the J12 factorial Gate0 scorer target to an isolated source copy."""
from __future__ import annotations

import argparse
from pathlib import Path

BLOCK = r'''

# Benchmark-only fresh J12 factorial Gate0 scorer (isolated execution copy).
add_executable(jass_scan_oracle_gate0_j12_factorial
    jobs/tools/scan_oracle_gate0_j12_factorial.cpp
    $<TARGET_OBJECTS:jass_t3_f6_runtime>)
target_link_libraries(jass_scan_oracle_gate0_j12_factorial PRIVATE jass_lib jass_warnings)
'''


def render(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "jass_scan_oracle_gate0_j12_factorial" in text:
        raise RuntimeError("J12 Gate0 CMake target already present")
    if "add_library(jass_lib STATIC" not in text or "jass_t3_f6_runtime" not in text:
        raise RuntimeError("CMake anchor drift")
    path.write_text(text.rstrip() + BLOCK + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cmake", type=Path, required=True)
    args = ap.parse_args()
    render(args.cmake)
    print("J12_GATE0_RENDER_COMPLETE_V1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

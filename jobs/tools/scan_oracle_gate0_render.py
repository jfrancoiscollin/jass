#!/usr/bin/env python3
"""Add Gate-0 scorer targets to an isolated source copy only."""
from __future__ import annotations

import argparse
from pathlib import Path

BLOCK = r'''

# Benchmark-only Scan-oracle Gate 0 scorers (isolated execution copy).
add_executable(jass_scan_oracle_gate0_runtime
    jobs/tools/scan_oracle_gate0_runtime.cpp
    $<TARGET_OBJECTS:jass_t3_f6_runtime>)
target_link_libraries(jass_scan_oracle_gate0_runtime PRIVATE jass_lib jass_warnings)

add_executable(jass_scan_oracle_gate0_search_variants
    jobs/tools/scan_oracle_gate0_search_variants.cpp
    $<TARGET_OBJECTS:jass_t3_f6_runtime>)
target_link_libraries(jass_scan_oracle_gate0_search_variants PRIVATE jass_lib jass_warnings)
'''


def render(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "jass_scan_oracle_gate0_runtime" in text or "jass_scan_oracle_gate0_search_variants" in text:
        raise RuntimeError("Gate-0 CMake target already present")
    if "add_library(jass_lib STATIC" not in text or "jass_t3_f6_runtime" not in text:
        raise RuntimeError("CMake anchor drift")
    path.write_text(text.rstrip() + BLOCK + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cmake", type=Path, required=True)
    args = ap.parse_args()
    render(args.cmake)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

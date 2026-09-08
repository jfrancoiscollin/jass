#!/usr/bin/env python3
"""Render the D4c pairwise rank-breaker into an isolated search.cpp."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools import d3_runtime_render as d3
from jobs.tools import d4b_runtime_render as d4b

INCLUDE_REPLACEMENT = d3.INCLUDE_ANCHOR + '#include "d4c_runtime_move_order.hpp"\n'

NEW_ORDER = d4b.NEW_ORDER.replace("D4b", "D4c").replace(
    "d4b_runtime_order::", "d4c_runtime_order::"
)
NEW_ORDER = NEW_ORDER.replace(
    "d4c_runtime_order::logit(rt, phase, rank, f)",
    "d4c_runtime_order::score(rt, phase, f)",
)
NEW_ORDER = NEW_ORDER.replace(
    "    if (best == 0) return;\n",
    "    d4c_runtime_order::note_prediction(best);\n    if (best == 0) return;\n",
)
CALL_NEW = d4b.CALL_NEW


def replace_once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"D4C_RUNTIME_RENDER_INVALID {label} count={n}")
    return text.replace(old, new, 1)


def render(src: Path, out: Path) -> None:
    text = src.read_text(encoding="utf-8")
    text = replace_once(text, d3.INCLUDE_ANCHOR, INCLUDE_REPLACEMENT, "include")
    text = replace_once(text, d3.OLD_ORDER, NEW_ORDER, "order body")
    text = replace_once(text, d3.CALL_OLD, CALL_NEW, "recursive call")
    if text.count("d4c_runtime_order::score") != 1 or text.count("note_prediction(best)") != 1:
        raise RuntimeError("D4C_RUNTIME_RENDER_INVALID treatment cardinality")
    if "d4b_runtime_order" in text:
        raise RuntimeError("D4C_RUNTIME_RENDER_INVALID D4b namespace leak")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--src", type=Path, required=True); ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(); render(a.src, a.out); print("D4C_RUNTIME_RENDER_COMPLETE_V1"); return 0


if __name__ == "__main__":
    raise SystemExit(main())

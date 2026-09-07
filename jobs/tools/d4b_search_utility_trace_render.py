#!/usr/bin/env python3
"""Render the frozen D4 teacher at D4b's exact 20k-node micro budget."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools import d4_search_utility_trace_render as d4render


def replace_once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected one occurrence, found {n}")
    return text.replace(old, new, 1)


def render(root: Path) -> None:
    d4render.render(root)
    cpp = root / "jobs/tools/d4_search_utility_trace_export.cpp"
    text = cpp.read_text(encoding="utf-8")
    text = replace_once(text, "limits.max_nodes = 50'000;", "limits.max_nodes = 20'000;", "teacher max_nodes")
    text = replace_once(text, "if (result.nodes > 50'000U)", "if (result.nodes > 20'000U)", "teacher overshoot")
    text = replace_once(text, '<< "  \\\"exact_nodes_per_root\\\": 50000,\\n"', '<< "  \\\"exact_nodes_per_root\\\": 20000,\\n"', "teacher report nodes")
    cpp.write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--root", type=Path, required=True)
    a = ap.parse_args(); render(a.root); print("D4B_TRACE_RENDER_COMPLETE_V1"); return 0


if __name__ == "__main__":
    raise SystemExit(main())

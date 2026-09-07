#!/usr/bin/env python3
"""Render D4b runtime plus a D4B-aware Scan Gate0 scorer in an isolated tree."""
from __future__ import annotations

import argparse
from pathlib import Path
from jobs.tools import d4b_runtime_render, scan_oracle_gate0_render


def once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1: raise RuntimeError(f"{label}: expected one anchor, found {n}")
    return text.replace(old, new, 1)


def render(root: Path) -> None:
    search = root / "src/search.cpp"
    tmp = root / "src/search.cpp.d4b"
    d4b_runtime_render.render(search, tmp); tmp.replace(search)
    scan_oracle_gate0_render.render(root / "CMakeLists.txt")
    scorer = root / "jobs/tools/scan_oracle_gate0_runtime.cpp"
    text = scorer.read_text(encoding="utf-8")
    text = once(text, '#include "scan_eval.hpp"\n', '#include "scan_eval.hpp"\n#include "d4b_runtime_move_order.hpp"\n', "scorer include")
    text = once(text,
        '        if (arm != "CONTROL" && arm != "D3")\n            throw std::runtime_error("unsupported Gate-0 arm");\n',
        '        if (arm != "CONTROL" && arm != "D3" && arm != "D4B")\n            throw std::runtime_error("unsupported Gate-0 arm");\n', "arm support")
    text = once(text,
        '        if ((arm == "CONTROL" && (d3a || d3b)) ||\n            (arm == "D3" && (!d3a || !d3b)))\n            throw std::runtime_error("D3 runtime environment/arm mismatch");\n',
        '        const char* d4b = std::getenv("JASS_D4B_RUNTIME_MODEL");\n        if ((arm == "CONTROL" && (d3a || d3b)) ||\n            (arm == "D3" && (!d3a || !d3b)) ||\n            (arm == "D4B" && (d3a || d3b || !d4b)) ||\n            (arm != "D4B" && d4b))\n            throw std::runtime_error("runtime environment/arm mismatch");\n', "env contract")
    text = once(text, '        Gate0Counters c{};\n', '        d4b_runtime_order::reset_counters();\n        Gate0Counters c{};\n', "counter reset")
    text = once(text,
        '        << "  \\\"scan_searches\\\": 0,\\n"\n',
        '        << "  \\\"d4b_eligible_nodes\\\": " << d4b_runtime_order::eligible_nodes() << ",\\n"\n        << "  \\\"d4b_hoists\\\": " << d4b_runtime_order::hoists() << ",\\n"\n        << "  \\\"scan_searches\\\": 0,\\n"\n', "report counters")
    text = once(text,
        '        if (c.selected_rows != 512 || c.processed_rows != 512 || c.invalid_rows != 0\n            || c.exact_budget_failures != 0)\n            throw std::runtime_error("Gate-0 scorer count/integrity drift");\n        write_report(report_path, arm, budget, shard, nshards, tt_mb, tb_cap, c);\n',
        '        if (c.selected_rows != 512 || c.processed_rows != 512 || c.invalid_rows != 0\n            || c.exact_budget_failures != 0)\n            throw std::runtime_error("Gate-0 scorer count/integrity drift");\n        if (arm == "D4B" && d4b_runtime_order::eligible_nodes() == 0)\n            throw std::runtime_error("D4b runtime was not exercised");\n        write_report(report_path, arm, budget, shard, nshards, tt_mb, tb_cap, c);\n', "activation guard")
    scorer.write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--root", type=Path, required=True)
    a = ap.parse_args(); render(a.root); print("D4B_GATE0_RENDER_COMPLETE_V1"); return 0


if __name__ == "__main__":
    raise SystemExit(main())

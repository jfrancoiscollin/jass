#!/usr/bin/env python3
"""Render the frozen D3 equal-node harness into isolated source copies.

The repository sources are never mutated by a job. Both arms receive the
same exact-node HUB extension. The candidate copy additionally receives a
diagnostic-only D3 feature-call counter; the counter cannot affect a node-budget
strength decision and is not used by any gate.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"{label}: expected exactly one anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


def render_hub(text: str, *, candidate: bool) -> str:
    text = once(
        text,
        '    bool async      = false;\n    bool depth_set  = false;\n',
        '    bool async      = false;\n    bool depth_set  = false;\n'
        '    bool nodes_set  = false;\n',
        "go local flags",
    )
    text = once(
        text,
        '        } else if (tok == "movetime") {\n'
        '            int v = 0;\n'
        '            if (!take_int(v) || v < 1) {\n'
        '                emit_error("go movetime: positive integer required");\n'
        '                return;\n'
        '            }\n'
        '            lim.movetime_ms = v;\n'
        '        } else if (tok == "wtime")',
        '        } else if (tok == "movetime") {\n'
        '            int v = 0;\n'
        '            if (!take_int(v) || v < 1) {\n'
        '                emit_error("go movetime: positive integer required");\n'
        '                return;\n'
        '            }\n'
        '            lim.movetime_ms = v;\n'
        '        } else if (tok == "nodes") {\n'
        '            int v = 0;\n'
        '            if (!take_int(v) || v < 1) {\n'
        '                emit_error("go nodes: positive integer required");\n'
        '                return;\n'
        '            }\n'
        '            lim.max_nodes = static_cast<std::uint64_t>(v);\n'
        '            lim.node_limit_mode = NodeLimitMode::Exact;\n'
        '            nodes_set = true;\n'
        '        } else if (tok == "wtime")',
        "go nodes parser",
    )
    text = once(
        text,
        '        lim.max_depth = (async || lim.movetime_ms > 0) ? MAX_PLY : 6;\n',
        '        lim.max_depth = (async || lim.movetime_ms > 0 || nodes_set) ? MAX_PLY : 6;\n',
        "go depth ceiling",
    )
    if candidate:
        text = once(
            text,
            '#include "timemgr.hpp"\n',
            '#include "timemgr.hpp"\n#include "d3_runtime_move_order.hpp"\n',
            "D3 diagnostics include",
        )
        text = once(
            text,
            '         << " rootorderfail=" << r.root_order_failures;\n',
            '         << " rootorderfail=" << r.root_order_failures\n'
            '         << " d3calls=" << d3_runtime_order::feature_calls();\n',
            "bestmove D3 diagnostics",
        )
        text = once(
            text,
            'void HubFrontEnd::cmd_go(std::string_view args) {\n'
            '    wait_for_worker();\n\n'
            '    SearchLimits lim;\n',
            'void HubFrontEnd::cmd_go(std::string_view args) {\n'
            '    wait_for_worker();\n'
            '    d3_runtime_order::reset_feature_calls();\n\n'
            '    SearchLimits lim;\n',
            "D3 diagnostics reset",
        )
    return text


def render_header(text: str) -> str:
    text = once(text, '#include <array>\n', '#include <array>\n#include <atomic>\n',
                "atomic include")
    text = once(
        text,
        'inline constexpr std::size_t WIDTH = BASE_WIDTH * PHASES;\n',
        'inline constexpr std::size_t WIDTH = BASE_WIDTH * PHASES;\n\n'
        'inline std::atomic<std::uint64_t> FEATURE_CALLS{0};\n'
        'inline void reset_feature_calls() noexcept {\n'
        '    FEATURE_CALLS.store(0, std::memory_order_relaxed);\n'
        '}\n'
        'inline std::uint64_t feature_calls() noexcept {\n'
        '    return FEATURE_CALLS.load(std::memory_order_relaxed);\n'
        '}\n',
        "feature counter declaration",
    )
    text = once(
        text,
        'inline double score(const Runtime& rt, const Position& parent,\n'
        '                    const Move& move) {\n'
        '    const Position child = parent.after(move);\n',
        'inline double score(const Runtime& rt, const Position& parent,\n'
        '                    const Move& move) {\n'
        '    FEATURE_CALLS.fetch_add(1, std::memory_order_relaxed);\n'
        '    const Position child = parent.after(move);\n',
        "feature counter increment",
    )
    return text


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--hub", type=Path, required=True)
    p.add_argument("--out-hub", type=Path, required=True)
    p.add_argument("--candidate", action="store_true")
    p.add_argument("--d3-header", type=Path)
    p.add_argument("--out-d3-header", type=Path)
    a = p.parse_args()
    a.out_hub.write_text(render_hub(a.hub.read_text(encoding="utf-8"),
                                    candidate=a.candidate), encoding="utf-8")
    if a.candidate:
        if a.d3_header is None or a.out_d3_header is None:
            p.error("--candidate requires --d3-header and --out-d3-header")
        a.out_d3_header.write_text(
            render_header(a.d3_header.read_text(encoding="utf-8")), encoding="utf-8"
        )
    elif a.d3_header is not None or a.out_d3_header is not None:
        p.error("D3 header arguments are candidate-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

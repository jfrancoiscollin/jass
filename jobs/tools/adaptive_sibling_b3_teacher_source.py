#!/usr/bin/env python3
"""Render the B3 real adaptive sibling teacher from the audited B2 teacher source.

The renderer first applies the reviewed B2 runtime adapter (fresh Engine/TT per
search, explicit EGDB, empty JASS_* environment), then replaces only the
per-parent unconditional full-ladder loop with the B2-confirmed 100/60/2 staged
racing policy. q200 is executed only after S50 is sealed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Iterable

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools import adaptive_sibling_b2_teacher_source as b2  # noqa: E402

SCHEMA = "jass.adaptive_sibling_b3_teacher_source_adapter.v1"
M5 = 100
M50 = 60
MIN_SURVIVORS = 2
BUDGETS = (5_000, 50_000, 200_000)

START = "        const std::string fingerprint = parent_fingerprint(row);\n        for (const Move& move : unique_moves) {"
END = "    }\n\n    char trailing = 0;"
HEADER_END = '              "pv50k_enters_egdb\\tpv200k_enters_egdb\\n";'
HEADER_B3 = (
    '              "pv50k_enters_egdb\\tpv200k_enters_egdb\\tsearched5\\tsearched50\\t"\n'
    '              "searched200\\tsurvived5\\tsurvived50\\tselected\\texact_shortcut_reason\\t"\n'
    '              "sole_survivor_reason\\tuncertified\\n";'
)

LOOP = r'''        const std::string fingerprint = parent_fingerprint(row);
        struct AdaptiveAction {
            Move move{};
            Position child{};
            bool moving_king{false};
            int captured_kings{0};
            int child_pieces{0};
            int child_legal_moves{0};
            bool child_forced_capture{false};
            bool rule_terminal{false};
            bool tb_exact{false};
            std::optional<int> exact_u{};
            int t_baseline_parent{0};
            SearchObs s5{};
            SearchObs s50{};
            SearchObs s200{};
            bool searched5{false};
            bool searched50{false};
            bool searched200{false};
            bool survived5{false};
            bool survived50{false};
            bool selected{false};
        };

        std::vector<AdaptiveAction> actions;
        actions.reserve(unique_moves.size());
        for (const Move& move : unique_moves) {
            AdaptiveAction action{};
            action.move = move;
            action.moving_king = test(parent.kings_of(parent.side_to_move()), move.from);
            action.captured_kings = popcount(
                move.captured & parent.kings_of(opposite(parent.side_to_move())));
            action.child = parent.after(move);
            MoveList child_legal;
            generate_legal_moves(action.child, child_legal);
            action.child_pieces = popcount(action.child.occupied());
            action.child_legal_moves = static_cast<int>(child_legal.size());
            action.child_forced_capture = !child_legal.empty() && child_legal[0].is_capture();
            action.exact_u = exact_parent_utility(
                parent, action.child, tb_cap, action.rule_terminal, action.tb_exact);
            c.rule_terminal_children += static_cast<std::uint64_t>(action.rule_terminal);
            c.exact_tb_children += static_cast<std::uint64_t>(action.tb_exact);
            action.t_baseline_parent = -curriculum->evaluate(action.child);
            actions.push_back(action);
        }

        auto top_with_margin = [&](const std::vector<std::size_t>& pool,
                                   auto score_of,
                                   int margin) {
            std::vector<std::size_t> ranked = pool;
            std::sort(ranked.begin(), ranked.end(), [&](std::size_t left, std::size_t right) {
                const int ls = score_of(actions[left]);
                const int rs = score_of(actions[right]);
                if (ls != rs) return ls > rs;
                return left < right;
            });
            std::vector<std::size_t> kept;
            if (ranked.empty()) return kept;
            const std::int64_t best = score_of(actions[ranked.front()]);
            for (std::size_t index : ranked) {
                const std::int64_t score = score_of(actions[index]);
                if (best - score <= margin) kept.push_back(index);
            }
            const std::size_t minimum = std::min<std::size_t>(B3_MIN_SURVIVORS, ranked.size());
            for (std::size_t k = 0; k < minimum; ++k) {
                if (std::find(kept.begin(), kept.end(), ranked[k]) == kept.end()) {
                    kept.push_back(ranked[k]);
                }
            }
            std::sort(kept.begin(), kept.end());
            return kept;
        };

        std::optional<std::size_t> chosen{};
        std::string exact_reason = "NONE";
        std::string sole_reason = "NONE";
        bool uncertified = false;

        std::vector<std::size_t> exact_wins;
        std::vector<std::size_t> unresolved;
        for (std::size_t i = 0; i < actions.size(); ++i) {
            if (actions[i].exact_u && *actions[i].exact_u == 1) exact_wins.push_back(i);
            if (!actions[i].exact_u) unresolved.push_back(i);
        }

        if (!exact_wins.empty()) {
            chosen = exact_wins.front();
            exact_reason = "EXACT_WIN";
        } else if (unresolved.empty()) {
            for (std::size_t i = 0; i < actions.size(); ++i) {
                if (actions[i].exact_u && *actions[i].exact_u == 0) {
                    chosen = i;
                    exact_reason = "ALL_EXACT_DRAW";
                    break;
                }
            }
            if (!chosen) {
                chosen = std::size_t{0};
                exact_reason = "ALL_EXACT_LOSS";
            }
        } else {
            for (std::size_t index : unresolved) {
                auto& action = actions[index];
                action.s5 = run_fresh_search(
                    tt_mb, c.engine_constructions, action.child, curriculum.get(), CHEAP_BUDGET, tb_cap);
                action.searched5 = true;
                ++c.cheap_searches;
                c.cheap_nodes += action.s5.nodes;
            }
            const auto s5 = top_with_margin(
                unresolved, [](const AdaptiveAction& action) { return action.s5.parent_score; }, B3_M5_CP);
            for (std::size_t index : s5) actions[index].survived5 = true;

            for (std::size_t index : s5) {
                auto& action = actions[index];
                action.s50 = run_fresh_search(
                    tt_mb, c.engine_constructions, action.child, curriculum.get(), SCREEN_BUDGET, tb_cap);
                action.searched50 = true;
                ++c.screen_searches;
                c.screen_nodes += action.s50.nodes;
            }
            const auto s50 = top_with_margin(
                s5, [](const AdaptiveAction& action) { return action.s50.parent_score; }, B3_M50_CP);
            for (std::size_t index : s50) actions[index].survived50 = true;

            if (s50.size() == 1) {
                chosen = s50.front();
                sole_reason = "SOLE_UNRESOLVED_BEFORE_Q200";
                uncertified = true;
            } else {
                for (std::size_t index : s50) {
                    auto& action = actions[index];
                    action.s200 = run_fresh_search(
                        tt_mb, c.engine_constructions, action.child, curriculum.get(), TEACHER_BUDGET, tb_cap);
                    action.searched200 = true;
                    ++c.teacher_searches;
                    c.teacher_nodes += action.s200.nodes;
                }
                chosen = *std::min_element(s50.begin(), s50.end(), [&](std::size_t left, std::size_t right) {
                    const int ls = actions[left].s200.parent_score;
                    const int rs = actions[right].s200.parent_score;
                    if (ls != rs) return ls > rs;
                    return left < right;
                });
            }
        }

        if (!chosen || *chosen >= actions.size()) {
            std::cerr << "error: B3 adaptive policy failed to choose parent " << idx << '\n';
            return 4;
        }
        actions[*chosen].selected = true;

        for (const AdaptiveAction& action : actions) {
            const Move& move = action.move;
            write_zero_target_row(children, action.child);
            groups << output_count << '\t' << idx << '\t' << fingerprint << '\t'
                   << static_cast<int>(row.stm) << '\t' << parent_pieces << '\t'
                   << static_cast<int>(move.from) << '\t' << static_cast<int>(move.to) << '\t'
                   << static_cast<int>(move.num_captures) << '\t' << (move.promotes ? 1 : 0) << '\t'
                   << (action.moving_king ? 1 : 0) << '\t' << action.captured_kings << '\t'
                   << material_count_delta_parent(parent, action.child) << '\t'
                   << action.child_pieces << '\t' << action.child_legal_moves << '\t'
                   << (action.child_forced_capture ? 1 : 0) << '\t'
                   << (action.rule_terminal ? 1 : 0) << '\t' << (action.tb_exact ? 1 : 0) << '\t'
                   << (action.exact_u ? *action.exact_u : 2) << '\t'
                   << action.t_baseline_parent << '\t' << action.s5.parent_score << '\t'
                   << action.s50.parent_score << '\t' << action.s200.parent_score << '\t'
                   << action.s5.nodes << '\t' << action.s50.nodes << '\t' << action.s200.nodes << '\t'
                   << action.s5.completed_depth << '\t' << action.s50.completed_depth << '\t'
                   << action.s200.completed_depth << '\t' << action.s5.effective_depth << '\t'
                   << action.s50.effective_depth << '\t' << action.s200.effective_depth << '\t'
                   << (action.s5.aborted_iteration ? 1 : 0) << '\t'
                   << (action.s50.aborted_iteration ? 1 : 0) << '\t'
                   << (action.s200.aborted_iteration ? 1 : 0) << '\t'
                   << search_stop_reason_name(action.s5.stop_reason) << '\t'
                   << search_stop_reason_name(action.s50.stop_reason) << '\t'
                   << search_stop_reason_name(action.s200.stop_reason) << '\t'
                   << action.s5.elapsed_us << '\t' << action.s50.elapsed_us << '\t'
                   << action.s200.elapsed_us << '\t' << (action.s5.pv_enters_egdb ? 1 : 0) << '\t'
                   << (action.s50.pv_enters_egdb ? 1 : 0) << '\t'
                   << (action.s200.pv_enters_egdb ? 1 : 0) << '\t'
                   << (action.searched5 ? 1 : 0) << '\t' << (action.searched50 ? 1 : 0) << '\t'
                   << (action.searched200 ? 1 : 0) << '\t' << (action.survived5 ? 1 : 0) << '\t'
                   << (action.survived50 ? 1 : 0) << '\t' << (action.selected ? 1 : 0) << '\t'
                   << exact_reason << '\t' << sole_reason << '\t' << (uncertified ? 1 : 0) << '\n';
            ++output_count;
            ++c.emitted_siblings;
        }
'''


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def replace_exact(text: str, old: str, new: str, *, count: int = 1) -> str:
    actual = text.count(old)
    if actual != count:
        raise ValueError(f"expected {count} occurrences of anchor, got {actual}: {old[:80]!r}")
    return text.replace(old, new)


def render(source: str) -> str:
    out = b2.render(source)
    out = replace_exact(
        out,
        "constexpr std::size_t DEFAULT_TT_MB = 16;\n",
        "constexpr std::size_t DEFAULT_TT_MB = 16;\n"
        "constexpr int B3_M5_CP = 100;\n"
        "constexpr int B3_M50_CP = 60;\n"
        "constexpr std::size_t B3_MIN_SURVIVORS = 2;\n",
    )
    out = replace_exact(out, HEADER_END, HEADER_B3)
    if out.count(START) != 1 or out.count(END) != 1:
        raise ValueError("B3 loop anchors are not unique")
    begin = out.index(START)
    end = out.index(END, begin)
    out = out[:begin] + LOOP + out[end:]
    out = replace_exact(
        out,
        '\"jass.deep_sibling_teacher_extract.v1\"',
        '\"jass.adaptive_sibling_b3_teacher_extract.v1\"',
    )
    out = replace_exact(
        out,
        '        << "  \"stable_pairs_selected\": false,\\n"\n',
        '        << "  \"adaptive_policy_real\": true,\\n"\n'
        '        << "  \"m5_cp\": 100,\\n"\n'
        '        << "  \"m50_cp\": 60,\\n"\n'
        '        << "  \"minimum_survivors\": 2,\\n"\n'
        '        << "  \"full_ladder_executed\": false,\\n"\n',
    )
    forbidden = (
        "const SearchObs s5 = run_fresh_search",
        "const SearchObs s50 = run_fresh_search",
        "const SearchObs s200 = run_fresh_search",
    )
    if any(token in out for token in forbidden):
        raise ValueError("unconditional full-ladder search survived B3 render")
    if out.count("run_fresh_search(tt_mb, c.engine_constructions") != 3:
        raise ValueError("B3 rendered source must contain exactly three staged search call sites")
    for token in (
        "B3_M5_CP = 100", "B3_M50_CP = 60", "B3_MIN_SURVIVORS = 2",
        "action.searched50 = true", "action.searched200 = true",
        "SOLE_UNRESOLVED_BEFORE_Q200", "adaptive_policy_real",
    ):
        if token not in out:
            raise ValueError(f"B3 rendered source lost required token {token!r}")
    return out


def render_file(source_path: Path, output_path: Path, receipt_path: Path) -> dict[str, object]:
    raw = source_path.read_bytes()
    normalized = raw.replace(b"\r\n", b"\n")
    if b"\r" in normalized:
        raise ValueError("base source contains bare CR")
    source = normalized.decode("utf-8")
    if sha256(normalized) != b2.BASE_SOURCE_NORMALIZED_SHA256:
        raise ValueError("base deep_sibling_teacher source SHA drift")
    rendered = render(source).encode("utf-8")
    receipt = {
        "schema": SCHEMA,
        "base_source_normalized_sha256": sha256(normalized),
        "b2_base_source_expected_sha256": b2.BASE_SOURCE_NORMALIZED_SHA256,
        "rendered_source_sha256": sha256(rendered),
        "rendered_source_bytes": len(rendered),
        "policy": {"M5": M5, "M50": M50, "minimum_survivors": MIN_SURVIVORS},
        "budgets_nodes": list(BUDGETS),
        "fresh_engine_each_search": True,
        "fresh_tt_each_search": True,
        "book_enabled": False,
        "threads_per_search": 1,
        "node_limit_mode": "exact",
        "q200_used_before_s50_seal": False,
        "search_decision_trace_affects_allocation": False,
        "fits": 0,
        "strength_games": 0,
        "promotion_authorized": False,
        "bake_authorized": False,
    }
    for path in (output_path, receipt_path):
        if path.exists() or path.is_symlink():
            raise ValueError(f"refusing existing output: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(rendered)
    receipt_path.write_text(
        json.dumps(receipt, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n",
        encoding="ascii",
    )
    return receipt


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    render_parser = sub.add_parser("render")
    render_parser.add_argument("--source", type=Path, required=True)
    render_parser.add_argument("--output", type=Path, required=True)
    render_parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = render_file(args.source, args.output, args.receipt)
        print(json.dumps({"schema": SCHEMA, "rendered_source_sha256": receipt["rendered_source_sha256"]},
                         sort_keys=True, separators=(",", ":")))
        return 0
    except Exception as exc:
        print(f"adaptive_sibling_b3_teacher_source: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

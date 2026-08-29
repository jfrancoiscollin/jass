// SPDX-License-Identifier: AGPL-3.0-or-later
// Frozen CURRICULUM search ladder for the benchmark-only Scan ceiling study.
// Every child/budget gets a newly constructed Engine and exact node mode.

#include "pattern_jass_bridge.hpp"
#include "scan_eval.hpp"

#define load_pattern_jass_network load_eval_network
#define main deep_sibling_teacher_main_disabled
#include "deep_sibling_teacher.cpp"
#undef main
#undef load_pattern_jass_network

#include <algorithm>
#include <array>
#include <bit>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>

namespace {

constexpr std::array<std::uint64_t, 5> ALLOWED_BUDGETS{
    1'000, 5'000, 50'000, 200'000, 1'000'000
};

struct LadderCounters {
    std::uint64_t source_rows{0};
    std::uint64_t selected_rows{0};
    std::uint64_t processed_rows{0};
    std::uint64_t invalid_rows{0};
    std::vector<std::uint64_t> searches;
    std::vector<std::uint64_t> nodes;
    std::vector<std::uint64_t> exact_budget_rows;
    std::vector<std::uint64_t> max_depth_exhausted_rows;
    std::vector<std::uint64_t> terminal_exact_rows;
    std::vector<std::uint64_t> tb_exact_rows;
    std::vector<std::uint64_t> elapsed_us;
};

struct ExactMeta {
    bool terminal{false};
    bool tb_exact{false};
    int parent_utility{2};
};

std::vector<std::string> split_tabs(const std::string& line) {
    std::vector<std::string> fields;
    std::stringstream stream(line);
    std::string field;
    while (std::getline(stream, field, '\t')) fields.push_back(field);
    if (!line.empty() && line.back() == '\t') fields.emplace_back();
    return fields;
}

std::vector<ExactMeta> load_exact_meta(const std::string& path,
                                       std::uint32_t expected_rows) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("cannot open sibling groups");
    std::string line;
    if (!std::getline(in, line)) throw std::runtime_error("empty sibling groups");
    if (!line.empty() && line.back() == '\r') line.pop_back();
    const auto header = split_tabs(line);
    const auto column = [&](const std::string& name) -> std::size_t {
        const auto it = std::find(header.begin(), header.end(), name);
        if (it == header.end()) throw std::runtime_error("missing sibling group field: " + name);
        return static_cast<std::size_t>(std::distance(header.begin(), it));
    };
    const std::size_t row_col = column("row_index");
    const std::size_t terminal_col = column("child_rule_terminal");
    const std::size_t tb_col = column("child_tb_exact");
    const std::size_t utility_col = column("exact_parent_utility");
    const std::size_t max_col = std::max({row_col, terminal_col, tb_col, utility_col});
    std::vector<ExactMeta> out;
    while (std::getline(in, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        const auto fields = split_tabs(line);
        if (fields.size() <= max_col) throw std::runtime_error("truncated sibling group row");
        if (std::stoull(fields[row_col]) != out.size())
            throw std::runtime_error("sibling group row_index drift");
        ExactMeta meta;
        const int terminal = std::stoi(fields[terminal_col]);
        const int tb_exact = std::stoi(fields[tb_col]);
        meta.parent_utility = std::stoi(fields[utility_col]);
        if ((terminal != 0 && terminal != 1) || (tb_exact != 0 && tb_exact != 1)
            || terminal + tb_exact > 1) {
            throw std::runtime_error("invalid sibling exact flags");
        }
        meta.terminal = terminal != 0;
        meta.tb_exact = tb_exact != 0;
        if ((meta.terminal || meta.tb_exact)
                ? (meta.parent_utility < -1 || meta.parent_utility > 1)
                : meta.parent_utility != 2) {
            throw std::runtime_error("sibling exact utility/sentinel drift");
        }
        out.push_back(meta);
    }
    if (out.size() != expected_rows)
        throw std::runtime_error("sibling groups/children cardinality drift");
    return out;
}

int exact_parent_score(const ExactMeta& meta) {
    if (!meta.terminal && !meta.tb_exact)
        throw std::runtime_error("exact score requested for searched row");
    if (meta.parent_utility == 0) return 0;
    const int magnitude = meta.terminal
        ? jass::MATE_SCORE
        : (jass::MATE_SCORE - jass::MAX_PLY - 1);
    return meta.parent_utility * magnitude;
}

std::vector<std::uint64_t> parse_budgets(const std::string& text) {
    std::vector<std::uint64_t> out;
    std::set<std::uint64_t> seen;
    std::stringstream stream(text);
    std::string token;
    while (std::getline(stream, token, ',')) {
        if (token.empty()) throw std::runtime_error("empty budget token");
        const auto value = static_cast<std::uint64_t>(std::stoull(token));
        if (std::find(ALLOWED_BUDGETS.begin(), ALLOWED_BUDGETS.end(), value)
                == ALLOWED_BUDGETS.end()) {
            throw std::runtime_error("budget outside preregistered Jass ladder");
        }
        if (!seen.insert(value).second) throw std::runtime_error("duplicate budget");
        out.push_back(value);
    }
    if (out.empty()) throw std::runtime_error("empty budget ladder");
    return out;
}

std::unordered_set<std::uint32_t> load_row_filter(const std::string& path) {
    std::unordered_set<std::uint32_t> rows;
    if (path == "-") return rows;
    std::ifstream in(path);
    if (!in) throw std::runtime_error("cannot open row filter");
    std::uint64_t value = 0;
    while (in >> value) {
        if (value > std::numeric_limits<std::uint32_t>::max())
            throw std::runtime_error("row filter value overflow");
        if (!rows.insert(static_cast<std::uint32_t>(value)).second)
            throw std::runtime_error("duplicate row filter value");
    }
    if (!in.eof()) throw std::runtime_error("invalid row filter token");
    if (rows.empty()) throw std::runtime_error("explicit row filter is empty");
    return rows;
}

SearchObs run_new_engine_search(const jass::Position& child,
                                const jass::INetwork* network,
                                std::uint64_t budget,
                                int tb_cap,
                                std::size_t tt_mb) {
    jass::Engine engine(tt_mb);
    engine.use_book(false);
    return run_fresh_search(engine, child, network, budget, tb_cap);
}

void write_ladder_report(const std::string& path,
                         std::uint32_t declared,
                         int shard,
                         int nshards,
                         int tb_cap,
                         std::size_t tt_mb,
                         const std::vector<std::uint64_t>& budgets,
                         const std::string& groups_path,
                         const std::string& row_filter,
                         const LadderCounters& c) {
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot open Scan-ceiling Jass report");
    std::uint64_t max_depth_exhausted_total = 0;
    for (const auto rows : c.max_depth_exhausted_rows)
        max_depth_exhausted_total += rows;
    out << "{\n"
        << "  \"schema\": \"jass.scan_ceiling_jass_ladder.v1\",\n"
        << "  \"input_children\": " << declared << ",\n"
        << "  \"shard\": " << shard << ",\n"
        << "  \"nshards\": " << nshards << ",\n"
        << "  \"budgets_nodes\": [";
    for (std::size_t i = 0; i < budgets.size(); ++i)
        out << (i ? ", " : "") << budgets[i];
    out << "],\n"
        << "  \"groups\": \"" << groups_path << "\",\n"
        << "  \"row_filter\": \"" << row_filter << "\",\n"
        << "  \"book_enabled\": false,\n"
        << "  \"threads_per_search\": 1,\n"
        << "  \"fresh_engine_tt_search_state_each_sibling_budget\": true,\n"
        << "  \"score_pov\": \"parent\",\n"
        << "  \"child_to_parent_sign_validated\": true,\n"
        << "  \"node_limit_mode\": \"exact\",\n"
        << "  \"requested_node_caps_exactly_configured\": true,\n"
        << "  \"node_stopped_rows_equal_requested\": true,\n"
        << "  \"max_depth_exhaustion_allowed\": true,\n"
        << "  \"max_ply\": " << jass::MAX_PLY << ",\n"
        << "  \"reported_nodes_equal_requested_for_all_searches\": "
        << (max_depth_exhausted_total == 0 ? "true" : "false") << ",\n"
        << "  \"exact_terminal_or_tb_nodes\": 0,\n"
        << "  \"tt_mb\": " << tt_mb << ",\n"
        << "  \"egdb_max_pieces\": " << tb_cap << ",\n"
        << "  \"source_rows\": " << c.source_rows << ",\n"
        << "  \"selected_rows\": " << c.selected_rows << ",\n"
        << "  \"processed_rows\": " << c.processed_rows << ",\n"
        << "  \"invalid_rows\": " << c.invalid_rows << ",\n"
        << "  \"by_budget\": {\n";
    for (std::size_t i = 0; i < budgets.size(); ++i) {
        out << "    \"" << budgets[i] << "\": {\"searches\": " << c.searches[i]
            << ", \"nodes\": " << c.nodes[i]
            << ", \"exact_budget_rows\": " << c.exact_budget_rows[i]
            << ", \"max_depth_exhausted_rows\": " << c.max_depth_exhausted_rows[i]
            << ", \"terminal_exact_rows\": " << c.terminal_exact_rows[i]
            << ", \"tb_exact_rows\": " << c.tb_exact_rows[i]
            << ", \"elapsed_us\": " << c.elapsed_us[i] << "}"
            << (i + 1 == budgets.size() ? "\n" : ",\n");
    }
    out << "  },\n"
        << "  \"labels_read\": 0,\n"
        << "  \"fits\": 0,\n"
        << "  \"refits\": 0,\n"
        << "  \"calibrations\": 0,\n"
        << "  \"strength_games\": 0,\n"
        << "  \"training_allowed\": false,\n"
        << "  \"tuning_allowed\": false,\n"
        << "  \"calibration_allowed\": false,\n"
        << "  \"model_selection_allowed\": false,\n"
        << "  \"runtime_scale_selection_allowed\": false,\n"
        << "  \"promotion_authorized\": false\n"
        << "}\n";
}

}  // namespace

int main(int argc, char** argv) {
    static_assert(std::endian::native == std::endian::little,
                  "JNNW tool requires a little-endian host");
    if (argc < 8 || argc > 13) {
        std::cerr << "usage: jass_scan_ceiling_jass_ladder <children.jnnw> "
                     "<groups.tsv> <scores.tsv> <report.json> <curriculum.pjtw> <egdb_dir> "
                     "<budgets_csv> [row_ids.txt|-] [shard=0] [nshards=1] "
                     "[tt_mb=16] [egdb_cache_mb=256]\n";
        return 2;
    }
    if (std::getenv("JASS_TB_MOVE_ORDER_POLICY") != nullptr ||
        std::getenv("JASS_DSSD_MOVE_ORDER_POLICY") != nullptr ||
        std::getenv("JASS_T3_F6_MODEL") != nullptr) {
        std::cerr << "error: runtime policy/model variables must be absent\n";
        return 2;
    }

    const std::string input_path = argv[1];
    const std::string groups_path = argv[2];
    const std::string score_path = argv[3];
    const std::string report_path = argv[4];
    const std::string curriculum_path = argv[5];
    const std::string egdb_dir = argv[6];
    const std::vector<std::uint64_t> budgets = parse_budgets(argv[7]);
    const std::string row_filter_path = argc >= 9 ? argv[8] : "-";
    const int shard = argc >= 10 ? std::stoi(argv[9]) : 0;
    const int nshards = argc >= 11 ? std::stoi(argv[10]) : 1;
    const std::size_t tt_mb = argc >= 12
        ? static_cast<std::size_t>(std::max(1, std::stoi(argv[11]))) : DEFAULT_TT_MB;
    const int egdb_cache_mb = argc >= 13 ? std::max(64, std::stoi(argv[12])) : 256;
    if (nshards <= 0 || shard < 0 || shard >= nshards) {
        std::cerr << "error: invalid shard/nshards\n";
        return 2;
    }
    const auto row_filter = load_row_filter(row_filter_path);
    const bool filter_all = row_filter_path == "-";

    std::string network_error;
    auto curriculum = load_eval_network(curriculum_path, &network_error);
    if (!curriculum) {
        std::cerr << "error: cannot load CURRICULUM: " << network_error << '\n';
        return 3;
    }
    if (!jass::egdb::init(egdb_dir, egdb_cache_mb) || !jass::egdb::available()) {
        std::cerr << "error: real EGDB unavailable at " << egdb_dir << '\n';
        return 3;
    }
    const int tb_cap = jass::egdb::max_pieces();
    if (tb_cap <= 0) return 3;

    std::ifstream in(input_path, std::ios::binary);
    if (!in) return 4;
    std::array<char, 8> header{};
    if (!in.read(header.data(), static_cast<std::streamsize>(header.size())) ||
        std::memcmp(header.data(), "JNNW", 4) != 0) return 4;
    const std::uint32_t declared = load_le<std::uint32_t>(header.data() + 4);
    const std::vector<ExactMeta> exact_meta = load_exact_meta(groups_path, declared);
    if (!filter_all) {
        for (const auto row : row_filter) {
            if (row >= declared) {
                std::cerr << "error: row filter outside child corpus\n";
                return 4;
            }
        }
    }

    std::ofstream out(score_path);
    if (!out) return 5;
    out << "row_index\tbudget_nodes\tparent_score\tchild_score\tnodes\tcompleted_depth\t"
           "effective_depth\taborted_iteration\tstop_reason\telapsed_us\t"
           "budget_status\tpv_enters_egdb\tterminal_exact\ttb_exact\t"
           "exact_parent_utility\n";

    LadderCounters counters{};
    counters.searches.assign(budgets.size(), 0);
    counters.nodes.assign(budgets.size(), 0);
    counters.exact_budget_rows.assign(budgets.size(), 0);
    counters.max_depth_exhausted_rows.assign(budgets.size(), 0);
    counters.terminal_exact_rows.assign(budgets.size(), 0);
    counters.tb_exact_rows.assign(budgets.size(), 0);
    counters.elapsed_us.assign(budgets.size(), 0);
    DiskRow row{};
    for (std::uint32_t idx = 0; idx < declared; ++idx) {
        if (!read_row(in, row)) return 4;
        ++counters.source_rows;
        if (!filter_all && !row_filter.count(idx)) continue;
        ++counters.selected_rows;
        if (static_cast<int>(idx % static_cast<std::uint32_t>(nshards)) != shard) continue;
        ++counters.processed_rows;
        if (!valid_row(row)) {
            ++counters.invalid_rows;
            continue;
        }
        if (row.score != 0 || row.wdl != 0) {
            std::cerr << "error: child target bytes are not zero at row " << idx << '\n';
            return 4;
        }
        const jass::Position child = position_from_row(row);
        for (std::size_t b = 0; b < budgets.size(); ++b) {
            const ExactMeta& meta = exact_meta[idx];
            if (meta.terminal || meta.tb_exact) {
                if (meta.terminal) ++counters.terminal_exact_rows[b];
                else ++counters.tb_exact_rows[b];
                const int parent_score = exact_parent_score(meta);
                out << idx << '\t' << budgets[b] << '\t' << parent_score << '\t'
                    << -parent_score << "\t0\t0\t0\t0\t"
                    << (meta.terminal ? "terminal_exact" : "tb_exact")
                    << "\t0\t" << (meta.terminal ? "terminal_exact" : "tb_exact")
                    << "\t0\t" << (meta.terminal ? 1 : 0) << '\t'
                    << (meta.tb_exact ? 1 : 0) << '\t' << meta.parent_utility << '\n';
                continue;
            }
            const SearchObs obs = run_new_engine_search(
                child, curriculum.get(), budgets[b], tb_cap, tt_mb);
            ++counters.searches[b];
            counters.nodes[b] += obs.nodes;
            counters.elapsed_us[b] += obs.elapsed_us;
            const char* budget_status = nullptr;
            if (obs.nodes == budgets[b]
                    && obs.stop_reason == jass::SearchStopReason::Nodes
                    && obs.aborted_iteration) {
                ++counters.exact_budget_rows[b];
                budget_status = "requested_nodes_reached";
            } else if (obs.nodes > 0 && obs.nodes < budgets[b]
                    && obs.stop_reason == jass::SearchStopReason::None
                    && obs.completed_depth == jass::MAX_PLY
                    && obs.effective_depth == jass::MAX_PLY
                    && !obs.aborted_iteration) {
                ++counters.max_depth_exhausted_rows[b];
                budget_status = "max_depth_exhausted";
            } else {
                std::cerr << "error: exact Jass node budget mismatch at row " << idx
                          << ": " << obs.nodes << " != " << budgets[b] << '\n';
                return 4;
            }
            if (obs.parent_score != -obs.child_score) {
                std::cerr << "error: Jass child-to-parent POV sign drift at row " << idx << '\n';
                return 4;
            }
            out << idx << '\t' << budgets[b] << '\t' << obs.parent_score << '\t'
                << obs.child_score << '\t' << obs.nodes << '\t' << obs.completed_depth << '\t'
                << obs.effective_depth << '\t' << (obs.aborted_iteration ? 1 : 0) << '\t'
                << search_stop_reason_name(obs.stop_reason) << '\t' << obs.elapsed_us << '\t'
                << budget_status << '\t' << (obs.pv_enters_egdb ? 1 : 0)
                << "\t0\t0\t2\n";
        }
    }
    char trailing = 0;
    if (in.read(&trailing, 1)) return 4;
    out.close();
    for (std::size_t b = 0; b < budgets.size(); ++b) {
        if (counters.searches[b] + counters.terminal_exact_rows[b]
                + counters.tb_exact_rows[b] != counters.processed_rows) {
            std::cerr << "error: Jass ladder cardinality drift\n";
            return 4;
        }
    }
    write_ladder_report(report_path, declared, shard, nshards, tb_cap, tt_mb,
                        budgets, groups_path, row_filter_path, counters);
    return 0;
}

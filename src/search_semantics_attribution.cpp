// SPDX-License-Identifier: AGPL-3.0-or-later
// HOME-only exact-node scorer for the preregistered search-semantics arms.
// It exposes no training, tuning, strength-game, bake, or promotion path.

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
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iomanip>
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

constexpr std::array<const char*, 7> ARMS{
    "J0", "J1_SCAN_VERIFY", "J2_SCAN_THREAT_REENTRY",
    "J3_SCAN_SINGLE_REPLY", "J4_SCAN_LMR", "J5_SCAN_ORDERING",
    "J6_NO_NULL_MOVE",
};

struct ExactMeta {
    bool terminal{false};
    bool tb_exact{false};
    int parent_utility{2};
};

struct AttributionObs {
    jass::SearchResult result{};
    int parent_score{0};
    std::uint64_t elapsed_us{0};
    bool pv_enters_egdb{false};
};

struct Totals {
    std::uint64_t source_rows{0};
    std::uint64_t selected_rows{0};
    std::uint64_t processed_rows{0};
    std::uint64_t invalid_rows{0};
    std::uint64_t searches{0};
    std::uint64_t nodes{0};
    std::uint64_t exact_budget_rows{0};
    std::uint64_t max_depth_exhausted_rows{0};
    std::uint64_t terminal_exact_rows{0};
    std::uint64_t tb_exact_rows{0};
    std::uint64_t elapsed_us{0};
    std::uint64_t eval_calls{0};
    std::uint64_t qsearch_calls{0};
    std::uint64_t qnodes{0};
    std::uint64_t tt_probes{0};
    std::uint64_t tt_hits{0};
    std::uint64_t cutoffs{0};
    std::uint64_t first_move_cutoffs{0};
    std::uint64_t pvs_researches{0};
    std::uint64_t moves_searched{0};
    std::uint64_t reductions{0};
    std::uint64_t reduced_plies{0};
    std::uint64_t lmr_researches{0};
    std::uint64_t extensions{0};
    std::uint64_t singular_extensions{0};
    std::uint64_t promotion_extensions{0};
    std::uint64_t forcing_extensions{0};
    std::uint64_t single_reply_extensions{0};
    std::uint64_t null_probes{0};
    std::uint64_t null_cutoffs{0};
    std::uint64_t ordering_good_updates{0};
    std::uint64_t ordering_bad_updates{0};
    std::uint64_t scan_verify_probes{0};
    std::uint64_t scan_verify_cutoffs{0};
    std::uint64_t scan_threat_reentries{0};
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
        if (it == header.end())
            throw std::runtime_error("missing sibling group field: " + name);
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
        ? jass::MATE_SCORE : (jass::MATE_SCORE - jass::MAX_PLY - 1);
    return meta.parent_utility * magnitude;
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
    if (!in.eof() || rows.empty()) throw std::runtime_error("invalid/empty row filter");
    return rows;
}

jass::SearchParams params_for_arm(const std::string& arm) {
    if (std::find(ARMS.begin(), ARMS.end(), arm) == ARMS.end())
        throw std::runtime_error("arm outside preregistration");
    jass::SearchParams params{};
    if (arm == "J1_SCAN_VERIFY") {
        params.scan_verify_pruning = true;
    } else if (arm == "J2_SCAN_THREAT_REENTRY") {
        params.qs_threat_ext = false;
        params.scan_threat_reentry = true;
    } else if (arm == "J3_SCAN_SINGLE_REPLY") {
        params.ext_single_reply = true;
    } else if (arm == "J4_SCAN_LMR") {
        params.scan_lmr_semantics = true;
    } else if (arm == "J5_SCAN_ORDERING") {
        params.scan_probabilistic_ordering = true;
    } else if (arm == "J6_NO_NULL_MOVE") {
        params.disable_null_move = true;
    }
    return params;
}

AttributionObs run_search(const jass::Position& child,
                          const jass::INetwork* network,
                          std::uint64_t budget,
                          int tb_cap,
                          std::size_t tt_mb,
                          const jass::SearchParams& params) {
    jass::Engine engine(tt_mb);
    engine.use_book(false);
    engine.clear_tt();
    engine.set_position(child);
    jass::SearchLimits limits;
    limits.max_depth = jass::MAX_PLY;
    limits.max_nodes = budget;
    limits.node_limit_mode = jass::NodeLimitMode::Exact;
    limits.threads = 1;
    limits.nnue = network;
    limits.params = params;
    const auto t0 = std::chrono::steady_clock::now();
    const jass::SearchResult result = engine.search(limits);
    const auto t1 = std::chrono::steady_clock::now();
    if (result.from_book) throw std::runtime_error("attribution search used book");
    return {
        result,
        -result.score,
        static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::microseconds>(t1 - t0).count()),
        pv_enters_egdb(child, result, tb_cap),
    };
}

void add_totals(Totals& t, const AttributionObs& obs) {
    const auto& r = obs.result;
    ++t.searches;
    t.nodes += r.nodes;
    t.elapsed_us += obs.elapsed_us;
    t.eval_calls += r.eval_calls;
    t.qsearch_calls += r.qsearch_calls;
    t.qnodes += r.qnodes;
    t.tt_probes += r.tt_probes;
    t.tt_hits += r.tt_hits;
    t.cutoffs += r.cutoffs;
    t.first_move_cutoffs += r.first_move_cutoffs;
    t.pvs_researches += r.pvs_researches;
    t.moves_searched += r.moves_searched;
    t.reductions += r.reductions;
    t.reduced_plies += r.reduced_plies;
    t.lmr_researches += r.lmr_researches;
    t.extensions += r.extensions;
    t.singular_extensions += r.singular_extensions;
    t.promotion_extensions += r.promotion_extensions;
    t.forcing_extensions += r.forcing_extensions;
    t.single_reply_extensions += r.single_reply_extensions;
    t.null_probes += r.null_probes;
    t.null_cutoffs += r.null_cutoffs;
    t.ordering_good_updates += r.ordering_good_updates;
    t.ordering_bad_updates += r.ordering_bad_updates;
    t.scan_verify_probes += r.scan_verify_probes;
    t.scan_verify_cutoffs += r.scan_verify_cutoffs;
    t.scan_threat_reentries += r.scan_threat_reentries;
}

void json_counter(std::ostream& out, const char* key, std::uint64_t value,
                  bool comma = true) {
    out << "  \"" << key << "\": " << value << (comma ? ",\n" : "\n");
}

void write_report(const std::string& path, const std::string& arm,
                  std::uint64_t budget, int shard, int nshards,
                  int tb_cap, std::size_t tt_mb, const Totals& t) {
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot write attribution report");
    out << "{\n"
        << "  \"schema\": \"jass.search_semantics_attribution_score.v1\",\n"
        << "  \"arm\": \"" << arm << "\",\n"
        << "  \"budget_nodes\": " << budget << ",\n"
        << "  \"shard\": " << shard << ",\n"
        << "  \"nshards\": " << nshards << ",\n"
        << "  \"book_enabled\": false,\n"
        << "  \"threads_per_search\": 1,\n"
        << "  \"fresh_engine_tt_search_state_each_sibling_budget\": true,\n"
        << "  \"node_limit_mode\": \"exact\",\n"
        << "  \"score_pov\": \"parent\",\n"
        << "  \"tt_mb\": " << tt_mb << ",\n"
        << "  \"egdb_max_pieces\": " << tb_cap << ",\n";
    json_counter(out, "source_rows", t.source_rows);
    json_counter(out, "selected_rows", t.selected_rows);
    json_counter(out, "processed_rows", t.processed_rows);
    json_counter(out, "invalid_rows", t.invalid_rows);
    json_counter(out, "searches", t.searches);
    json_counter(out, "nodes", t.nodes);
    json_counter(out, "exact_budget_rows", t.exact_budget_rows);
    json_counter(out, "max_depth_exhausted_rows", t.max_depth_exhausted_rows);
    json_counter(out, "terminal_exact_rows", t.terminal_exact_rows);
    json_counter(out, "tb_exact_rows", t.tb_exact_rows);
    json_counter(out, "elapsed_us", t.elapsed_us);
    json_counter(out, "eval_calls", t.eval_calls);
    json_counter(out, "qsearch_calls", t.qsearch_calls);
    json_counter(out, "qnodes", t.qnodes);
    json_counter(out, "tt_probes", t.tt_probes);
    json_counter(out, "tt_hits", t.tt_hits);
    json_counter(out, "cutoffs", t.cutoffs);
    json_counter(out, "first_move_cutoffs", t.first_move_cutoffs);
    json_counter(out, "pvs_researches", t.pvs_researches);
    json_counter(out, "moves_searched", t.moves_searched);
    json_counter(out, "reductions", t.reductions);
    json_counter(out, "reduced_plies", t.reduced_plies);
    json_counter(out, "lmr_researches", t.lmr_researches);
    json_counter(out, "extensions", t.extensions);
    json_counter(out, "singular_extensions", t.singular_extensions);
    json_counter(out, "promotion_extensions", t.promotion_extensions);
    json_counter(out, "forcing_extensions", t.forcing_extensions);
    json_counter(out, "single_reply_extensions", t.single_reply_extensions);
    json_counter(out, "null_probes", t.null_probes);
    json_counter(out, "null_cutoffs", t.null_cutoffs);
    json_counter(out, "ordering_good_updates", t.ordering_good_updates);
    json_counter(out, "ordering_bad_updates", t.ordering_bad_updates);
    json_counter(out, "scan_verify_probes", t.scan_verify_probes);
    json_counter(out, "scan_verify_cutoffs", t.scan_verify_cutoffs);
    json_counter(out, "scan_threat_reentries", t.scan_threat_reentries);
    out << "  \"labels_read\": 0,\n"
        << "  \"fits\": 0,\n"
        << "  \"strength_games\": 0,\n"
        << "  \"training_allowed\": false,\n"
        << "  \"tuning_allowed\": false,\n"
        << "  \"bake\": false,\n"
        << "  \"promotion\": false\n"
        << "}\n";
}

}  // namespace

int main(int argc, char** argv) {
    static_assert(std::endian::native == std::endian::little);
    if (argc < 9 || argc > 14) {
        std::cerr << "usage: jass_search_semantics_attribution <children.jnnw> "
                     "<groups.tsv> <scores.tsv> <report.json> <curriculum.pjtw> "
                     "<egdb_dir> <arm> <budget> [row_ids.txt|-] [shard=0] "
                     "[nshards=1] [tt_mb=16] [egdb_cache_mb=256]\n";
        return 2;
    }
    if (std::getenv("JASS_TB_MOVE_ORDER_POLICY") != nullptr
        || std::getenv("JASS_DSSD_MOVE_ORDER_POLICY") != nullptr
        || std::getenv("JASS_T3_F6_MODEL") != nullptr
        || std::getenv("JASS_SEARCH_PARAMS") != nullptr) {
        std::cerr << "error: forbidden runtime policy/model/search override\n";
        return 2;
    }
    const std::string input_path = argv[1];
    const std::string groups_path = argv[2];
    const std::string score_path = argv[3];
    const std::string report_path = argv[4];
    const std::string curriculum_path = argv[5];
    const std::string egdb_dir = argv[6];
    const std::string arm = argv[7];
    const std::uint64_t budget = std::stoull(argv[8]);
    const std::string row_filter_path = argc >= 10 ? argv[9] : "-";
    const int shard = argc >= 11 ? std::stoi(argv[10]) : 0;
    const int nshards = argc >= 12 ? std::stoi(argv[11]) : 1;
    const std::size_t tt_mb = argc >= 13
        ? static_cast<std::size_t>(std::max(1, std::stoi(argv[12]))) : DEFAULT_TT_MB;
    const int egdb_cache_mb = argc >= 14 ? std::max(64, std::stoi(argv[13])) : 256;
    if ((budget != 200'000 && budget != 1'000'000)
        || (budget == 1'000'000 && arm != "J0")
        || nshards <= 0 || shard < 0 || shard >= nshards) {
        std::cerr << "error: arm/budget/shard outside preregistration\n";
        return 2;
    }
    const jass::SearchParams params = params_for_arm(arm);
    const auto row_filter = load_row_filter(row_filter_path);
    const bool filter_all = row_filter_path == "-";

    std::string network_error;
    auto curriculum = load_eval_network(curriculum_path, &network_error);
    if (!curriculum) {
        std::cerr << "error: cannot load CURRICULUM: " << network_error << '\n';
        return 3;
    }
    if (!jass::egdb::init(egdb_dir, egdb_cache_mb) || !jass::egdb::available()) {
        std::cerr << "error: real EGDB unavailable\n";
        return 3;
    }
    const int tb_cap = jass::egdb::max_pieces();

    std::ifstream in(input_path, std::ios::binary);
    if (!in) return 4;
    std::array<char, 8> header{};
    if (!in.read(header.data(), static_cast<std::streamsize>(header.size()))
        || std::memcmp(header.data(), "JNNW", 4) != 0) return 4;
    const std::uint32_t declared = load_le<std::uint32_t>(header.data() + 4);
    const auto exact_meta = load_exact_meta(groups_path, declared);
    for (const auto row : row_filter) if (row >= declared) return 4;

    std::ofstream out(score_path);
    if (!out) return 5;
    out << "row_index\tarm\tbudget_nodes\tparent_score\tchild_score\tnodes\t"
           "completed_depth\teffective_depth\taborted_iteration\tstop_reason\t"
           "elapsed_us\tbudget_status\tpv_enters_egdb\tterminal_exact\ttb_exact\t"
           "exact_parent_utility\teval_calls\tqsearch_calls\tqnodes\ttt_probes\t"
           "tt_hits\tcutoffs\tfirst_move_cutoffs\tpvs_researches\tmoves_searched\t"
           "reductions\treduced_plies\tlmr_researches\textensions\tsingular_extensions\t"
           "promotion_extensions\tforcing_extensions\tsingle_reply_extensions\t"
           "null_probes\tnull_cutoffs\tordering_good_updates\tordering_bad_updates\t"
           "scan_verify_probes\tscan_verify_cutoffs\tscan_threat_reentries\n";

    Totals totals{};
    DiskRow row{};
    for (std::uint32_t idx = 0; idx < declared; ++idx) {
        if (!read_row(in, row)) return 4;
        ++totals.source_rows;
        if (!filter_all && !row_filter.count(idx)) continue;
        ++totals.selected_rows;
        if (static_cast<int>(idx % static_cast<std::uint32_t>(nshards)) != shard) continue;
        ++totals.processed_rows;
        if (!valid_row(row) || row.score != 0 || row.wdl != 0) {
            ++totals.invalid_rows;
            continue;
        }
        const ExactMeta& meta = exact_meta[idx];
        if (meta.terminal || meta.tb_exact) {
            if (meta.terminal) ++totals.terminal_exact_rows;
            else ++totals.tb_exact_rows;
            const int parent = exact_parent_score(meta);
            out << idx << '\t' << arm << '\t' << budget << '\t' << parent << '\t'
                << -parent << "\t0\t0\t0\t0\t"
                << (meta.terminal ? "terminal_exact" : "tb_exact") << "\t0\t"
                << (meta.terminal ? "terminal_exact" : "tb_exact") << "\t0\t"
                << (meta.terminal ? 1 : 0) << '\t' << (meta.tb_exact ? 1 : 0)
                << '\t' << meta.parent_utility;
            for (int k = 0; k < 24; ++k) out << "\t0";
            out << '\n';
            continue;
        }
        const jass::Position child = position_from_row(row);
        const AttributionObs obs = run_search(
            child, curriculum.get(), budget, tb_cap, tt_mb, params);
        add_totals(totals, obs);
        const auto& r = obs.result;
        const char* budget_status = nullptr;
        if (r.nodes == budget && r.stop_reason == jass::SearchStopReason::Nodes
            && r.aborted_iteration) {
            ++totals.exact_budget_rows;
            budget_status = "requested_nodes_reached";
        } else if (r.nodes > 0 && r.nodes < budget
            && r.stop_reason == jass::SearchStopReason::None
            && r.completed_depth == jass::MAX_PLY
            && r.effective_depth == jass::MAX_PLY && !r.aborted_iteration) {
            ++totals.max_depth_exhausted_rows;
            budget_status = "max_depth_exhausted";
        } else {
            std::cerr << "error: exact node budget mismatch at row " << idx << '\n';
            return 4;
        }
        out << idx << '\t' << arm << '\t' << budget << '\t' << obs.parent_score
            << '\t' << r.score << '\t' << r.nodes << '\t' << r.completed_depth
            << '\t' << r.effective_depth << '\t' << (r.aborted_iteration ? 1 : 0)
            << '\t' << jass::search_stop_reason_name(r.stop_reason) << '\t'
            << obs.elapsed_us << '\t' << budget_status << '\t'
            << (obs.pv_enters_egdb ? 1 : 0) << "\t0\t0\t2\t"
            << r.eval_calls << '\t' << r.qsearch_calls << '\t' << r.qnodes << '\t'
            << r.tt_probes << '\t' << r.tt_hits << '\t' << r.cutoffs << '\t'
            << r.first_move_cutoffs << '\t' << r.pvs_researches << '\t'
            << r.moves_searched << '\t' << r.reductions << '\t' << r.reduced_plies
            << '\t' << r.lmr_researches << '\t' << r.extensions << '\t'
            << r.singular_extensions << '\t' << r.promotion_extensions << '\t'
            << r.forcing_extensions << '\t' << r.single_reply_extensions << '\t'
            << r.null_probes << '\t' << r.null_cutoffs << '\t'
            << r.ordering_good_updates << '\t' << r.ordering_bad_updates << '\t'
            << r.scan_verify_probes << '\t' << r.scan_verify_cutoffs << '\t'
            << r.scan_threat_reentries << '\n';
    }
    if (in.read(reinterpret_cast<char*>(&row), 1)) return 4;
    if (totals.searches + totals.terminal_exact_rows + totals.tb_exact_rows
        != totals.processed_rows || totals.invalid_rows != 0) return 4;
    write_report(report_path, arm, budget, shard, nshards, tb_cap, tt_mb, totals);
    return 0;
}


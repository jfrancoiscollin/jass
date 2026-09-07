// SPDX-License-Identifier: AGPL-3.0-or-later
// Diagnostic-only D4 beta-cutoff search-utility exporter.
// This target exists only in an isolated rendered source tree.

#include "scan_eval.hpp"
#include "search.hpp"
#include "t3_f6.hpp"
#include "tt.hpp"

#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>

namespace {

struct RootRow {
    int index{0};
    std::string split;
    std::string canonical_identity;
    std::string fen;
    std::string selection_digest;
    jass::Position position;
};

std::string json_string(const std::string& value) {
    std::ostringstream out;
    out << '"';
    for (const unsigned char c : value) {
        switch (c) {
            case '"': out << "\\\""; break;
            case '\\': out << "\\\\"; break;
            case '\b': out << "\\b"; break;
            case '\f': out << "\\f"; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default:
                if (c < 0x20U) {
                    constexpr char HEX[] = "0123456789abcdef";
                    out << "\\u00" << HEX[c >> 4U] << HEX[c & 0x0FU];
                } else {
                    out << static_cast<char>(c);
                }
        }
    }
    out << '"';
    return out.str();
}

std::vector<std::string> split_tabs(const std::string& line) {
    std::vector<std::string> fields;
    std::stringstream stream(line);
    std::string field;
    while (std::getline(stream, field, '\t')) fields.push_back(field);
    if (!line.empty() && line.back() == '\t') fields.emplace_back();
    return fields;
}

int parse_int(const std::string& text, const char* label) {
    if (text.empty() || !std::all_of(text.begin(), text.end(), [](unsigned char c) {
            return c >= static_cast<unsigned char>('0')
                && c <= static_cast<unsigned char>('9');
        })) {
        throw std::runtime_error(std::string("invalid ") + label);
    }
    std::size_t used = 0;
    const int value = std::stoi(text, &used, 10);
    if (used != text.size()) throw std::runtime_error(std::string("invalid ") + label);
    return value;
}

std::vector<RootRow> load_roots(const std::string& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open D4 root manifest");
    std::string line;
    if (!std::getline(input, line)) throw std::runtime_error("empty D4 root manifest");
    if (!line.empty() && line.back() == '\r') line.pop_back();
    if (line != "root_index\tsplit\tcanonical_identity\tfen\tselection_digest")
        throw std::runtime_error("D4 root manifest header drift");

    std::vector<RootRow> rows;
    std::unordered_set<int> seen;
    while (std::getline(input, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty()) throw std::runtime_error("blank D4 root manifest row");
        const auto f = split_tabs(line);
        if (f.size() != 5U) throw std::runtime_error("D4 root manifest row width drift");
        const int index = parse_int(f[0], "root_index");
        if (!seen.insert(index).second) throw std::runtime_error("duplicate root_index");
        if (f[1] != "train" && f[1] != "valid" && f[1] != "test")
            throw std::runtime_error("bad root split");
        auto pos = jass::Position::from_fen(f[3]);
        if (!pos) throw std::runtime_error("invalid root FEN");
        rows.push_back(RootRow{index, f[1], f[2], f[3], f[4], *pos});
    }
    if (rows.empty()) throw std::runtime_error("root manifest shard is empty");
    return rows;
}

std::string sha_file(const std::string& path) {
    std::string error;
    const std::string digest = jass::t3_f6::sha256_file(path, &error);
    if (digest.size() != 64U)
        throw std::runtime_error("cannot hash file " + path + ": " + error);
    return digest;
}

void emit_move(std::ostream& out, const jass::Move& move) {
    out << "{\"from\":" << static_cast<int>(move.from)
        << ",\"to\":" << static_cast<int>(move.to)
        << ",\"num_captures\":" << static_cast<int>(move.num_captures)
        << ",\"promotes\":" << (move.promotes ? "true" : "false")
        << ",\"captured\":" << move.captured << '}';
}

void emit_features(std::ostream& out, const std::array<double, 24>& features) {
    out << '[' << std::setprecision(17);
    for (std::size_t i = 0; i < features.size(); ++i) {
        if (i != 0U) out << ',';
        out << features[i];
    }
    out << ']';
}

void reject_hidden_runtime_context() {
    constexpr const char* VARS[] = {
        "JASS_D3_RUNTIME_ADAPTER", "JASS_D3_RUNTIME_BASE_MODEL",
        "JASS_DENSE_REMAP", "JASS_DSSD_MOVE_ORDER_POLICY",
        "JASS_EGDB_CACHE_MB", "JASS_EGDB_MTC_PATH", "JASS_EGDB_PATH",
        "JASS_NO_SCAN_ACC", "JASS_SEARCH_PARAMS", "JASS_T3_F6_MODEL",
        "JASS_TB_MOVE_ORDER_POLICY", "JASS_TRACE_ROOT"
    };
    for (const char* var : VARS) {
        if (std::getenv(var) != nullptr)
            throw std::runtime_error(std::string("runtime variable must be absent: ") + var);
    }
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 7) {
        std::cerr
            << "usage: d4_search_utility_trace_export <roots.tsv> <events.jsonl> "
               "<report.json> <WDL_CONTROL.pjtw> <declared_code_sha> <expected_model_sha256>\n";
        return 2;
    }

    try {
        reject_hidden_runtime_context();
        const std::string roots_path = argv[1];
        const std::string events_path = argv[2];
        const std::string report_path = argv[3];
        const std::string model_path = argv[4];
        const std::string code_sha = argv[5];
        const std::string expected_model_sha = argv[6];
        if (code_sha.size() != 40U || expected_model_sha.size() != 64U)
            throw std::runtime_error("declared provenance width drift");

        const std::string actual_model_sha = sha_file(model_path);
        if (actual_model_sha != expected_model_sha)
            throw std::runtime_error("WDL_CONTROL sha256 mismatch");

        std::string load_error;
        std::unique_ptr<jass::INetwork> network = jass::load_eval_network(model_path, &load_error);
        if (!network) throw std::runtime_error("cannot load WDL_CONTROL: " + load_error);

        const auto roots = load_roots(roots_path);
        std::ofstream out(events_path);
        if (!out) throw std::runtime_error("cannot open D4 event output");

        std::uint64_t total_nodes = 0;
        std::uint64_t total_eval_calls = 0;
        std::uint64_t total_events = 0;
        std::uint64_t exact_node_mismatches = 0;
        int train_roots = 0, valid_roots = 0, test_roots = 0;

        for (const RootRow& root : roots) {
            if (root.split == "train") ++train_roots;
            else if (root.split == "valid") ++valid_roots;
            else ++test_roots;

            jass::TranspositionTable tt;
            tt.resize_mb(16);
            jass::SearchUtilityTrace trace;
            jass::SearchLimits limits;
            limits.max_depth = jass::MAX_PLY;
            limits.max_nodes = 50'000;
            limits.node_limit_mode = jass::NodeLimitMode::Exact;
            limits.movetime_ms = 0;
            limits.threads = 1;
            limits.nnue = network.get();
            limits.search_utility_trace = &trace;

            const jass::SearchResult result = jass::search(root.position, limits, tt, {});
            total_nodes += result.nodes;
            total_eval_calls += result.eval_calls;
            if (result.nodes > 50'000U) ++exact_node_mismatches;

            std::uint64_t event_index = 0;
            for (const auto& event : trace.cutoffs) {
                if (event.label_index < 0
                    || event.label_index >= static_cast<int>(event.candidates.size())
                    || event.candidates.size() < 2U || event.candidates.size() > 4U) {
                    throw std::runtime_error("rendered D4 trace contract drift");
                }
                out << "{\"schema\":\"jass.d4.search_utility_teacher_event.v1\""
                    << ",\"root_index\":" << root.index
                    << ",\"root_split\":" << json_string(root.split)
                    << ",\"root_canonical_identity\":" << json_string(root.canonical_identity)
                    << ",\"event_index\":" << event_index++
                    << ",\"parent_fen\":" << json_string(event.parent.to_fen())
                    << ",\"search_ply\":" << event.search_ply
                    << ",\"remaining_depth\":" << event.remaining_depth
                    << ",\"alpha\":" << event.alpha
                    << ",\"beta\":" << event.beta
                    << ",\"parent_piece_count\":" << event.parent_piece_count
                    << ",\"legal_move_count\":" << event.legal_move_count
                    << ",\"tt_move_valid\":" << (event.tt_move_valid ? "true" : "false")
                    << ",\"tt_move\":";
                emit_move(out, event.tt_move);
                out << ",\"cutoff_move\":";
                emit_move(out, event.cutoff_move);
                out << ",\"label_index\":" << event.label_index
                    << ",\"candidates\":[";
                for (std::size_t i = 0; i < event.candidates.size(); ++i) {
                    if (i != 0U) out << ',';
                    const auto& candidate = event.candidates[i];
                    out << "{\"legacy_rank\":" << candidate.legacy_rank << ",\"move\":";
                    emit_move(out, candidate.move);
                    out << ",\"features\":";
                    emit_features(out, candidate.features);
                    out << '}';
                }
                out << "]}\n";
                ++total_events;
            }
        }
        out.close();
        if (!out) throw std::runtime_error("cannot finalize D4 event output");

        const std::string roots_sha = sha_file(roots_path);
        const std::string events_sha = sha_file(events_path);
        std::ofstream report(report_path);
        if (!report) throw std::runtime_error("cannot open D4 exporter report");
        report << "{\n"
               << "  \"schema\": \"jass.d4.search_utility_teacher_export.v1\",\n"
               << "  \"diagnostic_only\": true,\n"
               << "  \"declared_code_sha\": " << json_string(code_sha) << ",\n"
               << "  \"model_sha256\": " << json_string(actual_model_sha) << ",\n"
               << "  \"roots_manifest_sha256\": " << json_string(roots_sha) << ",\n"
               << "  \"events_sha256\": " << json_string(events_sha) << ",\n"
               << "  \"roots\": " << roots.size() << ",\n"
               << "  \"root_splits\": {\"train\": " << train_roots
               << ", \"valid\": " << valid_roots << ", \"test\": " << test_roots << "},\n"
               << "  \"teacher_searches\": " << roots.size() << ",\n"
               << "  \"exact_nodes_per_root\": 50000,\n"
               << "  \"node_overshoot_mismatches\": " << exact_node_mismatches << ",\n"
               << "  \"total_nodes\": " << total_nodes << ",\n"
               << "  \"total_eval_calls\": " << total_eval_calls << ",\n"
               << "  \"eligible_cutoff_events\": " << total_events << ",\n"
               << "  \"threads\": 1,\n"
               << "  \"book\": false,\n"
               << "  \"fits\": 0,\n"
               << "  \"strength_games\": 0,\n"
               << "  \"promotions\": 0,\n"
               << "  \"bakes\": 0,\n"
               << "  \"game_outcome_reads\": 0,\n"
               << "  \"qscore_reads\": 0,\n"
               << "  \"search_decision_trace_reads\": 0,\n"
               << "  \"full_ladder_1843_reads\": 0,\n"
               << "  \"d3_score_reads\": 0\n"
               << "}\n";
        report.close();
        std::cout << "D4_SEARCH_UTILITY_TEACHER_EXPORT_COMPLETE roots=" << roots.size()
                  << " events=" << total_events << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "error: " << error.what() << '\n';
        return 3;
    }
}

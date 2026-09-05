// SPDX-License-Identifier: AGPL-3.0-or-later
// Native-only, diagnostic SearchDecisionTrace v1 exporter.

#include "scan_eval.hpp"
#include "search.hpp"
#include "t3_f6.hpp"
#include "tt.hpp"

#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

namespace {

struct Invocation {
    std::string id;
    jass::Position position;
    std::vector<jass::ZobristHash> history;
};

struct EvaluationIdentity {
    std::string kind;
    std::string path;
    std::string sha256;
    bool sidecar_present{false};
    std::string sidecar_path;
    std::string sidecar_sha256;
};

std::string json_string(const std::string& value) {
    std::ostringstream out;
    out << '"';
    for (const char raw_byte : value) {
        const auto byte = static_cast<unsigned char>(raw_byte);
        switch (byte) {
            case '"': out << "\\\""; break;
            case '\\': out << "\\\\"; break;
            case '\b': out << "\\b"; break;
            case '\f': out << "\\f"; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default:
                if (byte < 0x20U) {
                    constexpr char HEX[] = "0123456789abcdef";
                    out << "\\u00" << HEX[byte >> 4U] << HEX[byte & 0x0FU];
                } else {
                    out << static_cast<char>(byte);
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

int parse_int(const std::string& text, const char* field) {
    if (text.empty() || !std::all_of(text.begin(), text.end(), [](unsigned char c) {
            return c >= static_cast<unsigned char>('0')
                && c <= static_cast<unsigned char>('9');
        })) {
        throw std::runtime_error(std::string("invalid ") + field);
    }
    std::size_t used = 0;
    int value = 0;
    try {
        value = std::stoi(text, &used, 10);
    } catch (const std::exception&) {
        throw std::runtime_error(std::string("invalid ") + field);
    }
    if (used != text.size()) throw std::runtime_error(std::string("invalid ") + field);
    return value;
}

std::uint64_t parse_u64(const std::string& text, int base, const char* field) {
    const auto valid_digit = [base](unsigned char c) {
        if (c >= static_cast<unsigned char>('0') && c <= static_cast<unsigned char>('9'))
            return true;
        return base == 16
            && ((c >= static_cast<unsigned char>('a') && c <= static_cast<unsigned char>('f'))
                || (c >= static_cast<unsigned char>('A') && c <= static_cast<unsigned char>('F')));
    };
    if (text.empty() || (base == 16 && text.size() > 16U)
            || !std::all_of(text.begin(), text.end(), valid_digit)) {
        throw std::runtime_error(std::string("invalid ") + field);
    }
    std::size_t used = 0;
    unsigned long long value = 0;
    try {
        value = std::stoull(text, &used, base);
    } catch (const std::exception&) {
        throw std::runtime_error(std::string("invalid ") + field);
    }
    if (used != text.size()) throw std::runtime_error(std::string("invalid ") + field);
    return static_cast<std::uint64_t>(value);
}

std::vector<jass::ZobristHash> parse_history(const std::string& text) {
    std::vector<jass::ZobristHash> history;
    if (text == "-") return history;
    if (text.empty() || text.back() == ',')
        throw std::runtime_error("invalid history field; use - for none");
    std::stringstream stream(text);
    std::string token;
    while (std::getline(stream, token, ',')) {
        if (token.empty()) throw std::runtime_error("empty history hash token");
        history.push_back(parse_u64(token, 16, "history hash"));
    }
    return history;
}

std::vector<Invocation> load_manifest(const std::string& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open invocation manifest");
    std::string line;
    if (!std::getline(input, line)) throw std::runtime_error("empty invocation manifest");
    if (!line.empty() && line.back() == '\r') line.pop_back();
    if (line != "invocation_id\tfen\thalfmove_clock\thistory_hashes_hex")
        throw std::runtime_error("invocation manifest header drift");

    std::vector<Invocation> rows;
    std::unordered_set<std::string> ids;
    std::size_t line_number = 1;
    while (std::getline(input, line)) {
        ++line_number;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty()) throw std::runtime_error("blank invocation manifest row");
        const std::vector<std::string> fields = split_tabs(line);
        if (fields.size() != 4) throw std::runtime_error("invocation manifest row width drift");
        const bool valid_id = !fields[0].empty()
            && std::all_of(fields[0].begin(), fields[0].end(), [](unsigned char c) {
                return (c >= static_cast<unsigned char>('a') && c <= static_cast<unsigned char>('z'))
                    || (c >= static_cast<unsigned char>('A') && c <= static_cast<unsigned char>('Z'))
                    || (c >= static_cast<unsigned char>('0') && c <= static_cast<unsigned char>('9'))
                    || c == static_cast<unsigned char>('.') || c == static_cast<unsigned char>('_')
                    || c == static_cast<unsigned char>(':') || c == static_cast<unsigned char>('-');
            });
        if (!valid_id || !ids.insert(fields[0]).second)
            throw std::runtime_error("invalid or duplicate invocation_id");
        auto position = jass::Position::from_fen(fields[1]);
        if (!position) throw std::runtime_error("invalid FEN at manifest line " + std::to_string(line_number));
        const int halfmove_clock = parse_int(fields[2], "halfmove_clock");
        if (halfmove_clock < 0
            || halfmove_clock > std::numeric_limits<int>::max() - jass::MAX_PLY)
            throw std::runtime_error("halfmove_clock outside search-safe range");
        position->set_halfmove_clock(halfmove_clock);
        rows.push_back(Invocation{fields[0], *position, parse_history(fields[3])});
    }
    if (rows.empty()) throw std::runtime_error("invocation manifest has no rows");
    return rows;
}

std::string checked_sha256(const std::string& path, const char* label) {
    std::string error;
    const std::string digest = jass::t3_f6::sha256_file(path, &error);
    if (digest.size() != 64U) {
        throw std::runtime_error(std::string("cannot hash ") + label + ": " + error);
    }
    return digest;
}

std::filesystem::path resolved_path(const std::string& path) {
    std::error_code error;
    const std::filesystem::path resolved = std::filesystem::weakly_canonical(
        std::filesystem::absolute(std::filesystem::path(path), error), error);
    if (error) throw std::runtime_error("cannot resolve path: " + path);
    return resolved;
}

bool aliases(const std::filesystem::path& first,
             const std::filesystem::path& second) {
    if (first == second) return true;
    std::error_code error;
    if (std::filesystem::exists(first, error) && !error
            && std::filesystem::exists(second, error) && !error) {
        const bool equivalent = std::filesystem::equivalent(first, second, error);
        if (error) throw std::runtime_error("cannot compare path identities");
        return equivalent;
    }
    return false;
}

void reject_output_aliases(
    const std::filesystem::path& output,
    const std::filesystem::path& report,
    const std::vector<std::filesystem::path>& protected_inputs) {
    if (aliases(output, report))
        throw std::runtime_error("trace/report output paths alias");
    for (const auto& input : protected_inputs) {
        if (aliases(output, input) || aliases(report, input))
            throw std::runtime_error("output path aliases an input artifact");
    }
}

void reject_hidden_runtime_context() {
    constexpr const char* VARIABLES[] = {
        "JASS_DENSE_REMAP", "JASS_DSSD_MOVE_ORDER_POLICY", "JASS_EGDB_CACHE_MB",
        "JASS_EGDB_MTC_PATH", "JASS_EGDB_PATH", "JASS_NO_SCAN_ACC",
        "JASS_SEARCH_PARAMS", "JASS_T3_F6_MODEL", "JASS_TB_MOVE_ORDER_POLICY",
        "JASS_TRACE_ROOT",
    };
    for (const char* variable : VARIABLES) {
        if (std::getenv(variable) != nullptr)
            throw std::runtime_error(std::string("runtime variable must be absent: ") + variable);
    }
}

std::string evaluation_json(const EvaluationIdentity& evaluation) {
    std::ostringstream out;
    out << "{\"kind\":" << json_string(evaluation.kind)
        << ",\"artifact_path\":";
    if (evaluation.path.empty()) out << "null";
    else out << json_string(evaluation.path);
    out << ",\"artifact_sha256\":";
    if (evaluation.sha256.empty()) out << "null";
    else out << json_string(evaluation.sha256);
    out << ",\"artifact_sha256_verified\":"
        << (evaluation.sha256.empty() ? "false" : "true")
        << ",\"conversion_sidecar_present\":"
        << (evaluation.sidecar_present ? "true" : "false")
        << ",\"conversion_sidecar_path\":";
    if (evaluation.sidecar_present) out << json_string(evaluation.sidecar_path);
    else out << "null";
    out << ",\"conversion_sidecar_sha256\":";
    if (evaluation.sidecar_present) out << json_string(evaluation.sidecar_sha256);
    else out << "null";
    out << '}';
    return out.str();
}

std::string context_json(const EvaluationIdentity& evaluation,
                         const std::string& declared_code,
                         const std::string& executable_path,
                         const std::string& executable_sha256,
                         int max_depth,
                         std::uint64_t max_nodes,
                         std::size_t tt_mb) {
    std::ostringstream out;
    out << "{\"evaluation\":" << evaluation_json(evaluation)
        << ",\"code_provenance\":{\"declared\":" << json_string(declared_code)
        << ",\"declared_verified_by_exporter\":false"
        << ",\"executable_path\":" << json_string(executable_path)
        << ",\"executable_sha256\":" << json_string(executable_sha256)
        << ",\"executable_sha256_verified\":true}"
        << ",\"search_params_source\":\"compiled_defaults\""
        << ",\"max_depth\":" << max_depth
        << ",\"max_nodes\":" << max_nodes
        << ",\"node_limit_mode\":\"" << (max_nodes == 0 ? "periodic" : "exact") << '"'
        << ",\"movetime_ms\":0,\"threads\":1,\"book_enabled\":false"
        << ",\"tt_mb\":" << tt_mb
        << ",\"fresh_tt_per_invocation\":true}"
        ;
    return out.str();
}

std::string history_json(const std::vector<jass::ZobristHash>& history) {
    std::ostringstream out;
    out << '[';
    for (std::size_t i = 0; i < history.size(); ++i) {
        if (i != 0) out << ',';
        out << history[i];
    }
    out << ']';
    return out.str();
}

void write_report(const std::string& path,
                  const std::string& manifest_path,
                  const std::string& manifest_sha256,
                  const std::string& output_path,
                  const std::string& output_sha256,
                  std::size_t rows,
                  const std::string& context) {
    std::ofstream out(path);
    if (!out) throw std::runtime_error("cannot open export report");
    out << "{\n"
        << "  \"schema\": \"jass.search-decision-trace-export.v1\",\n"
        << "  \"version\": 1,\n"
        << "  \"diagnostic_only\": true,\n"
        << "  \"input_manifest_path\": " << json_string(manifest_path) << ",\n"
        << "  \"input_manifest_sha256\": " << json_string(manifest_sha256) << ",\n"
        << "  \"input_manifest_sha256_verified\": true,\n"
        << "  \"output_jsonl_path\": " << json_string(output_path) << ",\n"
        << "  \"output_jsonl_sha256\": " << json_string(output_sha256) << ",\n"
        << "  \"output_jsonl_sha256_verified\": true,\n"
        << "  \"input_invocations\": " << rows << ",\n"
        << "  \"emitted_invocations\": " << rows << ",\n"
        << "  \"search_context_identity\": " << context << ",\n"
        << "  \"fits\": 0,\n"
        << "  \"strength_games\": 0,\n"
        << "  \"bakes\": 0,\n"
        << "  \"promotions\": 0,\n"
        << "  \"training_allowed\": false,\n"
        << "  \"tuning_allowed\": false,\n"
        << "  \"model_selection_allowed\": false,\n"
        << "  \"promotion_authorized\": false\n"
        << "}\n";
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 7 || argc > 9) {
        std::cerr
            << "usage: jass_search_decision_trace_export <invocations.tsv> "
               "<traces.jsonl> <report.json> <model.pjtw|-> "
               "<declared_code_provenance> <max_depth> [max_nodes=0] [tt_mb=16]\n";
        return 2;
    }
    try {
        reject_hidden_runtime_context();
        const std::filesystem::path manifest = resolved_path(argv[1]);
        const std::filesystem::path output_file = resolved_path(argv[2]);
        const std::filesystem::path report_file = resolved_path(argv[3]);
        const std::string manifest_path = manifest.string();
        const std::string output_path = output_file.string();
        const std::string report_path = report_file.string();
        const std::string requested_model_path = argv[4];
        const std::string declared_code = argv[5];
        const int max_depth = parse_int(argv[6], "max_depth");
        const std::uint64_t max_nodes = argc >= 8
            ? parse_u64(argv[7], 10, "max_nodes") : 0;
        const std::uint64_t parsed_tt_mb = argc >= 9
            ? parse_u64(argv[8], 10, "tt_mb") : 16;
        if (max_depth < 1 || max_depth > jass::MAX_PLY)
            throw std::runtime_error("max_depth outside 1..MAX_PLY");
        if (parsed_tt_mb < 1 || parsed_tt_mb > 1'048'576)
            throw std::runtime_error("tt_mb outside supported range");
        if (declared_code.empty()) throw std::runtime_error("empty declared code provenance");
        const std::size_t tt_mb = static_cast<std::size_t>(parsed_tt_mb);
        const std::vector<Invocation> invocations = load_manifest(manifest_path);

        EvaluationIdentity evaluation;
        std::unique_ptr<jass::INetwork> network;
        std::vector<std::filesystem::path> protected_inputs{manifest};
        if (requested_model_path == "-") {
            evaluation.kind = "handcrafted";
        } else {
            const std::filesystem::path model = resolved_path(requested_model_path);
            const std::string model_path = model.string();
            protected_inputs.push_back(model);
            evaluation.kind = "file";
            evaluation.path = model_path;
            evaluation.sha256 = checked_sha256(model_path, "evaluation artifact");
            const std::string sidecar = model_path + ".cvh";
            const std::filesystem::path resolved_sidecar = resolved_path(sidecar);
            // Reserve the conventional sidecar path even when it does not yet
            // exist. Otherwise an output could occupy that path and silently
            // become evaluator input on a later invocation.
            protected_inputs.push_back(resolved_sidecar);
            if (std::filesystem::exists(sidecar)) {
                evaluation.sidecar_present = true;
                evaluation.sidecar_path = resolved_sidecar.string();
                evaluation.sidecar_sha256 = checked_sha256(
                    evaluation.sidecar_path, "conversion sidecar");
            }
            std::string error;
            network = jass::load_eval_network(model_path, &error);
            if (!network) throw std::runtime_error("cannot load evaluation artifact: " + error);
        }

        const std::string executable_path = resolved_path(argv[0]).string();
        protected_inputs.push_back(std::filesystem::path(executable_path));
        reject_output_aliases(output_file, report_file, protected_inputs);
        const std::string executable_sha256 = checked_sha256(executable_path, "exporter executable");
        const std::string manifest_sha256 = checked_sha256(manifest_path, "invocation manifest");
        const std::string context = context_json(
            evaluation, declared_code, executable_path, executable_sha256,
            max_depth, max_nodes, tt_mb);

        std::ofstream output(output_path);
        if (!output) throw std::runtime_error("cannot open trace JSONL output");
        for (const Invocation& invocation : invocations) {
            jass::TranspositionTable tt;
            tt.resize_mb(tt_mb);
            jass::SearchDecisionTrace trace;
            jass::SearchLimits limits;
            limits.max_depth = max_depth;
            limits.max_nodes = max_nodes;
            limits.node_limit_mode = max_nodes == 0
                ? jass::NodeLimitMode::Periodic : jass::NodeLimitMode::Exact;
            limits.movetime_ms = 0;
            limits.threads = 1;
            limits.nnue = network.get();
            limits.search_decision_trace = &trace;
            (void)jass::search(invocation.position, limits, tt, invocation.history);
            output << "{\"schema\":\"jass.search-decision-trace-export-row.v1\""
                   << ",\"version\":1,\"invocation_id\":" << json_string(invocation.id)
                   << ",\"board_identity\":{\"canonical_fen\":"
                   << json_string(invocation.position.to_fen())
                   << ",\"zobrist_hash\":" << invocation.position.hash() << '}'
                   << ",\"rule_state_identity\":{\"halfmove_clock\":"
                   << invocation.position.halfmove_clock()
                   << ",\"history_hashes\":" << history_json(invocation.history) << '}'
                   << ",\"search_context_identity\":" << context
                   << ",\"trace\":" << jass::serialize_search_decision_trace_v1(trace)
                   << "}\n";
        }
        output.close();
        if (!output) throw std::runtime_error("cannot finalize trace JSONL output");
        const std::string output_sha256 = checked_sha256(output_path, "trace JSONL output");
        write_report(report_path, manifest_path, manifest_sha256, output_path,
                     output_sha256, invocations.size(), context);
        std::cout << "SEARCH_DECISION_TRACE_EXPORT_COMPLETE invocations="
                  << invocations.size() << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "error: " << error.what() << '\n';
        return 3;
    }
}

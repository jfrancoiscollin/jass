// SPDX-License-Identifier: AGPL-3.0-or-later
// T3/F6 O1 Gate-D technical cost profiler.
//
// This executable is strength-free. It authenticates the exact frozen R0-v4
// corpus/selection/summary, CURRICULUM, T3-A and Q00 bytes, derives the frozen
// Gate-D roots internally from stratified(corpus,32,2026092505), alternates
// OFF/ON order, and times only the inner depth-9 search call. Network/TT/cache
// construction and destruction are outside the primary timing window.
#include "egdb_bridge.hpp"
#include "scan_eval.hpp"
#include "search.hpp"
#include "search_params.hpp"
#include "t3_f6.hpp"

#include <algorithm>
#include <array>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

namespace {

using jass::Position;

constexpr std::string_view R0_CORPUS_SHA256 =
    "e22b5d8c8a89ff8491ca096a10219f8936f046a9b22977fcf2cfe48f96b309c5";
constexpr std::string_view R0_SELECTION_SHA256 =
    "8bc8ea375a20a83df3f82ee9235e62adcc37db6ef4035dbcf204279b937f5a18";
constexpr std::string_view R0_SUMMARY_SHA256 =
    "58d71be1c55d56d5140952e9af1baab48c0769214b615d0666f76b3bcbee0b5f";
constexpr std::string_view R0_Q00_SHA256 =
    "61cdaf50cc1948537990331d78f5b296dc6aee71cc7c2b98bcbd0969977619e1";
constexpr std::string_view ORDER_SEED = "2026092505";

struct FenRow {
    std::string fen;
    Position position;
};

Position parse(std::string_view fen) {
    auto position = Position::from_fen(fen);
    if (!position) throw std::runtime_error("invalid FEN: " + std::string(fen));
    return *position;
}

std::vector<FenRow> read_fens(const std::string& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open FEN file: " + path);
    std::vector<FenRow> rows;
    std::string line;
    while (std::getline(input, line)) {
        const auto comment = line.find('#');
        if (comment != std::string::npos) line.resize(comment);
        const auto first = line.find_first_not_of(" \t\r\n");
        if (first == std::string::npos) continue;
        const auto last = line.find_last_not_of(" \t\r\n");
        line = line.substr(first, last - first + 1U);
        rows.push_back({line, parse(line)});
    }
    return rows;
}

constexpr std::array<std::uint32_t, 64> SHA_K = {
    0x428a2f98U,0x71374491U,0xb5c0fbcfU,0xe9b5dba5U,0x3956c25bU,0x59f111f1U,0x923f82a4U,0xab1c5ed5U,
    0xd807aa98U,0x12835b01U,0x243185beU,0x550c7dc3U,0x72be5d74U,0x80deb1feU,0x9bdc06a7U,0xc19bf174U,
    0xe49b69c1U,0xefbe4786U,0x0fc19dc6U,0x240ca1ccU,0x2de92c6fU,0x4a7484aaU,0x5cb0a9dcU,0x76f988daU,
    0x983e5152U,0xa831c66dU,0xb00327c8U,0xbf597fc7U,0xc6e00bf3U,0xd5a79147U,0x06ca6351U,0x14292967U,
    0x27b70a85U,0x2e1b2138U,0x4d2c6dfcU,0x53380d13U,0x650a7354U,0x766a0abbU,0x81c2c92eU,0x92722c85U,
    0xa2bfe8a1U,0xa81a664bU,0xc24b8b70U,0xc76c51a3U,0xd192e819U,0xd6990624U,0xf40e3585U,0x106aa070U,
    0x19a4c116U,0x1e376c08U,0x2748774cU,0x34b0bcb5U,0x391c0cb3U,0x4ed8aa4aU,0x5b9cca4fU,0x682e6ff3U,
    0x748f82eeU,0x78a5636fU,0x84c87814U,0x8cc70208U,0x90befffaU,0xa4506cebU,0xbef9a3f7U,0xc67178f2U,
};

std::string sha256_text(std::string_view data) {
    std::array<std::uint32_t, 8> h = {
        0x6a09e667U,0xbb67ae85U,0x3c6ef372U,0xa54ff53aU,
        0x510e527fU,0x9b05688cU,0x1f83d9abU,0x5be0cd19U};
    const std::uint64_t bit_len = static_cast<std::uint64_t>(data.size()) * 8U;
    std::vector<unsigned char> bytes(data.begin(), data.end());
    bytes.push_back(0x80U);
    while ((bytes.size() % 64U) != 56U) bytes.push_back(0U);
    for (int shift = 56; shift >= 0; shift -= 8)
        bytes.push_back(static_cast<unsigned char>((bit_len >> shift) & 0xffU));
    for (std::size_t off = 0; off < bytes.size(); off += 64U) {
        std::array<std::uint32_t, 64> w{};
        for (std::size_t i = 0; i < 16U; ++i) {
            const std::size_t p = off + 4U * i;
            w[i] = (static_cast<std::uint32_t>(bytes[p]) << 24U)
                 | (static_cast<std::uint32_t>(bytes[p + 1U]) << 16U)
                 | (static_cast<std::uint32_t>(bytes[p + 2U]) << 8U)
                 | static_cast<std::uint32_t>(bytes[p + 3U]);
        }
        for (std::size_t i = 16U; i < 64U; ++i) {
            const std::uint32_t x = w[i - 15U], y = w[i - 2U];
            const std::uint32_t s0 = std::rotr(x, 7) ^ std::rotr(x, 18) ^ (x >> 3U);
            const std::uint32_t s1 = std::rotr(y, 17) ^ std::rotr(y, 19) ^ (y >> 10U);
            w[i] = w[i - 16U] + s0 + w[i - 7U] + s1;
        }
        std::uint32_t a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],hh=h[7];
        for (std::size_t i = 0; i < 64U; ++i) {
            const std::uint32_t s1 = std::rotr(e,6)^std::rotr(e,11)^std::rotr(e,25);
            const std::uint32_t ch = (e&f)^((~e)&g);
            const std::uint32_t t1 = hh+s1+ch+SHA_K[i]+w[i];
            const std::uint32_t s0 = std::rotr(a,2)^std::rotr(a,13)^std::rotr(a,22);
            const std::uint32_t t2 = s0+((a&b)^(a&c)^(b&c));
            hh=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;
        }
        h[0]+=a;h[1]+=b;h[2]+=c;h[3]+=d;h[4]+=e;h[5]+=f;h[6]+=g;h[7]+=hh;
    }
    std::ostringstream out;
    out << std::hex << std::setfill('0');
    for (const std::uint32_t v : h) out << std::setw(8) << v;
    return out.str();
}

std::string phase(const Position& p) {
    const int pieces = std::popcount(p.occupied());
    if (pieces >= 30 && pieces <= 40) return "P0";
    if (pieces >= 20 && pieces <= 29) return "P1";
    if (pieces >= 12 && pieces <= 19) return "P2";
    if (pieces >= 9 && pieces <= 11) return "P3";
    return "OUT";
}

std::vector<FenRow> expected_roots(const std::vector<FenRow>& corpus,
                                   std::size_t per_phase) {
    std::vector<FenRow> out;
    for (const std::string_view name : {"P0", "P1", "P2", "P3"}) {
        std::vector<FenRow> rows;
        for (const auto& row : corpus)
            if (phase(row.position) == name) rows.push_back(row);
        std::sort(rows.begin(), rows.end(), [](const FenRow& a, const FenRow& b) {
            const std::string ka = sha256_text(std::string(ORDER_SEED) + ":" + a.fen);
            const std::string kb = sha256_text(std::string(ORDER_SEED) + ":" + b.fen);
            return ka < kb;
        });
        if (rows.size() < per_phase)
            throw std::runtime_error("O1 Gate D phase support below frozen prefix");
        out.insert(out.end(), rows.begin(), rows.begin() + static_cast<std::ptrdiff_t>(per_phase));
    }
    std::sort(out.begin(), out.end(), [](const FenRow& a, const FenRow& b) {
        const std::string ka = sha256_text(std::string(ORDER_SEED) + ":all:" + a.fen);
        const std::string kb = sha256_text(std::string(ORDER_SEED) + ":all:" + b.fen);
        return ka < kb;
    });
    return out;
}

bool same_result(const jass::SearchResult& a, const jass::SearchResult& b) {
    return a.best_move == b.best_move
        && a.score == b.score
        && a.depth == b.depth
        && a.effective_depth == b.effective_depth
        && a.completed_depth == b.completed_depth
        && a.aborted_iteration == b.aborted_iteration
        && a.stop_reason == b.stop_reason
        && a.nodes == b.nodes
        && a.cutoffs == b.cutoffs
        && a.first_move_cutoffs == b.first_move_cutoffs
        && a.pvs_researches == b.pvs_researches
        && a.moves_searched == b.moves_searched
        && a.eval_calls == b.eval_calls
        && a.scan_verify_probes == b.scan_verify_probes
        && a.scan_verify_cutoffs == b.scan_verify_cutoffs
        && a.scan_threat_reentries == b.scan_threat_reentries
        && a.qnodes == b.qnodes
        && a.qsearch_calls == b.qsearch_calls
        && a.tablebase_probes == b.tablebase_probes
        && a.tablebase_hits == b.tablebase_hits
        && a.tt_probes == b.tt_probes
        && a.tt_hits == b.tt_hits
        && a.terminal_hits == b.terminal_hits
        && a.reductions == b.reductions
        && a.extensions == b.extensions
        && a.root_order_applications == b.root_order_applications
        && a.root_order_failures == b.root_order_failures
        && a.pv == b.pv
        && a.from_book == b.from_book;
}

std::unique_ptr<jass::INetwork> load_base(const std::string& curriculum) {
    std::string error;
    auto base = jass::load_eval_network(curriculum, &error);
    if (!base) throw std::runtime_error("CURRICULUM load failed: " + error);
    return base;
}

jass::t3_f6::Model load_t3(const std::string& model_path) {
    std::string error;
    auto model = jass::t3_f6::load_model(
        model_path, jass::t3_f6::LoadPolicy::FrozenOnly, &error);
    if (!model) throw std::runtime_error("T3-A load failed: " + error);
    return *model;
}

jass::SearchLimits depth9_limits(const jass::SearchParams& params) {
    jass::SearchLimits limits;
    limits.tt_mb = 16;
    limits.threads = 1;
    limits.max_depth = 9;
    limits.params = params;
    return limits;
}

struct TimedRun {
    jass::SearchResult result;
    jass::t3_f6::CacheStats cache{};
    std::uint64_t wall_ns{0};
};

TimedRun run_off(const Position& root, const std::string& curriculum,
                 const jass::t3_f6::Model& model,
                 const jass::SearchParams& params) {
    jass::t3_f6::Network network(load_base(curriculum), model);
    jass::TranspositionTable tt;
    auto limits = depth9_limits(params);
    tt.resize_mb(limits.tt_mb);
    limits.nnue = &network;
    const auto start = std::chrono::steady_clock::now();
    const auto result = jass::search(root, limits, tt, {});
    const auto stop = std::chrono::steady_clock::now();
    const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(stop - start).count();
    return {result, {}, static_cast<std::uint64_t>(ns)};
}

TimedRun run_on(const Position& root, const std::string& curriculum,
                const jass::t3_f6::Model& model,
                const jass::SearchParams& params) {
    std::string error;
    auto session = jass::t3_f6::O1SearchSession::create(
        load_base(curriculum), model, 1, &error);
    if (!session) throw std::runtime_error("O1 session creation failed: " + error);
    jass::TranspositionTable tt;
    auto limits = depth9_limits(params);
    tt.resize_mb(limits.tt_mb);
    std::uint64_t wall_ns = 0;
    const auto result = session->run_search(root, limits, tt, &wall_ns, &error);
    if (!result) throw std::runtime_error("O1 search rejected: " + error);
    return {*result, session->cache_stats(), wall_ns};
}

struct RowResult {
    std::size_t root_index{0};
    std::string phase;
    std::string fen_sha;
    TimedRun off;
    TimedRun on;
};

void write_run(std::ostream& out, const RowResult& row, bool on_arm,
               bool first_in_pair, bool trailing_comma) {
    const TimedRun& run = on_arm ? row.on : row.off;
    const double nps = run.wall_ns == 0 ? 0.0
        : static_cast<double>(run.result.nodes) * 1.0e9 / static_cast<double>(run.wall_ns);
    out << "    {\"root_index\": " << row.root_index
        << ", \"phase\": \"" << row.phase << "\""
        << ", \"fen_sha256\": \"" << row.fen_sha << "\""
        << ", \"arm\": \"" << (on_arm ? "ON" : "OFF") << "\""
        << ", \"order_in_pair\": " << (first_in_pair ? 1 : 2)
        << ", \"wall_ns\": " << run.wall_ns
        << ", \"nodes\": " << run.result.nodes
        << ", \"eval_calls\": " << run.result.eval_calls
        << ", \"effective_depth\": " << run.result.effective_depth
        << ", \"nps\": " << std::setprecision(17) << nps
        << ", \"cache_lookups\": " << run.cache.lookups
        << ", \"cache_hits\": " << run.cache.hits
        << ", \"cache_misses\": " << run.cache.misses
        << ", \"cache_replacements\": " << run.cache.replacements
        << ", \"extract_f6_executions\": " << run.cache.extract_f6_executions
        << "}" << (trailing_comma ? "," : "") << "\n";
}

int run_profile(int argc, char** argv) {
    const bool preflight = argc == 9 && std::string_view(argv[8]) == "--preflight";
    if (argc != 8 && !preflight) {
        throw std::runtime_error(
            "usage: t3_f6_exact_cache_o1_profile <r0-corpus.fen> <r0-selection.json> "
            "<r0-summary.json> <curriculum.pjtw> <t3.json> <q00-search-params> "
            "<report.json> [--preflight]");
    }
    const std::string corpus_path = argv[1];
    const std::string selection_path = argv[2];
    const std::string summary_path = argv[3];
    const std::string curriculum_path = argv[4];
    const std::string model_path = argv[5];
    const std::string params_spec = argv[6];
    const std::string report_path = argv[7];

    std::string error;
    const std::string corpus_sha = jass::t3_f6::sha256_file(corpus_path, &error);
    const std::string selection_sha = jass::t3_f6::sha256_file(selection_path, &error);
    const std::string summary_sha = jass::t3_f6::sha256_file(summary_path, &error);
    const std::string curriculum_sha = jass::t3_f6::sha256_file(curriculum_path, &error);
    const std::string model_sha = jass::t3_f6::sha256_file(model_path, &error);
    if (corpus_sha != R0_CORPUS_SHA256 || selection_sha != R0_SELECTION_SHA256
        || summary_sha != R0_SUMMARY_SHA256)
        throw std::runtime_error("R0-v4 immutable artifact SHA256 mismatch");
    if (curriculum_sha != jass::t3_f6::FROZEN_CURRICULUM_SHA256)
        throw std::runtime_error("CURRICULUM SHA256 mismatch");
    if (model_sha != jass::t3_f6::FROZEN_MODEL_SHA256)
        throw std::runtime_error("T3-A SHA256 mismatch");
    const std::string q00_sha = sha256_text(params_spec);
    if (q00_sha != R0_Q00_SHA256
        || std::count(params_spec.begin(), params_spec.end(), ',') != 62)
        throw std::runtime_error("R0-v4 Q00 contract mismatch");

    const auto corpus = read_fens(corpus_path);
    if (corpus.size() != 4096U)
        throw std::runtime_error("O1 Gate D requires exact 4096-row corpus");
    const std::size_t per_phase = preflight ? 1U : 32U;
    const auto roots = expected_roots(corpus, per_phase);
    if (roots.size() != 4U * per_phase)
        throw std::runtime_error("O1 Gate D root cardinality drift");

    const auto model = load_t3(model_path);
    const auto params = jass::parse_search_params(params_spec);
    jass::egdb::ensure_initialised();
    if (!jass::egdb::available())
        throw std::runtime_error("EGDB unavailable for O1 Gate D profile");

    std::vector<RowResult> rows;
    rows.reserve(roots.size());
    std::uint64_t off_wall = 0, on_wall = 0;
    std::uint64_t off_nodes = 0, on_nodes = 0;
    std::uint64_t off_evals = 0, on_evals = 0;
    std::uint64_t lookups = 0, hits = 0, misses = 0, replacements = 0, extracts = 0;
    std::size_t mismatches = 0;

    for (std::size_t i = 0; i < roots.size(); ++i) {
        TimedRun off;
        TimedRun on;
        if ((i % 2U) == 0U) {
            off = run_off(roots[i].position, curriculum_path, model, params);
            on = run_on(roots[i].position, curriculum_path, model, params);
        } else {
            on = run_on(roots[i].position, curriculum_path, model, params);
            off = run_off(roots[i].position, curriculum_path, model, params);
        }
        mismatches += !same_result(off.result, on.result);
        off_wall += off.wall_ns;
        on_wall += on.wall_ns;
        off_nodes += off.result.nodes;
        on_nodes += on.result.nodes;
        off_evals += off.result.eval_calls;
        on_evals += on.result.eval_calls;
        lookups += on.cache.lookups;
        hits += on.cache.hits;
        misses += on.cache.misses;
        replacements += on.cache.replacements;
        extracts += on.cache.extract_f6_executions;
        rows.push_back({i, phase(roots[i].position), sha256_text(roots[i].fen), off, on});
    }

    if (mismatches != 0U)
        throw std::runtime_error("O1_RUNTIME_TECHNICAL_FAILED: OFF/ON search mismatch");
    if (lookups == 0U || hits == 0U || extracts == 0U)
        throw std::runtime_error("O1_RUNTIME_TECHNICAL_FAILED: cache telemetry invalid");
    if (off_wall == 0U || on_wall == 0U)
        throw std::runtime_error("O1_RUNTIME_TECHNICAL_FAILED: zero wall clock");

    const double off_nps = static_cast<double>(off_nodes) * 1.0e9 / static_cast<double>(off_wall);
    const double on_nps = static_cast<double>(on_nodes) * 1.0e9 / static_cast<double>(on_wall);
    const double hit_rate = static_cast<double>(hits) / static_cast<double>(lookups);

    std::ofstream report(report_path);
    if (!report) throw std::runtime_error("cannot create O1 Gate D report");
    report << std::setprecision(17)
           << "{\n"
           << "  \"schema\": \"jass.t3_f6_exact_cache_o1_profile.v1\",\n"
           << "  \"status\": \"" << (preflight ? "O1_GATE_D_PREFLIGHT_SIZER_COMPLETE" : "O1_GATE_D_PROFILE_COMPLETE_NONTERMINAL") << "\",\n"
           << "  \"profile_mode\": \"" << (preflight ? "preflight_1_per_phase" : "gate_d_frozen_32_per_phase") << "\",\n"
           << "  \"primary_wall_window\": \"search_only\",\n"
           << "  \"setup_teardown_in_primary_wall\": false,\n"
           << "  \"threads\": 1,\n"
           << "  \"tt_mb\": 16,\n"
           << "  \"depth\": 9,\n"
           << "  \"order_seed\": 2026092505,\n"
           << "  \"roots\": " << roots.size() << ",\n"
           << "  \"searches\": " << (2U * roots.size()) << ",\n"
           << "  \"corpus_sha256\": \"" << corpus_sha << "\",\n"
           << "  \"selection_certificate_sha256\": \"" << selection_sha << "\",\n"
           << "  \"r0_summary_sha256\": \"" << summary_sha << "\",\n"
           << "  \"curriculum_sha256\": \"" << curriculum_sha << "\",\n"
           << "  \"t3_a_sha256\": \"" << model_sha << "\",\n"
           << "  \"q00_sha256\": \"" << q00_sha << "\",\n"
           << "  \"search_mismatches\": " << mismatches << ",\n"
           << "  \"off_wall_ns_total\": " << off_wall << ",\n"
           << "  \"on_wall_ns_total\": " << on_wall << ",\n"
           << "  \"wall_ratio_on_over_off\": " << (static_cast<double>(on_wall) / static_cast<double>(off_wall)) << ",\n"
           << "  \"off_nodes_total\": " << off_nodes << ",\n"
           << "  \"on_nodes_total\": " << on_nodes << ",\n"
           << "  \"off_eval_calls_total\": " << off_evals << ",\n"
           << "  \"on_eval_calls_total\": " << on_evals << ",\n"
           << "  \"off_nps\": " << off_nps << ",\n"
           << "  \"on_nps\": " << on_nps << ",\n"
           << "  \"nps_ratio_on_over_off\": " << (on_nps / off_nps) << ",\n"
           << "  \"cache_lookups\": " << lookups << ",\n"
           << "  \"cache_hits\": " << hits << ",\n"
           << "  \"cache_misses\": " << misses << ",\n"
           << "  \"cache_replacements\": " << replacements << ",\n"
           << "  \"cache_hit_rate\": " << hit_rate << ",\n"
           << "  \"extract_f6_executions\": " << extracts << ",\n"
           << "  \"strength_games\": 0,\n"
           << "  \"scientific_decision\": false,\n"
           << "  \"runs\": [\n";
    std::size_t emitted = 0;
    const std::size_t total_runs = rows.size() * 2U;
    for (const auto& row : rows) {
        const bool even = (row.root_index % 2U) == 0U;
        write_run(report, row, !even, false, false); // placeholder overwritten below
        // The line above is removed by seeking impossible on streams; keep the
        // actual ordered emission in the two branches below.
        throw std::logic_error("unreachable ordered emission guard");
    }
    (void)emitted;
    (void)total_runs;
    return 0;
}

int selftest() {
    if (sha256_text("abc") !=
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        throw std::runtime_error("O1 profile SHA256 selftest failed");
    std::cout << "T3/F6 O1 Gate-D profiler selftest PASS\n";
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc == 2 && std::string_view(argv[1]) == "--selftest")
            return selftest();
        return run_profile(argc, argv);
    } catch (const std::exception& error) {
        std::cerr << "t3_f6_exact_cache_o1_profile: " << error.what() << '\n';
        return 1;
    }
}

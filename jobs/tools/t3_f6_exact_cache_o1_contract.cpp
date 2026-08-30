// SPDX-License-Identifier: AGPL-3.0-or-later
// T3/F6 O1 exact-cache technical equivalence harness.
//
// This executable is deliberately strength-free. It authenticates the exact
// cpx62-1685 corpus, selector certificate and terminal summary against hashes
// published by read-only receipt cpx62-1691, derives the frozen Gate-C roots
// internally from stratified(corpus,16,2026092505), verifies any supplied root
// file row-for-row, then runs Gate B before Gate C.
#include "egdb_bridge.hpp"
#include "scan_eval.hpp"
#include "search.hpp"
#include "search_params.hpp"
#include "t3_f6.hpp"

#include <algorithm>
#include <array>
#include <bit>
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

// Exact immutable inputs from cpx62-1685, independently re-authenticated by
// cpx62-1691-l3-t3-f6-o1-r0-hash-receipt-v1, attempt
// 20260830T142614Z-4e67610f.  O1 must fail closed if any byte changes.
constexpr std::string_view R0_CORPUS_SHA256 =
    "e22b5d8c8a89ff8491ca096a10219f8936f046a9b22977fcf2cfe48f96b309c5";
constexpr std::string_view R0_SELECTION_SHA256 =
    "8bc8ea375a20a83df3f82ee9235e62adcc37db6ef4035dbcf204279b937f5a18";
constexpr std::string_view R0_SUMMARY_SHA256 =
    "58d71be1c55d56d5140952e9af1baab48c0769214b615d0666f76b3bcbee0b5f";
// cpx62-1692 independently parsed the pinned R0 summary's nested
// runtime_contract, verified threads=1 / tt_mb=16 / book=OFF / 63 params, and
// published this exact Q00 digest.  Pinning that receipt avoids ambiguous
// unscoped key lookup in the large nested summary while preserving the exact
// preregistered search vector byte-for-byte.
constexpr std::string_view R0_Q00_SHA256 =
    "61cdaf50cc1948537990331d78f5b296dc6aee71cc7c2b98bcbd0969977619e1";

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

std::string read_text(const std::string& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("cannot open certificate: " + path);
    return std::string(std::istreambuf_iterator<char>(input),
                       std::istreambuf_iterator<char>());
}

std::size_t json_value_start(const std::string& text, std::string_view key) {
    const std::string needle = "\"" + std::string(key) + "\"";
    const auto key_pos = text.find(needle);
    if (key_pos == std::string::npos)
        throw std::runtime_error("certificate missing key: " + std::string(key));
    const auto colon = text.find(':', key_pos + needle.size());
    if (colon == std::string::npos)
        throw std::runtime_error("certificate malformed key: " + std::string(key));
    const auto value = text.find_first_not_of(" \t\r\n", colon + 1U);
    if (value == std::string::npos)
        throw std::runtime_error("certificate missing value: " + std::string(key));
    return value;
}

std::string json_string_field(const std::string& text, std::string_view key) {
    const auto begin = json_value_start(text, key);
    if (text[begin] != '"')
        throw std::runtime_error("certificate non-string key: " + std::string(key));
    const auto end = text.find('"', begin + 1U);
    if (end == std::string::npos)
        throw std::runtime_error("certificate unterminated string: " + std::string(key));
    return text.substr(begin + 1U, end - begin - 1U);
}

std::uint64_t json_uint_field(const std::string& text, std::string_view key) {
    const auto begin = json_value_start(text, key);
    std::size_t end = begin;
    while (end < text.size() && text[end] >= '0' && text[end] <= '9') ++end;
    if (end == begin)
        throw std::runtime_error("certificate non-integer key: " + std::string(key));
    return std::stoull(text.substr(begin, end - begin));
}

bool json_bool_field(const std::string& text, std::string_view key) {
    const auto begin = json_value_start(text, key);
    if (text.compare(begin, 4U, "true") == 0) return true;
    if (text.compare(begin, 5U, "false") == 0) return false;
    throw std::runtime_error("certificate non-boolean key: " + std::string(key));
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

std::vector<std::string> expected_roots(const std::vector<FenRow>& corpus) {
    constexpr std::string_view seed = "2026092505";
    std::vector<std::string> out;
    for (const std::string_view name : {"P0", "P1", "P2", "P3"}) {
        std::vector<std::string> rows;
        for (const auto& row : corpus)
            if (phase(row.position) == name) rows.push_back(row.fen);
        std::sort(rows.begin(), rows.end(), [&](const std::string& a, const std::string& b) {
            const std::string ka = sha256_text(std::string(seed) + ":" + a);
            const std::string kb = sha256_text(std::string(seed) + ":" + b);
            return ka < kb;
        });
        if (rows.size() < 16U)
            throw std::runtime_error("O1 Gate C phase support below 16");
        out.insert(out.end(), rows.begin(), rows.begin() + 16);
    }
    std::sort(out.begin(), out.end(), [&](const std::string& a, const std::string& b) {
        const std::string ka = sha256_text(std::string(seed) + ":all:" + a);
        const std::string kb = sha256_text(std::string(seed) + ":all:" + b);
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

enum class Budget { Depth1, Depth9, Nodes1k, Nodes10k };

jass::SearchLimits limits_for(const jass::SearchParams& params, Budget budget) {
    jass::SearchLimits limits;
    limits.tt_mb = 16;
    limits.threads = 1;
    limits.params = params;
    if (budget == Budget::Depth1) {
        limits.max_depth = 1;
    } else if (budget == Budget::Depth9) {
        limits.max_depth = 9;
    } else {
        limits.max_depth = 6;
        limits.max_nodes = budget == Budget::Nodes1k ? 1000U : 10000U;
        limits.node_limit_mode = jass::NodeLimitMode::Exact;
    }
    return limits;
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

jass::SearchResult run_off(const Position& root,
                           const std::string& curriculum,
                           const jass::t3_f6::Model& model,
                           const jass::SearchParams& params,
                           Budget budget) {
    jass::t3_f6::Network network(load_base(curriculum), model);
    auto limits = limits_for(params, budget);
    limits.nnue = &network;
    return jass::search(root, limits);
}

std::pair<jass::SearchResult, jass::t3_f6::CacheStats> run_on(
    const Position& root,
    const std::string& curriculum,
    const jass::t3_f6::Model& model,
    const jass::SearchParams& params,
    Budget budget) {
    std::string error;
    auto session = jass::t3_f6::O1SearchSession::create(
        load_base(curriculum), model, 1, &error);
    if (!session) throw std::runtime_error("O1 session creation failed: " + error);
    auto limits = limits_for(params, budget);
    const auto result = session->run_search(root, limits, &error);
    if (!result) throw std::runtime_error("O1 search rejected: " + error);
    return {*result, session->cache_stats()};
}

const char* boolean(bool value) noexcept { return value ? "true" : "false"; }

void write_gate_b_failure(const std::string& path,
                          std::size_t corpus_rows,
                          const std::string& corpus_sha,
                          const std::string& selection_sha,
                          const std::string& summary_sha,
                          const std::string& q00_sha,
                          std::size_t residual_mismatches,
                          std::size_t score_mismatches,
                          std::size_t replay_residual_mismatches,
                          std::size_t replay_score_mismatches,
                          std::size_t flush_residual_mismatches,
                          std::size_t flush_score_mismatches,
                          std::size_t nonfinite,
                          std::size_t saturations,
                          std::uint64_t hits) {
    std::ofstream report(path);
    if (!report) throw std::runtime_error("cannot create O1 Gate B report");
    report << "{\n"
           << "  \"schema\": \"jass.t3_f6_exact_cache_o1_contract.v1\",\n"
           << "  \"verdict\": \"O1_EXACT_CACHE_EQUIVALENCE_FAILED\",\n"
           << "  \"gate_b_pass\": false,\n"
           << "  \"gate_c_run\": false,\n"
           << "  \"corpus_rows\": " << corpus_rows << ",\n"
           << "  \"corpus_sha256\": \"" << corpus_sha << "\",\n"
           << "  \"selection_certificate_sha256\": \"" << selection_sha << "\",\n"
           << "  \"r0_summary_sha256\": \"" << summary_sha << "\",\n"
           << "  \"q00_sha256\": \"" << q00_sha << "\",\n"
           << "  \"residual_mismatches\": " << residual_mismatches << ",\n"
           << "  \"score_mismatches\": " << score_mismatches << ",\n"
           << "  \"replay_residual_mismatches\": " << replay_residual_mismatches << ",\n"
           << "  \"replay_score_mismatches\": " << replay_score_mismatches << ",\n"
           << "  \"flush_residual_mismatches\": " << flush_residual_mismatches << ",\n"
           << "  \"flush_score_mismatches\": " << flush_score_mismatches << ",\n"
           << "  \"nonfinite\": " << nonfinite << ",\n"
           << "  \"saturations\": " << saturations << ",\n"
           << "  \"gate_b_hits\": " << hits << ",\n"
           << "  \"strength_games\": 0,\n"
           << "  \"scientific_decision\": false\n"
           << "}\n";
}

int run_contract(int argc, char** argv) {
    if (argc != 9) {
        throw std::runtime_error(
            "usage: t3_f6_exact_cache_o1_contract <r0-corpus.fen> <roots64.fen> "
            "<r0-selection.json> <r0-summary.json> <curriculum.pjtw> <t3.json> "
            "<q00-search-params> <report.json>");
    }
    const std::string corpus_path = argv[1];
    const std::string roots_path = argv[2];
    const std::string selection_path = argv[3];
    const std::string summary_path = argv[4];
    const std::string curriculum_path = argv[5];
    const std::string model_path = argv[6];
    const std::string params_spec = argv[7];
    const std::string report_path = argv[8];

    std::string error;
    const std::string curriculum_sha = jass::t3_f6::sha256_file(curriculum_path, &error);
    const std::string model_sha = jass::t3_f6::sha256_file(model_path, &error);
    const std::string corpus_sha = jass::t3_f6::sha256_file(corpus_path, &error);
    const std::string selection_sha = jass::t3_f6::sha256_file(selection_path, &error);
    const std::string summary_sha = jass::t3_f6::sha256_file(summary_path, &error);
    if (curriculum_sha != jass::t3_f6::FROZEN_CURRICULUM_SHA256)
        throw std::runtime_error("CURRICULUM SHA256 mismatch");
    if (model_sha != jass::t3_f6::FROZEN_MODEL_SHA256)
        throw std::runtime_error("T3-A SHA256 mismatch");
    if (corpus_sha != R0_CORPUS_SHA256
        || selection_sha != R0_SELECTION_SHA256
        || summary_sha != R0_SUMMARY_SHA256) {
        throw std::runtime_error("R0-v4 immutable artifact SHA256 mismatch");
    }

    const std::string selection = read_text(selection_path);
    if (json_string_field(selection, "schema") != "jass.t3_f6_r0_target_blind_selection.v4"
        || json_string_field(selection, "verdict") != "R0_V4_TARGET_BLIND_CORPUS_READY"
        || json_uint_field(selection, "selected") != 4096U
        || json_uint_field(selection, "selection_seed") != 2026092502U
        || json_uint_field(selection, "permutation_seed") != 2026092503U
        || json_uint_field(selection, "search_seed") != 2026092504U
        || json_uint_field(selection, "benchmark_seed") != 2026092505U
        || json_uint_field(selection, "forbidden_overlap") != 0U
        || json_string_field(selection, "fen_sha256") != corpus_sha) {
        throw std::runtime_error("R0-v4 corpus/selection certificate mismatch");
    }

    // The full R0 summary bytes are already pinned above by cpx62-1691.  The
    // exact nested runtime_contract/Q00 was independently scoped and pinned by
    // cpx62-1692.  Do not search the nested summary globally for repeated keys
    // such as `threads`, `book`, `passed`, or `search_params`.
    const std::string q00_sha = sha256_text(params_spec);
    if (q00_sha != R0_Q00_SHA256
        || std::count(params_spec.begin(), params_spec.end(), ',') != 62) {
        throw std::runtime_error("R0-v4 terminal/Q00 contract mismatch");
    }

    const auto corpus = read_fens(corpus_path);
    const auto roots = read_fens(roots_path);
    if (corpus.size() != 4096U)
        throw std::runtime_error("O1 Gate B requires exactly 4096 corpus rows");
    if (roots.size() != 64U)
        throw std::runtime_error("O1 Gate C requires exactly 64 roots");

    const auto expected = expected_roots(corpus);
    for (std::size_t i = 0; i < roots.size(); ++i) {
        if (roots[i].fen != expected[i])
            throw std::runtime_error("O1 Gate C roots differ from frozen stratified order");
    }

    const auto model = load_t3(model_path);
    const auto params = jass::parse_search_params(params_spec);
    jass::egdb::ensure_initialised();
    if (!jass::egdb::available())
        throw std::runtime_error("EGDB unavailable for O1 Gate C");

    jass::t3_f6::Network off_leaf(load_base(curriculum_path), model);
    auto on_leaf = jass::t3_f6::O1SearchSession::create(
        load_base(curriculum_path), model, 1, &error);
    if (!on_leaf) throw std::runtime_error("O1 Gate B session creation failed: " + error);

    std::size_t residual_mismatches = 0;
    std::size_t score_mismatches = 0;
    std::size_t replay_residual_mismatches = 0;
    std::size_t replay_score_mismatches = 0;
    std::size_t flush_residual_mismatches = 0;
    std::size_t flush_score_mismatches = 0;
    std::size_t nonfinite = 0;
    std::size_t saturations = 0;
    for (const auto& row : corpus) {
        const double off_residual = off_leaf.residual_parent(row.position);
        const double on_residual = on_leaf->residual_parent(row.position);
        const int off_score = off_leaf.evaluate(row.position);
        const int on_score = on_leaf->evaluate(row.position);
        residual_mismatches += std::bit_cast<std::uint64_t>(off_residual)
                            != std::bit_cast<std::uint64_t>(on_residual);
        score_mismatches += off_score != on_score;
        nonfinite += !std::isfinite(off_residual) || !std::isfinite(on_residual);
        saturations += std::abs(off_score) == 20000 || std::abs(on_score) == 20000;
    }

    for (auto it = corpus.rbegin(); it != corpus.rend(); ++it) {
        const double off_residual = off_leaf.residual_parent(it->position);
        const double on_residual = on_leaf->residual_parent(it->position);
        replay_residual_mismatches += std::bit_cast<std::uint64_t>(off_residual)
                                   != std::bit_cast<std::uint64_t>(on_residual);
        replay_score_mismatches += off_leaf.evaluate(it->position) != on_leaf->evaluate(it->position);
        nonfinite += !std::isfinite(off_residual) || !std::isfinite(on_residual);
    }
    const auto replay_stats = on_leaf->cache_stats();
    const bool real_hit_observed = replay_stats.hits > 0U;

    on_leaf->clear_cache();
    const bool flush_zero = on_leaf->cache_stats().lookups == 0U;
    const Position& flushed = corpus.front().position;
    const double off_after_flush = off_leaf.residual_parent(flushed);
    const double on_after_flush = on_leaf->residual_parent(flushed);
    flush_residual_mismatches += std::bit_cast<std::uint64_t>(off_after_flush)
                               != std::bit_cast<std::uint64_t>(on_after_flush);
    flush_score_mismatches += off_leaf.evaluate(flushed) != on_leaf->evaluate(flushed);
    nonfinite += !std::isfinite(off_after_flush) || !std::isfinite(on_after_flush);
    const auto cold_after_flush = on_leaf->cache_stats();
    const bool flush_miss = cold_after_flush.hits == 1U
                         && cold_after_flush.misses == 1U
                         && cold_after_flush.extract_f6_executions == 1U;

    const bool gate_b = residual_mismatches == 0U
                     && score_mismatches == 0U
                     && replay_residual_mismatches == 0U
                     && replay_score_mismatches == 0U
                     && flush_residual_mismatches == 0U
                     && flush_score_mismatches == 0U
                     && nonfinite == 0U
                     && saturations == 0U
                     && real_hit_observed
                     && flush_zero
                     && flush_miss;
    if (!gate_b) {
        write_gate_b_failure(report_path, corpus.size(), corpus_sha, selection_sha,
                             summary_sha, q00_sha,
                             residual_mismatches, score_mismatches,
                             replay_residual_mismatches, replay_score_mismatches,
                             flush_residual_mismatches, flush_score_mismatches,
                             nonfinite, saturations, replay_stats.hits);
        std::cout << "O1_EXACT_CACHE_EQUIVALENCE_FAILED\n";
        return 2;
    }

    constexpr std::array<Budget, 4> budgets = {
        Budget::Depth1, Budget::Depth9, Budget::Nodes1k, Budget::Nodes10k};
    std::size_t search_mismatches = 0;
    std::size_t search_pairs = 0;
    std::uint64_t gate_c_lookups = 0;
    std::uint64_t gate_c_hits = 0;
    std::uint64_t gate_c_misses = 0;
    for (const auto& row : roots) {
        for (const auto budget : budgets) {
            const auto off = run_off(row.position, curriculum_path, model, params, budget);
            const auto [on, stats] = run_on(row.position, curriculum_path, model, params, budget);
            ++search_pairs;
            search_mismatches += !same_result(off, on);
            gate_c_lookups += stats.lookups;
            gate_c_hits += stats.hits;
            gate_c_misses += stats.misses;
        }
    }
    const bool gate_c = search_pairs == 64U * budgets.size() && search_mismatches == 0U;

    std::ofstream report(report_path);
    if (!report) throw std::runtime_error("cannot create O1 Gate B/C report");
    report << "{\n"
           << "  \"schema\": \"jass.t3_f6_exact_cache_o1_contract.v1\",\n";
    if (gate_c)
        report << "  \"status\": \"O1_GATES_BC_PASS_NONTERMINAL\",\n";
    else
        report << "  \"verdict\": \"O1_EXACT_CACHE_SEARCH_EQUIVALENCE_FAILED\",\n";
    report << "  \"gate_b_pass\": true,\n"
           << "  \"gate_c_pass\": " << boolean(gate_c) << ",\n"
           << "  \"corpus_rows\": " << corpus.size() << ",\n"
           << "  \"corpus_sha256\": \"" << corpus_sha << "\",\n"
           << "  \"selection_certificate_sha256\": \"" << selection_sha << "\",\n"
           << "  \"r0_summary_sha256\": \"" << summary_sha << "\",\n"
           << "  \"q00_sha256\": \"" << q00_sha << "\",\n"
           << "  \"q00_parameter_count\": 63,\n"
           << "  \"roots\": " << roots.size() << ",\n"
           << "  \"roots_sha256\": \"" << jass::t3_f6::sha256_file(roots_path, &error) << "\",\n"
           << "  \"root_selection_verified_internally\": true,\n"
           << "  \"order_seed\": 2026092505,\n"
           << "  \"residual_mismatches\": " << residual_mismatches << ",\n"
           << "  \"score_mismatches\": " << score_mismatches << ",\n"
           << "  \"replay_residual_mismatches\": " << replay_residual_mismatches << ",\n"
           << "  \"replay_score_mismatches\": " << replay_score_mismatches << ",\n"
           << "  \"flush_residual_mismatches\": " << flush_residual_mismatches << ",\n"
           << "  \"flush_score_mismatches\": " << flush_score_mismatches << ",\n"
           << "  \"nonfinite\": " << nonfinite << ",\n"
           << "  \"saturations\": " << saturations << ",\n"
           << "  \"gate_b_hits\": " << replay_stats.hits << ",\n"
           << "  \"search_pairs\": " << search_pairs << ",\n"
           << "  \"search_mismatches\": " << search_mismatches << ",\n"
           << "  \"gate_c_cache_lookups\": " << gate_c_lookups << ",\n"
           << "  \"gate_c_cache_hits\": " << gate_c_hits << ",\n"
           << "  \"gate_c_cache_misses\": " << gate_c_misses << ",\n"
           << "  \"strength_games\": 0,\n"
           << "  \"scientific_decision\": false\n"
           << "}\n";
    std::cout << (gate_c ? "O1_GATES_BC_PASS_NONTERMINAL"
                         : "O1_EXACT_CACHE_SEARCH_EQUIVALENCE_FAILED")
              << " search_pairs=" << search_pairs
              << " mismatches=" << search_mismatches << '\n';
    return gate_c ? 0 : 2;
}

int selftest() {
    if (sha256_text("abc") !=
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        throw std::runtime_error("O1 SHA256 selftest failed");
    class Square final : public jass::INetwork {
    public:
        int evaluate(const Position& p) const noexcept override {
            return static_cast<int>((p.white_men() ^ p.black_men()) % 401U) - 200;
        }
    };
    std::string error;
    auto session = jass::t3_f6::O1SearchSession::create(
        std::make_unique<Square>(), jass::t3_f6::Model{}, 2, &error);
    if (session || error.empty())
        throw std::runtime_error("O1 threads>1 selftest failed");
    std::cout << "T3/F6 O1 contract selftest PASS\n";
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc == 2 && std::string_view(argv[1]) == "--selftest")
            return selftest();
        return run_contract(argc, argv);
    } catch (const std::exception& error) {
        std::cerr << "t3_f6_exact_cache_o1_contract: " << error.what() << '\n';
        return 1;
    }
}

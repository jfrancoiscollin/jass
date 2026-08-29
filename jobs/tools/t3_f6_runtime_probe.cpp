// SPDX-License-Identifier: AGPL-3.0-or-later
// Target-blind native parity dump and non-selective runtime profile for R0.
#include "movegen.hpp"
#include "position.hpp"
#include "residual_features.hpp"
#include "scan_eval.hpp"
#include "t3_f6.hpp"

#include <array>
#include <bit>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using Clock = std::chrono::steady_clock;

std::vector<jass::Position> read_positions(const std::string& path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("cannot open FEN corpus");
    std::vector<jass::Position> out;
    std::string line;
    while (std::getline(in, line)) {
        const auto hash = line.find('#');
        if (hash != std::string::npos) line.resize(hash);
        if (line.empty()) continue;
        auto p = jass::Position::from_fen(line);
        if (!p) throw std::runtime_error("bad corpus FEN");
        out.push_back(*p);
    }
    if (out.empty()) throw std::runtime_error("empty FEN corpus");
    return out;
}

const char* phase(const jass::Position& p) noexcept {
    const int pieces = jass::popcount(p.occupied());
    if (pieces >= 30) return "P0";
    if (pieces >= 20) return "P1";
    if (pieces >= 12) return "P2";
    return "P3";
}

const char* branch_bin(std::size_t n) noexcept {
    if (n == 1U) return "b01";
    if (n <= 4U) return "b02_04";
    if (n <= 8U) return "b05_08";
    return "b09_plus";
}

struct Bucket { std::uint64_t ns{0}; std::uint64_t n{0}; };

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 8) {
            std::cerr << "usage: t3_f6_runtime_probe <corpus.fen> <curriculum.pjtw> "
                         "<t3.json> <rows.tsv> <profile.json> <passes> <order-seed>\n";
            return 2;
        }
        const int passes = std::stoi(argv[6]);
        const std::uint64_t order_seed = std::stoull(argv[7]);
        if (passes < 1) throw std::runtime_error("passes must be positive");
        if (order_seed != 2026090904ULL && order_seed != 2026091704ULL
            && order_seed != 2026092104ULL)
            throw std::runtime_error("R0 benchmark order seed drift");
        const auto positions = read_positions(argv[1]);
        std::string err;
        if (jass::t3_f6::sha256_file(argv[2], &err)
            != jass::t3_f6::FROZEN_CURRICULUM_SHA256)
            throw std::runtime_error("CURRICULUM SHA mismatch");
        auto base = jass::load_eval_network(argv[2], &err);
        if (!base) throw std::runtime_error("base load: " + err);
        auto model = jass::t3_f6::load_model(
            argv[3], jass::t3_f6::LoadPolicy::FrozenOnly, &err);
        if (!model) throw std::runtime_error("T3 load: " + err);
        jass::t3_f6::Network t3(std::move(base), std::move(*model));
        const jass::INetwork* t0 = t3.base_network();

        std::ofstream rows(argv[4]);
        if (!rows) throw std::runtime_error("cannot create parity TSV");
        rows << "row\tfen\tt0_int\tresidual_parent\tt3_float\tt3_int";
        for (std::size_t i=0;i<jass::t3_f6::INPUT_WIDTH;++i)
            rows << "\tf" << std::setw(2) << std::setfill('0') << i << "_bits";
        for (std::size_t i=0;i<jass::t3_f6::INPUT_WIDTH;++i)
            rows << "\tz" << std::setw(2) << std::setfill('0') << i << "_bits";
        rows << '\n' << std::setprecision(17);
        std::uint64_t saturations = 0;
        std::vector<std::array<float,jass::t3_f6::INPUT_WIDTH>> features;
        features.reserve(positions.size());
        for (std::size_t row=0;row<positions.size();++row) {
            const auto f = jass::residual_features::extract_f6(positions[row]).all_new();
            features.push_back(f);
            const int base_score=t0->evaluate(positions[row]);
            const double residual=t3.model().residual_parent(f);
            const double raw=static_cast<double>(base_score)-residual;
            const int final_score=t3.evaluate_from_base(positions[row],base_score);
            saturations += (final_score==20000 || final_score==-20000) ? 1U : 0U;
            rows << row << '\t' << positions[row].to_fen() << '\t' << base_score
                 << '\t' << residual << '\t' << raw << '\t' << final_score;
            rows << std::hex << std::setfill('0');
            for (float v:f) rows << '\t' << std::setw(8) << std::bit_cast<std::uint32_t>(v);
            for (std::size_t i=0;i<jass::t3_f6::INPUT_WIDTH;++i) {
                const double z=(static_cast<double>(f[i])-t3.model().mean[i])
                              /t3.model().stddev[i];
                rows << '\t' << std::setw(16) << std::bit_cast<std::uint64_t>(z);
            }
            rows << std::dec << std::setfill(' ') << '\n';
        }

        // Two fixed warm-up passes, then exactly the requested measured passes.
        std::int64_t checksum=0;
        for (int warm=0;warm<2;++warm)
            for (const auto& p:positions) checksum += t3.evaluate(p);
        std::uint64_t t0_ns=0,t3_ns=0,residual_ns=0;
        std::map<std::string,Bucket> phase_buckets, branch_buckets;
        std::vector<std::string> phases;
        std::vector<std::string> branches;
        phases.reserve(positions.size());
        branches.reserve(positions.size());
        for (const auto& p:positions) {
            phases.emplace_back(phase(p));
            jass::MoveList legal;
            jass::generate_legal_moves(p,legal);
            if (legal.empty())
                throw std::runtime_error("R0 corpus contains terminal position");
            branches.emplace_back(branch_bin(legal.size()));
        }
        for (int pass=0;pass<passes;++pass) {
            for (std::size_t i=0;i<positions.size();++i) {
                const auto& p=positions[i];
                auto start=Clock::now();
                checksum += t0->evaluate(p);
                t0_ns += static_cast<std::uint64_t>(
                    std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-start).count());
                start=Clock::now();
                checksum += static_cast<std::int64_t>(t3.model().residual_parent(features[i]));
                residual_ns += static_cast<std::uint64_t>(
                    std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-start).count());
                start=Clock::now();
                checksum += t3.evaluate(p);
                const auto elapsed=static_cast<std::uint64_t>(
                    std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-start).count());
                t3_ns += elapsed;
                auto& pb=phase_buckets[phases[i]];
                pb.ns+=elapsed;
                ++pb.n;
                auto& bb=branch_buckets[branches[i]];
                bb.ns+=elapsed;
                ++bb.n;
            }
        }
        // Fine-grained feature instrumentation is deliberately isolated from
        // the timing loop and performed exactly once over the whole corpus.
        jass::residual_features::Profile family_profile;
        for (const auto& p:positions)
            (void)jass::residual_features::extract_f6(p,&family_profile);
        const double evals=static_cast<double>(positions.size())*passes;
        const double instrumented_evals=static_cast<double>(positions.size());
        std::ofstream report(argv[5]);
        if (!report) throw std::runtime_error("cannot create profile JSON");
        report << std::setprecision(17)
               << "{\n  \"schema\": \"jass.t3_f6_runtime_profile.v1\",\n"
               << "  \"model_sha256\": \"" << jass::t3_f6::FROZEN_MODEL_SHA256 << "\",\n"
               << "  \"curriculum_sha256\": \"" << jass::t3_f6::FROZEN_CURRICULUM_SHA256 << "\",\n"
               << "  \"feature_order_sha256\": \"" << jass::t3_f6::FROZEN_FEATURE_ORDER_SHA256 << "\",\n"
               << "  \"positions\": " << positions.size() << ",\n"
               << "  \"order_seed\": " << order_seed << ",\n"
               << "  \"warmup_passes\": 2,\n  \"measured_passes\": " << passes << ",\n"
               << "  \"curriculum_us_per_eval\": "
               << static_cast<double>(t0_ns)/evals/1000.0 << ",\n"
               << "  \"t3_us_per_eval\": "
               << static_cast<double>(t3_ns)/evals/1000.0 << ",\n"
               << "  \"cost_ratio\": "
               << (t0_ns ? static_cast<double>(t3_ns)/static_cast<double>(t0_ns) : 0.0)
               << ",\n"
               << "  \"mlp_residual_us_per_eval\": "
               << static_cast<double>(residual_ns)/evals/1000.0 << ",\n"
               << "  \"family_us_per_eval\": {";
        for (std::size_t i=0;i<5U;++i) {
            if (i) report << ',';
            report << "\n    \"F" << (i+1U) << "\": "
                   << static_cast<double>(family_profile.family_ns[i])
                        /instrumented_evals/1000.0;
        }
        report << "\n  },\n  \"instrumented_passes\": 1,"
               << "\n  \"movegen_calls\": " << family_profile.movegen_calls
               << ",\n  \"response_enumerations_f2\": " << family_profile.response_enumerations
               << ",\n  \"saturations\": " << saturations << ",\n  \"phase_us_per_eval\": {";
        bool first=true;
        for (const auto& [key,b]:phase_buckets) {
            if (!first) report << ',';
            first=false;
            report << "\n    \"" << key << "\": "
                   << static_cast<double>(b.ns)/static_cast<double>(b.n)/1000.0;
        }
        report << "\n  },\n  \"branching_us_per_eval\": {"; first=true;
        for (const auto& [key,b]:branch_buckets) {
            if (!first) report << ',';
            first=false;
            report << "\n    \"" << key << "\": "
                   << static_cast<double>(b.ns)/static_cast<double>(b.n)/1000.0;
        }
        report << "\n  },\n  \"checksum\": " << checksum << "\n}\n";
        std::cout << "T3/F6 runtime probe PASS rows=" << positions.size() << '\n';
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "t3_f6_runtime_probe: " << e.what() << '\n';
        return 1;
    }
}

// SPDX-License-Identifier: AGPL-3.0-or-later
// Score-free random legal-trajectory source for the Scan ceiling benchmark.

#include "bitboard.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "types.hpp"

#include <array>
#include <bit>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>

namespace {

constexpr std::size_t RECORD_SIZE = 38;

template <typename T>
void store_le(char* output, T value) noexcept {
    std::memcpy(output, &value, sizeof(T));
}

std::string fingerprint(const jass::Position& position) {
    std::ostringstream output;
    output << std::hex << std::setfill('0')
           << std::setw(13) << position.white_men() << ':'
           << std::setw(13) << position.white_kings() << ':'
           << std::setw(13) << position.black_men() << ':'
           << std::setw(13) << position.black_kings() << ':'
           << std::dec << (position.side_to_move() == jass::Color::White ? 0 : 1);
    return output.str();
}

void write_zero_target(std::ostream& output, const jass::Position& position) {
    std::array<char, RECORD_SIZE> record{};
    store_le<std::uint64_t>(record.data() + 0, position.white_men());
    store_le<std::uint64_t>(record.data() + 8, position.white_kings());
    store_le<std::uint64_t>(record.data() + 16, position.black_men());
    store_le<std::uint64_t>(record.data() + 24, position.black_kings());
    store_le<std::uint8_t>(
        record.data() + 32,
        position.side_to_move() == jass::Color::White ? 0U : 1U);
    store_le<std::int32_t>(record.data() + 33, 0);
    store_le<std::int8_t>(record.data() + 37, 0);
    output.write(record.data(), static_cast<std::streamsize>(record.size()));
}

const char* phase_for(int pieces) {
    if (pieces >= 30) return "P0";
    if (pieces >= 20) return "P1";
    if (pieces >= 12) return "P2";
    return "P3";
}

}  // namespace

int main(int argc, char** argv) {
    static_assert(std::endian::native == std::endian::little,
                  "JNNW generator requires a little-endian host");
    if (argc < 5 || argc > 8) {
        std::cerr << "usage: jass_scan_ceiling_source_generator <count> <out.jnnw> "
                     "<report.json> <seed> [min_ply=8] [max_ply=160] [min_pieces=9]\n";
        return 2;
    }
    try {
        const std::uint32_t count = static_cast<std::uint32_t>(std::stoul(argv[1]));
        const std::string output_path = argv[2];
        const std::string report_path = argv[3];
        const std::uint64_t seed = std::stoull(argv[4]);
        const int min_ply = argc >= 6 ? std::stoi(argv[5]) : 8;
        const int max_ply = argc >= 7 ? std::stoi(argv[6]) : 160;
        const int min_pieces = argc >= 8 ? std::stoi(argv[7]) : 9;
        if (count == 0 || seed == 0 || min_ply < 0 || max_ply < min_ply
                || min_pieces < 2 || min_pieces > 40) {
            throw std::runtime_error("invalid frozen source-generator arguments");
        }

        std::ofstream output(output_path, std::ios::binary | std::ios::trunc);
        if (!output) throw std::runtime_error("cannot open source JNNW output");
        output.write("JNNW", 4);
        output.write(reinterpret_cast<const char*>(&count), 4);

        std::mt19937_64 random(seed);
        std::unordered_set<std::string> seen;
        seen.reserve(static_cast<std::size_t>(count) * 2U);
        std::array<std::uint64_t, 4> phases{};
        std::uint64_t attempts = 0;
        std::uint64_t terminal_rejected = 0;
        std::uint64_t material_rejected = 0;
        std::uint64_t exact_duplicates = 0;
        std::uint64_t capture_parents = 0;
        const std::uint64_t maximum_attempts = static_cast<std::uint64_t>(count) * 500U + 10'000U;

        std::uint32_t written = 0;
        while (written < count && attempts < maximum_attempts) {
            ++attempts;
            jass::Position position = jass::Position::start_position();
            const int target_ply = min_ply + static_cast<int>(
                random() % static_cast<std::uint64_t>(max_ply - min_ply + 1));
            bool terminal = false;
            for (int ply = 0; ply < target_ply; ++ply) {
                jass::MoveList legal;
                jass::generate_legal_moves(position, legal);
                if (legal.empty()) {
                    terminal = true;
                    break;
                }
                position = position.after(legal[static_cast<std::size_t>(random() % legal.size())]);
            }
            if (terminal) {
                ++terminal_rejected;
                continue;
            }
            const int pieces = jass::popcount(position.occupied());
            if (pieces < min_pieces) {
                ++material_rejected;
                continue;
            }
            jass::MoveList legal;
            jass::generate_legal_moves(position, legal);
            if (legal.empty()) {
                ++terminal_rejected;
                continue;
            }
            const std::string identity = fingerprint(position);
            if (!seen.insert(identity).second) {
                ++exact_duplicates;
                continue;
            }
            capture_parents += static_cast<std::uint64_t>(legal[0].is_capture());
            const char* phase = phase_for(pieces);
            phases[phase[1] - '0'] += 1;
            write_zero_target(output, position);
            ++written;
        }
        output.close();
        if (written != count) {
            throw std::runtime_error("fixed source support exhausted before requested count");
        }

        std::ofstream report(report_path);
        if (!report) throw std::runtime_error("cannot open source report output");
        report << "{\n"
               << "  \"schema\": \"jass.scan_ceiling_score_free_source.v1\",\n"
               << "  \"benchmark_only\": true,\n"
               << "  \"target_blind\": true,\n"
               << "  \"seed\": " << seed << ",\n"
               << "  \"records\": " << written << ",\n"
               << "  \"min_ply\": " << min_ply << ",\n"
               << "  \"max_ply\": " << max_ply << ",\n"
               << "  \"min_pieces\": " << min_pieces << ",\n"
               << "  \"attempts\": " << attempts << ",\n"
               << "  \"terminal_rejected\": " << terminal_rejected << ",\n"
               << "  \"material_rejected\": " << material_rejected << ",\n"
               << "  \"exact_duplicates_rejected\": " << exact_duplicates << ",\n"
               << "  \"capture_parents\": " << capture_parents << ",\n"
               << "  \"records_by_phase\": {\"P0\": " << phases[0]
               << ", \"P1\": " << phases[1] << ", \"P2\": " << phases[2]
               << ", \"P3\": " << phases[3] << "},\n"
               << "  \"evaluations\": 0,\n"
               << "  \"searches\": 0,\n"
               << "  \"scores_generated\": 0,\n"
               << "  \"wdl_generated\": 0,\n"
               << "  \"fits\": 0,\n"
               << "  \"strength_games\": 0,\n"
               << "  \"training_allowed\": false,\n"
               << "  \"tuning_allowed\": false,\n"
               << "  \"calibration_allowed\": false,\n"
               << "  \"model_selection_allowed\": false,\n"
               << "  \"runtime_scale_selection_allowed\": false,\n"
               << "  \"promotion_authorized\": false\n"
               << "}\n";
        std::cout << "score-free source rows=" << written << " seed=" << seed
                  << " attempts=" << attempts << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "scan-ceiling source generator error: " << error.what() << '\n';
        return 3;
    }
}

// SPDX-License-Identifier: AGPL-3.0-or-later
// Offline scalar scoring only for preregistered M5 transfer confirmation.
// Loads the frozen T0/T1 PJTW evaluators and scores already deep-labelled
// sibling states. No D, no micro-search, no fitting, no game play.

#define main micro_search_m4_anchor_drift_main_disabled
#include "micro_search_m4_anchor_drift.cpp"
#undef main

#include <array>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <string>

int main(int argc, char** argv) {
    if (argc != 6) {
        std::cerr << "usage: micro_search_m5_score <children.jnnw> <t0.pjtw> <t1.pjtw> <scores.tsv> <report.json>\n";
        return 2;
    }
    const std::string states_path = argv[1];
    const std::string t0_path = argv[2];
    const std::string t1_path = argv[3];
    const std::string scores_path = argv[4];
    const std::string report_path = argv[5];

    std::string err0, err1;
    auto t0 = load_eval_network(t0_path, &err0);
    auto t1 = load_eval_network(t1_path, &err1);
    if (!t0) {
        std::cerr << "error: cannot reload T0: " << err0 << '\n';
        return 3;
    }
    if (!t1) {
        std::cerr << "error: cannot reload T1: " << err1 << '\n';
        return 3;
    }

    std::ifstream in(states_path, std::ios::binary);
    if (!in) {
        std::cerr << "error: cannot open children JNNW\n";
        return 4;
    }
    std::array<char, 8> header{};
    if (!in.read(header.data(), static_cast<std::streamsize>(header.size())) ||
        std::memcmp(header.data(), "JNNW", 4) != 0) {
        std::cerr << "error: children input is not counted JNNW\n";
        return 4;
    }
    const std::uint32_t n = load_le<std::uint32_t>(header.data() + 4);
    if (n == 0) {
        std::cerr << "error: empty M5 children corpus\n";
        return 4;
    }

    std::ofstream scores(scores_path);
    if (!scores) {
        std::cerr << "error: cannot create score TSV\n";
        return 5;
    }
    scores << "row_index\tt0_parent\tt1_parent\n";

    DiskRow row{};
    for (std::uint32_t i = 0; i < n; ++i) {
        if (!read_row(in, row)) {
            std::cerr << "error: truncated children JNNW at row " << i << '\n';
            return 4;
        }
        if (!valid_row(row)) {
            std::cerr << "error: invalid M5 child row " << i << '\n';
            return 4;
        }
        if (row.score != 0 || row.wdl != 0) {
            std::cerr << "error: M5 child target bytes must remain zero at row " << i << '\n';
            return 4;
        }
        const Position child = position_from_row(row);
        // Child STM is the opponent of the parent mover, so negate both leaf
        // evaluations into the parent point of view, exactly as the deep teacher
        // computes t_baseline_parent for T0.
        const int t0_parent = -t0->evaluate(child);
        const int t1_parent = -t1->evaluate(child);
        scores << i << '\t' << t0_parent << '\t' << t1_parent << '\n';
    }
    char trailing = 0;
    if (in.read(&trailing, 1)) {
        std::cerr << "error: children JNNW has trailing bytes\n";
        return 4;
    }
    scores.close();

    std::ofstream report(report_path);
    if (!report) {
        std::cerr << "error: cannot create score report\n";
        return 5;
    }
    report << "{\n"
           << "  \"schema\": \"jass.micro_search_m5_scalar_score.v1\",\n"
           << "  \"rows\": " << n << ",\n"
           << "  \"score_convention\": \"higher_is_better_for_parent\",\n"
           << "  \"t0_t1_serialize_reload\": true,\n"
           << "  \"d_present_at_inference\": false,\n"
           << "  \"micro_search_present_at_inference\": false,\n"
           << "  \"runtime_micro_search\": false,\n"
           << "  \"fits\": 0,\n"
           << "  \"strength_games\": 0,\n"
           << "  \"promotion_authorized\": false\n"
           << "}\n";
    return 0;
}

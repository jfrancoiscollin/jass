// SPDX-License-Identifier: AGPL-3.0-or-later
// Exact serialize/reload anchor drift evaluator for preregistered M4.
// Reads only zero-target JNNW states and two real PJTW v3 evaluators.

#include "scan_eval.hpp"

#define load_pattern_jass_network load_eval_network
#define main deep_sibling_teacher_main_disabled
#include "deep_sibling_teacher.cpp"
#undef main
#undef load_pattern_jass_network

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

int main(int argc, char** argv) {
    if (argc != 5) {
        std::cerr << "usage: micro_search_m4_anchor_drift <states.jnnw> <t0.pjtw> <t1.pjtw> <report.json>\n";
        return 2;
    }
    const std::string states_path = argv[1];
    const std::string t0_path = argv[2];
    const std::string t1_path = argv[3];
    const std::string report_path = argv[4];

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
        std::cerr << "error: cannot open anchor states\n";
        return 4;
    }
    std::array<char, 8> header{};
    if (!in.read(header.data(), static_cast<std::streamsize>(header.size())) ||
        std::memcmp(header.data(), "JNNW", 4) != 0) {
        std::cerr << "error: anchor input is not counted JNNW\n";
        return 4;
    }
    const std::uint32_t n = load_le<std::uint32_t>(header.data() + 4);
    if (n != 500000U) {
        std::cerr << "error: M4 anchor must contain exactly 500000 states\n";
        return 4;
    }

    long double sum_sq = 0.0L;
    int max_abs = 0;
    std::vector<int> diffs;
    diffs.reserve(n);
    DiskRow row{};
    for (std::uint32_t i = 0; i < n; ++i) {
        if (!read_row(in, row)) {
            std::cerr << "error: truncated anchor JNNW at row " << i << '\n';
            return 4;
        }
        if (!valid_row(row)) {
            std::cerr << "error: invalid anchor row " << i << '\n';
            return 4;
        }
        if (row.score != 0 || row.wdl != 0) {
            std::cerr << "error: anchor target bytes nonzero at row " << i << '\n';
            return 4;
        }
        const Position pos = position_from_row(row);
        const int a = t0->evaluate(pos);
        const int b = t1->evaluate(pos);
        const int d = std::abs(b - a);
        diffs.push_back(d);
        sum_sq += static_cast<long double>(d) * static_cast<long double>(d);
        max_abs = std::max(max_abs, d);
    }
    char trailing = 0;
    if (in.read(&trailing, 1)) {
        std::cerr << "error: anchor JNNW has trailing bytes\n";
        return 4;
    }
    std::sort(diffs.begin(), diffs.end());
    const std::size_t p99_rank = (static_cast<std::size_t>(n) * 99U + 99U) / 100U;
    const int p99 = diffs.at(std::max<std::size_t>(1, p99_rank) - 1);
    const double rms = std::sqrt(static_cast<double>(sum_sq / static_cast<long double>(n)));

    std::ofstream out(report_path);
    if (!out) {
        std::cerr << "error: cannot create anchor report\n";
        return 5;
    }
    out.setf(std::ios::fixed);
    out.precision(12);
    out << "{\n"
        << "  \"schema\": \"jass.micro_search_m4_anchor_drift.v1\",\n"
        << "  \"states\": " << n << ",\n"
        << "  \"rms_abs_cp\": " << rms << ",\n"
        << "  \"p99_abs_cp\": " << p99 << ",\n"
        << "  \"max_abs_cp\": " << max_abs << ",\n"
        << "  \"serialize_reload\": true,\n"
        << "  \"source_labels_read\": false,\n"
        << "  \"deep_scores_read\": 0,\n"
        << "  \"runtime_micro_search\": false,\n"
        << "  \"promotion_authorized\": false\n"
        << "}\n";
    return 0;
}

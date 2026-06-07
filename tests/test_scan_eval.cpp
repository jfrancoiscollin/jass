// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Tests for the full Scan-style structured eval (PJTW v3, src/scan_eval.*).
// We verify the consistency-critical pieces : the extras feature vector,
// the MG/EG phase interpolation, the black→stm sign flip, and the v3
// file round-trip.

#include "test_framework.hpp"

#include "position.hpp"
#include "scan_eval.hpp"

#include "../pattern_jass/src/pattern.hpp"

#include <cstdio>
#include <cstring>
#include <fstream>
#include <string>
#include <string_view>
#include <unistd.h>

using namespace jass;
using namespace jass::scan_eval;

namespace {

Position parse(std::string_view fen) {
    auto p = Position::from_fen(fen);
    JASS_CHECK(p.has_value());
    return p.value_or(Position{});
}

ScanWeights zero_weights(std::uint32_t scale) {
    ScanWeights w;
    w.scale = scale;
    w.pat_mg.assign(pattern_jass::TOTAL_BUCKETS, 0);
    w.pat_eg.assign(pattern_jass::TOTAL_BUCKETS, 0);
    // ext_mg / ext_eg are std::array, value-initialised to 0.
    return w;
}

// --- extras --------------------------------------------------------------

void test_extras_start_position() {
    const Position p = Position::start_position();
    std::array<float, NUM_EXTRAS> e{};
    compute_extras(p, e);

    JASS_CHECK_EQ(static_cast<int>(e[EXTRA_BLACK_MEN]), 20);
    JASS_CHECK_EQ(static_cast<int>(e[EXTRA_WHITE_MEN]), 20);
    // No kings on the board → all PST one-hots are zero.
    for (int i = EXTRA_BK_PST_BASE; i < EXTRA_BK_PST_BASE + 100; ++i) {
        JASS_CHECK_EQ(static_cast<int>(e[static_cast<std::size_t>(i)]), 0);
    }
    // The FMJD start is left-right symmetric → balance 0 on both sides.
    JASS_CHECK_EQ(static_cast<int>(e[EXTRA_BLACK_BAL]), 0);
    JASS_CHECK_EQ(static_cast<int>(e[EXTRA_WHITE_BAL]), 0);
    // 180°-symmetric position → equal mobility, and strictly positive
    // (the front rank can advance into the two empty central rows).
    JASS_CHECK(e[EXTRA_BLACK_MOB] > 0.0f);
    JASS_CHECK_EQ(static_cast<int>(e[EXTRA_BLACK_MOB]),
                  static_cast<int>(e[EXTRA_WHITE_MOB]));
}

void test_extras_king_pst_one_hot() {
    // One black king on 33, one white king on 28, plus a man each side.
    const Position p = parse("W:WK28,31:BK33,1");
    std::array<float, NUM_EXTRAS> e{};
    compute_extras(p, e);

    JASS_CHECK_EQ(static_cast<int>(e[EXTRA_BK_PST_BASE + (33 - 1)]), 1);
    JASS_CHECK_EQ(static_cast<int>(e[EXTRA_WK_PST_BASE + (28 - 1)]), 1);
    JASS_CHECK_EQ(static_cast<int>(e[EXTRA_BLACK_MEN]), 1);
    JASS_CHECK_EQ(static_cast<int>(e[EXTRA_WHITE_MEN]), 1);
    // A centralised king has slide moves available.
    JASS_CHECK(e[EXTRA_BLACK_MOB] > 0.0f);
    JASS_CHECK(e[EXTRA_WHITE_MOB] > 0.0f);
}

// --- evaluate : phase interpolation + sign -------------------------------

void test_evaluate_midgame_uses_mg_bank() {
    // Full board → stage 40 → wmg = 1, weg = 0 : only the MG bank counts.
    ScanWeights w = zero_weights(100);
    w.ext_mg[EXTRA_BLACK_MEN] = 5;   // +5 piece-units per black man (MG)
    w.ext_eg[EXTRA_BLACK_MEN] = 999; // EG bank must be ignored at stage 40

    ScanEvalNetwork net(std::move(w));
    const Position p = Position::start_position();  // white to move, 20 black men
    // eval_black = 1*(5*20) = 100 piece-units ; cp = 100*100/100 = 100 ;
    // white to move → stm-POV = -100.
    JASS_CHECK_EQ(net.evaluate(p), -100);
}

void test_evaluate_endgame_uses_eg_bank() {
    // 2 men/side → stage 4 → wmg = 0.1, weg = 0.9.
    ScanWeights w = zero_weights(100);
    w.ext_mg[EXTRA_BLACK_MEN] = 0;
    w.ext_eg[EXTRA_BLACK_MEN] = 10;  // +10 per black man (EG)

    ScanEvalNetwork net(std::move(w));
    const Position p = parse("B:W31,32:B1,2");  // black to move, 2 black men
    // eval_black = 0.1*(0) + 0.9*(10*2) = 18 ; cp = 18*100/100 = 18 ;
    // black to move → stm-POV = +18.
    JASS_CHECK_EQ(net.evaluate(p), 18);
}

void test_evaluate_sign_flips_with_stm() {
    ScanWeights w = zero_weights(100);
    w.ext_mg[EXTRA_BLACK_MEN] = 5;
    w.ext_eg[EXTRA_BLACK_MEN] = 5;
    ScanEvalNetwork net(std::move(w));

    // Same board, opposite side to move → opposite stm-POV scores.
    const Position pw = parse("W:W31,32,33:B1,2,3");
    const Position pb = parse("B:W31,32,33:B1,2,3");
    JASS_CHECK_EQ(net.evaluate(pw), -net.evaluate(pb));
}

// --- v3 file round-trip --------------------------------------------------

void test_v3_file_roundtrip() {
    const std::uint32_t n_pat = pattern_jass::TOTAL_BUCKETS;
    const std::uint32_t n_ext = static_cast<std::uint32_t>(NUM_EXTRAS);

    std::string tmpl = jass_tmp_template("jass_scan_v3");
    const int fd = mkstemp(tmpl.data());
    JASS_CHECK(fd != -1);
    if (fd == -1) return;   // no writable tmp → skip rather than write garbage
    close(fd);
    const std::string path = tmpl;

    // Write a v3 file with a couple of distinctive non-zero weights.
    {
        std::ofstream f(path, std::ios::binary);
        auto u32 = [&](std::uint32_t v) {
            f.write(reinterpret_cast<const char*>(&v), 4);
        };
        u32(V3_MAGIC); u32(V3_VERSION); u32(1000); u32(n_pat); u32(n_ext);
        std::vector<std::int32_t> block(n_pat, 0);
        block[7] = 123;                       // pat_mg[7]
        f.write(reinterpret_cast<const char*>(block.data()),
                static_cast<std::streamsize>(block.size() * 4));
        block[7] = 0; block[9] = -456;        // pat_eg[9]
        f.write(reinterpret_cast<const char*>(block.data()),
                static_cast<std::streamsize>(block.size() * 4));
        std::vector<std::int32_t> ext(n_ext, 0);
        ext[EXTRA_WHITE_MOB] = 11;            // ext_mg
        f.write(reinterpret_cast<const char*>(ext.data()),
                static_cast<std::streamsize>(ext.size() * 4));
        ext[EXTRA_WHITE_MOB] = 0; ext[EXTRA_BLACK_MEN] = 22;  // ext_eg
        f.write(reinterpret_cast<const char*>(ext.data()),
                static_cast<std::streamsize>(ext.size() * 4));
    }

    std::string err;
    auto w = load_scan_weights(path, &err);
    JASS_CHECK(w.has_value());
    if (w) {
        JASS_CHECK_EQ(static_cast<int>(w->scale), 1000);
        JASS_CHECK_EQ(static_cast<int>(w->pat_mg.size()),
                      static_cast<int>(n_pat));
        JASS_CHECK_EQ(w->pat_mg[7], 123);
        JASS_CHECK_EQ(w->pat_eg[9], -456);
        JASS_CHECK_EQ(w->ext_mg[EXTRA_WHITE_MOB], 11);
        JASS_CHECK_EQ(w->ext_eg[EXTRA_BLACK_MEN], 22);
    }

    // The unified loader must dispatch a v3 file to ScanEvalNetwork.
    auto net = load_eval_network(path, &err);
    JASS_CHECK(net != nullptr);

    std::remove(path.c_str());
}

void test_v3_loader_rejects_v1() {
    // A 16-byte v1-style header must NOT be parsed as v3.
    std::string tmpl = jass_tmp_template("jass_scan_v1");
    const int fd = mkstemp(tmpl.data());
    JASS_CHECK(fd != -1);
    if (fd == -1) return;
    close(fd);
    const std::string path = tmpl;
    {
        std::ofstream f(path, std::ios::binary);
        std::uint32_t hdr[4] = {V3_MAGIC, 1U, pattern_jass::TOTAL_BUCKETS, 1000U};
        f.write(reinterpret_cast<const char*>(hdr), sizeof(hdr));
    }
    std::string err;
    auto w = load_scan_weights(path, &err);
    JASS_CHECK(!w.has_value());  // version 1 → rejected by the v3 loader
    std::remove(path.c_str());
}

}  // namespace

void run_scan_eval_tests() {
    test_extras_start_position();
    test_extras_king_pst_one_hot();
    test_evaluate_midgame_uses_mg_bank();
    test_evaluate_endgame_uses_eg_bank();
    test_evaluate_sign_flips_with_stm();
    test_v3_file_roundtrip();
    test_v3_loader_rejects_v1();
}

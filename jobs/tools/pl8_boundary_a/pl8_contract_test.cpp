// SPDX-License-Identifier: AGPL-3.0-or-later
#include "pl8.hpp"
#include "bitboard.hpp"
#include "board.hpp"
#include "scan_eval.hpp"
#include "../pattern_jass/src/pattern.hpp"

#include <array>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <string>
#include <unistd.h>

using namespace jass;

namespace {
int failures = 0;
#define CHECK(x) do { if (!(x)) { ++failures; std::cerr << "FAIL " << __LINE__ << ": " #x "\n"; } } while (0)

Position parse(const char* fen) {
    auto p = Position::from_fen(fen);
    if (!p) throw std::runtime_error("bad test FEN");
    return *p;
}

scan_eval::ScanWeights test_weights() {
    scan_eval::ScanWeights w;
    w.scale = 1000;
    w.pat.assign(pattern_jass::TOTAL_BUCKETS, {});
    for (std::size_t i = 0; i < w.pat.size(); ++i) {
        if ((i % 9973U) == 0U) {
            w.pat[i].mg = static_cast<std::int32_t>((i % 101U) - 50U);
            w.pat[i].eg = static_cast<std::int32_t>((i % 79U) - 39U);
        }
    }
    for (std::size_t i = 0; i < static_cast<std::size_t>(scan_eval::NUM_EXTRAS); ++i) {
        w.ext_mg[i] = static_cast<std::int32_t>((i % 11U) - 5U);
        w.ext_eg[i] = static_cast<std::int32_t>((i % 13U) - 6U);
    }
    return w;
}

bool same_model(const pl8::Model& a, const pl8::Model& b) {
    return a.mu == b.mu && a.sigma == b.sigma && a.w1 == b.w1
        && a.b1 == b.b1 && a.w2 == b.w2 && a.b2 == b.b2
        && a.shrink == b.shrink && a.curriculum_sha256 == b.curriculum_sha256;
}

std::string temp_path() {
    std::string p = "/tmp/pl8_contract_XXXXXX";
    int fd = mkstemp(p.data());
    if (fd < 0) throw std::runtime_error("mkstemp failed");
    close(fd);
    return p;
}

void test_canonical_and_inputs() {
    static_assert(pattern_jass::NUM_PATTERNS == 8);
    static_assert(scan_eval::NUM_EXTRAS == 120);
    static_assert(pl8::INPUT_WIDTH == 138);
    static_assert(pl8::LATENT_WIDTH == 8);
    static_assert(pl8::LEARNED_PARAMS == 1121);

    const Position white = parse("W:W18,23,K29:B7,12,14,K34");
    const Position canon = pl8::canonical_stm_black(white);
    CHECK(canon.side_to_move() == Color::Black);
    CHECK(canon.halfmove_clock() == white.halfmove_clock());
    CHECK(canon.white_men() == ((Bitboard{1} << square_to_bit(static_cast<Square>(51-7)))
                              | (Bitboard{1} << square_to_bit(static_cast<Square>(51-12)))
                              | (Bitboard{1} << square_to_bit(static_cast<Square>(51-14)))));
    CHECK(canon.black_men() == ((Bitboard{1} << square_to_bit(static_cast<Square>(51-18)))
                              | (Bitboard{1} << square_to_bit(static_cast<Square>(51-23)))));
    CHECK(canon.white_kings() == (Bitboard{1} << square_to_bit(static_cast<Square>(51-34))));
    CHECK(canon.black_kings() == (Bitboard{1} << square_to_bit(static_cast<Square>(51-29))));
    CHECK(std::fabs(pl8::tempo_wmg_exact(white) - pl8::tempo_wmg_exact(canon)) < 1e-15);

    auto w = test_weights();
    scan_eval::ScanWeights manual = w;
    pl8::FeatureExtractor ext(std::move(w));
    const auto x = ext.extract(white);

    std::array<std::uint32_t, pattern_jass::NUM_PATTERNS> idx{};
    pattern_jass::extract_all(scan_eval::pat_black(canon), scan_eval::pat_white(canon), idx);
    constexpr auto offsets = pattern_jass::pattern_offsets();
    for (std::size_t p = 0; p < pattern_jass::NUM_PATTERNS; ++p) {
        const auto col = static_cast<std::size_t>(offsets[p] + idx[p] % pattern_jass::BUCKETS_PER_PATTERN);
        CHECK(x[2*p] == 100.0 * static_cast<double>(manual.pat[col].mg) / manual.scale);
        CHECK(x[2*p+1] == 100.0 * static_cast<double>(manual.pat[col].eg) / manual.scale);
    }
    std::array<float, scan_eval::NUM_EXTRAS> raw{};
    scan_eval::compute_extras(canon, raw);
    for (std::size_t i = 0; i < pl8::EXTRA_INPUTS; ++i)
        CHECK(x[pl8::PATTERN_INPUTS+i] == static_cast<double>(raw[i]));
    CHECK(x[136] == pl8::tempo_wmg_exact(canon));
    scan_eval::ScanEvalNetwork base(std::move(manual));
    CHECK(x[137] == static_cast<double>(base.evaluate(white)));

    const auto image = pl8::canonical_stm_black(canon);
    CHECK(image.white_men() == canon.white_men());
    CHECK(image.black_men() == canon.black_men());
}

void test_zero_residual_and_roundtrip() {
    pl8::Model m;
    m.sigma.fill(1.0);
    for (std::size_t i = 0; i < m.mu.size(); ++i) m.mu[i] = static_cast<double>(i) / 17.0;
    for (std::size_t i = 0; i < m.w1.size(); ++i) m.w1[i] = (static_cast<int>(i % 9U)-4) * 1e-4;
    for (std::size_t i = 0; i < m.b1.size(); ++i) m.b1[i] = static_cast<double>(i) * 1e-3;
    for (std::size_t i = 0; i < m.w2.size(); ++i) m.w2[i] = (static_cast<int>(i)-4) * 1e-2;
    m.b2 = 0.125;
    m.shrink = 0.75;

    const std::string path = temp_path();
    std::string err;
    CHECK(pl8::save_model(path, m, &err));
    auto loaded = pl8::load_model(path, &err);
    CHECK(loaded.has_value());
    if (loaded) CHECK(same_model(m, *loaded));

    {
        std::ofstream out(path, std::ios::binary | std::ios::app);
        out.put('x');
    }
    CHECK(!pl8::load_model(path, &err).has_value());
    std::remove(path.c_str());

    pl8::Model zero;
    zero.sigma.fill(1.0);
    auto w = test_weights();
    scan_eval::ScanWeights base_w = w;
    pl8::Network net(std::move(w), zero);
    scan_eval::ScanEvalNetwork base(std::move(base_w));
    for (const char* fen : {
            "B:W26,31,32,37,K41:B12,16,21,K27",
            "W:W18,23,K29:B7,12,14,K34",
            "B:W31,32,36:B17,22,27"}) {
        const Position p = parse(fen);
        CHECK(net.evaluate(p) == base.evaluate(p));
    }
}

} // namespace

int main() {
    try {
        test_canonical_and_inputs();
        test_zero_residual_and_roundtrip();
    } catch (const std::exception& e) {
        std::cerr << "exception: " << e.what() << '\n';
        return 2;
    }
    if (failures) {
        std::cerr << failures << " PL8 contract checks failed\n";
        return 1;
    }
    std::cout << "PL8 exact contract PASS\n";
    return 0;
}

// SPDX-License-Identifier: AGPL-3.0-or-later
#include "pl8.hpp"

#include "bitboard.hpp"
#include "board.hpp"
#include "../pattern_jass/src/pattern.hpp"

#include <algorithm>
#include <bit>
#include <cmath>
#include <cstring>
#include <fstream>
#include <limits>
#include <utility>

namespace jass::pl8 {
namespace {

constexpr std::array<unsigned char, 4> MAGIC{{'P','L','8','P'}};
constexpr std::uint32_t VERSION = 1U;

Piece swapped(Piece p) noexcept {
    switch (p) {
    case Piece::WhiteMan:  return Piece::BlackMan;
    case Piece::BlackMan:  return Piece::WhiteMan;
    case Piece::WhiteKing: return Piece::BlackKing;
    case Piece::BlackKing: return Piece::WhiteKing;
    default: return Piece::None;
    }
}

void write_u32(std::ostream& out, std::uint32_t v) {
    const unsigned char b[4] = {
        static_cast<unsigned char>(v & 0xffU),
        static_cast<unsigned char>((v >> 8) & 0xffU),
        static_cast<unsigned char>((v >> 16) & 0xffU),
        static_cast<unsigned char>((v >> 24) & 0xffU),
    };
    out.write(reinterpret_cast<const char*>(b), 4);
}

bool read_u32(std::istream& in, std::uint32_t& v) {
    unsigned char b[4]{};
    in.read(reinterpret_cast<char*>(b), 4);
    if (!in) return false;
    v = static_cast<std::uint32_t>(b[0])
      | (static_cast<std::uint32_t>(b[1]) << 8)
      | (static_cast<std::uint32_t>(b[2]) << 16)
      | (static_cast<std::uint32_t>(b[3]) << 24);
    return true;
}

void write_f64(std::ostream& out, double x) {
    static_assert(sizeof(double) == sizeof(std::uint64_t));
    const std::uint64_t u = std::bit_cast<std::uint64_t>(x);
    unsigned char b[8]{};
    for (unsigned i = 0; i < 8; ++i)
        b[i] = static_cast<unsigned char>((u >> (8U * i)) & 0xffULL);
    out.write(reinterpret_cast<const char*>(b), 8);
}

bool read_f64(std::istream& in, double& x) {
    unsigned char b[8]{};
    in.read(reinterpret_cast<char*>(b), 8);
    if (!in) return false;
    std::uint64_t u = 0;
    for (unsigned i = 0; i < 8; ++i)
        u |= static_cast<std::uint64_t>(b[i]) << (8U * i);
    x = std::bit_cast<double>(u);
    return true;
}

template <std::size_t N>
void write_array(std::ostream& out, const std::array<double, N>& a) {
    for (double x : a) write_f64(out, x);
}

template <std::size_t N>
bool read_array(std::istream& in, std::array<double, N>& a) {
    for (double& x : a) if (!read_f64(in, x)) return false;
    return true;
}

bool finite_model(const Model& m) noexcept {
    auto finite = [](const auto& a) {
        for (double x : a) if (!std::isfinite(x)) return false;
        return true;
    };
    if (!finite(m.mu) || !finite(m.sigma) || !finite(m.w1)
        || !finite(m.b1) || !finite(m.w2)
        || !std::isfinite(m.b2) || !std::isfinite(m.shrink)) return false;
    if (m.shrink < 0.0 || m.shrink > 1.0) return false;
    for (double s : m.sigma) if (!(s >= 1.0e-6)) return false;
    return m.curriculum_sha256 == CURRICULUM_SHA256;
}

}  // namespace

Position canonical_stm_black(const Position& pos) noexcept {
    if (pos.side_to_move() == Color::Black) return pos;
    Position out;
    out.clear();
    out.set_side_to_move(Color::Black);
    for (int raw = 1; raw <= 50; ++raw) {
        const Square from = static_cast<Square>(raw);
        const Piece p = pos.piece_at(from);
        if (p == Piece::None) continue;
        const Square to = static_cast<Square>(51 - raw);
        out.add_piece(to, swapped(p));
    }
    out.set_halfmove_clock(pos.halfmove_clock());
    return out;
}

double tempo_wmg_exact(const Position& pos) noexcept {
    // Exact algebra of scan_eval.cpp's frozen JASS_TEMPO_STAGE path, expressed
    // by square rows to keep PL8 independent of search/movegen semantics.
    long tempo = 0;
    for (Bitboard b = pos.black_men(); b; ) {
        const Square sq = pop_lsb(b);
        tempo += 9L - static_cast<long>(row_of(sq));
    }
    for (Bitboard b = pos.white_men(); b; ) {
        const Square sq = pop_lsb(b);
        tempo += static_cast<long>(row_of(sq));
    }
    const double w = static_cast<double>(tempo) / 300.0;
    return std::clamp(w, 0.0, 1.0);
}

FeatureExtractor::FeatureExtractor(scan_eval::ScanWeights weights)
    : weights_(std::move(weights)),
      base_(std::make_unique<scan_eval::ScanEvalNetwork>(weights_)) {
    static_assert(pattern_jass::NUM_PATTERNS == 8,
                  "PL8 prereg requires exactly 8 active patterns");
    static_assert(scan_eval::NUM_EXTRAS == 120,
                  "PL8 prereg requires exact 120-extra production architecture");
}

scan_eval::PatPair FeatureExtractor::pair_at(std::size_t global_col) const noexcept {
    if (!weights_.remap8.empty()) return weights_.pat[weights_.remap8[global_col]];
    if (!weights_.remap.empty()) return weights_.pat[weights_.remap[global_col]];
    return weights_.pat[global_col];
}

int FeatureExtractor::base_score(const Position& pos) const noexcept {
    return base_->evaluate(pos);
}

std::array<double, INPUT_WIDTH> FeatureExtractor::extract(const Position& pos) const noexcept {
    std::array<double, INPUT_WIDTH> out{};
    const Position canon = canonical_stm_black(pos);
    std::array<std::uint32_t, pattern_jass::NUM_PATTERNS> idx{};
    pattern_jass::extract_all(scan_eval::pat_black(canon), scan_eval::pat_white(canon), idx);
    static constexpr auto offsets = pattern_jass::pattern_offsets();
    const double scale = static_cast<double>(weights_.scale);
    for (std::size_t p = 0; p < pattern_jass::NUM_PATTERNS; ++p) {
        const std::uint32_t r = idx[p] % pattern_jass::BUCKETS_PER_PATTERN;
        const scan_eval::PatPair pair = pair_at(offsets[p] + r);
        out[2U * p] = 100.0 * static_cast<double>(pair.mg) / scale;
        out[2U * p + 1U] = 100.0 * static_cast<double>(pair.eg) / scale;
    }
    std::array<float, scan_eval::NUM_EXTRAS> extras{};
    scan_eval::compute_extras(canon, extras);
    for (std::size_t i = 0; i < EXTRA_INPUTS; ++i)
        out[PATTERN_INPUTS + i] = static_cast<double>(extras[i]);
    out[136] = tempo_wmg_exact(canon);
    out[137] = static_cast<double>(base_->evaluate(pos));
    return out;
}

Network::Network(scan_eval::ScanWeights curriculum, Model model)
    : extractor_(std::move(curriculum)), model_(std::move(model)) {}

int Network::evaluate(const Position& pos) const noexcept {
    const auto x = extractor_.extract(pos);
    std::array<double, LATENT_WIDTH> z{};
    for (std::size_t h = 0; h < LATENT_WIDTH; ++h) {
        double a = model_.b1[h];
        const std::size_t row = h * INPUT_WIDTH;
        for (std::size_t j = 0; j < INPUT_WIDTH; ++j) {
            const double xhat = (x[j] - model_.mu[j]) / model_.sigma[j];
            a += model_.w1[row + j] * xhat;
        }
        z[h] = std::tanh(a);
    }
    double residual = model_.b2;
    for (std::size_t h = 0; h < LATENT_WIDTH; ++h)
        residual += model_.w2[h] * z[h];
    const double pre = x[137] + model_.shrink * residual;
    if (!std::isfinite(pre)) return static_cast<int>(x[137]);
    const long long rounded = std::llround(pre);
    return static_cast<int>(std::clamp(rounded, -20000LL, 20000LL));
}

bool save_model(const std::string& path, const Model& model, std::string* error) {
    if (!finite_model(model)) {
        if (error) *error = "PL8 model contract invalid";
        return false;
    }
    std::ofstream out(path, std::ios::binary);
    if (!out) { if (error) *error = "cannot create PL8 model"; return false; }
    out.write(reinterpret_cast<const char*>(MAGIC.data()), 4);
    write_u32(out, VERSION);
    write_u32(out, static_cast<std::uint32_t>(INPUT_WIDTH));
    write_u32(out, static_cast<std::uint32_t>(LATENT_WIDTH));
    write_u32(out, static_cast<std::uint32_t>(LEARNED_PARAMS));
    out.write(model.curriculum_sha256.data(), 64);
    write_f64(out, model.shrink);
    write_array(out, model.mu);
    write_array(out, model.sigma);
    write_array(out, model.w1);
    write_array(out, model.b1);
    write_array(out, model.w2);
    write_f64(out, model.b2);
    if (!out) { if (error) *error = "PL8 model write failed"; return false; }
    return true;
}

std::optional<Model> load_model(const std::string& path, std::string* error) {
    std::ifstream in(path, std::ios::binary);
    if (!in) { if (error) *error = "cannot open PL8 model"; return std::nullopt; }
    std::array<unsigned char, 4> magic{};
    in.read(reinterpret_cast<char*>(magic.data()), 4);
    std::uint32_t version=0, width=0, latent=0, params=0;
    if (!in || magic != MAGIC || !read_u32(in, version) || !read_u32(in, width)
        || !read_u32(in, latent) || !read_u32(in, params)
        || version != VERSION || width != INPUT_WIDTH || latent != LATENT_WIDTH
        || params != LEARNED_PARAMS) {
        if (error) *error = "PL8 header mismatch";
        return std::nullopt;
    }
    Model m;
    std::array<char, 64> sha{};
    in.read(sha.data(), static_cast<std::streamsize>(sha.size()));
    m.curriculum_sha256.assign(sha.data(), sha.size());
    if (!read_f64(in, m.shrink) || !read_array(in, m.mu) || !read_array(in, m.sigma)
        || !read_array(in, m.w1) || !read_array(in, m.b1) || !read_array(in, m.w2)
        || !read_f64(in, m.b2)) {
        if (error) *error = "PL8 payload truncated";
        return std::nullopt;
    }
    char extra=0;
    if (in.read(&extra, 1)) {
        if (error) *error = "PL8 trailing bytes";
        return std::nullopt;
    }
    if (!finite_model(m)) {
        if (error) *error = "PL8 payload contract invalid";
        return std::nullopt;
    }
    return m;
}

std::unique_ptr<Network> load_network(const std::string& curriculum_path,
                                      const std::string& model_path,
                                      std::string* error) {
    auto model = load_model(model_path, error);
    if (!model) return nullptr;
    auto weights = scan_eval::load_scan_weights(curriculum_path, error);
    if (!weights) return nullptr;
    if (weights->fm_rank != 0) {
        if (error) *error = "PL8 requires frozen linear CURRICULUM v3";
        return nullptr;
    }
    return std::make_unique<Network>(std::move(*weights), std::move(*model));
}

}  // namespace jass::pl8

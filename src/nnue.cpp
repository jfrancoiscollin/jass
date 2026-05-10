// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "nnue.hpp"

#include "bitboard.hpp"
#include "board.hpp"
#include "eval.hpp"
#include "nnue_default_data.hpp"

#include <cstring>
#include <fstream>
#include <string>

namespace jass {

namespace {

// Mirror of eval.cpp's hand-tuned constants. We duplicate them here on
// purpose: the network defines the effective evaluation once trained,
// and we don't want it to silently drift if eval.cpp's tables ever
// change without a corresponding NNUE refit.
constexpr int ADV_STEP        = 4;
constexpr int EDGE_PENALTY    = 3;
constexpr int BACKRANK_BONUS  = 5;

int file_of_sq(int s) noexcept {
    const int r = (s - 1) / 5;
    const int c = (s - 1) % 5;
    return (r % 2 == 0) ? (2 * c + 1) : (2 * c);
}

int iabs(int x) noexcept { return x < 0 ? -x : x; }

}  // namespace

LinearNetwork::LinearNetwork() {
    for (int s = FIRST_SQUARE; s <= LAST_SQUARE; ++s) {
        const int r        = (s - 1) / 5;
        const int file     = file_of_sq(s);
        const int edge     = (file == 0 || file == 9) ? -EDGE_PENALTY : 0;
        const int wman_psq = ADV_STEP * (9 - r) + (r == 9 ? BACKRANK_BONUS : 0) + edge;
        const int bman_psq = ADV_STEP * r       + (r == 0 ? BACKRANK_BONUS : 0) + edge;
        const int d2       = iabs(2 * r - 9) + iabs(2 * file - 9);
        const int king_psq = 16 - d2;

        const std::size_t idx = static_cast<std::size_t>(s - 1);
        weights_[idx][0] =  MAN_VALUE  + wman_psq;
        weights_[idx][1] =  KING_VALUE + king_psq;
        weights_[idx][2] = -(MAN_VALUE  + bman_psq);
        weights_[idx][3] = -(KING_VALUE + king_psq);
    }
}

namespace {

template <std::size_t Kind>
int sum_kind(const std::array<std::array<std::int32_t, 4>, NUM_SQUARES>& w,
             Bitboard bb) noexcept {
    int s = 0;
    while (bb) {
        const int bit = square_to_bit(pop_lsb(bb));
        s += w[static_cast<std::size_t>(bit)][Kind];
    }
    return s;
}

}  // namespace

int LinearNetwork::evaluate(const Position& pos) const noexcept {
    int score = 0;
    score += sum_kind<0>(weights_, pos.white_men());
    score += sum_kind<1>(weights_, pos.white_kings());
    score += sum_kind<2>(weights_, pos.black_men());
    score += sum_kind<3>(weights_, pos.black_kings());
    score += (pos.side_to_move() == Color::White) ? TEMPO_BONUS : -TEMPO_BONUS;
    return (pos.side_to_move() == Color::White) ? score : -score;
}

bool LinearNetwork::load(std::string_view path) {
    std::ifstream f(std::string{path}, std::ios::binary);
    if (!f) return false;
    decltype(weights_) tmp{};
    f.read(reinterpret_cast<char*>(tmp.data()),
           static_cast<std::streamsize>(sizeof(tmp)));
    if (!f || f.gcount() != static_cast<std::streamsize>(sizeof(tmp))) {
        return false;
    }
    weights_ = tmp;
    return true;
}

bool LinearNetwork::save(std::string_view path) const {
    std::ofstream f(std::string{path}, std::ios::binary);
    if (!f) return false;
    f.write(reinterpret_cast<const char*>(weights_.data()),
            static_cast<std::streamsize>(sizeof(weights_)));
    return f.good();
}

bool LinearNetwork::load_from_bytes(const unsigned char* data,
                                    std::size_t          n) {
    if (data == nullptr || n != sizeof(weights_)) return false;
    std::memcpy(weights_.data(), data, n);
    return true;
}

// ---------------------------------------------------------------------------
// MLPNetwork
// ---------------------------------------------------------------------------

namespace {

// Add column `feat` of W1 (row-major, HIDDEN1 × INPUT_DIM) to `h1`.
// Equivalent to one sparse multiply-add per active input feature.
inline void add_w1_column(const std::array<float,
                              MLPNetwork::HIDDEN1 * MLPNetwork::INPUT_DIM>& w1,
                          float*       h1,
                          std::size_t  feat) noexcept {
    for (std::size_t j = 0; j < MLPNetwork::HIDDEN1; ++j) {
        h1[j] += w1[j * MLPNetwork::INPUT_DIM + feat];
    }
}

inline void accumulate_kind(const std::array<float,
                                MLPNetwork::HIDDEN1 * MLPNetwork::INPUT_DIM>& w1,
                            float*       h1,
                            Bitboard     bb,
                            std::size_t  kind) noexcept {
    while (bb) {
        const int         bit  = square_to_bit(pop_lsb(bb));
        const std::size_t feat = static_cast<std::size_t>(bit) * 4 + kind;
        add_w1_column(w1, h1, feat);
    }
}

}  // namespace

int MLPNetwork::evaluate(const Position& pos) const noexcept {
    // Layer 1: h1 = ReLU(b1 + W1 @ input).
    // Input is sparse one-hot over (square × kind); we only add the
    // columns of W1 that correspond to pieces actually present.
    float h1[HIDDEN1];
    for (std::size_t j = 0; j < HIDDEN1; ++j) h1[j] = b1_[j];
    accumulate_kind(w1_, h1, pos.white_men(),    0);
    accumulate_kind(w1_, h1, pos.white_kings(),  1);
    accumulate_kind(w1_, h1, pos.black_men(),    2);
    accumulate_kind(w1_, h1, pos.black_kings(),  3);
    for (std::size_t j = 0; j < HIDDEN1; ++j) {
        if (h1[j] < 0.0f) h1[j] = 0.0f;
    }

    // Layer 2: h2 = ReLU(b2 + W2 @ h1).
    float h2[HIDDEN2];
    for (std::size_t k = 0; k < HIDDEN2; ++k) {
        float s = b2_[k];
        for (std::size_t j = 0; j < HIDDEN1; ++j) {
            s += w2_[k * HIDDEN1 + j] * h1[j];
        }
        h2[k] = s > 0.0f ? s : 0.0f;
    }

    // Output layer: out = b3 + w3 @ h2 (no activation).
    float out = b3_;
    for (std::size_t k = 0; k < HIDDEN2; ++k) {
        out += w3_[k] * h2[k];
    }

    // Clamp into the non-mate range so a noisy network can never
    // shadow a real mate score from the search.
    constexpr float kClamp = 29000.0f;
    if (out >  kClamp) out =  kClamp;
    if (out < -kClamp) out = -kClamp;

    const int score_white = static_cast<int>(out);
    return (pos.side_to_move() == Color::White) ? score_white : -score_white;
}

namespace {

constexpr char     MLP_MAGIC[4]    = {'J', 'N', 'N', 'M'};
constexpr std::uint32_t MLP_VERSION = 1;

bool read_u32(std::istream& f, std::uint32_t& out) {
    f.read(reinterpret_cast<char*>(&out), 4);
    return f.gcount() == 4;
}

bool write_u32(std::ostream& f, std::uint32_t v) {
    f.write(reinterpret_cast<const char*>(&v), 4);
    return f.good();
}

template <std::size_t N>
bool read_floats(std::istream& f, std::array<float, N>& a) {
    f.read(reinterpret_cast<char*>(a.data()),
           static_cast<std::streamsize>(N * sizeof(float)));
    return static_cast<std::size_t>(f.gcount()) == N * sizeof(float);
}

template <std::size_t N>
bool write_floats(std::ostream& f, const std::array<float, N>& a) {
    f.write(reinterpret_cast<const char*>(a.data()),
            static_cast<std::streamsize>(N * sizeof(float)));
    return f.good();
}

}  // namespace

bool MLPNetwork::load(std::string_view path) {
    std::ifstream f(std::string{path}, std::ios::binary);
    if (!f) return false;

    char magic[4]{};
    f.read(magic, 4);
    if (!f || std::memcmp(magic, MLP_MAGIC, 4) != 0) return false;

    std::uint32_t version{}, in_dim{}, h1{}, h2{}, out_dim{};
    if (!read_u32(f, version)) return false;
    if (!read_u32(f, in_dim))  return false;
    if (!read_u32(f, h1))      return false;
    if (!read_u32(f, h2))      return false;
    if (!read_u32(f, out_dim)) return false;
    if (version != MLP_VERSION ||
        in_dim  != INPUT_DIM   ||
        h1      != HIDDEN1     ||
        h2      != HIDDEN2     ||
        out_dim != 1) {
        return false;
    }

    // Read into temporaries first so a partial/corrupt file never
    // mutates the live weights.
    decltype(w1_) tw1{};
    decltype(b1_) tb1{};
    decltype(w2_) tw2{};
    decltype(b2_) tb2{};
    decltype(w3_) tw3{};
    float         tb3{0.0f};

    if (!read_floats(f, tw1))                                 return false;
    if (!read_floats(f, tb1))                                 return false;
    if (!read_floats(f, tw2))                                 return false;
    if (!read_floats(f, tb2))                                 return false;
    if (!read_floats(f, tw3))                                 return false;
    f.read(reinterpret_cast<char*>(&tb3), sizeof(float));
    if (static_cast<std::size_t>(f.gcount()) != sizeof(float)) return false;

    w1_ = tw1; b1_ = tb1;
    w2_ = tw2; b2_ = tb2;
    w3_ = tw3; b3_ = tb3;
    return true;
}

bool MLPNetwork::save(std::string_view path) const {
    std::ofstream f(std::string{path}, std::ios::binary);
    if (!f) return false;
    f.write(MLP_MAGIC, 4);
    if (!write_u32(f, MLP_VERSION))                                  return false;
    if (!write_u32(f, static_cast<std::uint32_t>(INPUT_DIM)))        return false;
    if (!write_u32(f, static_cast<std::uint32_t>(HIDDEN1)))          return false;
    if (!write_u32(f, static_cast<std::uint32_t>(HIDDEN2)))          return false;
    if (!write_u32(f, 1u))                                            return false;
    if (!write_floats(f, w1_))                                        return false;
    if (!write_floats(f, b1_))                                        return false;
    if (!write_floats(f, w2_))                                        return false;
    if (!write_floats(f, b2_))                                        return false;
    if (!write_floats(f, w3_))                                        return false;
    f.write(reinterpret_cast<const char*>(&b3_), sizeof(float));
    return f.good();
}

std::unique_ptr<INetwork> load_network(std::string_view path) {
    std::ifstream f(std::string{path}, std::ios::binary);
    if (!f) return nullptr;
    char magic[4]{};
    f.read(magic, 4);
    const bool got_header = (f.gcount() == 4);
    f.close();
    if (!got_header) return nullptr;

    if (std::memcmp(magic, MLP_MAGIC, 4) == 0) {
        auto n = std::make_unique<MLPNetwork>();
        if (!n->load(path)) return nullptr;
        return n;
    }
    auto n = std::make_unique<LinearNetwork>();
    if (!n->load(path)) return nullptr;
    return n;
}

const LinearNetwork* default_nnue() {
    // Lazy initialisation: the embedded weights are decoded once on the
    // first call and reused for the lifetime of the process. If the
    // embedded byte count doesn't match `LinearNetwork`'s footprint
    // (e.g. the engine was compiled against a stale `nnue.bin`), we
    // fall back to a default-constructed network so the runtime keeps
    // working on top of the handcrafted-equivalent weights.
    static const LinearNetwork* net = []() {
        auto* n = new LinearNetwork();
        n->load_from_bytes(NNUE_DEFAULT_BYTES, NNUE_DEFAULT_LEN);
        return n;
    }();
    return net;
}

int evaluate_nnue(const Position& pos) {
    static const LinearNetwork net;
    return net.evaluate(pos);
}

}  // namespace jass

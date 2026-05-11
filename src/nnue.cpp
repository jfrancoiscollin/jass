// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "nnue.hpp"

#include "bitboard.hpp"
#include "board.hpp"
#include "eval.hpp"
#include "nnue_default_data.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <fstream>
#include <string>

#if defined(__AVX2__)
#include <immintrin.h>
#endif

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
//
// Input encoding (v2): the network sees the board from the side-to-
// move's perspective.
//
//   feat[b * 4 + 0] = STM has man  on b   (b in 0..49)
//   feat[b * 4 + 1] = STM has king on b
//   feat[b * 4 + 2] = OPP has man  on b
//   feat[b * 4 + 3] = OPP has king on b
//
// For black-to-move positions we mirror the bit (b -> 49 - b, the bit
// equivalent of FMJD square s -> 51 - s) and swap the colour role
// before populating the features. The output is therefore already in
// STM-POV; no final sign flip is needed.
//
// This bakes the rotation-by-180° + colour-swap symmetry of draughts
// into the model: the same "position from my POV" maps to the same
// network input regardless of which physical colour is to move,
// effectively doubling the dataset and aligning the MLP with the
// inductive bias the LinearNetwork gets for free (per-colour weights
// and a final sign flip).
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

// Walk the set bits of `bb` and add the corresponding W1 column for
// every piece, indexing the feature space as
// `(mirror ? 49 - bit : bit) * 4 + kind`.
inline void accumulate_kind(const std::array<float,
                                MLPNetwork::HIDDEN1 * MLPNetwork::INPUT_DIM>& w1,
                            float*       h1,
                            Bitboard     bb,
                            std::size_t  kind,
                            bool         mirror) noexcept {
    while (bb) {
        const int         bit = square_to_bit(pop_lsb(bb));
        const std::size_t b   = mirror
            ? static_cast<std::size_t>(49 - bit)
            : static_cast<std::size_t>(bit);
        add_w1_column(w1, h1, b * 4 + kind);
    }
}

}  // namespace

int MLPNetwork::evaluate(const Position& pos) const noexcept {
    // Layer 1: h1 = ReLU(b1 + W1 @ input). Build the sparse input from
    // STM's perspective — see the file header for the encoding spec.
    float h1[HIDDEN1];
    for (std::size_t j = 0; j < HIDDEN1; ++j) h1[j] = b1_[j];

    if (pos.side_to_move() == Color::White) {
        accumulate_kind(w1_, h1, pos.white_men(),    0, /*mirror=*/false);
        accumulate_kind(w1_, h1, pos.white_kings(),  1, /*mirror=*/false);
        accumulate_kind(w1_, h1, pos.black_men(),    2, /*mirror=*/false);
        accumulate_kind(w1_, h1, pos.black_kings(),  3, /*mirror=*/false);
    } else {
        accumulate_kind(w1_, h1, pos.black_men(),    0, /*mirror=*/true);
        accumulate_kind(w1_, h1, pos.black_kings(),  1, /*mirror=*/true);
        accumulate_kind(w1_, h1, pos.white_men(),    2, /*mirror=*/true);
        accumulate_kind(w1_, h1, pos.white_kings(),  3, /*mirror=*/true);
    }
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

    // Output layer: out = b3 + w3 @ h2 (no activation). Already in
    // STM-POV by construction of the input encoding above.
    float out = b3_;
    for (std::size_t k = 0; k < HIDDEN2; ++k) {
        out += w3_[k] * h2[k];
    }

    // Clamp into the non-mate range so a noisy network can never
    // shadow a real mate score from the search.
    constexpr float kClamp = 29000.0f;
    if (out >  kClamp) out =  kClamp;
    if (out < -kClamp) out = -kClamp;

    return static_cast<int>(out);
}

namespace {

constexpr char          MLP_MAGIC[4]  = {'J', 'N', 'N', 'M'};
constexpr char          MLPQ_MAGIC[4] = {'J', 'N', 'N', 'Q'};
// Bumped to 2 when the input encoding switched to STM-relative with
// board mirroring + colour swap. v1 weights interpreted under the new
// encoding would silently miscompute, so we reject them at load time.
constexpr std::uint32_t MLP_VERSION   = 2;
constexpr std::uint32_t MLPQ_VERSION  = 1;

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

bool MLPNetwork::load_from_bytes(const unsigned char* data, std::size_t n) {
    // Smallest valid file: 6 × uint32 header + the float arrays.
    constexpr std::size_t kHeader = 6 * sizeof(std::uint32_t);
    constexpr std::size_t kFloats =
        (HIDDEN1 * INPUT_DIM + HIDDEN1
       + HIDDEN2 * HIDDEN1   + HIDDEN2
       + HIDDEN2             + 1) * sizeof(float);
    if (data == nullptr || n != kHeader + kFloats) return false;

    if (std::memcmp(data, MLP_MAGIC, 4) != 0) return false;

    auto read_u32_at = [&](std::size_t off) {
        std::uint32_t v;
        std::memcpy(&v, data + off, sizeof(v));
        return v;
    };
    if (read_u32_at(4)  != MLP_VERSION)                               return false;
    if (read_u32_at(8)  != static_cast<std::uint32_t>(INPUT_DIM))     return false;
    if (read_u32_at(12) != static_cast<std::uint32_t>(HIDDEN1))       return false;
    if (read_u32_at(16) != static_cast<std::uint32_t>(HIDDEN2))       return false;
    if (read_u32_at(20) != 1u)                                        return false;

    // Memcpy each region. Streaming into temporaries first so a
    // partial overlap mid-load can't corrupt live weights.
    decltype(w1_) tw1{};
    decltype(b1_) tb1{};
    decltype(w2_) tw2{};
    decltype(b2_) tb2{};
    decltype(w3_) tw3{};
    float         tb3{0.0f};

    const unsigned char* p = data + kHeader;
    auto take = [&](void* dst, std::size_t bytes) {
        std::memcpy(dst, p, bytes);
        p += bytes;
    };
    take(tw1.data(), tw1.size() * sizeof(float));
    take(tb1.data(), tb1.size() * sizeof(float));
    take(tw2.data(), tw2.size() * sizeof(float));
    take(tb2.data(), tb2.size() * sizeof(float));
    take(tw3.data(), tw3.size() * sizeof(float));
    take(&tb3,       sizeof(float));

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

// ---------------------------------------------------------------------------
// MLPNetworkQ — int8 quantised forward pass.
// ---------------------------------------------------------------------------
//
// Scale convention (see tools/quantize_mlp.py for derivation):
//   * Layer-1 accumulator units = sw1 (only weights are scaled; input
//     is a unitless one-hot).  Bias `b1_` is stored at this scale.
//   * Quantising acc1 to int8 h1 with magnitude ≤ 127 requires the
//     factor `mul1 = sw1 / sh1`.
//   * Layer-2 accumulator units = sw2 × sh1.  Bias `b2_` at that scale.
//   * `mul2 = (sw2 × sh1) / sh2`.
//   * Layer-3 accumulator units = sw3 × sh2.  Bias `b3_` at that scale.
//   * `mul_out = sw3 × sh2` directly converts acc3 to centipawn.

namespace {

inline std::int32_t saturate_to_int8(float x) noexcept {
    // Round-to-nearest via truncation of (x + 0.5) for positive values.
    // ReLU clips negatives to 0 immediately so we don't need to handle
    // the negative-rounding case. std::lround is a function call with
    // rounding-mode semantics — way slower than a static_cast in the
    // hot path.
    if (x <= 0.0f)   return 0;
    if (x >= 126.5f) return 127;
    return static_cast<int>(x + 0.5f);
}

inline void accumulate_q_kind(
        const std::array<std::int8_t,
                         MLPNetworkQ::HIDDEN1 * MLPNetworkQ::INPUT_DIM>& w1,
        std::int32_t* acc1,
        Bitboard      bb,
        std::size_t   kind,
        bool          mirror) noexcept {
    while (bb) {
        const int         bit = square_to_bit(pop_lsb(bb));
        const std::size_t b   = mirror
            ? static_cast<std::size_t>(49 - bit)
            : static_cast<std::size_t>(bit);
        const std::size_t feat = b * 4 + kind;
        for (std::size_t j = 0; j < MLPNetworkQ::HIDDEN1; ++j) {
            acc1[j] += static_cast<std::int32_t>(w1[j * MLPNetworkQ::INPUT_DIM + feat]);
        }
    }
}

}  // namespace

namespace {

#if defined(__AVX2__)

// Horizontal sum of an AVX2 int32 vector → single int32.
inline std::int32_t hsum_epi32_avx2(__m256i v) noexcept {
    const __m128i hi = _mm256_extracti128_si256(v, 1);
    const __m128i lo = _mm256_castsi256_si128(v);
    const __m128i s4 = _mm_add_epi32(hi, lo);              // 4 int32
    const __m128i s2 = _mm_hadd_epi32(s4, s4);              // 2 int32 in low half
    const __m128i s1 = _mm_hadd_epi32(s2, s2);              // 1 int32 in lowest lane
    return _mm_cvtsi128_si32(s1);
}

// Dot product over `n_bytes` of `(h: uint8, w: int8)` pairs using
// AVX2 maddubs + madd. Returns the int32 sum. `n_bytes` must be a
// multiple of 32 (one AVX2 register).
inline std::int32_t dot_uint8_int8_avx2(const std::int8_t* h,
                                        const std::int8_t* w,
                                        std::size_t        n_bytes) noexcept {
    const __m256i ones16 = _mm256_set1_epi16(1);
    __m256i acc = _mm256_setzero_si256();
    for (std::size_t off = 0; off < n_bytes; off += 32) {
        // Bytes in h are guaranteed to be in [0, 127] (post-ReLU
        // saturate_to_int8), so reinterpreting them as unsigned for
        // maddubs is safe — same bit pattern.
        const __m256i hv = _mm256_loadu_si256(
            reinterpret_cast<const __m256i*>(h + off));
        const __m256i wv = _mm256_loadu_si256(
            reinterpret_cast<const __m256i*>(w + off));
        // maddubs: 16 int16, each = h[2i]*w[2i] + h[2i+1]*w[2i+1].
        // Max magnitude per pair = 2 * 127 * 127 = 32258, fits in int16.
        const __m256i p16 = _mm256_maddubs_epi16(hv, wv);
        // madd with ones16: 8 int32, each = sum of two adjacent int16.
        const __m256i p32 = _mm256_madd_epi16(p16, ones16);
        acc = _mm256_add_epi32(acc, p32);
    }
    return hsum_epi32_avx2(acc);
}

#endif  // __AVX2__

}  // namespace

int MLPNetworkQ::evaluate(const Position& pos) const noexcept {
    // Layer 1 — sparse input → int32 accumulator (biases pre-scaled).
    // The active-feature loop is naturally efficient (≈20 pieces per
    // position, each adds a 64-int8 column) so it stays scalar even
    // when AVX2 is available; auto-vectorisation handles the inner
    // 64-element add adequately at -O3.
    std::int32_t acc1[HIDDEN1];
    for (std::size_t j = 0; j < HIDDEN1; ++j) acc1[j] = b1_[j];

    if (pos.side_to_move() == Color::White) {
        accumulate_q_kind(w1_, acc1, pos.white_men(),    0, false);
        accumulate_q_kind(w1_, acc1, pos.white_kings(),  1, false);
        accumulate_q_kind(w1_, acc1, pos.black_men(),    2, false);
        accumulate_q_kind(w1_, acc1, pos.black_kings(),  3, false);
    } else {
        accumulate_q_kind(w1_, acc1, pos.black_men(),    0, true);
        accumulate_q_kind(w1_, acc1, pos.black_kings(),  1, true);
        accumulate_q_kind(w1_, acc1, pos.white_men(),    2, true);
        accumulate_q_kind(w1_, acc1, pos.white_kings(),  3, true);
    }

    // ReLU + quantise to int8 ([0, 127]).
    std::int8_t h1[HIDDEN1];
    for (std::size_t j = 0; j < HIDDEN1; ++j) {
        h1[j] = static_cast<std::int8_t>(
            saturate_to_int8(static_cast<float>(acc1[j]) * mul1_));
    }

    // Layer 2 — int8 × int8 → int32 dense matmul. HIDDEN2 outputs,
    // HIDDEN1 inputs. AVX2 path uses maddubs/madd; otherwise scalar.
    std::int32_t acc2[HIDDEN2];
#if defined(__AVX2__)
    static_assert(HIDDEN1 % 32 == 0,
                  "AVX2 layer 2 expects HIDDEN1 to be a multiple of 32");
    for (std::size_t k = 0; k < HIDDEN2; ++k) {
        acc2[k] = b2_[k]
                + dot_uint8_int8_avx2(h1, w2_.data() + k * HIDDEN1, HIDDEN1);
    }
#else
    for (std::size_t k = 0; k < HIDDEN2; ++k) {
        std::int32_t s = b2_[k];
        for (std::size_t j = 0; j < HIDDEN1; ++j) {
            s += static_cast<std::int32_t>(w2_[k * HIDDEN1 + j])
               * static_cast<std::int32_t>(h1[j]);
        }
        acc2[k] = s;
    }
#endif

    std::int8_t h2[HIDDEN2];
    for (std::size_t k = 0; k < HIDDEN2; ++k) {
        h2[k] = static_cast<std::int8_t>(
            saturate_to_int8(static_cast<float>(acc2[k]) * mul2_));
    }

    // Layer 3 — single output, HIDDEN2 inputs. With HIDDEN2 = 32 this
    // is exactly one AVX2 register; the scalar fallback covers other
    // dimensions.
    std::int32_t acc3 = b3_;
#if defined(__AVX2__)
    static_assert(HIDDEN2 % 32 == 0 || HIDDEN2 < 32,
                  "AVX2 layer 3 expects HIDDEN2 to fit a single register "
                  "or be a multiple of 32");
    if constexpr (HIDDEN2 % 32 == 0) {
        acc3 += dot_uint8_int8_avx2(h2, w3_.data(), HIDDEN2);
    } else {
        for (std::size_t k = 0; k < HIDDEN2; ++k) {
            acc3 += static_cast<std::int32_t>(w3_[k])
                  * static_cast<std::int32_t>(h2[k]);
        }
    }
#else
    for (std::size_t k = 0; k < HIDDEN2; ++k) {
        acc3 += static_cast<std::int32_t>(w3_[k])
              * static_cast<std::int32_t>(h2[k]);
    }
#endif

    float out = static_cast<float>(acc3) * mul_out_;
    constexpr float kClamp = 29000.0f;
    if (out >  kClamp) out =  kClamp;
    if (out < -kClamp) out = -kClamp;
    return static_cast<int>(out);
}

namespace {

template <typename T, std::size_t N>
bool read_typed(std::istream& f, std::array<T, N>& a) {
    f.read(reinterpret_cast<char*>(a.data()),
           static_cast<std::streamsize>(N * sizeof(T)));
    return static_cast<std::size_t>(f.gcount()) == N * sizeof(T);
}

template <typename T, std::size_t N>
bool write_typed(std::ostream& f, const std::array<T, N>& a) {
    f.write(reinterpret_cast<const char*>(a.data()),
            static_cast<std::streamsize>(N * sizeof(T)));
    return f.good();
}

bool read_f32(std::istream& f, float& out) {
    f.read(reinterpret_cast<char*>(&out), sizeof(float));
    return f.gcount() == sizeof(float);
}

bool write_f32(std::ostream& f, float v) {
    f.write(reinterpret_cast<const char*>(&v), sizeof(float));
    return f.good();
}

}  // namespace

bool MLPNetworkQ::load(std::string_view path) {
    std::ifstream f(std::string{path}, std::ios::binary);
    if (!f) return false;

    char magic[4]{};
    f.read(magic, 4);
    if (!f || std::memcmp(magic, MLPQ_MAGIC, 4) != 0) return false;

    std::uint32_t version{}, in_dim{}, h1d{}, h2d{}, out_dim{};
    if (!read_u32(f, version)) return false;
    if (!read_u32(f, in_dim))  return false;
    if (!read_u32(f, h1d))     return false;
    if (!read_u32(f, h2d))     return false;
    if (!read_u32(f, out_dim)) return false;
    if (version != MLPQ_VERSION ||
        in_dim  != INPUT_DIM    ||
        h1d     != HIDDEN1      ||
        h2d     != HIDDEN2      ||
        out_dim != 1) {
        return false;
    }

    float t_mul1{}, t_mul2{}, t_mul_out{};
    if (!read_f32(f, t_mul1))    return false;
    if (!read_f32(f, t_mul2))    return false;
    if (!read_f32(f, t_mul_out)) return false;

    decltype(w1_) tw1{};
    decltype(b1_) tb1{};
    decltype(w2_) tw2{};
    decltype(b2_) tb2{};
    decltype(w3_) tw3{};
    std::int32_t  tb3{0};

    if (!read_typed(f, tw1))                                 return false;
    if (!read_typed(f, tb1))                                 return false;
    if (!read_typed(f, tw2))                                 return false;
    if (!read_typed(f, tb2))                                 return false;
    if (!read_typed(f, tw3))                                 return false;
    f.read(reinterpret_cast<char*>(&tb3), sizeof(std::int32_t));
    if (static_cast<std::size_t>(f.gcount()) != sizeof(std::int32_t)) return false;

    w1_ = tw1; b1_ = tb1;
    w2_ = tw2; b2_ = tb2;
    w3_ = tw3; b3_ = tb3;
    mul1_    = t_mul1;
    mul2_    = t_mul2;
    mul_out_ = t_mul_out;
    return true;
}

bool MLPNetworkQ::save(std::string_view path) const {
    std::ofstream f(std::string{path}, std::ios::binary);
    if (!f) return false;
    f.write(MLPQ_MAGIC, 4);
    if (!write_u32(f, MLPQ_VERSION))                                 return false;
    if (!write_u32(f, static_cast<std::uint32_t>(INPUT_DIM)))        return false;
    if (!write_u32(f, static_cast<std::uint32_t>(HIDDEN1)))          return false;
    if (!write_u32(f, static_cast<std::uint32_t>(HIDDEN2)))          return false;
    if (!write_u32(f, 1u))                                            return false;
    if (!write_f32(f, mul1_))                                         return false;
    if (!write_f32(f, mul2_))                                         return false;
    if (!write_f32(f, mul_out_))                                      return false;
    if (!write_typed(f, w1_))                                         return false;
    if (!write_typed(f, b1_))                                         return false;
    if (!write_typed(f, w2_))                                         return false;
    if (!write_typed(f, b2_))                                         return false;
    if (!write_typed(f, w3_))                                         return false;
    f.write(reinterpret_cast<const char*>(&b3_), sizeof(std::int32_t));
    return f.good();
}

bool MLPNetworkQ::load_from_bytes(const unsigned char* data, std::size_t n) {
    constexpr std::size_t kHeader = 6 * sizeof(std::uint32_t)
                                  + 3 * sizeof(float);
    constexpr std::size_t kWeights =
          HIDDEN1 * INPUT_DIM                        // w1
        + HIDDEN1 * sizeof(std::int32_t)              // b1
        + HIDDEN2 * HIDDEN1                           // w2
        + HIDDEN2 * sizeof(std::int32_t)              // b2
        + HIDDEN2                                     // w3
        + sizeof(std::int32_t);                       // b3
    if (data == nullptr || n != kHeader + kWeights) return false;
    if (std::memcmp(data, MLPQ_MAGIC, 4) != 0)        return false;

    auto read_u32_at = [&](std::size_t off) {
        std::uint32_t v;
        std::memcpy(&v, data + off, sizeof(v));
        return v;
    };
    auto read_f32_at = [&](std::size_t off) {
        float v;
        std::memcpy(&v, data + off, sizeof(v));
        return v;
    };

    if (read_u32_at(4)  != MLPQ_VERSION)                              return false;
    if (read_u32_at(8)  != static_cast<std::uint32_t>(INPUT_DIM))     return false;
    if (read_u32_at(12) != static_cast<std::uint32_t>(HIDDEN1))       return false;
    if (read_u32_at(16) != static_cast<std::uint32_t>(HIDDEN2))       return false;
    if (read_u32_at(20) != 1u)                                        return false;

    const float t_mul1    = read_f32_at(24);
    const float t_mul2    = read_f32_at(28);
    const float t_mul_out = read_f32_at(32);

    decltype(w1_) tw1{};
    decltype(b1_) tb1{};
    decltype(w2_) tw2{};
    decltype(b2_) tb2{};
    decltype(w3_) tw3{};
    std::int32_t  tb3{0};

    const unsigned char* p = data + kHeader;
    auto take = [&](void* dst, std::size_t bytes) {
        std::memcpy(dst, p, bytes);
        p += bytes;
    };
    take(tw1.data(), tw1.size() * sizeof(std::int8_t));
    take(tb1.data(), tb1.size() * sizeof(std::int32_t));
    take(tw2.data(), tw2.size() * sizeof(std::int8_t));
    take(tb2.data(), tb2.size() * sizeof(std::int32_t));
    take(tw3.data(), tw3.size() * sizeof(std::int8_t));
    take(&tb3,       sizeof(std::int32_t));

    w1_ = tw1; b1_ = tb1;
    w2_ = tw2; b2_ = tb2;
    w3_ = tw3; b3_ = tb3;
    mul1_    = t_mul1;
    mul2_    = t_mul2;
    mul_out_ = t_mul_out;
    return true;
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
    if (std::memcmp(magic, MLPQ_MAGIC, 4) == 0) {
        auto n = std::make_unique<MLPNetworkQ>();
        if (!n->load(path)) return nullptr;
        return n;
    }
    auto n = std::make_unique<LinearNetwork>();
    if (!n->load(path)) return nullptr;
    return n;
}

std::unique_ptr<INetwork> load_network_from_bytes(const unsigned char* data,
                                                  std::size_t          n) {
    if (data == nullptr || n < 4) return nullptr;
    if (std::memcmp(data, MLP_MAGIC, 4) == 0) {
        auto net = std::make_unique<MLPNetwork>();
        if (!net->load_from_bytes(data, n)) return nullptr;
        return net;
    }
    if (std::memcmp(data, MLPQ_MAGIC, 4) == 0) {
        auto net = std::make_unique<MLPNetworkQ>();
        if (!net->load_from_bytes(data, n)) return nullptr;
        return net;
    }
    auto net = std::make_unique<LinearNetwork>();
    if (!net->load_from_bytes(data, n)) return nullptr;
    return net;
}

const INetwork* default_nnue() {
    // Lazy initialisation: the embedded weights are decoded once on the
    // first call and reused for the lifetime of the process. The
    // concrete type (LinearNetwork or MLPNetwork) is determined by
    // sniffing the JNNM magic at the start of the byte buffer. If
    // decoding fails — e.g. the engine was compiled against a stale
    // `nnue.bin` with mismatched dimensions — we fall back to a
    // default-constructed LinearNetwork so the runtime keeps working
    // on top of the handcrafted-equivalent weights.
    static const INetwork* net = []() -> const INetwork* {
        auto loaded = load_network_from_bytes(NNUE_DEFAULT_BYTES,
                                              NNUE_DEFAULT_LEN);
        if (loaded) return loaded.release();
        return new LinearNetwork();
    }();
    return net;
}

int evaluate_nnue(const Position& pos) {
    static const LinearNetwork net;
    return net.evaluate(pos);
}

}  // namespace jass

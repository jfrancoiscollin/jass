// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Full Scan-style structured evaluation for jass (PJTW v3).
//
// This is the "tout comme Scan" eval : a single linear function of
//
//     material (men + king counts)
//   + king PST   (one-hot per square, per colour)
//   + mobility   (men step + king slide, per colour)
//   + balance    (left/right men distribution, per colour)
//   + men patterns (8 vertical bands × 12 squares, ternary — pattern_jass)
//
// with EVERY feature stored in TWO weight banks (midgame / endgame) and
// interpolated by the game stage (piece count / 40), exactly like Scan
// (cf docs/SCAN_ARCHITECTURE_NOTES.md §3, docs/PATTERN_PROGRAM_NOTES.md §A).
//
// Consistency contract :
//   * `compute_extras()` is the SINGLE source of truth for the dense
//     "extras" feature vector. It is called both by the training-time
//     feature dump (`jass --dump-eval-features`) and by the playable
//     `ScanEvalNetwork::evaluate()`. There is no second implementation in
//     Python — the trainer consumes the dumped extras verbatim. Mobility
//     therefore uses fast bitboard shifts (no movegen) and is identical on
//     both sides by construction.
//   * The 8 men-pattern bucket indices are computed by pattern_jass on both
//     sides (base-3, men only) — already mirrored in pattern_jass/tools.
//
// Score convention (matches pattern_jass_bridge) : the eval is accumulated
// in BLACK POV (positive = good for Black), divided by `scale`, multiplied
// by 100 → centipawn-like units, then sign-flipped to stm-POV.

#pragma once

#include "nnue.hpp"
#include "position.hpp"

#include "../pattern_jass/src/pattern.hpp"

#include <array>
#include <cstdint>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace jass::scan_eval {

// ---------------------------------------------------------------------------
// Pattern piece-presence (king-aware switch).
// ---------------------------------------------------------------------------
// The men-pattern bucket index is base-3 per square : 0 empty / 1 black / 2
// white. By DEFAULT only MEN occupy a square (kings invisible to the patterns —
// a king square reads as empty ; the king's value is carried by the king-PST +
// king-mobility extras). With -DJASS_KING_PATTERNS the occupancy becomes
// men|kings, so a king counts as a "piece" on its square EXACTLY like Scan
// (base-3 amalgamating man+king, cf docs/SCAN_ARCHITECTURE_NOTES.md §1) — NOT
// base-5 (that was jass v2 : king buckets near-empty, worse). A king-aware
// build MUST be paired with a king-aware eval : train with
// `pattern_jass/tools/train.py --king-patterns`.
#ifdef JASS_KING_PATTERNS
inline constexpr bool KING_AWARE_PATTERNS = true;
#else
inline constexpr bool KING_AWARE_PATTERNS = false;
#endif
inline std::uint64_t pat_black(const Position& p) noexcept {
    return static_cast<std::uint64_t>(KING_AWARE_PATTERNS ? p.blacks() : p.black_men());
}
inline std::uint64_t pat_white(const Position& p) noexcept {
    return static_cast<std::uint64_t>(KING_AWARE_PATTERNS ? p.whites() : p.white_men());
}

// ---------------------------------------------------------------------------
// Dense "extras" feature layout (black-POV indicators / counts).
// ---------------------------------------------------------------------------
// Kept in a fixed, stable order so the trainer and the C++ eval agree. The
// men patterns (pattern_jass) are appended separately as sparse one-hots.
inline constexpr int EXTRA_BK_PST_BASE  = 0;    // [0..49]   black king on FMJD (i+1)
inline constexpr int EXTRA_WK_PST_BASE  = 50;   // [50..99]  white king on FMJD (i+1)
inline constexpr int EXTRA_BLACK_MEN    = 100;  // black men count
inline constexpr int EXTRA_WHITE_MEN    = 101;  // white men count
inline constexpr int EXTRA_BLACK_MOB    = 102;  // black mobility (men step + king slide)
inline constexpr int EXTRA_WHITE_MOB    = 103;  // white mobility
inline constexpr int EXTRA_BLACK_BAL    = 104;  // black men left − right
inline constexpr int EXTRA_WHITE_BAL    = 105;  // white men left − right
// 1st batch of structural extras (king-mob/back-rank/advancement, 106->112)
// was RE-TESTED on the clean (score-drop) baseline in 0172 and CONDEMNED:
// v4+112 = 0.889/0.389 vs the v4+106 champion 0.944/0.389 (hurts vs hc,
// neutral vs v15). Reverted to 106. To re-test, re-add here + NUM_EXTRAS.
#ifdef JASS_ENDGAME_FEATURES
// Endgame KING-INTERACTION features (gated; -DJASS_ENDGAME_FEATURES). The
// per-square king-PST [0..99] + per-side mobility [102..103] do NOT capture
// king CENTRALITY (active vs edge kings) nor king→enemy PROXIMITY (chasing /
// opposition), which decide king endgames where we bleed (autopsy ~3.6). NOT
// the 0172-condemned set. Black-POV (white negated by the trainer antisymmetry).
inline constexpr int EXTRA_BK_CENTRAL   = 106;  // Σ black-king centralisation
inline constexpr int EXTRA_WK_CENTRAL   = 107;  // Σ white-king centralisation
inline constexpr int EXTRA_BK_PROX      = 108;  // Σ black-king proximity to white pieces
inline constexpr int EXTRA_WK_PROX      = 109;  // Σ white-king proximity to black pieces
inline constexpr int EXTRAS_AFTER_ENDGAME = 110;
#else
inline constexpr int EXTRAS_AFTER_ENDGAME = 106;
#endif

// King-MOBILITY / CONFINEMENT (gated; -DJASS_KING_MOBILITY). The base mobility
// extras [102/103] LUMP men-steps with king-slides into one raw number per side,
// so the trainer cannot weight KING mobility distinctly — and there is no
// confinement signal. Scan's `king_mob` (king-specific, denial-aware) is exactly
// what drives its conversion in king endgames WITHOUT any MTC (cf
// docs/SCAN_EVAL_DIFF.md, LEAD 1). Here we SEPARATE king-slide mobility per side
// (the eval can then learn "maximise my king mobility, minimise the enemy's" =
// confinement gradient, structural & linear) plus a trapped-king count (the
// extreme). v1 uses raw slide mobility (blocked diagonals already capture most
// confinement); a safety/denial refinement is a follow-up if v1 transfers.
#ifdef JASS_KING_MOBILITY
inline constexpr int EXTRA_BK_KMOB  = EXTRAS_AFTER_ENDGAME + 0;  // black king slide mobility
inline constexpr int EXTRA_WK_KMOB  = EXTRAS_AFTER_ENDGAME + 1;  // white king slide mobility
inline constexpr int EXTRA_BK_KTRAP = EXTRAS_AFTER_ENDGAME + 2;  // # black kings with 0 slides
inline constexpr int EXTRA_WK_KTRAP = EXTRAS_AFTER_ENDGAME + 3;  // # white kings with 0 slides
inline constexpr int NUM_EXTRAS     = EXTRAS_AFTER_ENDGAME + 4;
#else
inline constexpr int NUM_EXTRAS     = EXTRAS_AFTER_ENDGAME;
#endif

// Game-stage normaliser : 20 men/side at the FMJD start = 40 pieces.
inline constexpr int MAX_PIECES = 40;

// Phase ramp endpoints (pieces). wmg ramps 0 (≤LO) → 1 (≥HI), weg = 1−wmg.
// DEFAULT LO=0, HI=40 reproduces the legacy `wmg = pieces/40` blend EXACTLY.
// A SHARPER ramp (e.g. LO=10, HI=24) lets the endgame (eg) bank specialise on
// low-piece positions instead of being pulled 0.25 by every midgame position —
// the phase CONFLICT 0310 measured (endgame fits far better when not co-fit
// with midgame). A king-mobility/phase build MUST be evaluated AND trained with
// the SAME endpoints (train.py --phase-lo/--phase-hi). Cf docs/SCAN_EVAL_DIFF.md.
#ifndef JASS_PHASE_LO
#define JASS_PHASE_LO 0
#endif
#ifndef JASS_PHASE_HI
#define JASS_PHASE_HI 40
#endif
inline double phase_wmg(int pieces) noexcept {
    constexpr double LO = static_cast<double>(JASS_PHASE_LO);
    constexpr double HI = static_cast<double>(JASS_PHASE_HI);
    const double denom = (HI > LO) ? (HI - LO) : 1.0;
    const double w = (static_cast<double>(pieces) - LO) / denom;
    return w < 0.0 ? 0.0 : (w > 1.0 ? 1.0 : w);
}

// Fast bitboard mobility (no movegen) : number of quiet destinations for
// `c`'s men (one forward step) plus king slides (until first blocker).
// Used identically by the feature dump and by evaluate().
int mobility(const Position& pos, Color c) noexcept;

// Fill `out` with the NUM_EXTRAS dense features in black-POV. Position-only
// (independent of side to move), so a single row is dumped per position.
void compute_extras(const Position& pos,
                    std::array<float, NUM_EXTRAS>& out) noexcept;

// Game stage = min(total pieces, 40). wmg = stage/40, weg = 1 − wmg.
int game_stage(const Position& pos) noexcept;

// ---------------------------------------------------------------------------
// PJTW v3 weights : full phase-split structured eval.
// ---------------------------------------------------------------------------
// File layout (little-endian) :
//   uint32 magic   = 0x57544A50  ("PJTW")
//   uint32 version = 3
//   uint32 scale   = quantisation factor (piece-units × scale)
//   uint32 n_pat   = pattern bucket count (= pattern_jass::TOTAL_BUCKETS)
//   uint32 n_ext   = extras count (= NUM_EXTRAS)
//   int32  w[2 * (n_pat + n_ext)]  ordered [pat_mg | pat_eg | ext_mg | ext_eg]
inline constexpr std::uint32_t V3_MAGIC   = 0x57544A50U;  // "PJTW"
inline constexpr std::uint32_t V3_VERSION = 3U;
inline constexpr std::uint32_t V4_VERSION = 4U;          // v3 linear + FM term
inline constexpr std::size_t   V3_HEADER  = 20;
// High bits OR'd into the version word self-describe the eval so a wrong
// binary/weights pairing fails loudly instead of silently mis-evaluating
// (the king-aware footgun). SELFDESC marks a file written by a king-aware-era
// trainer; KING marks king|men occupancy. Legacy files (neither bit) load with
// a stderr note. base version = version & 0xFF.
inline constexpr std::uint32_t V_VERMASK     = 0x000000FFU;
inline constexpr std::uint32_t V_SELFDESC_BIT= 0x00000200U;
inline constexpr std::uint32_t V_KING_BIT    = 0x00000100U;

struct ScanWeights {
    std::uint32_t scale = 1000;
    std::vector<std::int32_t> pat_mg;   // size n_pat
    std::vector<std::int32_t> pat_eg;   // size n_pat
    std::array<std::int32_t, NUM_EXTRAS> ext_mg{};
    std::array<std::int32_t, NUM_EXTRAS> ext_eg{};
    // Optional Factorization-Machine term (PJTW v4). fm_rank=0 → none. The
    // pairwise pattern-interaction term ½ Σ_f[(Σ_p V_{p,f})² − Σ_p V_{p,f}²]
    // is added in piece-units (same scale as the linear eval ÷ scale), using
    // the same per-pattern bucket the accumulator already maintains, hashed to
    // fm_hash slots. fm_v laid out slot-major : slot s=p*fm_hash+(bucket%H),
    // then fm_rank factors. Size = NUM_PATTERNS * fm_hash * fm_rank.
    std::uint32_t fm_rank = 0;
    std::uint32_t fm_hash = 0;
    std::vector<float> fm_v;
};

std::optional<ScanWeights> load_scan_weights(const std::string& path,
                                             std::string* err = nullptr);

class ScanEvalNetwork : public INetwork {
public:
    explicit ScanEvalNetwork(ScanWeights w) : w_(std::move(w)) {}
    int evaluate(const Position& pos) const noexcept override;

    // Accumulator fast path : same eval as evaluate(pos) but with the 32
    // pattern base-3 indices supplied precomputed (the search maintains them
    // incrementally via ScanAccumulator), skipping extract_all. `idx` must
    // point to NUM_PATTERNS entries equal to extract_all(pat_black(pos),
    // pat_white(pos)) — i.e. men-only or men|kings per the king-aware switch.
    int evaluate_with_idx(const Position& pos,
                          const std::uint32_t* idx) const noexcept;

    std::uint32_t scale() const noexcept { return w_.scale; }
    std::size_t   count() const noexcept {
        return 2 * (w_.pat_mg.size() + NUM_EXTRAS);
    }

private:
    ScanWeights w_;
};

std::unique_ptr<ScanEvalNetwork> load_scan_eval_network(
    const std::string& path, std::string* err = nullptr);

// Per-ply pattern accumulator for the search. Holds the 32 base-3 pattern
// indices; `refresh_from` rebuilds them from scratch (root / fallback) and
// `apply_move` updates them incrementally for a played move. Occupancy fed to
// the patterns is `pat_black/pat_white` (men only, or men|kings when king-aware)
// — with king-aware occupancy, update_all naturally handles king moves AND
// promotions (man→king keeps the square occupied → index unchanged). One
// accumulator per ply (the index does not depend on side-to-move;
// evaluate_with_idx applies the sign).
struct ScanAccumulator {
    std::array<std::uint32_t, pattern_jass::NUM_PATTERNS> idx{};

    void refresh_from(const Position& pos) noexcept {
        pattern_jass::extract_all(pat_black(pos), pat_white(pos), idx);
    }
    void apply_move(const Position& before, const Position& after) noexcept {
        pattern_jass::update_all(pat_black(before), pat_white(before),
                                 pat_black(after),  pat_white(after), idx);
    }
};

}  // namespace jass::scan_eval

namespace jass {

// Unified eval loader : peeks the PJTW version and returns the right
// INetwork — v3 → ScanEvalNetwork, v1/v2 → PatternJassNetwork. Lets the
// HUB `--pattern` flag, SPSA and benches accept either format transparently.
std::unique_ptr<INetwork> load_eval_network(const std::string& path,
                                            std::string* err = nullptr);

}  // namespace jass

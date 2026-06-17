// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Scan-style opening book.
// ---------------------------------------------------------------------------
// Unlike the classic `Book` (a flat zobrist→single-move table, see book.hpp),
// this book stores the BACKED-UP negamax score of EVERY position in an
// expanded opening tree — exactly the shape Scan's `data/book` has. The value
// of a move is read from the resulting CHILD position, so a single
// position→score table is enough to rank every move.
//
// At probe time we mirror Scan's `book::probe`: rank the legal moves by the
// (negamax) value of their child, keep those within `margin` centipawns of the
// best, and pick ONE at random with a softmax weight (temperature `temp`). That
// gives sound variety — the engine never leaves the near-optimal envelope but
// does not play the same line every game.
//
// The tree itself is produced offline by the drop-out best-first expansion in
// `--gen-scan-book` (see main.cpp), which writes the JBK2 file this class loads.
//
// JBK2 binary format (little-endian throughout):
//   [0..4)   magic = "JBK2"
//   [4..8)   uint32 version (currently 1)
//   [8..16)  uint64 entry_count
//   [16..)   entry_count × 10-byte entries:
//              uint64  zobrist_key
//              int16   score   (backed-up negamax value, STM POV, centipawns)

#pragma once

#include "position.hpp"
#include "types.hpp"
#include "zobrist.hpp"

#include <cstddef>
#include <cstdint>
#include <optional>
#include <random>
#include <string_view>
#include <unordered_map>

namespace jass {

class ScanBook {
public:
    ScanBook();

    // Probe the book for a move to play in `pos`. Returns nullopt when `pos`
    // is not itself a known book node, or when none of its legal children are
    // in the book (we have left the book). Otherwise ranks the children by
    // negamax value, keeps those within `margin` of the best and softmax-picks
    // one. Mutates the internal RNG, hence non-const.
    std::optional<Move> probe(const Position& pos);

    // Replace the in-memory table with the contents of a JBK2 file. Returns
    // false on I/O error or bad magic/version (the JBOK loader in Book rejects
    // JBK2 and vice-versa, so the caller can auto-detect the format by trying
    // both loaders).
    bool load(std::string_view path);

    // Serialise the table to a JBK2 file. Returns false on I/O error.
    bool save(std::string_view path) const;

    // Insert / overwrite one position's backed-up score (centipawns, STM POV).
    void put(ZobristHash key, int score);

    bool        contains(ZobristHash key) const { return scores_.count(key) != 0; }
    // Backed-up score (centipawns, STM POV) for a key, or nullopt if absent.
    std::optional<int> score_of(ZobristHash key) const {
        const auto it = scores_.find(key);
        if (it == scores_.end()) return std::nullopt;
        return static_cast<int>(it->second);
    }
    std::size_t size() const noexcept { return scores_.size(); }

    // Tunables. Defaults mirror Scan's standard-variant behaviour.
    void set_margin(int cp)        noexcept { margin_ = cp; }
    void set_temperature(double t) noexcept { temp_   = t;  }
    void seed(std::uint64_t s)     noexcept { rng_.seed(s); }

private:
    std::unordered_map<ZobristHash, std::int16_t> scores_;
    int             margin_{30};     // centipawns around best kept at probe time
    double          temp_{20.0};     // softmax temperature (Scan standard = 20)
    std::mt19937_64 rng_;
};

}  // namespace jass

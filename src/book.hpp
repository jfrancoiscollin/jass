// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Opening book: a map from Zobrist hash to a single recommended move,
// stored as a `PackedMove` (4 bytes — from, to, num_captures,
// promotes) so the book fits comfortably in memory and on disk for
// large position sets.
//
// The default-constructed book ships with a hand-coded list of
// elementary opening lines. Larger pre-computed books (e.g. from a
// `--build-book` run over a position DB) can be loaded from a JBOK
// file via `load(path)` — they replace the in-memory entries.
//
// JBOK binary format (little-endian throughout):
//   [0..4)   magic = "JBOK"
//   [4..8)   uint32 version (currently 1)
//   [8..12)  uint32 entry_count
//   [12..)   `entry_count` × 16-byte entries:
//              uint64       zobrist_hash
//              PackedMove   best_move      (4 bytes)
//              int16        score          (centipawn, STM POV; 0 if unknown)
//              uint16       depth_searched (0 if unknown)

#pragma once

#include "position.hpp"
#include "tt.hpp"            // for PackedMove
#include "types.hpp"
#include "zobrist.hpp"

#include <cstddef>
#include <cstdint>
#include <optional>
#include <string_view>
#include <unordered_map>

namespace jass {

struct BookEntry {
    PackedMove   best_move{};
    std::int16_t score{0};
    std::uint16_t depth_searched{0};
};

class Book {
public:
    Book();

    // Probe the book for a move applicable in `pos`. Returns nullopt on
    // miss, on hash collision (the stored move isn't legal here) or if
    // the book is disabled.
    std::optional<Move> probe(const Position& pos) const;

    // Replace the in-memory entries with the contents of a JBOK file.
    // Returns false on I/O error or bad magic/version; the existing
    // entries are preserved in that case.
    bool load(std::string_view path);

    // Serialise the current entries to a JBOK file at `path`. Returns
    // false on I/O error.
    bool save(std::string_view path) const;

    // Add or overwrite a single entry. Used by `--build-book` and by
    // tests; the score/depth fields are advisory metadata.
    void put(ZobristHash key, const Move& m,
             int score = 0, int depth_searched = 0);

    std::size_t size() const noexcept { return entries_.size(); }

private:
    std::unordered_map<ZobristHash, BookEntry> entries_;

    void populate();
};

}  // namespace jass


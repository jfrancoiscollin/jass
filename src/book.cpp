// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "book.hpp"

#include "movegen.hpp"

#include <cstring>
#include <fstream>
#include <string>
#include <utility>
#include <vector>

namespace jass {

namespace {

// Each opening line is a flat list of (from, to) pairs starting from the
// initial position; intermediate stops are not needed because the book
// only needs the (from, to) endpoints to disambiguate a legal move.
//
// The lines were chosen from elementary international-draughts opening
// theory — the kind of moves a beginner would play almost reflexively.
// They are not copied from any opening database.
struct Step { int from; int to; };

const std::vector<std::vector<Step>> OPENING_LINES = {
    // Centre opening (32-28) and a few black replies + replies-to-replies.
    {{32, 28}, {19, 23}, {28, 19}, {14, 23}},
    {{32, 28}, {18, 22}, {37, 32}},
    {{32, 28}, {18, 23}, {38, 32}},
    {{32, 28}, {17, 22}, {28, 19}, {14, 23}},

    // Roozenburg-style 33-29.
    {{33, 28}, {18, 22}, {39, 33}},
    {{33, 29}, {19, 23}, {35, 30}},
    {{33, 29}, {18, 22}, {39, 33}},

    // 31-26 lateral push.
    {{31, 26}, {17, 22}, {37, 31}},
    {{31, 26}, {17, 21}, {26, 22}},
    {{31, 26}, {18, 22}, {37, 31}},

    // 34-30 wing.
    {{34, 30}, {20, 25}, {30, 24}},
    {{34, 30}, {19, 24}, {30, 19}},

    // 35-30.
    {{35, 30}, {20, 25}, {40, 35}},
};

constexpr char     JBOK_MAGIC[4]  = {'J', 'B', 'O', 'K'};
constexpr std::uint32_t JBOK_VERSION = 1;

}  // namespace

Book::Book() {
    populate();
}

void Book::put(ZobristHash key, const Move& m, int score, int depth_searched) {
    BookEntry e;
    e.best_move      = pack_move(m);
    e.score          = static_cast<std::int16_t>(score);
    e.depth_searched = static_cast<std::uint16_t>(
        depth_searched < 0 ? 0
      : depth_searched > 65535 ? 65535
      : depth_searched);
    entries_[key] = e;
}

void Book::populate() {
    for (const auto& line : OPENING_LINES) {
        Position pos = Position::start_position();

        for (const Step& s : line) {
            // Find the legal move whose (from, to) match this step.
            MoveList ml;
            generate_legal_moves(pos, ml);
            const Move* found = nullptr;
            for (const auto& m : ml) {
                if (static_cast<int>(m.from) == s.from
                 && static_cast<int>(m.to)   == s.to) {
                    found = &m;
                    break;
                }
            }
            if (!found) break;  // line invalid, skip the rest

            // First entry seen for this position wins; subsequent lines
            // sharing the same prefix don't overwrite.
            const ZobristHash h = zobrist_hash(pos);
            if (entries_.find(h) == entries_.end()) {
                BookEntry e;
                e.best_move      = pack_move(*found);
                e.score          = 0;
                e.depth_searched = 0;
                entries_[h]      = e;
            }
            pos = pos.after(*found);
        }
    }
}

std::optional<Move> Book::probe(const Position& pos) const {
    const auto it = entries_.find(zobrist_hash(pos));
    if (it == entries_.end()) return std::nullopt;

    // Defensive: confirm the stored move is legal in this position. A
    // hash collision (or tampered table) could otherwise have us emit
    // an illegal move. Since the book stores PackedMove, we resolve
    // against the legal-move list to recover the full capture path.
    MoveList ml;
    generate_legal_moves(pos, ml);
    for (const auto& m : ml) {
        if (same_packed_move(m, it->second.best_move)) return m;
    }
    return std::nullopt;
}

bool Book::load(std::string_view path) {
    std::ifstream f(std::string{path}, std::ios::binary);
    if (!f) return false;

    char magic[4]{};
    f.read(magic, 4);
    if (f.gcount() != 4 || std::memcmp(magic, JBOK_MAGIC, 4) != 0) return false;

    std::uint32_t version{}, count{};
    f.read(reinterpret_cast<char*>(&version), 4);
    f.read(reinterpret_cast<char*>(&count),   4);
    if (!f || version != JBOK_VERSION) return false;

    constexpr std::size_t kEntrySize = sizeof(ZobristHash)
                                     + sizeof(PackedMove)
                                     + sizeof(std::int16_t)
                                     + sizeof(std::uint16_t);
    static_assert(kEntrySize == 16, "JBOK entry must be 16 bytes");

    std::unordered_map<ZobristHash, BookEntry> tmp;
    tmp.reserve(count);
    for (std::uint32_t i = 0; i < count; ++i) {
        unsigned char buf[kEntrySize];
        f.read(reinterpret_cast<char*>(buf), kEntrySize);
        if (static_cast<std::size_t>(f.gcount()) != kEntrySize) return false;

        ZobristHash  h;       std::memcpy(&h, buf,      8);
        PackedMove   pm;      std::memcpy(&pm, buf + 8, 4);
        std::int16_t score;   std::memcpy(&score, buf + 12, 2);
        std::uint16_t depth;  std::memcpy(&depth, buf + 14, 2);

        BookEntry e;
        e.best_move      = pm;
        e.score          = score;
        e.depth_searched = depth;
        tmp[h]           = e;
    }

    entries_ = std::move(tmp);
    return true;
}

bool Book::save(std::string_view path) const {
    std::ofstream f(std::string{path}, std::ios::binary);
    if (!f) return false;

    f.write(JBOK_MAGIC, 4);
    const std::uint32_t version = JBOK_VERSION;
    const std::uint32_t count   = static_cast<std::uint32_t>(entries_.size());
    f.write(reinterpret_cast<const char*>(&version), 4);
    f.write(reinterpret_cast<const char*>(&count),   4);

    for (const auto& [h, e] : entries_) {
        unsigned char buf[16];
        std::memcpy(buf,      &h,                8);
        std::memcpy(buf + 8,  &e.best_move,      4);
        std::memcpy(buf + 12, &e.score,          2);
        std::memcpy(buf + 14, &e.depth_searched, 2);
        f.write(reinterpret_cast<const char*>(buf), 16);
    }
    return f.good();
}

}  // namespace jass

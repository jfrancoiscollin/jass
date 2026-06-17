// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "scan_book.hpp"

#include "movegen.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

namespace jass {

namespace {
constexpr char          JBK2_MAGIC[4] = {'J', 'B', 'K', '2'};
constexpr std::uint32_t JBK2_VERSION  = 1;
constexpr std::size_t   kEntrySize    = sizeof(ZobristHash) + sizeof(std::int16_t);
static_assert(kEntrySize == 10, "JBK2 entry must be 10 bytes");
}  // namespace

ScanBook::ScanBook() : rng_(std::random_device{}()) {}

void ScanBook::put(ZobristHash key, int score) {
    if (score >  32767) score =  32767;
    if (score < -32767) score = -32767;
    scores_[key] = static_cast<std::int16_t>(score);
}

std::optional<Move> ScanBook::probe(const Position& pos) {
    // Must be a known book node, otherwise we have left the book. This guards
    // against a stray midgame position whose child happens to collide with a
    // book key.
    if (scores_.find(zobrist_hash(pos)) == scores_.end()) return std::nullopt;

    MoveList ml;
    generate_legal_moves(pos, ml);
    if (ml.empty()) return std::nullopt;

    struct Cand { Move m; int val; };
    std::vector<Cand> cand;
    cand.reserve(ml.size());
    for (const auto& m : ml) {
        const Position child = pos.after(m);
        const auto it = scores_.find(zobrist_hash(child));
        if (it == scores_.end()) continue;          // child not in book
        // Negamax: the value of the move to US is minus the child's value
        // (which is stored from the child STM's perspective).
        cand.push_back({m, -static_cast<int>(it->second)});
    }
    if (cand.empty()) return std::nullopt;

    std::sort(cand.begin(), cand.end(),
              [](const Cand& a, const Cand& b) { return a.val > b.val; });
    const int best = cand[0].val;

    // Keep moves within `margin` of the best and softmax-weight them.
    std::vector<double> w;
    w.reserve(cand.size());
    double total = 0.0;
    for (const auto& c : cand) {
        if (c.val + margin_ < best) break;          // drop clearly inferior
        const double e = std::exp(static_cast<double>(c.val - best)
                                  / (temp_ > 1.0 ? temp_ : 1.0));
        w.push_back(e);
        total += e;
    }
    if (total <= 0.0) return cand.front().m;

    std::uniform_real_distribution<double> uni(0.0, total);
    double r = uni(rng_);
    for (std::size_t i = 0; i < w.size(); ++i) {
        r -= w[i];
        if (r <= 0.0) return cand[i].m;
    }
    return cand.front().m;
}

bool ScanBook::load(std::string_view path) {
    std::ifstream f(std::string{path}, std::ios::binary);
    if (!f) return false;

    char magic[4]{};
    f.read(magic, 4);
    if (f.gcount() != 4 || std::memcmp(magic, JBK2_MAGIC, 4) != 0) return false;

    std::uint32_t version{};
    std::uint64_t count{};
    f.read(reinterpret_cast<char*>(&version), 4);
    f.read(reinterpret_cast<char*>(&count),   8);
    if (!f || version != JBK2_VERSION) return false;

    std::unordered_map<ZobristHash, std::int16_t> tmp;
    tmp.reserve(count);
    for (std::uint64_t i = 0; i < count; ++i) {
        unsigned char buf[kEntrySize];
        f.read(reinterpret_cast<char*>(buf), kEntrySize);
        if (static_cast<std::size_t>(f.gcount()) != kEntrySize) return false;

        ZobristHash  h;     std::memcpy(&h,     buf,     8);
        std::int16_t score; std::memcpy(&score, buf + 8, 2);
        tmp[h] = score;
    }

    scores_ = std::move(tmp);
    return true;
}

bool ScanBook::save(std::string_view path) const {
    std::ofstream f(std::string{path}, std::ios::binary);
    if (!f) return false;

    f.write(JBK2_MAGIC, 4);
    const std::uint32_t version = JBK2_VERSION;
    const std::uint64_t count   = static_cast<std::uint64_t>(scores_.size());
    f.write(reinterpret_cast<const char*>(&version), 4);
    f.write(reinterpret_cast<const char*>(&count),   8);

    for (const auto& [h, score] : scores_) {
        unsigned char buf[kEntrySize];
        std::memcpy(buf,     &h,     8);
        std::memcpy(buf + 8, &score, 2);
        f.write(reinterpret_cast<const char*>(buf), kEntrySize);
    }
    return f.good();
}

}  // namespace jass

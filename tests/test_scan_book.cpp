// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Tests for the Scan-style opening book (position->score table, JBK2 format,
// margin + softmax probe) and its Engine auto-detection.

#include "test_framework.hpp"

#include "engine.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "scan_book.hpp"
#include "search.hpp"
#include "zobrist.hpp"

#include <cstdio>
#include <fstream>
#include <string>
#include <unistd.h>
#include <vector>

using namespace jass;

namespace {

// Build a one-ply book around the start position: insert the start node plus
// every child, giving exactly one child a clearly better (negamax) value.
// Returns the move that leads to that best child.
Move seed_start_book(ScanBook& b, int gap_cp = 500) {
    const Position start = Position::start_position();
    b.put(zobrist_hash(start), 0);

    MoveList ml;
    generate_legal_moves(start, ml);
    JASS_CHECK(ml.size() > 1);

    Move best{};
    bool first = true;
    for (const auto& m : ml) {
        const Position child = start.after(m);
        // child score is from the CHILD STM's POV; a LOW child score means a
        // HIGH value for us (negamax). Make the first child the best by giving
        // it the most negative child score.
        const int child_score = first ? -gap_cp : 0;
        b.put(zobrist_hash(child), child_score);
        if (first) { best = m; first = false; }
    }
    return best;
}

void test_scan_book_roundtrip() {
    ScanBook a;
    seed_start_book(a);
    const std::size_t n = a.size();

    char tmpl[] = "/tmp/jass_scanbook_XXXXXX";
    const int fd = mkstemp(tmpl);
    JASS_CHECK(fd >= 0);
    if (fd >= 0) close(fd);
    const std::string path = tmpl;

    JASS_CHECK(a.save(path));
    ScanBook b;
    JASS_CHECK(b.load(path));
    JASS_CHECK_EQ(b.size(), n);
    JASS_CHECK(b.contains(zobrist_hash(Position::start_position())));
    std::remove(path.c_str());
}

void test_scan_book_rejects_bad_magic() {
    char tmpl[] = "/tmp/jass_scanbook_bad_XXXXXX";
    const int fd = mkstemp(tmpl);
    JASS_CHECK(fd >= 0);
    if (fd >= 0) close(fd);
    const std::string path = tmpl;

    std::ofstream f(path, std::ios::binary);
    f << "JBOK....not a scan book....";
    f.close();

    ScanBook b;
    JASS_CHECK(!b.load(path));   // must refuse a non-JBK2 file
    std::remove(path.c_str());
}

// With a wide margin the probe must always return a legal move; with a tiny
// margin and a large value gap it must return exactly the best move.
void test_scan_book_probe_picks_best_under_tight_margin() {
    ScanBook b;
    const Move best = seed_start_book(b, /*gap_cp=*/500);
    b.set_margin(1);             // only the single best child survives the cut
    b.seed(12345);

    const Position start = Position::start_position();
    for (int i = 0; i < 20; ++i) {
        const auto m = b.probe(start);
        JASS_CHECK(m.has_value());
        if (m) JASS_CHECK(*m == best);
    }
}

// A position absent from the book (or one whose children are absent) yields no
// book move — the engine must fall back to search.
void test_scan_book_misses_off_book() {
    ScanBook b;
    seed_start_book(b);

    // An off-book position: play one legal move from start, that child is in
    // the book but ITS children are not, so probing it returns nullopt.
    const Position start = Position::start_position();
    MoveList ml;
    generate_legal_moves(start, ml);
    const Position child = start.after(ml[0]);
    JASS_CHECK(b.contains(zobrist_hash(child)));   // child node present
    JASS_CHECK(!b.probe(child).has_value());        // but its kids are not
}

// Engine::load_book must auto-detect a JBK2 file and route probes through the
// Scan book.
void test_engine_autodetects_scan_book() {
    ScanBook b;
    seed_start_book(b, /*gap_cp=*/500);

    char tmpl[] = "/tmp/jass_scanbook_eng_XXXXXX";
    const int fd = mkstemp(tmpl);
    JASS_CHECK(fd >= 0);
    if (fd >= 0) close(fd);
    const std::string path = tmpl;
    JASS_CHECK(b.save(path));

    Engine e;
    JASS_CHECK(e.load_book(path));
    JASS_CHECK_EQ(e.book_size(), b.size());

    e.new_game();
    const SearchResult r = e.search(/*max_depth=*/1);
    JASS_CHECK(r.from_book);     // start position is a book node -> book move
    std::remove(path.c_str());
}

}  // namespace

void run_scan_book_tests() {
    test_scan_book_roundtrip();
    test_scan_book_rejects_bad_magic();
    test_scan_book_probe_picks_best_under_tight_margin();
    test_scan_book_misses_off_book();
    test_engine_autodetects_scan_book();
}

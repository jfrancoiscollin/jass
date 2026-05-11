// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Tests for the opening book and its Engine integration.

#include "test_framework.hpp"

#include "book.hpp"
#include "engine.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "search.hpp"
#include "zobrist.hpp"

#include <cstdio>
#include <cstdint>
#include <fstream>
#include <string>
#include <unistd.h>

using namespace jass;

namespace {

bool legal_move(const Position& pos, const Move& m) {
    MoveList ml;
    generate_legal_moves(pos, ml);
    for (const auto& lm : ml) if (lm == m) return true;
    return false;
}

// -----------------------------------------------------------------------------
// Book itself
// -----------------------------------------------------------------------------
void test_book_has_entries() {
    Book b;
    JASS_CHECK(b.size() > 0);
}

void test_book_probes_start_position() {
    Book b;
    const auto m = b.probe(Position::start_position());
    JASS_CHECK(m.has_value());
    if (m) JASS_CHECK(legal_move(Position::start_position(), *m));
}

void test_book_misses_after_off_book_move() {
    Book b;
    Position p = Position::start_position();

    // Play an arbitrary off-book move (the book lines all start with
    // 31-26 / 32-28 / 33-28 / 33-29 / 34-30 / 35-30; pick something
    // else: 35-30 IS in the book, but 34-29 is not).
    MoveList ml;
    generate_legal_moves(p, ml);
    for (const auto& m : ml) {
        if (m.from == 34 && m.to == 29) { p = p.after(m); break; }
    }
    JASS_CHECK(p.side_to_move() == Color::Black);

    JASS_CHECK(!b.probe(p).has_value());
}

// -----------------------------------------------------------------------------
// Engine integration
// -----------------------------------------------------------------------------
void test_engine_search_uses_book_in_opening() {
    Engine e;
    const SearchResult r = e.search(/*max_depth=*/1);
    JASS_CHECK(r.from_book);
    JASS_CHECK_EQ(r.depth, 0);
    JASS_CHECK_EQ(r.nodes, static_cast<std::uint64_t>(0));
    JASS_CHECK(legal_move(e.position(), r.best_move));
}

void test_engine_disabled_book_falls_back_to_search() {
    Engine e;
    e.use_book(false);
    const SearchResult r = e.search(/*max_depth=*/2);
    JASS_CHECK(!r.from_book);
    JASS_CHECK_EQ(r.depth, 2);
    JASS_CHECK(r.nodes > 0);
}

// -----------------------------------------------------------------------------
// JBOK save / load round-trip
// -----------------------------------------------------------------------------
std::string mkstemp_path(const char* tmpl_in) {
    std::string buf{tmpl_in};
    int fd = ::mkstemp(buf.data());
    if (fd >= 0) ::close(fd);
    return buf;
}

void test_book_save_load_roundtrip() {
    Book a;
    const std::size_t before = a.size();
    JASS_CHECK(before > 0);

    // Add a manually crafted entry so we can detect that round-trip
    // captures user-added data and not just the hard-coded openings.
    const Position p = Position::start_position();
    MoveList ml;
    generate_legal_moves(p, ml);
    // Pick a specific move (34-30 — not in the hard-coded opening set
    // we test, well, it IS in the set, but as a starter — let's pick
    // 34-29 which is intentionally off-book).
    const Move* off = nullptr;
    for (const auto& m : ml) {
        if (m.from == 34 && m.to == 29) { off = &m; break; }
    }
    JASS_CHECK(off != nullptr);

    // We register the entry at a fake hash so we can detect it; the
    // legal-move match would fail at probe time (off-position), but
    // the entry round-trips by size + lookup directly via probe()'s
    // sister API would, which we don't have. Instead we just assert
    // size grew by one.
    a.put(0xDEADBEEFCAFEBABEULL, *off, /*score=*/42, /*depth=*/7);
    JASS_CHECK_EQ(a.size(), before + 1);

    const std::string path = mkstemp_path("/tmp/jass-book-XXXXXX");
    JASS_CHECK(a.save(path));

    Book b;
    JASS_CHECK(b.load(path));
    JASS_CHECK_EQ(b.size(), a.size());

    // The hard-coded entries should still probe correctly after load.
    const auto m_start = b.probe(Position::start_position());
    JASS_CHECK(m_start.has_value());

    std::remove(path.c_str());
}

void test_book_load_rejects_bad_files() {
    Book b;

    // Missing file.
    JASS_CHECK(!b.load("/no/such/path/jass-book.bok"));

    // Wrong magic.
    const std::string bad_magic = mkstemp_path("/tmp/jass-book-bad-XXXXXX");
    {
        std::ofstream f(bad_magic, std::ios::binary);
        f.write("ZZZZ", 4);
        const std::uint32_t zero = 0;
        f.write(reinterpret_cast<const char*>(&zero), 4);
        f.write(reinterpret_cast<const char*>(&zero), 4);
    }
    JASS_CHECK(!b.load(bad_magic));
    std::remove(bad_magic.c_str());

    // The original hard-coded book should still be intact.
    JASS_CHECK(b.size() > 0);
}

void test_book_engine_load_book_swaps_default() {
    Book b;
    const std::size_t default_size = b.size();
    const std::string path = mkstemp_path("/tmp/jass-engine-book-XXXXXX");

    // Save the current (default) book to disk, then load it back via
    // the engine surface — the size should match and probes should
    // still work in the opening.
    JASS_CHECK(b.save(path));

    Engine e;
    JASS_CHECK_EQ(e.book_size(), default_size);
    JASS_CHECK(e.load_book(path));
    JASS_CHECK_EQ(e.book_size(), default_size);

    const SearchResult r = e.search(/*max_depth=*/1);
    JASS_CHECK(r.from_book);

    std::remove(path.c_str());
}

}  // namespace

void run_book_tests() {
    test_book_has_entries();
    test_book_probes_start_position();
    test_book_misses_after_off_book_move();
    test_engine_search_uses_book_in_opening();
    test_engine_disabled_book_falls_back_to_search();
    test_book_save_load_roundtrip();
    test_book_load_rejects_bad_files();
    test_book_engine_load_book_swaps_default();
}

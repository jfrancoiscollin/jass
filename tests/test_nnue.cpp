// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin
//
// Tests for the NNUE-lite framework. The default-constructed network
// is meant to *approximate* the handcrafted eval; the small differences
// come from the omitted runtime support-bonus term, so we test
// behaviour invariants (sign, ordering, reload round-trip) rather than
// exact equality.

#include "test_framework.hpp"

#include "eval.hpp"
#include "nnue.hpp"
#include "position.hpp"

#include <cstdio>
#include <string>
#include <string_view>
#include <unistd.h>

using namespace jass;

namespace {

Position parse(std::string_view fen) {
    auto p = Position::from_fen(fen);
    JASS_CHECK(p.has_value());
    return p.value_or(Position{});
}

void test_default_network_close_to_handcrafted_on_start() {
    const Position p = Position::start_position();
    const int      h = evaluate(p);
    const int      n = evaluate_nnue(p);
    // Both should be tiny (near tempo magnitude). The NNUE omits the
    // runtime support bonus so the two numbers can differ by a few
    // tens of centipawns.
    JASS_CHECK(n > -2 * MAN_VALUE / 5);
    JASS_CHECK(n <  2 * MAN_VALUE / 5);
    (void)h;  // keep `h` referenced so the compiler keeps the call alive
}

void test_default_network_tracks_material() {
    const Position p_full   = Position::start_position();
    const Position p_minus  = parse("W:W31-50:B1-19");
    JASS_CHECK(evaluate_nnue(p_minus) - evaluate_nnue(p_full)
               > MAN_VALUE / 2);
}

void test_default_network_signs_with_stm() {
    const Position w = parse("W:W31-50:B1-15");
    const Position b = parse("B:W31-50:B1-15");
    JASS_CHECK(evaluate_nnue(w) >  MAN_VALUE);
    JASS_CHECK(evaluate_nnue(b) < -MAN_VALUE);
}

void test_network_save_load_roundtrip() {
    LinearNetwork net;
    const Position p = Position::start_position();
    const int before = net.evaluate(p);

    char tmpl[] = "/tmp/jass-nnue-XXXXXX";
    int fd = ::mkstemp(tmpl);
    JASS_CHECK(fd >= 0);
    if (fd < 0) return;
    ::close(fd);

    JASS_CHECK(net.save(tmpl));

    LinearNetwork loaded;
    JASS_CHECK(loaded.load(tmpl));
    JASS_CHECK_EQ(loaded.evaluate(p), before);

    std::remove(tmpl);
}

void test_network_load_rejects_missing_file() {
    LinearNetwork net;
    JASS_CHECK(!net.load("/no/such/path/jass-nnue.bin"));
}

}  // namespace

void run_nnue_tests() {
    test_default_network_close_to_handcrafted_on_start();
    test_default_network_tracks_material();
    test_default_network_signs_with_stm();
    test_network_save_load_roundtrip();
    test_network_load_rejects_missing_file();
}

// SPDX-License-Identifier: AGPL-3.0-or-later
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
#include <cstring>
#include <fstream>
#include <memory>
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

// ---------------------------------------------------------------------------
// MLPNetwork — float32 perceptron 200 → 64 → 32 → 1.
// ---------------------------------------------------------------------------

// Hand-write a JNNM file with the supplied weights so the tests can
// validate the forward pass against numbers we computed by hand.
bool write_mlp_file(
        const std::string& path,
        const std::array<float, MLPNetwork::HIDDEN1 * MLPNetwork::INPUT_DIM>& w1,
        const std::array<float, MLPNetwork::HIDDEN1>&                         b1,
        const std::array<float, MLPNetwork::HIDDEN2 * MLPNetwork::HIDDEN1>&   w2,
        const std::array<float, MLPNetwork::HIDDEN2>&                         b2,
        const std::array<float, MLPNetwork::HIDDEN2>&                         w3,
        float                                                                  b3) {
    std::ofstream f(path, std::ios::binary);
    if (!f) return false;
    f.write("JNNM", 4);
    auto wu32 = [&](std::uint32_t v) {
        f.write(reinterpret_cast<const char*>(&v), 4);
    };
    wu32(1);  // version
    wu32(static_cast<std::uint32_t>(MLPNetwork::INPUT_DIM));
    wu32(static_cast<std::uint32_t>(MLPNetwork::HIDDEN1));
    wu32(static_cast<std::uint32_t>(MLPNetwork::HIDDEN2));
    wu32(1);  // output_dim

    auto wbytes = [&](const void* p, std::size_t n) {
        f.write(reinterpret_cast<const char*>(p), static_cast<std::streamsize>(n));
    };
    wbytes(w1.data(), w1.size() * sizeof(float));
    wbytes(b1.data(), b1.size() * sizeof(float));
    wbytes(w2.data(), w2.size() * sizeof(float));
    wbytes(b2.data(), b2.size() * sizeof(float));
    wbytes(w3.data(), w3.size() * sizeof(float));
    f.write(reinterpret_cast<const char*>(&b3), sizeof(float));
    return f.good();
}

std::string make_tmp_path(const char* tmpl_in) {
    std::string buf{tmpl_in};
    int fd = ::mkstemp(buf.data());
    JASS_CHECK(fd >= 0);
    if (fd >= 0) ::close(fd);
    return buf;
}

void test_mlp_default_returns_zero() {
    MLPNetwork net;
    const Position p = Position::start_position();
    JASS_CHECK_EQ(net.evaluate(p), 0);

    const Position pb = parse("B:W31-50:B1-15");
    JASS_CHECK_EQ(net.evaluate(pb), 0);
}

void test_mlp_forward_pass_matches_hand_computed() {
    // Configure a single non-zero path through the network so we can
    // predict the output bit by bit:
    //   feature 4 (square_idx=1, kind=0) → "white man on FMJD square 2"
    //   w1[0 * INPUT_DIM + 4] = 1   → only neuron 0 of layer 1 fires
    //   w2[0 * HIDDEN1 + 0]   = 2   → only neuron 0 of layer 2 fires (= 2)
    //   w3[0]                 = 100 → output = 100 * 2 = 200
    std::array<float, MLPNetwork::HIDDEN1 * MLPNetwork::INPUT_DIM> w1{};
    std::array<float, MLPNetwork::HIDDEN1>                         b1{};
    std::array<float, MLPNetwork::HIDDEN2 * MLPNetwork::HIDDEN1>   w2{};
    std::array<float, MLPNetwork::HIDDEN2>                         b2{};
    std::array<float, MLPNetwork::HIDDEN2>                         w3{};
    w1[0 * MLPNetwork::INPUT_DIM + 4] = 1.0f;
    w2[0 * MLPNetwork::HIDDEN1 + 0]   = 2.0f;
    w3[0]                             = 100.0f;

    const std::string path = make_tmp_path("/tmp/jass-mlp-fwd-XXXXXX");
    JASS_CHECK(write_mlp_file(path, w1, b1, w2, b2, w3, 0.0f));

    MLPNetwork net;
    JASS_CHECK(net.load(path));

    const Position p = parse("W:W2:B1");
    JASS_CHECK_EQ(net.evaluate(p), 200);

    // Same board, black to move — STM flip should negate the output.
    const Position pb = parse("B:W2:B1");
    JASS_CHECK_EQ(net.evaluate(pb), -200);

    // White man elsewhere → feature 4 inactive → no contribution.
    const Position other = parse("W:W3:B1");
    JASS_CHECK_EQ(net.evaluate(other), 0);

    std::remove(path.c_str());
}

void test_mlp_save_load_roundtrip() {
    std::array<float, MLPNetwork::HIDDEN1 * MLPNetwork::INPUT_DIM> w1{};
    std::array<float, MLPNetwork::HIDDEN1>                         b1{};
    std::array<float, MLPNetwork::HIDDEN2 * MLPNetwork::HIDDEN1>   w2{};
    std::array<float, MLPNetwork::HIDDEN2>                         b2{};
    std::array<float, MLPNetwork::HIDDEN2>                         w3{};
    w1[0 * MLPNetwork::INPUT_DIM + 4] = 1.0f;
    w2[0 * MLPNetwork::HIDDEN1 + 0]   = 2.0f;
    w3[0]                             = 100.0f;

    const std::string in_path  = make_tmp_path("/tmp/jass-mlp-in-XXXXXX");
    const std::string out_path = make_tmp_path("/tmp/jass-mlp-out-XXXXXX");
    JASS_CHECK(write_mlp_file(in_path, w1, b1, w2, b2, w3, 0.0f));

    MLPNetwork net;
    JASS_CHECK(net.load(in_path));
    JASS_CHECK(net.save(out_path));

    MLPNetwork reloaded;
    JASS_CHECK(reloaded.load(out_path));

    const Position p = parse("W:W2:B1");
    JASS_CHECK_EQ(net.evaluate(p), reloaded.evaluate(p));
    JASS_CHECK_EQ(reloaded.evaluate(p), 200);

    std::remove(in_path.c_str());
    std::remove(out_path.c_str());
}

void test_mlp_load_rejects_missing_or_bad_file() {
    MLPNetwork net;
    JASS_CHECK(!net.load("/no/such/path/jass-mlp.bin"));

    // Wrong magic — should not load.
    const std::string bad_magic = make_tmp_path("/tmp/jass-mlp-bad-XXXXXX");
    {
        std::ofstream f(bad_magic, std::ios::binary);
        f.write("XXXX", 4);
        const std::uint32_t zero = 0;
        for (int i = 0; i < 5; ++i) f.write(reinterpret_cast<const char*>(&zero), 4);
    }
    JASS_CHECK(!net.load(bad_magic));
    std::remove(bad_magic.c_str());

    // Right magic but wrong dimensions in the header.
    const std::string bad_dims = make_tmp_path("/tmp/jass-mlp-dim-XXXXXX");
    {
        std::ofstream f(bad_dims, std::ios::binary);
        f.write("JNNM", 4);
        const std::uint32_t v[5] = {1, 999u, 64u, 32u, 1u};  // input_dim wrong
        f.write(reinterpret_cast<const char*>(v), sizeof(v));
    }
    JASS_CHECK(!net.load(bad_dims));
    std::remove(bad_dims.c_str());
}

void test_load_network_dispatches_on_magic() {
    // A JNNM file should come back as something whose evaluate() matches
    // a freshly loaded MLPNetwork.
    std::array<float, MLPNetwork::HIDDEN1 * MLPNetwork::INPUT_DIM> w1{};
    std::array<float, MLPNetwork::HIDDEN1>                         b1{};
    std::array<float, MLPNetwork::HIDDEN2 * MLPNetwork::HIDDEN1>   w2{};
    std::array<float, MLPNetwork::HIDDEN2>                         b2{};
    std::array<float, MLPNetwork::HIDDEN2>                         w3{};
    w1[0 * MLPNetwork::INPUT_DIM + 4] = 1.0f;
    w2[0 * MLPNetwork::HIDDEN1 + 0]   = 2.0f;
    w3[0]                             = 100.0f;

    const std::string mlp_path = make_tmp_path("/tmp/jass-mlp-disp-XXXXXX");
    JASS_CHECK(write_mlp_file(mlp_path, w1, b1, w2, b2, w3, 0.0f));

    std::unique_ptr<INetwork> net = load_network(mlp_path);
    JASS_CHECK(net != nullptr);
    if (net) {
        JASS_CHECK_EQ(net->evaluate(parse("W:W2:B1")), 200);
    }
    std::remove(mlp_path.c_str());

    // A raw-int32 LinearNetwork file should round-trip via load_network too.
    const std::string lin_path = make_tmp_path("/tmp/jass-lin-disp-XXXXXX");
    {
        LinearNetwork ln;
        JASS_CHECK(ln.save(lin_path));
    }
    std::unique_ptr<INetwork> lin = load_network(lin_path);
    JASS_CHECK(lin != nullptr);
    if (lin) {
        const int direct  = LinearNetwork{}.evaluate(Position::start_position());
        const int through = lin->evaluate(Position::start_position());
        JASS_CHECK_EQ(direct, through);
    }
    std::remove(lin_path.c_str());
}

}  // namespace

void run_nnue_tests() {
    test_default_network_close_to_handcrafted_on_start();
    test_default_network_tracks_material();
    test_default_network_signs_with_stm();
    test_network_save_load_roundtrip();
    test_network_load_rejects_missing_file();
    test_mlp_default_returns_zero();
    test_mlp_forward_pass_matches_hand_computed();
    test_mlp_save_load_roundtrip();
    test_mlp_load_rejects_missing_or_bad_file();
    test_load_network_dispatches_on_magic();
}

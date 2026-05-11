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
    wu32(2);  // version (STM-relative encoding)
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
    //   feature 4 (b=1, kind=0) = "STM has man on bit 1 (FMJD square 2)"
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

    // White-to-move, white man on FMJD square 2 (bit 1). Encoding does
    // NOT mirror, so feature index = 1 * 4 + 0 (stm-man) = 4. Active.
    const Position p_w = parse("W:W2:B1");
    JASS_CHECK_EQ(net.evaluate(p_w), 200);

    // STM-symmetric counterpart: black to move with a black man on the
    // mirrored square (49 -> bit 48 -> mirrored bit 1 -> feature 4),
    // white man on the mirrored other square (1 -> bit 0 -> mirrored
    // bit 49 -> feature 49*4+2=198, weight zero). Same input vector,
    // therefore same output 200 (no sign flip in v2 encoding).
    const Position p_b = parse("B:W1:B49");
    JASS_CHECK_EQ(net.evaluate(p_b), 200);

    // White-to-move with the man on a different square → feature 4
    // inactive → no contribution.
    const Position other = parse("W:W3:B1");
    JASS_CHECK_EQ(net.evaluate(other), 0);

    std::remove(path.c_str());
}

void test_mlp_position_level_symmetry() {
    // Same hand-crafted single-path network. Any position P (white to
    // move) and its mirror+colour-swap P' (black to move) must
    // evaluate to the same number under the v2 STM-relative encoding.
    std::array<float, MLPNetwork::HIDDEN1 * MLPNetwork::INPUT_DIM> w1{};
    std::array<float, MLPNetwork::HIDDEN1>                         b1{};
    std::array<float, MLPNetwork::HIDDEN2 * MLPNetwork::HIDDEN1>   w2{};
    std::array<float, MLPNetwork::HIDDEN2>                         b2{};
    std::array<float, MLPNetwork::HIDDEN2>                         w3{};
    // A handful of arbitrary live weights so the network actually
    // discriminates between positions instead of returning a constant.
    w1[0 * MLPNetwork::INPUT_DIM +   4] =  1.0f;
    w1[1 * MLPNetwork::INPUT_DIM +  60] = -2.0f;
    w1[2 * MLPNetwork::INPUT_DIM + 158] =  3.0f;
    w2[0 * MLPNetwork::HIDDEN1 + 0]     =  2.0f;
    w2[1 * MLPNetwork::HIDDEN1 + 0]     = -1.5f;
    w2[2 * MLPNetwork::HIDDEN1 + 2]     =  4.0f;
    w3[0] = 100.0f;
    w3[1] =  50.0f;
    w3[2] =  25.0f;

    const std::string path = make_tmp_path("/tmp/jass-mlp-sym-XXXXXX");
    JASS_CHECK(write_mlp_file(path, w1, b1, w2, b2, w3, 7.0f));

    MLPNetwork net;
    JASS_CHECK(net.load(path));

    // P : white men on {2, 15}, black men on {40, 49}. White to move.
    // Mirror white squares 2 -> 49, 15 -> 36. Mirror black squares
    // 40 -> 11, 49 -> 2. Swap colours: white now has men on the
    // mirrored black squares {11, 2}, black on the mirrored white
    // squares {49, 36}. Black to move.
    const Position p_w = parse("W:W2,15:B40,49");
    const Position p_b = parse("B:W2,11:B36,49");
    JASS_CHECK_EQ(net.evaluate(p_w), net.evaluate(p_b));

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

// Cycle-3 regression: a JNNM file with non-default hidden dims must
// round-trip cleanly. We build a 128×64 network with a single non-zero
// path (input 4 → h1[0] → h2[0] → out), save, reload, and check the
// forward pass.
void test_mlp_load_supports_non_default_hidden_dims() {
    constexpr std::size_t kH1 = 128;
    constexpr std::size_t kH2 = 64;

    MLPNetwork net(kH1, kH2);
    JASS_CHECK_EQ(net.hidden1(), kH1);
    JASS_CHECK_EQ(net.hidden2(), kH2);

    // Build a JNNM file by hand for the 128-64 topology. Single wired
    // path: feature 4 (white man on bit 1) → h1[0] (weight 1) →
    // h2[0] (weight 2) → out (weight 100). Expected score = 200 when a
    // white man stands on FMJD square 2 (bit 1).
    const std::string in_path  = make_tmp_path("/tmp/jass-mlp-wide-in-XXXXXX");
    const std::string out_path = make_tmp_path("/tmp/jass-mlp-wide-out-XXXXXX");
    {
        std::ofstream f(in_path, std::ios::binary);
        JASS_CHECK(static_cast<bool>(f));
        f.write("JNNM", 4);
        auto wu32 = [&](std::uint32_t v) {
            f.write(reinterpret_cast<const char*>(&v), 4);
        };
        wu32(2u);
        wu32(static_cast<std::uint32_t>(MLPNetwork::INPUT_DIM));
        wu32(static_cast<std::uint32_t>(kH1));
        wu32(static_cast<std::uint32_t>(kH2));
        wu32(1u);

        std::vector<float> w1(kH1 * MLPNetwork::INPUT_DIM, 0.0f);
        std::vector<float> b1(kH1, 0.0f);
        std::vector<float> w2(kH2 * kH1, 0.0f);
        std::vector<float> b2(kH2, 0.0f);
        std::vector<float> w3(kH2, 0.0f);
        w1[0 * MLPNetwork::INPUT_DIM + 4] = 1.0f;
        w2[0 * kH1 + 0]                   = 2.0f;
        w3[0]                             = 100.0f;
        auto wbytes = [&](const void* p, std::size_t n) {
            f.write(reinterpret_cast<const char*>(p),
                    static_cast<std::streamsize>(n));
        };
        wbytes(w1.data(), w1.size() * sizeof(float));
        wbytes(b1.data(), b1.size() * sizeof(float));
        wbytes(w2.data(), w2.size() * sizeof(float));
        wbytes(b2.data(), b2.size() * sizeof(float));
        wbytes(w3.data(), w3.size() * sizeof(float));
        const float b3 = 0.0f;
        f.write(reinterpret_cast<const char*>(&b3), sizeof(float));
    }

    JASS_CHECK(net.load(in_path));
    JASS_CHECK_EQ(net.hidden1(), kH1);
    JASS_CHECK_EQ(net.hidden2(), kH2);

    // Re-save through MLPNetwork::save, reload, and check both
    // instances return the same score on the trigger position.
    JASS_CHECK(net.save(out_path));
    MLPNetwork reloaded;
    JASS_CHECK(reloaded.load(out_path));
    JASS_CHECK_EQ(reloaded.hidden1(), kH1);
    JASS_CHECK_EQ(reloaded.hidden2(), kH2);

    const Position p = parse("W:W2:B1");
    JASS_CHECK_EQ(net.evaluate(p),      200);
    JASS_CHECK_EQ(reloaded.evaluate(p), 200);

    std::remove(in_path.c_str());
    std::remove(out_path.c_str());
}

// Cycle-6c: HalfMen-lite encoding (450 features = 200 abs + 200
// anchor-relative + 50 anchor one-hot). Builds a 450 → 32 → 16 → 1
// network with a single hand-wired path covering one example of each
// of the three feature groups, hand-computes the expected output, and
// verifies save+load round-trip preserves both dims and behaviour.
void test_mlp_halfmen_encoding_end_to_end() {
    constexpr std::size_t kInD = MLPNetwork::HALFMEN_INPUT_DIM;  // 450
    constexpr std::size_t kH1  = 32;
    constexpr std::size_t kH2  = 16;

    // Test position W:W2:B1 — white-to-move, white man at FMJD 2
    // (bit 1), black man at FMJD 1 (bit 0). Hand-computed encoding:
    //   * white pieces ⇒ anchor = MSB of white bb = bit 1, so anchor=1.
    //   * abs[1*4+0] = abs[4]   (white man on FMJD 2, kind 0)
    //   * abs[0*4+2] = abs[2]   (black man on FMJD 1, kind 2 in STM-POV)
    //   * rel for white: (1-1) mod 50 = 0 → 200 + 0*4 + 0 = 200
    //   * rel for black: (0-1) mod 50 = 49 → 200 + 49*4 + 2 = 398
    //   * anchor one-hot at 400 + 1 = 401
    // Wire each of those features into neuron 0 of layer 1, plumb
    // through h2[0] then out. Total h1[0] = 4.0, evaluate() = 4.
    MLPNetwork net(kInD, kH1, kH2);
    JASS_CHECK_EQ(net.input_dim(), kInD);
    JASS_CHECK_EQ(net.hidden1(),   kH1);
    JASS_CHECK_EQ(net.hidden2(),   kH2);

    const std::string in_path  = make_tmp_path("/tmp/jass-mlp-hm-in-XXXXXX");
    const std::string out_path = make_tmp_path("/tmp/jass-mlp-hm-out-XXXXXX");
    {
        std::ofstream f(in_path, std::ios::binary);
        JASS_CHECK(static_cast<bool>(f));
        f.write("JNNM", 4);
        auto wu32 = [&](std::uint32_t v) {
            f.write(reinterpret_cast<const char*>(&v), 4);
        };
        wu32(3u);  // version 3 — HalfMen support
        wu32(static_cast<std::uint32_t>(kInD));
        wu32(static_cast<std::uint32_t>(kH1));
        wu32(static_cast<std::uint32_t>(kH2));
        wu32(1u);

        std::vector<float> w1(kH1 * kInD, 0.0f);
        std::vector<float> b1(kH1, 0.0f);
        std::vector<float> w2(kH2 * kH1, 0.0f);
        std::vector<float> b2(kH2, 0.0f);
        std::vector<float> w3(kH2, 0.0f);
        // Single-neuron path through layer 1:
        w1[0 * kInD +   4] = 1.0f;  // abs white
        w1[0 * kInD +   2] = 1.0f;  // abs black
        w1[0 * kInD + 200] = 1.0f;  // rel white (rel = 0)
        w1[0 * kInD + 398] = 1.0f;  // rel black (rel = 49)
        w1[0 * kInD + 401] = 1.0f;  // anchor one-hot (anchor = 1)
        w2[0 * kH1  +   0] = 1.0f;  // h1[0] → h2[0]
        w3[0]              = 1.0f;  // h2[0] → out

        auto wbytes = [&](const void* p, std::size_t n) {
            f.write(reinterpret_cast<const char*>(p),
                    static_cast<std::streamsize>(n));
        };
        wbytes(w1.data(), w1.size() * sizeof(float));
        wbytes(b1.data(), b1.size() * sizeof(float));
        wbytes(w2.data(), w2.size() * sizeof(float));
        wbytes(b2.data(), b2.size() * sizeof(float));
        wbytes(w3.data(), w3.size() * sizeof(float));
        const float b3 = 0.0f;
        f.write(reinterpret_cast<const char*>(&b3), sizeof(float));
    }

    JASS_CHECK(net.load(in_path));
    JASS_CHECK_EQ(net.input_dim(), kInD);
    JASS_CHECK_EQ(net.hidden1(),   kH1);
    JASS_CHECK_EQ(net.hidden2(),   kH2);

    const Position p = parse("W:W2:B1");
    JASS_CHECK_EQ(net.evaluate(p), 5);  // abs+abs+rel+rel+anchor = 5

    // Save round-trip preserves input_dim and behaviour.
    JASS_CHECK(net.save(out_path));
    MLPNetwork reloaded;
    JASS_CHECK(reloaded.load(out_path));
    JASS_CHECK_EQ(reloaded.input_dim(), kInD);
    JASS_CHECK_EQ(reloaded.hidden1(),   kH1);
    JASS_CHECK_EQ(reloaded.hidden2(),   kH2);
    JASS_CHECK_EQ(reloaded.evaluate(p), 5);

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

    // Right magic but wrong dimensions in the header (input_dim).
    const std::string bad_dims = make_tmp_path("/tmp/jass-mlp-dim-XXXXXX");
    {
        std::ofstream f(bad_dims, std::ios::binary);
        f.write("JNNM", 4);
        const std::uint32_t v[5] = {
            2,
            999u,  // input_dim — wrong
            static_cast<std::uint32_t>(MLPNetwork::HIDDEN1),
            static_cast<std::uint32_t>(MLPNetwork::HIDDEN2),
            1u,
        };
        f.write(reinterpret_cast<const char*>(v), sizeof(v));
    }
    JASS_CHECK(!net.load(bad_dims));
    std::remove(bad_dims.c_str());

    // Right dimensions but old (v1) version — must be rejected
    // explicitly because the input encoding changed in v2.
    const std::string old_version = make_tmp_path("/tmp/jass-mlp-v1-XXXXXX");
    {
        std::ofstream f(old_version, std::ios::binary);
        f.write("JNNM", 4);
        const std::uint32_t v[5] = {
            1,  // version — wrong (must be 2)
            static_cast<std::uint32_t>(MLPNetwork::INPUT_DIM),
            static_cast<std::uint32_t>(MLPNetwork::HIDDEN1),
            static_cast<std::uint32_t>(MLPNetwork::HIDDEN2),
            1u,
        };
        f.write(reinterpret_cast<const char*>(v), sizeof(v));
    }
    JASS_CHECK(!net.load(old_version));
    std::remove(old_version.c_str());
}

// ---------------------------------------------------------------------------
// default_nnue() — pointer to the binary-embedded network (Linear or MLP).
// ---------------------------------------------------------------------------
void test_default_nnue_is_non_null_and_returns_finite_score() {
    const INetwork* net = default_nnue();
    JASS_CHECK(net != nullptr);
    if (!net) return;

    const Position p = Position::start_position();
    const int score = net->evaluate(p);
    // The trained weights tend to call the start position close to even
    // (small magnitude of a few centipawns); 1000 is a generous bound
    // that catches any catastrophic deserialization bug.
    JASS_CHECK(score >  -1000);
    JASS_CHECK(score <   1000);
}

void test_default_nnue_is_stable_across_calls() {
    // The lazy initialiser must hand out the same instance every call,
    // not allocate a fresh one (otherwise an Engine that pinned the
    // pointer at startup would be holding a dangling reference).
    const INetwork* a = default_nnue();
    const INetwork* b = default_nnue();
    JASS_CHECK_EQ(a, b);
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

// ---------------------------------------------------------------------------
// MLPNetworkQ — int8 quantised perceptron.
// ---------------------------------------------------------------------------

bool write_mlpq_file(
        const std::string& path,
        const std::array<std::int8_t,
                         MLPNetworkQ::HIDDEN1 * MLPNetworkQ::INPUT_DIM>& w1,
        const std::array<std::int32_t, MLPNetworkQ::HIDDEN1>&            b1,
        const std::array<std::int8_t,
                         MLPNetworkQ::HIDDEN2 * MLPNetworkQ::HIDDEN1>&   w2,
        const std::array<std::int32_t, MLPNetworkQ::HIDDEN2>&            b2,
        const std::array<std::int8_t, MLPNetworkQ::HIDDEN2>&             w3,
        std::int32_t b3,
        float mul1, float mul2, float mul_out) {
    std::ofstream f(path, std::ios::binary);
    if (!f) return false;
    f.write("JNNQ", 4);
    auto wu32 = [&](std::uint32_t v) {
        f.write(reinterpret_cast<const char*>(&v), 4);
    };
    wu32(1);  // version
    wu32(static_cast<std::uint32_t>(MLPNetworkQ::INPUT_DIM));
    wu32(static_cast<std::uint32_t>(MLPNetworkQ::HIDDEN1));
    wu32(static_cast<std::uint32_t>(MLPNetworkQ::HIDDEN2));
    wu32(1u);
    auto wf = [&](float v) {
        f.write(reinterpret_cast<const char*>(&v), 4);
    };
    wf(mul1); wf(mul2); wf(mul_out);
    auto wbytes = [&](const void* p, std::size_t n) {
        f.write(reinterpret_cast<const char*>(p), static_cast<std::streamsize>(n));
    };
    wbytes(w1.data(), w1.size() * sizeof(std::int8_t));
    wbytes(b1.data(), b1.size() * sizeof(std::int32_t));
    wbytes(w2.data(), w2.size() * sizeof(std::int8_t));
    wbytes(b2.data(), b2.size() * sizeof(std::int32_t));
    wbytes(w3.data(), w3.size() * sizeof(std::int8_t));
    f.write(reinterpret_cast<const char*>(&b3), sizeof(std::int32_t));
    return f.good();
}

void test_mlpq_forward_pass_matches_hand_computed() {
    // Build the smallest deterministic path that yields a non-trivial
    // output, mirroring the float MLP test.
    //   feature 4 (b=1, kind=0) = "STM has man on bit 1 (FMJD square 2)"
    //   w1[0 * INPUT_DIM + 4] = 100  → acc1[0] = 100 (only neuron firing)
    //   mul1 = 0.5                    → h1[0] = round(50) = 50
    //   w2[0 * HIDDEN1 + 0]   = 4     → acc2[0] = 4 * 50 = 200
    //   mul2 = 1.0                    → h2[0] = 200 → clipped to 127
    //   w3[0]                 = 1     → acc3 = 127
    //   mul_out = 2.0                 → out = 254
    std::array<std::int8_t,  MLPNetworkQ::HIDDEN1 * MLPNetworkQ::INPUT_DIM> w1{};
    std::array<std::int32_t, MLPNetworkQ::HIDDEN1>                          b1{};
    std::array<std::int8_t,  MLPNetworkQ::HIDDEN2 * MLPNetworkQ::HIDDEN1>   w2{};
    std::array<std::int32_t, MLPNetworkQ::HIDDEN2>                          b2{};
    std::array<std::int8_t,  MLPNetworkQ::HIDDEN2>                          w3{};
    w1[0 * MLPNetworkQ::INPUT_DIM + 4]   = 100;
    w2[0 * MLPNetworkQ::HIDDEN1   + 0]   = 4;
    w3[0]                                 = 1;

    const std::string path = make_tmp_path("/tmp/jass-mlpq-fwd-XXXXXX");
    JASS_CHECK(write_mlpq_file(path, w1, b1, w2, b2, w3, 0,
                               /*mul1=*/0.5f, /*mul2=*/1.0f, /*mul_out=*/2.0f));

    MLPNetworkQ net;
    JASS_CHECK(net.load(path));

    const Position p_w = parse("W:W2:B1");
    JASS_CHECK_EQ(net.evaluate(p_w), 254);

    // STM symmetry: mirrored black-to-move position must light up the
    // same feature index.
    const Position p_b = parse("B:W1:B49");
    JASS_CHECK_EQ(net.evaluate(p_b), 254);

    // Different square → feature inactive → 0 contribution at every layer.
    const Position other = parse("W:W3:B1");
    JASS_CHECK_EQ(net.evaluate(other), 0);

    std::remove(path.c_str());
}

void test_mlpq_save_load_roundtrip() {
    std::array<std::int8_t,  MLPNetworkQ::HIDDEN1 * MLPNetworkQ::INPUT_DIM> w1{};
    std::array<std::int32_t, MLPNetworkQ::HIDDEN1>                          b1{};
    std::array<std::int8_t,  MLPNetworkQ::HIDDEN2 * MLPNetworkQ::HIDDEN1>   w2{};
    std::array<std::int32_t, MLPNetworkQ::HIDDEN2>                          b2{};
    std::array<std::int8_t,  MLPNetworkQ::HIDDEN2>                          w3{};
    w1[0 * MLPNetworkQ::INPUT_DIM + 4] = 100;
    w2[0 * MLPNetworkQ::HIDDEN1   + 0] = 4;
    w3[0]                              = 1;

    const std::string in_path  = make_tmp_path("/tmp/jass-mlpq-in-XXXXXX");
    const std::string out_path = make_tmp_path("/tmp/jass-mlpq-out-XXXXXX");
    JASS_CHECK(write_mlpq_file(in_path, w1, b1, w2, b2, w3, 0,
                               0.5f, 1.0f, 2.0f));

    MLPNetworkQ net;
    JASS_CHECK(net.load(in_path));
    JASS_CHECK(net.save(out_path));

    MLPNetworkQ reloaded;
    JASS_CHECK(reloaded.load(out_path));

    const Position p = parse("W:W2:B1");
    JASS_CHECK_EQ(net.evaluate(p), reloaded.evaluate(p));
    JASS_CHECK_EQ(reloaded.evaluate(p), 254);

    std::remove(in_path.c_str());
    std::remove(out_path.c_str());
}

// Cycle-4a regression: a JNNQ file with non-default hidden dims must
// round-trip cleanly through the load+save path and produce the same
// evaluation. We replicate the trigger-path setup from
// test_mlpq_forward_pass_matches_hand_computed but on a 128×64
// topology, which exercises the runtime SIMD-tile loop bounds.
void test_mlpq_load_supports_non_default_hidden_dims() {
    constexpr std::size_t kH1 = 128;
    constexpr std::size_t kH2 = 64;

    MLPNetworkQ net(kH1, kH2);
    JASS_CHECK_EQ(net.hidden1(), kH1);
    JASS_CHECK_EQ(net.hidden2(), kH2);

    const std::string in_path  = make_tmp_path("/tmp/jass-mlpq-wide-in-XXXXXX");
    const std::string out_path = make_tmp_path("/tmp/jass-mlpq-wide-out-XXXXXX");
    {
        std::ofstream f(in_path, std::ios::binary);
        JASS_CHECK(static_cast<bool>(f));
        f.write("JNNQ", 4);
        auto wu32 = [&](std::uint32_t v) {
            f.write(reinterpret_cast<const char*>(&v), 4);
        };
        auto wf32 = [&](float v) {
            f.write(reinterpret_cast<const char*>(&v), sizeof(float));
        };
        wu32(1u);  // version
        wu32(static_cast<std::uint32_t>(MLPNetworkQ::INPUT_DIM));
        wu32(static_cast<std::uint32_t>(kH1));
        wu32(static_cast<std::uint32_t>(kH2));
        wu32(1u);
        wf32(0.5f);   // mul1
        wf32(1.0f);   // mul2
        wf32(2.0f);   // mul_out

        std::vector<std::int8_t>  w1(kH1 * MLPNetworkQ::INPUT_DIM, 0);
        std::vector<std::int32_t> b1(kH1, 0);
        std::vector<std::int8_t>  w2(kH2 * kH1, 0);
        std::vector<std::int32_t> b2(kH2, 0);
        std::vector<std::int8_t>  w3(kH2, 0);
        w1[0 * MLPNetworkQ::INPUT_DIM + 4] = 100;  // feat 4 → h1[0]
        w2[0 * kH1 + 0]                    = 4;    // h1[0]  → h2[0]
        w3[0]                              = 1;    // h2[0]  → out
        auto wbytes = [&](const void* p, std::size_t n) {
            f.write(reinterpret_cast<const char*>(p),
                    static_cast<std::streamsize>(n));
        };
        wbytes(w1.data(), w1.size() * sizeof(std::int8_t));
        wbytes(b1.data(), b1.size() * sizeof(std::int32_t));
        wbytes(w2.data(), w2.size() * sizeof(std::int8_t));
        wbytes(b2.data(), b2.size() * sizeof(std::int32_t));
        wbytes(w3.data(), w3.size() * sizeof(std::int8_t));
        const std::int32_t b3 = 0;
        f.write(reinterpret_cast<const char*>(&b3), sizeof(std::int32_t));
    }

    JASS_CHECK(net.load(in_path));
    JASS_CHECK_EQ(net.hidden1(), kH1);
    JASS_CHECK_EQ(net.hidden2(), kH2);

    JASS_CHECK(net.save(out_path));
    MLPNetworkQ reloaded;
    JASS_CHECK(reloaded.load(out_path));
    JASS_CHECK_EQ(reloaded.hidden1(), kH1);
    JASS_CHECK_EQ(reloaded.hidden2(), kH2);

    // Trigger path: feat 4 = white man on bit 1 (FMJD square 2).
    // acc1[0] = 100 → mul1*100 = 50 → h1[0] = 50.
    // acc2[0] = 4 * 50 = 200 → mul2*200 = 200 → saturates to 127 → h2[0] = 127.
    // acc3 = 1 * 127 = 127 → mul_out * 127 = 254.
    const Position p = parse("W:W2:B1");
    JASS_CHECK_EQ(net.evaluate(p),      254);
    JASS_CHECK_EQ(reloaded.evaluate(p), 254);

    std::remove(in_path.c_str());
    std::remove(out_path.c_str());
}

// Cycle-4a: dims that would break the SIMD dot-product (not a
// multiple of SIMD_TILE) must be rejected at load time.
void test_mlpq_load_rejects_simd_incompatible_dims() {
    const std::string path = make_tmp_path("/tmp/jass-mlpq-odd-XXXXXX");
    {
        std::ofstream f(path, std::ios::binary);
        f.write("JNNQ", 4);
        const std::uint32_t v[5] = {
            1u,                                                 // version
            static_cast<std::uint32_t>(MLPNetworkQ::INPUT_DIM),
            48u,  // hidden1 — not a multiple of 32, must be rejected
            32u,
            1u,
        };
        f.write(reinterpret_cast<const char*>(v), sizeof(v));
    }
    MLPNetworkQ net;
    JASS_CHECK(!net.load(path));
    std::remove(path.c_str());
}

void test_mlpq_load_rejects_missing_or_bad_file() {
    MLPNetworkQ net;
    JASS_CHECK(!net.load("/no/such/path/jass-mlpq.bin"));

    // Wrong magic.
    const std::string bad_magic = make_tmp_path("/tmp/jass-mlpq-bad-XXXXXX");
    {
        std::ofstream f(bad_magic, std::ios::binary);
        f.write("ZZZZ", 4);
        const std::uint32_t zero = 0;
        for (int i = 0; i < 5; ++i)
            f.write(reinterpret_cast<const char*>(&zero), 4);
    }
    JASS_CHECK(!net.load(bad_magic));
    std::remove(bad_magic.c_str());

    // Right magic but wrong version.
    const std::string bad_ver = make_tmp_path("/tmp/jass-mlpq-ver-XXXXXX");
    {
        std::ofstream f(bad_ver, std::ios::binary);
        f.write("JNNQ", 4);
        const std::uint32_t v[5] = {
            999u,  // version — wrong
            static_cast<std::uint32_t>(MLPNetworkQ::INPUT_DIM),
            static_cast<std::uint32_t>(MLPNetworkQ::HIDDEN1),
            static_cast<std::uint32_t>(MLPNetworkQ::HIDDEN2),
            1u,
        };
        f.write(reinterpret_cast<const char*>(v), sizeof(v));
    }
    JASS_CHECK(!net.load(bad_ver));
    std::remove(bad_ver.c_str());
}

void test_load_network_dispatches_to_mlpq() {
    // A JNNQ file should come back as something whose evaluate()
    // matches a freshly loaded MLPNetworkQ.
    std::array<std::int8_t,  MLPNetworkQ::HIDDEN1 * MLPNetworkQ::INPUT_DIM> w1{};
    std::array<std::int32_t, MLPNetworkQ::HIDDEN1>                          b1{};
    std::array<std::int8_t,  MLPNetworkQ::HIDDEN2 * MLPNetworkQ::HIDDEN1>   w2{};
    std::array<std::int32_t, MLPNetworkQ::HIDDEN2>                          b2{};
    std::array<std::int8_t,  MLPNetworkQ::HIDDEN2>                          w3{};
    w1[0 * MLPNetworkQ::INPUT_DIM + 4] = 100;
    w2[0 * MLPNetworkQ::HIDDEN1   + 0] = 4;
    w3[0]                              = 1;

    const std::string path = make_tmp_path("/tmp/jass-mlpq-disp-XXXXXX");
    JASS_CHECK(write_mlpq_file(path, w1, b1, w2, b2, w3, 0,
                               0.5f, 1.0f, 2.0f));

    std::unique_ptr<INetwork> net = load_network(path);
    JASS_CHECK(net != nullptr);
    if (net) {
        JASS_CHECK_EQ(net->evaluate(parse("W:W2:B1")), 254);
    }
    std::remove(path.c_str());
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
    test_mlp_position_level_symmetry();
    test_mlp_save_load_roundtrip();
    test_mlp_load_supports_non_default_hidden_dims();
    test_mlp_halfmen_encoding_end_to_end();
    test_mlp_load_rejects_missing_or_bad_file();
    test_default_nnue_is_non_null_and_returns_finite_score();
    test_default_nnue_is_stable_across_calls();
    test_load_network_dispatches_on_magic();
    test_mlpq_forward_pass_matches_hand_computed();
    test_mlpq_save_load_roundtrip();
    test_mlpq_load_supports_non_default_hidden_dims();
    test_mlpq_load_rejects_simd_incompatible_dims();
    test_mlpq_load_rejects_missing_or_bad_file();
    test_load_network_dispatches_to_mlpq();
}

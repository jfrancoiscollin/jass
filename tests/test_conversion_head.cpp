// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "test_framework.hpp"

#include "conversion_head.hpp"
#include "position.hpp"

#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <string>
#include <string_view>
#include <unistd.h>

using namespace jass;
using namespace jass::conversion_head;

namespace {

Position parse(std::string_view fen) {
    auto p = Position::from_fen(fen);
    JASS_CHECK(p.has_value());
    return p.value_or(Position{});
}

Model test_model() {
    Model model;
    model.lambda_cp = 20.0F;
    model.tanh_scale = 1.0F;
    model.center_logit = 0.0F;
    model.piece_min = 8.0F;
    model.piece_full_max = 12.0F;
    model.piece_zero_max = 20.0F;
    model.margin_min = 1.0F;
    model.margin_max = 1.0F;
    model.bias = 10.0F;
    model.inv_std.fill(1.0F);
    return model;
}

void test_gate() {
    const Model model = test_model();
    JASS_CHECK_EQ(gate_for(7, 1, model), 0.0F);
    JASS_CHECK_EQ(gate_for(8, 1, model), 1.0F);
    JASS_CHECK_EQ(gate_for(12, 1, model), 1.0F);
    JASS_CHECK(std::fabs(gate_for(16, 1, model) - 0.5F) < 1e-6F);
    JASS_CHECK_EQ(gate_for(20, 1, model), 0.0F);
    JASS_CHECK_EQ(gate_for(10, 0, model), 0.0F);
    JASS_CHECK_EQ(gate_for(10, 2, model), 0.0F);
}

void test_leader_relative_features() {
    // Black: 4 men + 1 king = 7. White: 3 men + 1 king = 6.
    const Position black_leader = parse("B:WK31,32,33,34:BK1,2,3,4,5");
    const Features black = compute_features(black_leader);
    JASS_CHECK_EQ(black.leader_sign_black, 1);
    JASS_CHECK_EQ(black.material_margin, 1);
    JASS_CHECK_EQ(black.total_pieces, 9);
    JASS_CHECK_EQ(static_cast<int>(black.value[LEADER_MEN]), 4);
    JASS_CHECK_EQ(static_cast<int>(black.value[LEADER_KINGS]), 1);
    JASS_CHECK_EQ(static_cast<int>(black.value[DEFENDER_MEN]), 3);
    JASS_CHECK_EQ(static_cast<int>(black.value[DEFENDER_KINGS]), 1);

    // White: 4 men + 1 king = 7. Black: 3 men + 1 king = 6.
    const Position white_leader = parse("W:WK31,32,33,34,35:BK1,2,3,4");
    const Features white = compute_features(white_leader);
    JASS_CHECK_EQ(white.leader_sign_black, -1);
    JASS_CHECK_EQ(white.material_margin, 1);
    JASS_CHECK_EQ(white.total_pieces, 9);
    JASS_CHECK_EQ(static_cast<int>(white.value[LEADER_MEN]), 4);
    JASS_CHECK_EQ(static_cast<int>(white.value[LEADER_KINGS]), 1);
    JASS_CHECK_EQ(static_cast<int>(white.value[DEFENDER_MEN]), 3);
    JASS_CHECK_EQ(static_cast<int>(white.value[DEFENDER_KINGS]), 1);
}

void test_delta_is_bounded_and_signed() {
    Model model = test_model();
    const Position black_leader = parse("B:WK31,32,33,34:BK1,2,3,4,5");
    const Position white_leader = parse("W:WK31,32,33,34,35:BK1,2,3,4");

    const double db = delta_cp_black(black_leader, model);
    const double dw = delta_cp_black(white_leader, model);
    JASS_CHECK(db > 19.0 && db <= 20.0);
    JASS_CHECK(dw < -19.0 && dw >= -20.0);

    model.lambda_cp = 0.0F;
    JASS_CHECK_EQ(delta_cp_black(black_leader, model), 0.0);

    model = test_model();
    const Position outside_margin = parse("B:WK31,32,33:BK1,2,3,4,5");
    JASS_CHECK_EQ(delta_cp_black(outside_margin, model), 0.0);
}

void write_u32(std::ofstream& file, std::uint32_t value) {
    const unsigned char bytes[4] = {
        static_cast<unsigned char>(value & 0xffU),
        static_cast<unsigned char>((value >> 8) & 0xffU),
        static_cast<unsigned char>((value >> 16) & 0xffU),
        static_cast<unsigned char>((value >> 24) & 0xffU),
    };
    file.write(reinterpret_cast<const char*>(bytes), 4);
}

void write_f32(std::ofstream& file, float value) {
    std::uint32_t bits = 0;
    static_assert(sizeof(bits) == sizeof(value));
    std::memcpy(&bits, &value, sizeof(bits));
    write_u32(file, bits);
}

void write_model_file(const std::string& path, const Model& model,
                      std::uint32_t magic = MAGIC) {
    std::ofstream file(path, std::ios::binary);
    write_u32(file, magic);
    write_u32(file, SCHEMA);
    write_u32(file, static_cast<std::uint32_t>(NUM_FEATURES));
    write_u32(file, model.flags);
    for (float value : {
             model.lambda_cp, model.tanh_scale, model.center_logit,
             model.piece_min, model.piece_full_max, model.piece_zero_max,
             model.margin_min, model.margin_max, model.bias}) {
        write_f32(file, value);
    }
    for (float value : model.mean) write_f32(file, value);
    for (float value : model.inv_std) write_f32(file, value);
    for (float value : model.weight) write_f32(file, value);
}

void test_binary_roundtrip_and_rejection() {
    std::string tmpl = jass_tmp_template("jass_conversion_head");
    const int fd = mkstemp(tmpl.data());
    JASS_CHECK(fd != -1);
    if (fd == -1) return;
    close(fd);

    Model model = test_model();
    model.mean[3] = 4.5F;
    model.weight[7] = -0.25F;
    write_model_file(tmpl, model);

    std::string err;
    auto loaded = load_model(tmpl, &err);
    JASS_CHECK(loaded.has_value());
    if (loaded) {
        JASS_CHECK_EQ(loaded->lambda_cp, 20.0F);
        JASS_CHECK_EQ(loaded->mean[3], 4.5F);
        JASS_CHECK_EQ(loaded->weight[7], -0.25F);
    }

    write_model_file(tmpl, model, 0U);
    loaded = load_model(tmpl, &err);
    JASS_CHECK(!loaded.has_value());

    {
        std::ofstream truncated(tmpl, std::ios::binary | std::ios::trunc);
        write_u32(truncated, MAGIC);
    }
    loaded = load_model(tmpl, &err);
    JASS_CHECK(!loaded.has_value());
    std::remove(tmpl.c_str());
}

}  // namespace

void run_conversion_head_tests() {
    test_gate();
    test_leader_relative_features();
    test_delta_is_bounded_and_signed();
    test_binary_roundtrip_and_rejection();
}

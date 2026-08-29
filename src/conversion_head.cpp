// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "conversion_head.hpp"

#include "bitboard.hpp"
#include "board.hpp"
#include "scan_eval.hpp"
#include "t3_f6.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <limits>
#include <utility>
#include <vector>

namespace jass::conversion_head {
namespace {

std::uint32_t rd_u32(const unsigned char* p) noexcept {
    return  static_cast<std::uint32_t>(p[0])
         | (static_cast<std::uint32_t>(p[1]) << 8)
         | (static_cast<std::uint32_t>(p[2]) << 16)
         | (static_cast<std::uint32_t>(p[3]) << 24);
}

float rd_f32(const unsigned char* p) noexcept {
    const std::uint32_t bits = rd_u32(p);
    float value = 0.0F;
    static_assert(sizeof(value) == sizeof(bits));
    std::memcpy(&value, &bits, sizeof(value));
    return value;
}

bool finite(float value) noexcept {
    return std::isfinite(static_cast<double>(value));
}

float king_centrality(Bitboard kings) noexcept {
    float sum = 0.0F;
    for (Bitboard b = kings; b != 0; ) {
        const Square sq = pop_lsb(b);
        const float row = static_cast<float>(row_of(sq));
        const float col = static_cast<float>(col_of(sq));
        sum += (4.5F - std::fabs(row - 4.5F))
             + (4.5F - std::fabs(col - 4.5F));
    }
    return sum;
}

float men_advancement(Bitboard men, Color color) noexcept {
    float sum = 0.0F;
    for (Bitboard b = men; b != 0; ) {
        const int row = row_of(pop_lsb(b));
        sum += static_cast<float>(color == Color::White ? 9 - row : row);
    }
    return sum;
}

float near_promotion(Bitboard men, Color color) noexcept {
    int count = 0;
    for (Bitboard b = men; b != 0; ) {
        const int row = row_of(pop_lsb(b));
        if ((color == Color::White && row == 1)
            || (color == Color::Black && row == 8)) {
            ++count;
        }
    }
    return static_cast<float>(count);
}

float lr_imbalance(Bitboard men) noexcept {
    int left = 0;
    int right = 0;
    for (Bitboard b = men; b != 0; ) {
        const Square sq = pop_lsb(b);
        if (col_of(sq) < 5) {
            ++left;
        } else {
            ++right;
        }
    }
    const int diff = left - right;
    return static_cast<float>(diff < 0 ? -diff : diff);
}

bool validate_model(const Model& model, std::string* err) {
    const auto fail = [err](const char* message) {
        if (err != nullptr) *err = message;
        return false;
    };
    if (model.flags != 0U) return fail("unsupported conversion-head flags");
    if (!finite(model.lambda_cp) || model.lambda_cp < 0.0F)
        return fail("invalid conversion-head lambda_cp");
    if (!finite(model.tanh_scale) || model.tanh_scale <= 0.0F)
        return fail("invalid conversion-head tanh_scale");
    if (!finite(model.center_logit) || !finite(model.bias))
        return fail("non-finite conversion-head intercept");
    if (!finite(model.piece_min) || !finite(model.piece_full_max)
        || !finite(model.piece_zero_max)
        || !(model.piece_min <= model.piece_full_max
             && model.piece_full_max < model.piece_zero_max)) {
        return fail("invalid conversion-head piece gate");
    }
    if (!finite(model.margin_min) || !finite(model.margin_max)
        || model.margin_min < 0.0F || model.margin_min > model.margin_max) {
        return fail("invalid conversion-head margin gate");
    }
    for (std::size_t i = 0; i < NUM_FEATURES; ++i) {
        if (!finite(model.mean[i]) || !finite(model.inv_std[i])
            || !finite(model.weight[i]) || model.inv_std[i] < 0.0F) {
            return fail("non-finite conversion-head feature parameter");
        }
    }
    return true;
}

}  // namespace

float gate_for(int total_pieces, int material_margin,
               const Model& model) noexcept {
    const float pieces = static_cast<float>(total_pieces);
    const float margin = static_cast<float>(material_margin);
    if (margin < model.margin_min || margin > model.margin_max)
        return 0.0F;
    if (pieces < model.piece_min || pieces >= model.piece_zero_max)
        return 0.0F;
    if (pieces <= model.piece_full_max)
        return 1.0F;
    const float denom = model.piece_zero_max - model.piece_full_max;
    if (denom <= 0.0F) return 0.0F;
    return std::clamp((model.piece_zero_max - pieces) / denom, 0.0F, 1.0F);
}

Features compute_features(const Position& pos) noexcept {
    Features out;
    const int black_men = popcount(pos.black_men());
    const int black_kings = popcount(pos.black_kings());
    const int white_men = popcount(pos.white_men());
    const int white_kings = popcount(pos.white_kings());
    const int black_value = black_men + 3 * black_kings;
    const int white_value = white_men + 3 * white_kings;
    const int diff = black_value - white_value;

    out.leader_sign_black = diff > 0 ? 1 : (diff < 0 ? -1 : 0);
    out.material_margin = diff < 0 ? -diff : diff;
    out.total_pieces = black_men + black_kings + white_men + white_kings;

    const Color leader = out.leader_sign_black >= 0 ? Color::Black : Color::White;
    const Color defender = leader == Color::Black ? Color::White : Color::Black;
    const Bitboard leader_men = pos.men_of(leader);
    const Bitboard leader_kings = pos.kings_of(leader);
    const Bitboard defender_men = pos.men_of(defender);
    const Bitboard defender_kings = pos.kings_of(defender);
    const int leader_mobility = scan_eval::mobility(pos, leader);
    const int defender_mobility = scan_eval::mobility(pos, defender);

    out.value[TOTAL_PIECES] = static_cast<float>(out.total_pieces);
    out.value[LEADER_MEN] = static_cast<float>(popcount(leader_men));
    out.value[LEADER_KINGS] = static_cast<float>(popcount(leader_kings));
    out.value[DEFENDER_MEN] = static_cast<float>(popcount(defender_men));
    out.value[DEFENDER_KINGS] = static_cast<float>(popcount(defender_kings));
    out.value[LEADER_MOBILITY] = static_cast<float>(leader_mobility);
    out.value[DEFENDER_MOBILITY] = static_cast<float>(defender_mobility);
    out.value[MOBILITY_DIFF] = static_cast<float>(leader_mobility - defender_mobility);
    out.value[LEADER_KING_CENTRALITY] = king_centrality(leader_kings);
    out.value[DEFENDER_KING_CENTRALITY] = king_centrality(defender_kings);
    out.value[LEADER_MEN_ADVANCEMENT] = men_advancement(leader_men, leader);
    out.value[DEFENDER_MEN_ADVANCEMENT] = men_advancement(defender_men, defender);
    out.value[LEADER_NEAR_PROMOTION] = near_promotion(leader_men, leader);
    out.value[DEFENDER_NEAR_PROMOTION] = near_promotion(defender_men, defender);
    out.value[LEADER_LR_IMBALANCE] = lr_imbalance(leader_men);
    out.value[DEFENDER_LR_IMBALANCE] = lr_imbalance(defender_men);
    return out;
}

double delta_cp_black(const Position& pos, const Model& model) noexcept {
    if (model.lambda_cp == 0.0F) return 0.0;
    // Cheap gate pre-check from popcounts only: the phase/margin gate depends on
    // material, so short-circuit BEFORE the full 16-feature extraction (mobility
    // king-slides are the dominant cost). Byte-identical delta for gated
    // positions; the discarded path used to compute all features then return 0.
    {
        const int bm = popcount(pos.black_men()), bk = popcount(pos.black_kings());
        const int wm = popcount(pos.white_men()), wk = popcount(pos.white_kings());
        const int diff = (bm + 3 * bk) - (wm + 3 * wk);
        if (diff == 0) return 0.0;
        const int margin = diff < 0 ? -diff : diff;
        const int total = bm + bk + wm + wk;
        if (gate_for(total, margin, model) == 0.0F) return 0.0;
    }
    const Features features = compute_features(pos);
    if (features.leader_sign_black == 0) return 0.0;
    const float gate = gate_for(features.total_pieces, features.material_margin, model);
    if (gate == 0.0F) return 0.0;

    double raw = static_cast<double>(model.bias);
    for (std::size_t i = 0; i < NUM_FEATURES; ++i) {
        const double x = (static_cast<double>(features.value[i])
                          - static_cast<double>(model.mean[i]))
                         * static_cast<double>(model.inv_std[i]);
        raw += static_cast<double>(model.weight[i]) * x;
    }
    const double centered = raw - static_cast<double>(model.center_logit);
    const double bounded = std::tanh(centered / static_cast<double>(model.tanh_scale));
    return static_cast<double>(features.leader_sign_black)
         * static_cast<double>(gate)
         * static_cast<double>(model.lambda_cp)
         * bounded;
}

std::optional<Model> load_model(const std::string& path, std::string* err) {
    std::ifstream file(path, std::ios::binary);
    if (!file) {
        if (err != nullptr) *err = "cannot open conversion head " + path;
        return std::nullopt;
    }
    file.seekg(0, std::ios::end);
    const std::streamoff end = file.tellg();
    file.seekg(0, std::ios::beg);
    if (end != static_cast<std::streamoff>(BINARY_SIZE)) {
        if (err != nullptr) {
            *err = "conversion-head size " + std::to_string(end)
                 + " != expected " + std::to_string(BINARY_SIZE);
        }
        return std::nullopt;
    }
    std::vector<unsigned char> raw(BINARY_SIZE);
    file.read(reinterpret_cast<char*>(raw.data()),
              static_cast<std::streamsize>(raw.size()));
    if (!file) {
        if (err != nullptr) *err = "conversion-head read failure";
        return std::nullopt;
    }

    const unsigned char* p = raw.data();
    const std::uint32_t magic = rd_u32(p); p += 4;
    const std::uint32_t schema = rd_u32(p); p += 4;
    const std::uint32_t n_features = rd_u32(p); p += 4;
    Model model;
    model.flags = rd_u32(p); p += 4;
    if (magic != MAGIC || schema != SCHEMA || n_features != NUM_FEATURES) {
        if (err != nullptr) *err = "bad conversion-head header";
        return std::nullopt;
    }

    auto next_float = [&p]() noexcept {
        const float value = rd_f32(p);
        p += sizeof(float);
        return value;
    };
    model.lambda_cp = next_float();
    model.tanh_scale = next_float();
    model.center_logit = next_float();
    model.piece_min = next_float();
    model.piece_full_max = next_float();
    model.piece_zero_max = next_float();
    model.margin_min = next_float();
    model.margin_max = next_float();
    model.bias = next_float();
    for (float& value : model.mean) value = next_float();
    for (float& value : model.inv_std) value = next_float();
    for (float& value : model.weight) value = next_float();

    if (!validate_model(model, err)) return std::nullopt;
    return model;
}

int Network::evaluate(const Position& pos) const noexcept {
    if (!base_) return 0;
    const double base_cp = static_cast<double>(base_->evaluate(pos));
    const double delta_black = delta_cp_black(pos, model_);
    const double delta_stm = pos.side_to_move() == Color::Black
        ? delta_black : -delta_black;
    const double total = base_cp + delta_stm;
    if (total > 20000.0) return 20000;
    if (total < -20000.0) return -20000;
    return static_cast<int>(total);
}

std::unique_ptr<INetwork> maybe_wrap(std::unique_ptr<INetwork> base,
                                    const std::string& pattern_path,
                                    std::string* err) {
    if (!base) return nullptr;
    const std::string sidecar = pattern_path + ".cvh";
    std::ifstream probe(sidecar, std::ios::binary);
    if (!probe) return base;
    probe.close();
    auto model = load_model(sidecar, err);
    if (!model) return nullptr;
    return std::make_unique<Network>(std::move(base), std::move(*model));
}

}  // namespace jass::conversion_head

namespace jass {

// src/scan_eval.cpp is compiled with a file-local token rename so its historical
// unified loader remains available as this base function. This wrapper is the
// only public load_eval_network symbol.
std::unique_ptr<INetwork> load_eval_network_base(const std::string& path,
                                                 std::string* err);

std::unique_ptr<INetwork> load_eval_network(const std::string& path,
                                            std::string* err) {
    auto base = load_eval_network_base(path, err);
    if (!base) return nullptr;
    // Explicit frozen T3/F6 takes the pristine CURRICULUM base. With the env
    // absent, the legacy OFF loader and optional conversion sidecar are exact.
    if (std::getenv("JASS_T3_F6_MODEL") != nullptr)
        return t3_f6::maybe_wrap_from_env(std::move(base), path, err);
    return conversion_head::maybe_wrap(std::move(base), path, err);
}

}  // namespace jass

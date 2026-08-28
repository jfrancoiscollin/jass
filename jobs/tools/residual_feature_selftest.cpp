// SPDX-License-Identifier: AGPL-3.0-or-later
#include "movegen.hpp"
#include "position.hpp"
#include "residual_features.hpp"

#include <array>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string_view>

namespace {

jass::Position parse(std::string_view fen) {
    auto p = jass::Position::from_fen(fen);
    if (!p) throw std::runtime_error("selftest bad FEN");
    return *p;
}

void require(bool ok, const char* what) {
    if (!ok) throw std::runtime_error(what);
}

bool close(float a, float b, float eps = 1e-6F) { return std::fabs(a - b) <= eps; }

}  // namespace

int main() {
    try {
        using namespace jass;
        using namespace jass::residual_features;
        static_assert(CTX2_WIDTH == 15U);
        static_assert(F1_WIDTH == 12U && F2_WIDTH == 14U && F3_WIDTH == 12U);
        static_assert(F4_WIDTH == 16U && F5_WIDTH == 12U && ALL_NEW_WIDTH == 66U);
        static_assert(TOTAL_WIDTH == 81U);
        const std::array<int,16> expected_center = {
            12,13,17,18,19,22,23,24,27,28,29,32,33,34,38,39
        };
        require(CENTRAL_16 == expected_center, "central-16 contract drift");

        // Parent-POV antisymmetry on identical board with only STM toggled.
        Position a = parse("W:W28,31,K40:B14,22,K3");
        Position b = a;
        b.set_side_to_move(Color::Black);
        const auto fa = extract(a).all_new();
        const auto fb = extract(b).all_new();
        for (std::size_t i = 0; i < fa.size(); ++i)
            require(close(fa[i], -fb[i]), "parent-POV antisymmetry drift");

        // Full FMJD majority capture is one semantic move, not partial pseudo-moves.
        const Position cap = parse("W:W28:B22,23,14");
        MoveList legal;
        generate_legal_moves(cap, legal);
        require(legal.size() == 1U, "majority capture legal count drift");
        require(legal[0].num_captures == 2U, "multi-capture chain drift");
        const auto capf = extract(cap);
        require(std::isfinite(capf.capture_geometry[3]), "capture mean nonfinite");

        // RESPONSE_FRONTIER enumerates the exact complete opponent reply set once.
        const Position response = parse("W:W28:B22");
        MoveList response_legal;
        generate_legal_moves(response, response_legal);
        const auto rf = extract(response);
        require(close(rf.response_frontier[0], static_cast<float>(response_legal.size())),
                "response reply count drift");

        // White man on 6 has a one-step quiet route to promotion; opponent has no man.
        const auto promo = extract(parse("B:W6:BK50"));  // parent is White
        require(close(promo.promotion_race[0], -7.0F), "promotion BFS/sentinel drift");
        require(close(promo.promotion_race[6], -7.0F), "threat-blocked promotion BFS drift");

        // King geometry is mechanically visible and finite.
        const auto king = extract(parse("W:WK28:B1"));  // parent is Black
        require(close(king.king_geometry_plus[0], -1.0F), "king-count POV drift");
        for (float v : king.king_geometry_plus) require(std::isfinite(v), "king feature nonfinite");

        // Packed order is CTX2 then F1..F5 and exactly 81 floats.
        const auto packed = king.packed();
        const auto all = king.all_new();
        for (std::size_t i = 0; i < all.size(); ++i)
            require(close(packed[CTX2_WIDTH + i], all[i]), "packed feature order drift");
        require(ctx2_names().size() == 15U && f1_names().size() == 12U &&
                f2_names().size() == 14U && f3_names().size() == 12U &&
                f4_names().size() == 16U && f5_names().size() == 12U,
                "feature name width drift");

        std::cout << "residual feature selftest: PASS\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "residual feature selftest: FAIL: " << e.what() << "\n";
        return 1;
    }
}

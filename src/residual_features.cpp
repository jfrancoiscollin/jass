// SPDX-License-Identifier: AGPL-3.0-or-later
#include "residual_features.hpp"

#include "bitboard.hpp"
#include "board.hpp"
#include "movegen.hpp"
#include "scan_eval.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <chrono>
#include <limits>
#include <numeric>
#include <queue>
#include <vector>

namespace jass::residual_features {
namespace {

constexpr float SENTINEL = 8.0F;

bool is_central(Square s) noexcept {
    return std::find(CENTRAL_16.begin(), CENTRAL_16.end(), static_cast<int>(s)) != CENTRAL_16.end();
}

float parent_minus(Color parent, float white_value, float black_value) noexcept {
    return parent == Color::White ? white_value - black_value : black_value - white_value;
}

float material_balance(const Position& p, Color side) noexcept {
    const Color opp = opposite(side);
    const int own = popcount(p.men_of(side)) + 3 * popcount(p.kings_of(side));
    const int theirs = popcount(p.men_of(opp)) + 3 * popcount(p.kings_of(opp));
    return static_cast<float>(own - theirs);
}

int chebyshev(Square a, Square b) noexcept {
    return std::max(std::abs(row_of(a) - row_of(b)), std::abs(col_of(a) - col_of(b)));
}

std::vector<Square> squares_of(Bitboard bb) {
    std::vector<Square> out;
    out.reserve(static_cast<std::size_t>(popcount(bb)));
    while (bb) out.push_back(pop_lsb(bb));
    return out;
}

struct LegalSummary {
    float moves = 0.0F;
    float captures = 0.0F;
    float max_captured = 0.0F;
    float mean_captured = 0.0F;
    float max_captured_kings = 0.0F;
    float mean_captured_kings = 0.0F;
    float unique_landings = 0.0F;
    float unique_origins = 0.0F;
    float promotions = 0.0F;
    float capture_promotions = 0.0F;
    float forced = 0.0F;
    float landing_dispersion = 0.0F;
};

LegalSummary legal_summary(const Position& p, Color side, MoveList* keep,
                           Profile* profile) {
    Position q = p;
    q.set_side_to_move(side);
    MoveList legal;
    generate_legal_moves(q, legal);
    if (profile) ++profile->movegen_calls;
    if (keep) *keep = legal;
    LegalSummary s;
    s.moves = static_cast<float>(legal.size());
    s.forced = legal.size() == 1U ? 1.0F : 0.0F;

    std::array<bool, NUM_SQUARES + 1> landing_seen{};
    std::array<bool, NUM_SQUARES + 1> origin_seen{};
    std::vector<std::pair<float, float>> landing_coords;
    float cap_sum = 0.0F;
    float king_sum = 0.0F;
    for (const Move& m : legal) {
        if (m.promotes) s.promotions += 1.0F;
        if (!m.is_capture()) continue;
        s.captures += 1.0F;
        const float nc = static_cast<float>(m.num_captures);
        const float nk = static_cast<float>(popcount(m.captured & p.kings_of(opposite(side))));
        cap_sum += nc;
        king_sum += nk;
        s.max_captured = std::max(s.max_captured, nc);
        s.max_captured_kings = std::max(s.max_captured_kings, nk);
        if (m.promotes) s.capture_promotions += 1.0F;
        landing_seen[static_cast<std::size_t>(m.to)] = true;
        origin_seen[static_cast<std::size_t>(m.from)] = true;
        landing_coords.emplace_back(static_cast<float>(row_of(m.to)), static_cast<float>(col_of(m.to)));
    }
    if (s.captures > 0.0F) {
        s.mean_captured = cap_sum / s.captures;
        s.mean_captured_kings = king_sum / s.captures;
        s.unique_landings = static_cast<float>(std::count(landing_seen.begin(), landing_seen.end(), true));
        s.unique_origins = static_cast<float>(std::count(origin_seen.begin(), origin_seen.end(), true));
    }
    if (landing_coords.size() >= 2U) {
        float mr = 0.0F, mc = 0.0F;
        for (const auto& rc : landing_coords) { mr += rc.first; mc += rc.second; }
        const float n = static_cast<float>(landing_coords.size());
        mr /= n; mc /= n;
        float ss = 0.0F;
        for (const auto& rc : landing_coords) {
            const float dr = rc.first - mr;
            const float dc = rc.second - mc;
            ss += dr * dr + dc * dc;
        }
        s.landing_dispersion = ss / n;
    }
    return s;
}

std::array<float, F1_WIDTH> capture_geometry(const Position& p, Color parent,
                                             MoveList* child_replies,
                                             Profile* profile) {
    MoveList* keep_w = p.side_to_move() == Color::White ? child_replies : nullptr;
    MoveList* keep_b = p.side_to_move() == Color::Black ? child_replies : nullptr;
    const LegalSummary w = legal_summary(p, Color::White, keep_w, profile);
    const LegalSummary b = legal_summary(p, Color::Black, keep_b, profile);
    const std::array<float, F1_WIDTH> wa = {
        w.moves, w.captures, w.max_captured, w.mean_captured,
        w.max_captured_kings, w.mean_captured_kings, w.unique_landings,
        w.unique_origins, w.promotions, w.capture_promotions, w.forced,
        w.landing_dispersion,
    };
    const std::array<float, F1_WIDTH> ba = {
        b.moves, b.captures, b.max_captured, b.mean_captured,
        b.max_captured_kings, b.mean_captured_kings, b.unique_landings,
        b.unique_origins, b.promotions, b.capture_promotions, b.forced,
        b.landing_dispersion,
    };
    std::array<float, F1_WIDTH> out{};
    for (std::size_t i = 0; i < out.size(); ++i) out[i] = parent_minus(parent, wa[i], ba[i]);
    return out;
}

std::array<float, F2_WIDTH> response_frontier(const Position& child, Color parent,
                                              const MoveList* precomputed,
                                              Profile* profile) {
    MoveList replies;
    if (precomputed) replies = *precomputed;
    else {
        generate_legal_moves(child, replies);  // child STM == opponent of parent
        if (profile) ++profile->movegen_calls;
    }
    if (profile) profile->response_enumerations += replies.size();
    std::array<float, F2_WIDTH> out{};
    if (replies.empty()) return out;

    const float baseline_material = material_balance(child, parent);
    std::vector<float> material;
    std::vector<float> next_moves;
    std::vector<float> next_max_capture;
    material.reserve(replies.size());
    next_moves.reserve(replies.size());
    next_max_capture.reserve(replies.size());
    float reply_capture = 0.0F;
    float reply_promote = 0.0F;
    float next_has_capture = 0.0F;
    float next_forced = 0.0F;
    for (const Move& reply : replies) {
        reply_capture += reply.is_capture() ? 1.0F : 0.0F;
        reply_promote += reply.promotes ? 1.0F : 0.0F;
        const Position after = child.after(reply);
        material.push_back(material_balance(after, parent) - baseline_material);
        MoveList next;
        generate_legal_moves(after, next);
        if (profile) ++profile->movegen_calls;
        next_moves.push_back(static_cast<float>(next.size()));
        float mc = 0.0F;
        if (!next.empty() && next[0].is_capture()) {
            mc = static_cast<float>(next[0].num_captures);
            next_has_capture += 1.0F;
        }
        if (next.size() == 1U) next_forced += 1.0F;
        next_max_capture.push_back(mc);
    }
    const auto triplet = [](const std::vector<float>& v) {
        const auto [mn, mx] = std::minmax_element(v.begin(), v.end());
        const float mean = std::accumulate(v.begin(), v.end(), 0.0F) / static_cast<float>(v.size());
        return std::array<float, 3>{*mn, mean, *mx};
    };
    const auto m = triplet(material);
    const auto lm = triplet(next_moves);
    const auto mc = triplet(next_max_capture);
    const float n = static_cast<float>(replies.size());
    out = {
        n,
        reply_capture / n,
        reply_promote / n,
        m[0], m[1], m[2],
        lm[0], lm[1], lm[2],
        mc[0], mc[1], mc[2],
        next_has_capture / n,
        next_forced / n,
    };
    return out;
}

Bitboard man_attack_squares(const Position& p, Color attackers, Bitboard occupied) noexcept {
    Bitboard result = 0;
    Bitboard men = p.men_of(attackers);
    while (men) {
        const Square from = pop_lsb(men);
        for (Dir d : ALL_DIRS) {
            const Square target = neighbour(from, d);
            if (target == NO_SQUARE) continue;
            const Square landing = neighbour(target, d);
            if (landing == NO_SQUARE) continue;
            if (!test(occupied, landing)) set(result, target);
        }
    }
    return result;
}

int quiet_promo_distance(const Position& p, Square start, Color side, Bitboard extra_blocked) {
    if (is_promotion_square(start, side)) return 0;
    Bitboard occupied = p.occupied();
    clear(occupied, start);
    std::array<int, NUM_SQUARES + 1> dist{};
    dist.fill(-1);
    std::queue<Square> q;
    dist[static_cast<std::size_t>(start)] = 0;
    q.push(start);
    while (!q.empty()) {
        const Square cur = q.front(); q.pop();
        const int next_d = dist[static_cast<std::size_t>(cur)] + 1;
        for (Dir d : man_forward_dirs(side)) {
            const Square to = neighbour(cur, d);
            if (to == NO_SQUARE) continue;
            if (test(occupied, to) || test(extra_blocked, to)) continue;
            if (dist[static_cast<std::size_t>(to)] >= 0) continue;
            if (is_promotion_square(to, side)) return next_d;
            dist[static_cast<std::size_t>(to)] = next_d;
            q.push(to);
        }
    }
    return -1;
}

std::array<float, 6> promo_summary(const Position& p, Color side, bool threat_blocked) {
    const auto men = squares_of(p.men_of(side));
    std::vector<int> finite;
    finite.reserve(men.size());
    int d1 = 0, d2 = 0, d3 = 0, no_path = 0;
    for (Square man : men) {
        Bitboard blockers = 0;
        if (threat_blocked) {
            Bitboard occupied = p.occupied();
            clear(occupied, man);
            blockers = man_attack_squares(p, opposite(side), occupied);
        }
        const int d = quiet_promo_distance(p, man, side, blockers);
        if (d < 0) { ++no_path; continue; }
        finite.push_back(d);
        d1 += d <= 1 ? 1 : 0;
        d2 += d <= 2 ? 1 : 0;
        d3 += d <= 3 ? 1 : 0;
    }
    float min_d = SENTINEL;
    float mean_d = SENTINEL;
    if (!finite.empty()) {
        min_d = static_cast<float>(*std::min_element(finite.begin(), finite.end()));
        mean_d = static_cast<float>(std::accumulate(finite.begin(), finite.end(), 0)) /
                 static_cast<float>(finite.size());
    }
    return {min_d, mean_d, static_cast<float>(d1), static_cast<float>(d2),
            static_cast<float>(d3), static_cast<float>(no_path)};
}

std::array<float, F3_WIDTH> promotion_race(const Position& p, Color parent) {
    const auto w0 = promo_summary(p, Color::White, false);
    const auto b0 = promo_summary(p, Color::Black, false);
    const auto w1 = promo_summary(p, Color::White, true);
    const auto b1 = promo_summary(p, Color::Black, true);
    std::array<float, F3_WIDTH> out{};
    for (std::size_t i = 0; i < 6U; ++i) {
        out[i] = parent_minus(parent, w0[i], b0[i]);
        out[6U + i] = parent_minus(parent, w1[i], b1[i]);
    }
    return out;
}

float advancement(Square s, Color side) noexcept {
    return static_cast<float>(side == Color::White ? 9 - row_of(s) : row_of(s));
}

std::array<float, F4_WIDTH> structure_side(const Position& p, Color side) {
    const auto men = squares_of(p.men_of(side));
    std::array<float, F4_WIDTH> out{};
    if (men.empty()) return out;
    std::array<bool, NUM_SQUARES + 1> is_man{};
    for (Square s : men) is_man[static_cast<std::size_t>(s)] = true;

    int components = 0;
    int largest = 0;
    int isolated = 0;
    int edges = 0;
    std::array<bool, NUM_SQUARES + 1> seen{};
    for (Square s : men) {
        int degree = 0;
        for (Dir d : ALL_DIRS) {
            const Square n = neighbour(s, d);
            if (n != NO_SQUARE && is_man[static_cast<std::size_t>(n)]) ++degree;
        }
        if (degree == 0) ++isolated;
        edges += degree;
        if (seen[static_cast<std::size_t>(s)]) continue;
        ++components;
        int size = 0;
        std::queue<Square> q;
        q.push(s); seen[static_cast<std::size_t>(s)] = true;
        while (!q.empty()) {
            const Square cur = q.front(); q.pop(); ++size;
            for (Dir d : ALL_DIRS) {
                const Square n = neighbour(cur, d);
                if (n == NO_SQUARE || !is_man[static_cast<std::size_t>(n)] || seen[static_cast<std::size_t>(n)]) continue;
                seen[static_cast<std::size_t>(n)] = true; q.push(n);
            }
        }
        largest = std::max(largest, size);
    }
    edges /= 2;

    int edge_file = 0, central = 0, home = 0, blocked = 0;
    float nearest_sum = 0.0F, nearest_max = 0.0F;
    int wing_sum = 0;
    int min_r = 10, max_r = -1, min_c = 10, max_c = -1;
    float front = 0.0F, rear = 9.0F;
    int quiet_destinations = 0;
    const Bitboard occupied = p.occupied();
    for (Square s : men) {
        const int r = row_of(s), c = col_of(s);
        edge_file += (c == 0 || c == 9) ? 1 : 0;
        central += is_central(s) ? 1 : 0;
        home += (side == Color::White ? r == 9 : r == 0) ? 1 : 0;
        int quiet = 0;
        for (Dir d : man_forward_dirs(side)) {
            const Square to = neighbour(s, d);
            if (to != NO_SQUARE && !test(occupied, to)) ++quiet;
        }
        quiet_destinations += quiet;
        blocked += quiet == 0 ? 1 : 0;
        wing_sum += 2 * c - 9;
        min_r = std::min(min_r, r); max_r = std::max(max_r, r);
        min_c = std::min(min_c, c); max_c = std::max(max_c, c);
        const float a = advancement(s, side);
        front = std::max(front, a); rear = std::min(rear, a);
        if (men.size() >= 2U) {
            int nearest = 10;
            for (Square t : men) if (t != s) nearest = std::min(nearest, chebyshev(s, t));
            nearest_sum += static_cast<float>(nearest);
            nearest_max = std::max(nearest_max, static_cast<float>(nearest));
        }
    }
    const float nearest_mean = men.size() < 2U ? 0.0F : nearest_sum / static_cast<float>(men.size());
    if (men.size() < 2U) nearest_max = 0.0F;
    int holes3 = 0;
    for (int si = 1; si <= NUM_SQUARES; ++si) {
        const Square s = static_cast<Square>(si);
        if (test(occupied, s)) continue;
        int adj = 0;
        for (Dir d : ALL_DIRS) {
            const Square n = neighbour(s, d);
            if (n != NO_SQUARE && is_man[static_cast<std::size_t>(n)]) ++adj;
        }
        holes3 += adj >= 3 ? 1 : 0;
    }
    out = {
        static_cast<float>(components), static_cast<float>(largest), static_cast<float>(isolated),
        static_cast<float>(edges), static_cast<float>(edge_file), static_cast<float>(central),
        static_cast<float>(home), static_cast<float>(blocked), nearest_mean, nearest_max,
        static_cast<float>(std::abs(wing_sum)),
        static_cast<float>((max_r - min_r + 1) * (max_c - min_c + 1)),
        front, rear, static_cast<float>(holes3),
        static_cast<float>(quiet_destinations) / static_cast<float>(std::max<std::size_t>(1U, men.size())),
    };
    return out;
}

std::array<float, F4_WIDTH> structure_graph(const Position& p, Color parent) {
    const auto w = structure_side(p, Color::White);
    const auto b = structure_side(p, Color::Black);
    std::array<float, F4_WIDTH> out{};
    for (std::size_t i = 0; i < out.size(); ++i) out[i] = parent_minus(parent, w[i], b[i]);
    return out;
}

bool clear_diagonal(const Position& p, Square a, Square b) noexcept {
    const int dr = row_of(b) - row_of(a);
    const int dc = col_of(b) - col_of(a);
    if (dr == 0 || std::abs(dr) != std::abs(dc)) return false;
    Dir d = Dir::UpLeft;
    if (dr < 0 && dc > 0) d = Dir::UpRight;
    else if (dr > 0 && dc < 0) d = Dir::DownLeft;
    else if (dr > 0 && dc > 0) d = Dir::DownRight;
    Square cur = neighbour(a, d);
    while (cur != NO_SQUARE && cur != b) {
        if (test(p.occupied(), cur)) return false;
        cur = neighbour(cur, d);
    }
    return cur == b;
}

bool enemy_man_can_capture_king_destination(const Position& p, Color king_side,
                                             Square from, Square dest) noexcept {
    Bitboard occupied = p.occupied();
    clear(occupied, from);
    set(occupied, dest);
    Bitboard enemies = p.men_of(opposite(king_side));
    while (enemies) {
        const Square e = pop_lsb(enemies);
        for (Dir d : ALL_DIRS) {
            const Square x = neighbour(e, d);
            if (x != dest) continue;
            const Square landing = neighbour(x, d);
            if (landing != NO_SQUARE && !test(occupied, landing)) return true;
        }
    }
    return false;
}

std::array<float, F5_WIDTH> king_side(const Position& p, Color side) {
    const auto kings = squares_of(p.kings_of(side));
    const auto enemies = squares_of(p.pieces_of(opposite(side)));
    std::array<float, F5_WIDTH> out{};
    out[0] = static_cast<float>(kings.size());
    if (kings.empty()) {
        out[7] = SENTINEL;
        out[8] = SENTINEL;
        out[10] = SENTINEL;
        return out;
    }
    float total_slides = 0.0F, safe_slides = 0.0F, denied_slides = 0.0F;
    int edge = 0, central = 0, trapped = 0, visible_enemies = 0;
    float nearest_enemy_min = SENTINEL, nearest_enemy_sum = 0.0F;
    const Bitboard occupied = p.occupied();
    for (Square k : kings) {
        int king_safe = 0;
        for (Dir d : ALL_DIRS) {
            const KingRay& ray = king_ray(k, d);
            for (std::uint8_t ri = 0; ri < ray.length; ++ri) {
                const Square to = ray.squares[ri];
                if (test(occupied, to)) break;
                total_slides += 1.0F;
                if (enemy_man_can_capture_king_destination(p, side, k, to)) denied_slides += 1.0F;
                else { safe_slides += 1.0F; ++king_safe; }
            }
        }
        const int r = row_of(k), c = col_of(k);
        edge += (r == 0 || r == 9 || c == 0 || c == 9) ? 1 : 0;
        central += is_central(k) ? 1 : 0;
        trapped += king_safe <= 1 ? 1 : 0;
        if (!enemies.empty()) {
            int nearest = 10;
            for (Square e : enemies) {
                nearest = std::min(nearest, chebyshev(k, e));
                if (clear_diagonal(p, k, e)) ++visible_enemies;
            }
            nearest_enemy_min = std::min(nearest_enemy_min, static_cast<float>(nearest));
            nearest_enemy_sum += static_cast<float>(nearest);
        }
    }
    float pair_min = SENTINEL;
    int same_diag_pairs = 0;
    if (kings.size() >= 2U) {
        for (std::size_t i = 0; i < kings.size(); ++i) {
            for (std::size_t j = i + 1U; j < kings.size(); ++j) {
                pair_min = std::min(pair_min, static_cast<float>(chebyshev(kings[i], kings[j])));
                same_diag_pairs += clear_diagonal(p, kings[i], kings[j]) ? 1 : 0;
            }
        }
    }
    out[1] = total_slides;
    out[2] = safe_slides;
    out[3] = denied_slides;
    out[4] = static_cast<float>(edge);
    out[5] = static_cast<float>(central);
    out[6] = static_cast<float>(trapped);
    if (enemies.empty()) {
        out[7] = SENTINEL; out[8] = SENTINEL;
    } else {
        out[7] = nearest_enemy_min;
        out[8] = nearest_enemy_sum / static_cast<float>(kings.size());
    }
    out[9] = static_cast<float>(visible_enemies);
    out[10] = pair_min;
    out[11] = static_cast<float>(same_diag_pairs);
    return out;
}

std::array<float, F5_WIDTH> king_geometry_plus(const Position& p, Color parent) {
    const auto w = king_side(p, Color::White);
    const auto b = king_side(p, Color::Black);
    std::array<float, F5_WIDTH> out{};
    for (std::size_t i = 0; i < out.size(); ++i) out[i] = parent_minus(parent, w[i], b[i]);
    return out;
}

std::array<float, CTX2_WIDTH> ctx2_ref(const Position& p, Color parent, bool& available) {
    std::array<float, scan_eval::CONDITIONAL_CONTEXT_V2_WIDTH> raw{};
    available = scan_eval::compute_conditional_context_v2(p, raw);
    std::array<float, CTX2_WIDTH> out{};
    if (!available) return out;
    const float sign = parent == Color::Black ? 1.0F : -1.0F;
    for (std::size_t i = 0; i < CTX2_WIDTH; ++i) out[i] = sign * (raw[i] + raw[CTX2_WIDTH + i]);
    return out;
}

}  // namespace

std::array<float, ALL_NEW_WIDTH> FeatureVector::all_new() const noexcept {
    std::array<float, ALL_NEW_WIDTH> out{};
    std::size_t k = 0;
    for (float v : capture_geometry) out[k++] = v;
    for (float v : response_frontier) out[k++] = v;
    for (float v : promotion_race) out[k++] = v;
    for (float v : structure_graph) out[k++] = v;
    for (float v : king_geometry_plus) out[k++] = v;
    return out;
}

std::array<float, TOTAL_WIDTH> FeatureVector::packed() const noexcept {
    std::array<float, TOTAL_WIDTH> out{};
    std::size_t k = 0;
    for (float v : ctx2_ref) out[k++] = v;
    for (float v : all_new()) out[k++] = v;
    return out;
}

FeatureVector extract(const Position& child) {
    FeatureVector out;
    const Color parent = opposite(child.side_to_move());
    out.ctx2_ref = ctx2_ref(child, parent, out.ctx2_available);
    MoveList replies;
    out.capture_geometry = capture_geometry(child, parent, &replies, nullptr);
    out.response_frontier = response_frontier(child, parent, &replies, nullptr);
    out.promotion_race = promotion_race(child, parent);
    out.structure_graph = structure_graph(child, parent);
    out.king_geometry_plus = king_geometry_plus(child, parent);
    return out;
}

FeatureVector extract_f6(const Position& child, Profile* profile) {
    FeatureVector out;
    const Color parent = opposite(child.side_to_move());
    using Clock = std::chrono::steady_clock;
    MoveList replies;
    auto start = Clock::now();
    out.capture_geometry = capture_geometry(child, parent, &replies, profile);
    if (profile) profile->family_ns[0] += static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - start).count());
    start = Clock::now();
    out.response_frontier = response_frontier(child, parent, &replies, profile);
    if (profile) profile->family_ns[1] += static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - start).count());
    start = Clock::now();
    out.promotion_race = promotion_race(child, parent);
    if (profile) profile->family_ns[2] += static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - start).count());
    start = Clock::now();
    out.structure_graph = structure_graph(child, parent);
    if (profile) profile->family_ns[3] += static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - start).count());
    start = Clock::now();
    out.king_geometry_plus = king_geometry_plus(child, parent);
    if (profile) profile->family_ns[4] += static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - start).count());
    return out;
}

const std::array<const char*, CTX2_WIDTH>& ctx2_names() noexcept {
    static const std::array<const char*, CTX2_WIDTH> names = {
        "men_delta", "has_king_delta", "extra_king_delta", "legal_move_count_delta",
        "legal_capture_option_delta", "max_capture_length_delta", "forced_move_delta",
        "promotion_pressure_delta", "blocked_man_delta", "center_presence_delta",
        "wing_skew_abs_delta", "king_centrality_delta", "king_proximity_delta",
        "king_safe_mobility_delta", "king_denied_delta",
    };
    return names;
}

const std::array<const char*, F1_WIDTH>& f1_names() noexcept {
    static const std::array<const char*, F1_WIDTH> names = {
        "legal_move_count_delta", "legal_capture_move_count_delta", "max_captured_piece_count_delta",
        "mean_captured_piece_count_delta", "max_captured_king_count_delta", "mean_captured_king_count_delta",
        "unique_capture_landing_count_delta", "unique_capture_origin_count_delta", "legal_promotion_move_count_delta",
        "legal_capture_promote_count_delta", "forced_move_indicator_delta", "capture_landing_dispersion_delta",
    };
    return names;
}

const std::array<const char*, F2_WIDTH>& f2_names() noexcept {
    static const std::array<const char*, F2_WIDTH> names = {
        "opponent_reply_count", "opponent_reply_capture_fraction", "opponent_reply_promote_fraction",
        "min_parent_material_delta_after_reply", "mean_parent_material_delta_after_reply", "max_parent_material_delta_after_reply",
        "min_parent_next_legal_moves", "mean_parent_next_legal_moves", "max_parent_next_legal_moves",
        "min_parent_next_max_capture_length", "mean_parent_next_max_capture_length", "max_parent_next_max_capture_length",
        "reply_fraction_parent_has_capture", "reply_fraction_parent_forced",
    };
    return names;
}

const std::array<const char*, F3_WIDTH>& f3_names() noexcept {
    static const std::array<const char*, F3_WIDTH> names = {
        "promo_min_distance_delta", "promo_mean_distance_delta", "promo_count_le1_delta", "promo_count_le2_delta",
        "promo_count_le3_delta", "promo_no_path_count_delta", "threatblocked_promo_min_distance_delta",
        "threatblocked_promo_mean_distance_delta", "threatblocked_promo_count_le1_delta", "threatblocked_promo_count_le2_delta",
        "threatblocked_promo_count_le3_delta", "threatblocked_promo_no_path_count_delta",
    };
    return names;
}

const std::array<const char*, F4_WIDTH>& f4_names() noexcept {
    static const std::array<const char*, F4_WIDTH> names = {
        "men_component_count_delta", "men_largest_component_delta", "isolated_man_count_delta", "friendly_diagonal_edge_count_delta",
        "edge_file_man_count_delta", "central16_man_count_delta", "home_row_man_count_delta", "blocked_man_count_delta",
        "mean_nearest_friendly_man_distance_delta", "max_nearest_friendly_man_distance_delta", "wing_skew_abs_delta",
        "men_bounding_box_area_delta", "frontmost_man_advancement_delta", "rearmost_man_advancement_delta",
        "holes3_count_delta", "quiet_mobility_per_man_delta",
    };
    return names;
}

const std::array<const char*, F5_WIDTH>& f5_names() noexcept {
    static const std::array<const char*, F5_WIDTH> names = {
        "king_count_delta", "king_slide_destinations_delta", "king_safe_slide_destinations_delta", "king_denied_slide_destinations_delta",
        "edge_square_king_count_delta", "central16_king_count_delta", "trapped_king_count_delta", "min_king_enemy_distance_delta",
        "mean_nearest_enemy_distance_delta", "unobstructed_diagonal_enemy_pairs_delta", "min_same_colour_king_pair_distance_delta",
        "same_unobstructed_long_diagonal_king_pairs_delta",
    };
    return names;
}

}  // namespace jass::residual_features

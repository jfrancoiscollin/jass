// SPDX-License-Identifier: AGPL-3.0-or-later
// Deterministic, search-free feature extractor for
// L3_RESIDUAL_FEATURE_DISCOVERY_V1_20260828.
//
// Input:  JNNW child positions. score/wdl bytes are deliberately ignored.
// Output: RFF1 + uint32 count + uint32 width(66) + count*66 float32 values.
//
// This tool links against production jass_lib and therefore reuses the exact
// FMJD legal move generator, Position::after, board geometry and piece rules.
// It performs no alpha-beta, TT lookup, learned evaluation or node-budget
// search.  Bounded one-ply reply enumeration is the deepest operation.

#include "bitboard.hpp"
#include "board.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "types.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <limits>
#include <numeric>
#include <queue>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace rf {
using namespace jass;

constexpr std::size_t F1_WIDTH = 12;
constexpr std::size_t F2_WIDTH = 14;
constexpr std::size_t F3_WIDTH = 12;
constexpr std::size_t F4_WIDTH = 16;
constexpr std::size_t F5_WIDTH = 12;
constexpr std::size_t TOTAL_WIDTH = F1_WIDTH + F2_WIDTH + F3_WIDTH + F4_WIDTH + F5_WIDTH;
static_assert(TOTAL_WIDTH == 66);

// Frozen by prereg implementation tests: playable squares in physical rows
// 3..6 and physical columns 1..8, exactly 4 squares per row.
constexpr std::array<Square, 16> CENTRAL16 = {
    Square{17}, Square{18}, Square{19}, Square{20},
    Square{21}, Square{22}, Square{23}, Square{24},
    Square{27}, Square{28}, Square{29}, Square{30},
    Square{31}, Square{32}, Square{33}, Square{34},
};

bool is_central16(Square s) noexcept {
    return std::find(CENTRAL16.begin(), CENTRAL16.end(), s) != CENTRAL16.end();
}

bool is_edge_file(Square s) noexcept {
    const int c = col_of(s);
    return c == 0 || c == 9;
}

bool is_edge_square(Square s) noexcept {
    const int r = row_of(s), c = col_of(s);
    return r == 0 || r == 9 || c == 0 || c == 9;
}

Piece man_piece(Color c) noexcept {
    return c == Color::White ? Piece::WhiteMan : Piece::BlackMan;
}
Piece king_piece(Color c) noexcept {
    return c == Color::White ? Piece::WhiteKing : Piece::BlackKing;
}

std::vector<Square> squares(Bitboard bb) {
    std::vector<Square> out;
    out.reserve(static_cast<std::size_t>(popcount(bb)));
    while (bb) out.push_back(pop_lsb(bb));
    return out;
}

Position side_position(const Position& pos, Color side) {
    Position p = pos;
    p.set_side_to_move(side);
    return p;
}

MoveList legal_for(const Position& pos, Color side) {
    Position p = side_position(pos, side);
    MoveList out;
    generate_legal_moves(p, out);
    return out;
}

int captured_kings(const Position& pos, const Move& m, Color mover) noexcept {
    return popcount(m.captured & pos.kings_of(opposite(mover)));
}

double sq_distance(Square a, Square b) noexcept {
    const double dr = static_cast<double>(row_of(a) - row_of(b));
    const double dc = static_cast<double>(col_of(a) - col_of(b));
    return dr * dr + dc * dc;
}

std::array<double, F1_WIDTH> capture_geometry_side(const Position& pos, Color side) {
    const MoveList moves = legal_for(pos, side);
    int captures = 0, max_cap = 0, sum_cap = 0;
    int max_k = 0, sum_k = 0, promotions = 0, cap_promotions = 0;
    std::set<int> origins, landings;
    std::vector<Square> capture_landings;
    for (const auto& m : moves) {
        promotions += m.promotes ? 1 : 0;
        if (!m.is_capture()) continue;
        ++captures;
        max_cap = std::max(max_cap, static_cast<int>(m.num_captures));
        sum_cap += static_cast<int>(m.num_captures);
        const int ck = captured_kings(pos, m, side);
        max_k = std::max(max_k, ck);
        sum_k += ck;
        origins.insert(static_cast<int>(m.from));
        landings.insert(static_cast<int>(m.to));
        capture_landings.push_back(m.to);
        cap_promotions += m.promotes ? 1 : 0;
    }
    double dispersion = 0.0;
    if (capture_landings.size() >= 2) {
        double mr = 0.0, mc = 0.0;
        for (Square s : capture_landings) {
            mr += row_of(s);
            mc += col_of(s);
        }
        mr /= static_cast<double>(capture_landings.size());
        mc /= static_cast<double>(capture_landings.size());
        for (Square s : capture_landings) {
            const double dr = static_cast<double>(row_of(s)) - mr;
            const double dc = static_cast<double>(col_of(s)) - mc;
            dispersion += dr * dr + dc * dc;
        }
        dispersion /= static_cast<double>(capture_landings.size());
    }
    return {
        static_cast<double>(moves.size()),
        static_cast<double>(captures),
        static_cast<double>(max_cap),
        captures ? static_cast<double>(sum_cap) / captures : 0.0,
        static_cast<double>(max_k),
        captures ? static_cast<double>(sum_k) / captures : 0.0,
        static_cast<double>(landings.size()),
        static_cast<double>(origins.size()),
        static_cast<double>(promotions),
        static_cast<double>(cap_promotions),
        moves.size() == 1 ? 1.0 : 0.0,
        dispersion,
    };
}

template <std::size_t N>
std::array<double, N> subtract_arrays(const std::array<double, N>& a,
                                      const std::array<double, N>& b) {
    std::array<double, N> out{};
    for (std::size_t i = 0; i < N; ++i) out[i] = a[i] - b[i];
    return out;
}

int material_balance(const Position& pos, Color parent) noexcept {
    const Color opp = opposite(parent);
    return popcount(pos.men_of(parent)) + 3 * popcount(pos.kings_of(parent))
         - popcount(pos.men_of(opp)) - 3 * popcount(pos.kings_of(opp));
}

int max_capture_length(const MoveList& moves) noexcept {
    int best = 0;
    for (const auto& m : moves) best = std::max(best, static_cast<int>(m.num_captures));
    return best;
}

std::array<double, F2_WIDTH> response_frontier(const Position& child, Color parent) {
    const Color opponent = opposite(parent);
    Position opp_pos = side_position(child, opponent);
    MoveList replies;
    generate_legal_moves(opp_pos, replies);
    if (replies.empty()) return {};

    const int before_material = material_balance(child, parent);
    std::vector<double> material_delta, next_moves, next_max_capture;
    material_delta.reserve(replies.size());
    next_moves.reserve(replies.size());
    next_max_capture.reserve(replies.size());
    int reply_caps = 0, reply_promotes = 0, next_has_capture = 0, next_forced = 0;

    for (const auto& r : replies) {
        reply_caps += r.is_capture() ? 1 : 0;
        reply_promotes += r.promotes ? 1 : 0;
        Position after = opp_pos.after(r);
        // Position::after flips STM, so the parent is already on move.
        MoveList frontier;
        generate_legal_moves(after, frontier);
        material_delta.push_back(static_cast<double>(material_balance(after, parent) - before_material));
        next_moves.push_back(static_cast<double>(frontier.size()));
        const int mx = max_capture_length(frontier);
        next_max_capture.push_back(static_cast<double>(mx));
        next_has_capture += mx > 0 ? 1 : 0;
        next_forced += frontier.size() == 1 ? 1 : 0;
    }

    auto mm = [](const std::vector<double>& v) {
        const auto [lo, hi] = std::minmax_element(v.begin(), v.end());
        const double mean = std::accumulate(v.begin(), v.end(), 0.0) / static_cast<double>(v.size());
        return std::array<double, 3>{*lo, mean, *hi};
    };
    const auto md = mm(material_delta), nm = mm(next_moves), nc = mm(next_max_capture);
    const double n = static_cast<double>(replies.size());
    return {
        n,
        static_cast<double>(reply_caps) / n,
        static_cast<double>(reply_promotes) / n,
        md[0], md[1], md[2],
        nm[0], nm[1], nm[2],
        nc[0], nc[1], nc[2],
        static_cast<double>(next_has_capture) / n,
        static_cast<double>(next_forced) / n,
    };
}

// Empty squares on which a hypothetical man of `victim` would be immediately
// capturable by an enemy man, using only one direct FMJD man jump. This is a
// geometry predicate, not a legal-move/search call. Men capture in all four
// diagonal directions in international draughts.
Bitboard enemy_man_attackable_empty_squares(const Position& pos, Color victim) noexcept {
    const Color enemy = opposite(victim);
    const Bitboard occ = pos.occupied();
    Bitboard hazards = 0;
    Bitboard em = pos.men_of(enemy);
    while (em) {
        const Square from = pop_lsb(em);
        for (Dir d : ALL_DIRS) {
            const Square target = neighbour(from, d);
            if (target == NO_SQUARE || test(occ, target)) continue;
            const Square landing = neighbour(target, d);
            if (landing == NO_SQUARE || test(occ, landing)) continue;
            set(hazards, target);
        }
    }
    return hazards;
}

int quiet_promotion_distance(const Position& pos, Square start, Color side, Bitboard extra_blocked) {
    const Bitboard blocked = (pos.occupied() & ~square_bb(start)) | extra_blocked;
    std::array<int, NUM_SQUARES + 1> dist{};
    dist.fill(-1);
    std::queue<Square> q;
    q.push(start);
    dist[start] = 0;
    while (!q.empty()) {
        const Square cur = q.front(); q.pop();
        if (is_promotion_square(cur, side)) return dist[cur];
        for (Dir d : man_forward_dirs(side)) {
            const Square nxt = neighbour(cur, d);
            if (nxt == NO_SQUARE || test(blocked, nxt) || dist[nxt] >= 0) continue;
            dist[nxt] = dist[cur] + 1;
            q.push(nxt);
        }
    }
    return -1;
}

std::array<double, 6> promotion_summary(const Position& pos, Color side, Bitboard hazards) {
    std::vector<int> finite;
    int c1 = 0, c2 = 0, c3 = 0, no_path = 0;
    Bitboard men = pos.men_of(side);
    while (men) {
        const Square s = pop_lsb(men);
        const int d = quiet_promotion_distance(pos, s, side, hazards);
        if (d < 0) { ++no_path; continue; }
        finite.push_back(d);
        c1 += d <= 1 ? 1 : 0;
        c2 += d <= 2 ? 1 : 0;
        c3 += d <= 3 ? 1 : 0;
    }
    double mn = 8.0, mean = 8.0;
    if (!finite.empty()) {
        mn = static_cast<double>(*std::min_element(finite.begin(), finite.end()));
        mean = static_cast<double>(std::accumulate(finite.begin(), finite.end(), 0))
             / static_cast<double>(finite.size());
    }
    return {mn, mean, static_cast<double>(c1), static_cast<double>(c2),
            static_cast<double>(c3), static_cast<double>(no_path)};
}

std::array<double, F3_WIDTH> promotion_race(const Position& pos, Color parent) {
    const Color opp = opposite(parent);
    const auto p0 = promotion_summary(pos, parent, 0);
    const auto o0 = promotion_summary(pos, opp, 0);
    const auto p1 = promotion_summary(pos, parent, enemy_man_attackable_empty_squares(pos, parent));
    const auto o1 = promotion_summary(pos, opp, enemy_man_attackable_empty_squares(pos, opp));
    std::array<double, F3_WIDTH> out{};
    for (int i = 0; i < 6; ++i) {
        out[static_cast<std::size_t>(i)] = p0[static_cast<std::size_t>(i)] - o0[static_cast<std::size_t>(i)];
        out[static_cast<std::size_t>(i + 6)] = p1[static_cast<std::size_t>(i)] - o1[static_cast<std::size_t>(i)];
    }
    return out;
}

int advancement(Square s, Color side) noexcept {
    return side == Color::White ? 9 - row_of(s) : row_of(s);
}

std::array<double, F4_WIDTH> structure_side(const Position& pos, Color side) {
    const std::vector<Square> men = squares(pos.men_of(side));
    if (men.empty()) return {};
    std::array<int, NUM_SQUARES + 1> idx{};
    idx.fill(-1);
    for (std::size_t i = 0; i < men.size(); ++i) idx[men[i]] = static_cast<int>(i);

    std::vector<std::vector<int>> adj(men.size());
    int edges = 0;
    for (std::size_t i = 0; i < men.size(); ++i) {
        for (Dir d : ALL_DIRS) {
            const Square n = neighbour(men[i], d);
            if (n == NO_SQUARE || idx[n] < 0) continue;
            adj[i].push_back(idx[n]);
            if (static_cast<int>(i) < idx[n]) ++edges;
        }
    }
    std::vector<int> seen(men.size(), 0);
    int components = 0, largest = 0, isolated = 0;
    for (std::size_t i = 0; i < men.size(); ++i) {
        if (adj[i].empty()) ++isolated;
        if (seen[i]) continue;
        ++components;
        int size = 0;
        std::queue<int> q; q.push(static_cast<int>(i)); seen[i] = 1;
        while (!q.empty()) {
            const int u = q.front(); q.pop(); ++size;
            for (int v : adj[static_cast<std::size_t>(u)]) if (!seen[static_cast<std::size_t>(v)]) {
                seen[static_cast<std::size_t>(v)] = 1; q.push(v);
            }
        }
        largest = std::max(largest, size);
    }

    int edge_file = 0, central = 0, home = 0, blocked = 0, holes3 = 0, quiet_dest = 0;
    int minr = 10, maxr = -1, minc = 10, maxc = -1;
    int front = 0, rear = 10;
    long long skew = 0;
    double nearest_sum = 0.0, nearest_max = 0.0;
    const Bitboard occ = pos.occupied();
    for (Square s : men) {
        edge_file += is_edge_file(s) ? 1 : 0;
        central += is_central16(s) ? 1 : 0;
        const int r = row_of(s), c = col_of(s), a = advancement(s, side);
        home += (side == Color::White ? r == 9 : r == 0) ? 1 : 0;
        minr = std::min(minr, r); maxr = std::max(maxr, r);
        minc = std::min(minc, c); maxc = std::max(maxc, c);
        front = std::max(front, a); rear = std::min(rear, a);
        skew += 2 * c - 9;
        int qcount = 0;
        for (Dir d : man_forward_dirs(side)) {
            const Square n = neighbour(s, d);
            if (n != NO_SQUARE && !test(occ, n)) ++qcount;
        }
        blocked += qcount == 0 ? 1 : 0;
        quiet_dest += qcount;
        if (men.size() >= 2) {
            int best = 99;
            for (Square t : men) if (t != s) {
                best = std::min(best, std::max(std::abs(row_of(s)-row_of(t)), std::abs(col_of(s)-col_of(t))));
            }
            nearest_sum += best;
            nearest_max = std::max(nearest_max, static_cast<double>(best));
        }
    }
    for (int si = 1; si <= NUM_SQUARES; ++si) {
        const Square s = static_cast<Square>(si);
        if (test(occ, s)) continue;
        int neighbours_friendly = 0;
        for (Dir d : ALL_DIRS) {
            const Square n = neighbour(s, d);
            if (n != NO_SQUARE && test(pos.men_of(side), n)) ++neighbours_friendly;
        }
        holes3 += neighbours_friendly >= 3 ? 1 : 0;
    }
    return {
        static_cast<double>(components), static_cast<double>(largest), static_cast<double>(isolated),
        static_cast<double>(edges), static_cast<double>(edge_file), static_cast<double>(central),
        static_cast<double>(home), static_cast<double>(blocked),
        men.size() >= 2 ? nearest_sum / static_cast<double>(men.size()) : 0.0,
        men.size() >= 2 ? nearest_max : 0.0,
        static_cast<double>(std::llabs(skew)),
        static_cast<double>((maxr-minr+1) * (maxc-minc+1)),
        static_cast<double>(front), static_cast<double>(rear == 10 ? 0 : rear),
        static_cast<double>(holes3), static_cast<double>(quiet_dest) / static_cast<double>(men.size()),
    };
}

std::array<double, F4_WIDTH> structure_graph(const Position& pos, Color parent) {
    return subtract_arrays(structure_side(pos, parent), structure_side(pos, opposite(parent)));
}

bool target_capturable_by_enemy_man(const Position& pos, Square target, Color victim) noexcept {
    const Color enemy = opposite(victim);
    Bitboard men = pos.men_of(enemy);
    while (men) {
        const Square from = pop_lsb(men);
        for (Dir d : ALL_DIRS) {
            if (neighbour(from, d) != target) continue;
            const Square landing = neighbour(target, d);
            if (landing != NO_SQUARE && !test(pos.occupied(), landing)) return true;
        }
    }
    return false;
}

int chebyshev(Square a, Square b) noexcept {
    return std::max(std::abs(row_of(a)-row_of(b)), std::abs(col_of(a)-col_of(b)));
}

std::array<double, F5_WIDTH> king_side(const Position& pos, Color side) {
    const std::vector<Square> kings = squares(pos.kings_of(side));
    const std::vector<Square> enemies = squares(pos.pieces_of(opposite(side)));
    int total_slides = 0, safe_slides = 0, edge = 0, central = 0, trapped = 0;
    int shared_enemy_diag = 0, same_diag_pairs = 0;
    double nearest_enemy_sum = 0.0;
    int nearest_enemy_min = 8;
    int pair_min = 8;

    for (Square k : kings) {
        edge += is_edge_square(k) ? 1 : 0;
        central += is_central16(k) ? 1 : 0;
        int king_safe = 0;
        for (Dir d : ALL_DIRS) {
            const auto& ray = king_ray(k, d);
            for (std::uint8_t ri = 0; ri < ray.length; ++ri) {
                const Square dest = ray.squares[ri];
                if (test(pos.occupied(), dest)) break;
                ++total_slides;
                Position sim = pos;
                sim.remove_piece(k, king_piece(side));
                sim.add_piece(dest, king_piece(side));
                if (!target_capturable_by_enemy_man(sim, dest, side)) {
                    ++safe_slides; ++king_safe;
                }
            }
            // First occupied piece on this ray; count enemy visibility.
            for (std::uint8_t ri = 0; ri < ray.length; ++ri) {
                const Square s = ray.squares[ri];
                if (!test(pos.occupied(), s)) continue;
                if (test(pos.pieces_of(opposite(side)), s)) ++shared_enemy_diag;
                break;
            }
        }
        trapped += king_safe <= 1 ? 1 : 0;
        if (!enemies.empty()) {
            int best = 8;
            for (Square e : enemies) best = std::min(best, chebyshev(k, e));
            nearest_enemy_min = std::min(nearest_enemy_min, best);
            nearest_enemy_sum += best;
        }
    }
    for (std::size_t i = 0; i < kings.size(); ++i) {
        for (std::size_t j = i + 1; j < kings.size(); ++j) {
            pair_min = std::min(pair_min, chebyshev(kings[i], kings[j]));
            bool aligned_clear = false;
            for (Dir d : ALL_DIRS) {
                const auto& ray = king_ray(kings[i], d);
                for (std::uint8_t ri = 0; ri < ray.length; ++ri) {
                    const Square s = ray.squares[ri];
                    if (!test(pos.occupied(), s)) continue;
                    aligned_clear = s == kings[j];
                    break;
                }
                if (aligned_clear) break;
            }
            same_diag_pairs += aligned_clear ? 1 : 0;
        }
    }
    return {
        static_cast<double>(kings.size()), static_cast<double>(total_slides),
        static_cast<double>(safe_slides), static_cast<double>(total_slides-safe_slides),
        static_cast<double>(edge), static_cast<double>(central), static_cast<double>(trapped),
        (kings.empty() || enemies.empty()) ? 8.0 : static_cast<double>(nearest_enemy_min),
        (kings.empty() || enemies.empty()) ? 8.0 : nearest_enemy_sum / static_cast<double>(kings.size()),
        static_cast<double>(shared_enemy_diag),
        kings.size() < 2 ? 8.0 : static_cast<double>(pair_min),
        static_cast<double>(same_diag_pairs),
    };
}

std::array<double, F5_WIDTH> king_geometry_plus(const Position& pos, Color parent) {
    return subtract_arrays(king_side(pos, parent), king_side(pos, opposite(parent)));
}

std::array<double, TOTAL_WIDTH> extract(const Position& child) {
    const Color parent = opposite(child.side_to_move());
    const auto f1 = subtract_arrays(capture_geometry_side(child, parent), capture_geometry_side(child, opposite(parent)));
    const auto f2 = response_frontier(child, parent);
    const auto f3 = promotion_race(child, parent);
    const auto f4 = structure_graph(child, parent);
    const auto f5 = king_geometry_plus(child, parent);
    std::array<double, TOTAL_WIDTH> out{};
    std::size_t at = 0;
    auto append = [&](const auto& src) {
        for (double v : src) out[at++] = v;
    };
    append(f1); append(f2); append(f3); append(f4); append(f5);
    if (at != TOTAL_WIDTH) throw std::runtime_error("residual feature width drift");
    for (double v : out) if (!std::isfinite(v)) throw std::runtime_error("non-finite residual feature");
    return out;
}

Position exact_image(const Position& p) {
    Position q;
    q.clear();
    q.set_side_to_move(opposite(p.side_to_move()));
    auto add_rotated = [&](Bitboard bb, Piece piece) {
        while (bb) {
            const Square s = pop_lsb(bb);
            q.add_piece(static_cast<Square>(51 - static_cast<int>(s)), piece);
        }
    };
    // rotate180 + colour swap.
    add_rotated(p.black_men(), Piece::WhiteMan);
    add_rotated(p.black_kings(), Piece::WhiteKing);
    add_rotated(p.white_men(), Piece::BlackMan);
    add_rotated(p.white_kings(), Piece::BlackKing);
    return q;
}

void require(bool ok, const char* msg) {
    if (!ok) throw std::runtime_error(msg);
}

int self_test() {
    constexpr std::array<Square, 16> expected = {
        Square{17}, Square{18}, Square{19}, Square{20}, Square{21}, Square{22}, Square{23}, Square{24},
        Square{27}, Square{28}, Square{29}, Square{30}, Square{31}, Square{32}, Square{33}, Square{34},
    };
    require(CENTRAL16 == expected, "central16 contract drift");

    const auto start = Position::start_position();
    const auto a = extract(start);
    require(a.size() == 66, "feature width !=66");
    const auto ai = extract(exact_image(start));
    for (std::size_t i = 0; i < a.size(); ++i)
        require(std::abs(a[i] - ai[i]) < 1e-9, "parent-POV symmetry drift");

    // A complete two-capture chain must be represented as one semantic move.
    auto multi = Position::from_fen("W:W32:B22,13");
    require(multi.has_value(), "multi-capture fixture parse failed");
    MoveList ml; generate_legal_moves(*multi, ml);
    require(!ml.empty(), "multi-capture fixture has no move");
    int maxc = 0;
    for (const auto& m : ml) maxc = std::max(maxc, static_cast<int>(m.num_captures));
    require(maxc >= 2, "FMJD semantic multi-capture not preserved");

    auto race = Position::from_fen("W:W6:B45");
    require(race.has_value(), "promotion fixture parse failed");
    require(quiet_promotion_distance(*race, Square{6}, Color::White, 0) == 1,
            "promotion BFS distance drift");

    MoveList sm; generate_legal_moves(start, sm);
    const auto f2 = response_frontier(start, Color::Black); // child STM White, parent Black.
    require(std::abs(f2[0] - static_cast<double>(sm.size())) < 1e-12,
            "response enumeration count drift");

    std::cout << "RESIDUAL_FEATURE_SELFTEST_OK width=66 central16=17,18,19,20,21,22,23,24,27,28,29,30,31,32,33,34\n";
    return 0;
}

std::uint32_t le32(const unsigned char* p) noexcept {
    return static_cast<std::uint32_t>(p[0])
         | (static_cast<std::uint32_t>(p[1]) << 8)
         | (static_cast<std::uint32_t>(p[2]) << 16)
         | (static_cast<std::uint32_t>(p[3]) << 24);
}
std::uint64_t le64(const unsigned char* p) noexcept {
    std::uint64_t v = 0;
    for (int i = 0; i < 8; ++i) v |= static_cast<std::uint64_t>(p[i]) << (8*i);
    return v;
}
void write_u32(std::ofstream& out, std::uint32_t v) {
    unsigned char p[4] = {static_cast<unsigned char>(v), static_cast<unsigned char>(v>>8),
                          static_cast<unsigned char>(v>>16), static_cast<unsigned char>(v>>24)};
    out.write(reinterpret_cast<const char*>(p), 4);
}

Position record_position(const std::array<unsigned char, 38>& rec) {
    Position p; p.clear();
    const std::array<std::uint64_t, 4> bb = {
        le64(rec.data()+0), le64(rec.data()+8), le64(rec.data()+16), le64(rec.data()+24)};
    const std::array<Piece, 4> pc = {Piece::WhiteMan, Piece::WhiteKing, Piece::BlackMan, Piece::BlackKing};
    for (int k = 0; k < 4; ++k) {
        Bitboard b = bb[static_cast<std::size_t>(k)];
        while (b) p.add_piece(pop_lsb(b), pc[static_cast<std::size_t>(k)]);
    }
    if (rec[32] > 1) throw std::runtime_error("invalid JNNW stm");
    p.set_side_to_move(rec[32] == 0 ? Color::White : Color::Black);
    return p;
}

int dump(const std::string& input, const std::string& output) {
    std::ifstream in(input, std::ios::binary);
    if (!in) throw std::runtime_error("cannot open input JNNW");
    std::array<unsigned char, 8> hdr{};
    in.read(reinterpret_cast<char*>(hdr.data()), 8);
    if (in.gcount() != 8 || std::memcmp(hdr.data(), "JNNW", 4) != 0)
        throw std::runtime_error("bad JNNW header");
    const std::uint32_t count = le32(hdr.data()+4);
    std::ofstream out(output, std::ios::binary);
    if (!out) throw std::runtime_error("cannot open RFF1 output");
    out.write("RFF1", 4); write_u32(out, count); write_u32(out, static_cast<std::uint32_t>(TOTAL_WIDTH));
    for (std::uint32_t i = 0; i < count; ++i) {
        std::array<unsigned char, 38> rec{};
        in.read(reinterpret_cast<char*>(rec.data()), 38);
        if (in.gcount() != 38) throw std::runtime_error("truncated JNNW record");
        // Bytes [33..37] hold historical score/WDL. They are never read.
        const auto f = extract(record_position(rec));
        for (double v : f) {
            const float x = static_cast<float>(v);
            out.write(reinterpret_cast<const char*>(&x), sizeof(x));
        }
    }
    char extra = 0;
    if (in.read(&extra, 1)) throw std::runtime_error("trailing JNNW bytes");
    std::cout << "wrote " << count << " x " << TOTAL_WIDTH << " residual features\n";
    return 0;
}

} // namespace rf

int main(int argc, char** argv) {
    try {
        if (argc == 2 && std::string(argv[1]) == "--self-test") return rf::self_test();
        if (argc != 3) {
            std::cerr << "usage: residual_feature_dump <children.jnnw> <features.rff1> | --self-test\n";
            return 2;
        }
        return rf::dump(argv[1], argv[2]);
    } catch (const std::exception& e) {
        std::cerr << "residual_feature_dump: " << e.what() << '\n';
        return 1;
    }
}

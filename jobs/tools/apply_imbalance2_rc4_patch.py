#!/usr/bin/env python3
"""Apply the experimental D1-RC4 representation patch to an isolated source copy.

The production source tree is deliberately left untouched.  The D1 runner exports
HEAD with ``git archive``, applies this exact guarded transformation, and builds the
RC4 arm from that copy.  The control arm is built from the reviewed merge SHA
without modification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one guarded source block, found {count}")
    return text.replace(old, new, 1)


HEADER_OLD = """#ifdef JASS_SCAN_PARITY
inline constexpr int EXTRA_BK_SKEWABS = EXTRAS_AFTER_KMOB + 0;  // |skew| of black men
inline constexpr int EXTRA_WK_SKEWABS = EXTRAS_AFTER_KMOB + 1;  // |skew| of white men
inline constexpr int EXTRA_BK_HASKING = EXTRAS_AFTER_KMOB + 2;  // black has >=1 king
inline constexpr int EXTRA_WK_HASKING = EXTRAS_AFTER_KMOB + 3;  // white has >=1 king
inline constexpr int EXTRA_BK_EXTRAK  = EXTRAS_AFTER_KMOB + 4;  // black kings beyond the first
inline constexpr int EXTRA_WK_EXTRAK  = EXTRAS_AFTER_KMOB + 5;  // white kings beyond the first
inline constexpr int NUM_EXTRAS       = EXTRAS_AFTER_KMOB + 6;
#else
inline constexpr int NUM_EXTRAS       = EXTRAS_AFTER_KMOB;
#endif
"""

HEADER_NEW = """#ifdef JASS_SCAN_PARITY
inline constexpr int EXTRA_BK_SKEWABS = EXTRAS_AFTER_KMOB + 0;  // |skew| of black men
inline constexpr int EXTRA_WK_SKEWABS = EXTRAS_AFTER_KMOB + 1;  // |skew| of white men
inline constexpr int EXTRA_BK_HASKING = EXTRAS_AFTER_KMOB + 2;  // black has >=1 king
inline constexpr int EXTRA_WK_HASKING = EXTRAS_AFTER_KMOB + 3;  // white has >=1 king
inline constexpr int EXTRA_BK_EXTRAK  = EXTRAS_AFTER_KMOB + 4;  // black kings beyond the first
inline constexpr int EXTRA_WK_EXTRAK  = EXTRAS_AFTER_KMOB + 5;  // white kings beyond the first
inline constexpr int EXTRAS_AFTER_SCAN_PARITY = EXTRAS_AFTER_KMOB + 6;
#else
inline constexpr int EXTRAS_AFTER_SCAN_PARITY = EXTRAS_AFTER_KMOB;
#endif

// D1-RC4 experimental role-conditioned conversion terms.  They are present only
// in the isolated RC4 build and are zero unless the current position has exactly
// a two-man gap with equal king counts.  Each scalar is black-POV and therefore
// remains compatible with the existing colour-fold antisymmetry.
#ifdef JASS_ROLE_CONVERSION
inline constexpr int EXTRA_RC_SAFE_MOB_DELTA          = EXTRAS_AFTER_SCAN_PARITY + 0;
inline constexpr int EXTRA_RC_DEFENDER_CONFINEMENT    = EXTRAS_AFTER_SCAN_PARITY + 1;
inline constexpr int EXTRA_RC_PROMOTION_RACE_MARGIN   = EXTRAS_AFTER_SCAN_PARITY + 2;
inline constexpr int EXTRA_RC_TRADE_PRESSURE          = EXTRAS_AFTER_SCAN_PARITY + 3;
inline constexpr int NUM_EXTRAS = EXTRAS_AFTER_SCAN_PARITY + 4;
#else
inline constexpr int NUM_EXTRAS = EXTRAS_AFTER_SCAN_PARITY;
#endif
"""

CPP_HELPER_ANCHOR = """Bitboard man_attacks(Bitboard men, Bitboard empty) noexcept {
    return (shift_se(men) & shift_nw(empty))
         | (shift_sw(men) & shift_ne(empty))
         | (shift_ne(men) & shift_sw(empty))
         | (shift_nw(men) & shift_se(empty));
}
"""

CPP_HELPERS = CPP_HELPER_ANCHOR + r'''

#ifdef JASS_ROLE_CONVERSION
Bitboard man_quiet_destinations(Bitboard men, Color c, Bitboard empty) noexcept {
    if (c == Color::White)
        return (shift_nw(men) | shift_ne(men)) & empty;
    return (shift_sw(men) | shift_se(men)) & empty;
}

Bitboard safe_man_destinations(const Position& pos, Color c) noexcept {
    const Bitboard empty = pos.empties();
    const Bitboard enemy_men = c == Color::White ? pos.black_men() : pos.white_men();
    return man_quiet_destinations(pos.men_of(c), c, empty)
         & ~man_attacks(enemy_men, empty);
}

Bitboard movable_man_origins(Bitboard destinations, Color c) noexcept {
    if (c == Color::White)
        return shift_sw(destinations) | shift_se(destinations);
    return shift_nw(destinations) | shift_ne(destinations);
}

int safe_mobility_total(const Position& pos, Color c) noexcept {
    const Bitboard empty = pos.empties();
    const Bitboard enemy_men = c == Color::White ? pos.black_men() : pos.white_men();
    const Bitboard attacked = man_attacks(enemy_men, empty);
    const Bitboard man_dest = man_quiet_destinations(pos.men_of(c), c, empty) & ~attacked;
    const Bitboard king_dest = king_reach(pos.kings_of(c), empty) & ~attacked;
    return popcount(man_dest) + popcount(king_dest);
}

int blocked_men(const Position& pos, Color c) noexcept {
    const Bitboard men = pos.men_of(c);
    const Bitboard movable = movable_man_origins(safe_man_destinations(pos, c), c) & men;
    return popcount(men & ~movable);
}

int denied_king_squares(const Position& pos, Color c) noexcept {
    const Bitboard empty = pos.empties();
    const Bitboard enemy_men = c == Color::White ? pos.black_men() : pos.white_men();
    return popcount(king_reach(pos.kings_of(c), empty) & man_attacks(enemy_men, empty));
}

int best_safe_promotion_progress(const Position& pos, Color c) noexcept {
    Bitboard destinations = safe_man_destinations(pos, c);
    int best = 0;
    while (destinations) {
        const Square square = pop_lsb(destinations);
        const int row = row_of(square);
        const int progress = c == Color::Black ? row : 9 - row;
        if (progress > best) best = progress;
    }
    return best;
}

int capturable_targets_by_men(const Position& pos, Color c) noexcept {
    const Bitboard men = pos.men_of(c);
    const Bitboard enemy = c == Color::White ? pos.blacks() : pos.whites();
    const Bitboard empty = pos.empties();
    const Bitboard targets =
          (shift_nw(men) & enemy & shift_se(empty))
        | (shift_ne(men) & enemy & shift_sw(empty))
        | (shift_sw(men) & enemy & shift_ne(empty))
        | (shift_se(men) & enemy & shift_nw(empty));
    return popcount(targets);
}

// +1 = Black currently owns the exact +2-men role, -1 = White, 0 = outside.
int exact_two_man_role(const Position& pos) noexcept {
    const int black_kings = popcount(pos.black_kings());
    const int white_kings = popcount(pos.white_kings());
    if (black_kings != white_kings) return 0;
    const int black_men = popcount(pos.black_men());
    const int white_men = popcount(pos.white_men());
    if (black_men == white_men + 2) return 1;
    if (white_men == black_men + 2) return -1;
    return 0;
}
#endif
'''

CPP_FILL_ANCHOR = """#endif
    // NB: the 1st batch of structural extras (king-mob/back-rank/advancement,
"""

CPP_FILL = r'''#endif

#ifdef JASS_ROLE_CONVERSION
    const int role = exact_two_man_role(pos);
    if (role != 0) {
        const int black_safe = safe_mobility_total(pos, Color::Black);
        const int white_safe = safe_mobility_total(pos, Color::White);
        out[EXTRA_RC_SAFE_MOB_DELTA] = static_cast<float>(black_safe - white_safe);

        const int defender_confinement = role > 0
            ? denied_king_squares(pos, Color::White) + blocked_men(pos, Color::White)
            : -(denied_king_squares(pos, Color::Black) + blocked_men(pos, Color::Black));
        out[EXTRA_RC_DEFENDER_CONFINEMENT] = static_cast<float>(defender_confinement);

        const int black_promo = best_safe_promotion_progress(pos, Color::Black);
        const int white_promo = best_safe_promotion_progress(pos, Color::White);
        out[EXTRA_RC_PROMOTION_RACE_MARGIN] = static_cast<float>(black_promo - white_promo);

        const int black_trade = capturable_targets_by_men(pos, Color::Black);
        const int white_trade = capturable_targets_by_men(pos, Color::White);
        out[EXTRA_RC_TRADE_PRESSURE] = static_cast<float>(black_trade - white_trade);
    }
#endif
    // NB: the 1st batch of structural extras (king-mob/back-rank/advancement,
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    root = Path(args.source_root)
    header_path = root / "src/scan_eval.hpp"
    cpp_path = root / "src/scan_eval.cpp"
    header = header_path.read_text(encoding="utf-8")
    cpp = cpp_path.read_text(encoding="utf-8")
    before = {"src/scan_eval.hpp": digest(header), "src/scan_eval.cpp": digest(cpp)}

    header = replace_once(header, HEADER_OLD, HEADER_NEW, "scan_eval.hpp layout")
    cpp = replace_once(cpp, CPP_HELPER_ANCHOR, CPP_HELPERS, "scan_eval.cpp helpers")
    cpp = replace_once(cpp, CPP_FILL_ANCHOR, CPP_FILL, "scan_eval.cpp feature fill")

    if "EXTRA_RC_SAFE_MOB_DELTA" not in header or "exact_two_man_role" not in cpp:
        raise ValueError("RC4 patch postcondition failed")
    header_path.write_text(header, encoding="utf-8")
    cpp_path.write_text(cpp, encoding="utf-8")

    payload = {
        "schema": 1,
        "protocol": "d1-rc4-isolated-source-transform",
        "source_root": str(root),
        "before_sha256": before,
        "after_sha256": {
            "src/scan_eval.hpp": digest(header),
            "src/scan_eval.cpp": digest(cpp),
        },
        "compile_definition": "JASS_ROLE_CONVERSION=1",
        "extra_count_delta": 4,
        "domain": {"men_gap": 2, "equal_king_counts": True, "current_position": True},
        "features": [
            "safe_mobility_delta",
            "defender_confinement",
            "promotion_race_margin",
            "trade_pressure",
        ],
        "production_source_modified": False,
    }
    Path(args.report).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("RC4_PATCH_APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

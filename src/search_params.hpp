// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Tunable search parameters — Phase 1 (search avancé).
//
// All the pruning / reduction / extension magic numbers that used to live
// as function-local `constexpr` inside negamax are centralised here so an
// external tuner (SPSA) can perturb them and an A/B harness can compare
// two parameter sets in a single process. Defaults reproduce the exact
// pre-refactor behaviour, so `SearchParams{}` is behaviour-neutral.
//
// A parameter set can be loaded from a "k=v,k=v" string (used by the CLI
// A/B mode and the SPSA driver) or from the JASS_SEARCH_PARAMS env var.
#pragma once

#include <cstdlib>
#include <string>
#include <string_view>

namespace jass {

struct SearchParams {
    // Reverse futility pruning (RFP).
    int rfp_max_depth = 5;
    int rfp_margin    = 100;   // cp per remaining ply

    // Null-move pruning (NMP). R = nmp_r_base + depth / nmp_r_div.
    int nmp_min_depth  = 4;
    int nmp_min_pieces = 6;
    int nmp_r_base     = 2;
    int nmp_r_div      = 4;

    // Singular extension.
    int singular_min_depth = 8;
    int singular_margin    = 2;   // cp per ply of depth

    // Late move reductions (LMR). r = lmr_base + d/lmr_depth_div + idx/lmr_idx_div.
    int lmr_min_depth        = 3;
    int lmr_first_full_moves = 4;
    int lmr_base             = 1;
    int lmr_depth_div        = 6;
    int lmr_idx_div          = 8;

    // Late move pruning (LMP): first late-quiet index to skip at depth 1/2/3.
    int lmp_d1 = 4;
    int lmp_d2 = 8;
    int lmp_d3 = 14;

    // History aging (gated; 0 = legacy unbounded accumulation). When > 0 the
    // butterfly history (and conthist) is updated with a "gravity" rule
    // h += bonus - h*bonus/history_max instead of h += bonus, which CAPS the
    // table at ~history_max and decays large OLD cutoffs toward it — so stale
    // history stops dominating the quiet-move ordering. Standard technique
    // (~+5-15 Elo in chess). A/B before shipping (job 0269).
    int history_max = 0;

    // Aspiration window initial half-width (cp).
    int aspiration_initial = 50;

    // Principal Variation Search (zero-window scout on non-first moves).
    // Default ON since 2026-06-06: job 0135 measured +47 ELO at movetime
    // 0.3s and +39 ELO at fixed depth 9 vs use_pvs=0 on v15.
    bool use_pvs = true;

    // Razoring (gated; razor_max_depth = 0 disables). At shallow non-PV
    // quiet nodes, if static eval + razor_margin*depth <= alpha, drop to
    // quiescence; if qsearch confirms <= alpha, prune.
    int razor_max_depth = 0;     // 0 = off
    int razor_margin    = 200;   // cp per remaining ply

    // ProbCut (gated; probcut_min_depth = 0 disables). At high-depth
    // non-PV nodes, if a (forced) capture leads to a reduced-depth score
    // >= beta + probcut_margin, cut. NB draughts captures are forced, so
    // this only fires at tactical nodes — value uncertain, hence opt-in.
    int probcut_min_depth = 0;   // 0 = off
    int probcut_margin    = 150;
    int probcut_reduction = 4;

    // Promotion extension (gated). Extend by 1 ply when the move crowns a
    // man (Move::promotes) — these are sharp, tactically dense lines.
    bool ext_promotion = false;

    // --- 1b : raffinements search incrémentaux (gated, neutres par défaut) ---

    // Improving heuristic. Track the node's static eval and compare to the
    // same-side static eval 2 plies up : "improving" = the position is
    // getting better for us. When NOT improving we prune harder (LMP fires
    // earlier, LMR reduces one ply more). Pure modulation of existing knobs.
    // Enabled by default: job 0253 A/B (king-aware champion, mt0.2, 450 games)
    // measured +21.6 Elo [95% CI -10.5,+53.8] ON vs baseline — best of the gated
    // search features (conthist was -11, left off); consistent with the standard
    // +15-30 Elo. Not SPRT-significant at that budget, but a standard technique
    // with a positive, coherent signal; regressions would surface in the vs-Scan
    // validation. cf docs/ROADMAP.md.
    bool use_improving = true;

    // Continuation history. A second history table keyed by the opponent's
    // previous landing square × our move, accumulated like the main history
    // on beta cutoffs and added to the quiet-move ordering score. Captures
    // "after they go there, this reply is good" patterns the flat history
    // misses. ~+15-30 ELO typical.
    bool use_conthist = false;

    // Internal Iterative Deepening (gated; iid_min_depth = 0 disables). At a
    // deep node with no TT move, run a reduced-depth search first to populate
    // a move to order, instead of searching deep on a blind move order.
    int iid_min_depth = 0;    // 0 = off
    int iid_reduction = 2;

    // Multi-cut pruning (gated; multicut_min_depth = 0 disables). At a deep
    // non-PV quiet node, search the first `multicut_moves` moves at reduced
    // depth; if at least `multicut_cuts` of them fail high, the node almost
    // certainly fails high — cut. Speculative, hence opt-in.
    int multicut_min_depth = 0;   // 0 = off
    int multicut_reduction = 4;
    int multicut_moves     = 6;
    int multicut_cuts      = 3;

    // --- Time-management for the iterative-deepening loop (movetime only) ---
    // The "skip the next iteration" heuristic projects the next iteration's
    // cost as `last_iter * tm_next_iter_pct/100` and stops if even half of
    // that exceeds the remaining budget. These constants were set for the
    // NNUE's depth regime (~15-20); a fast eval reaches depth ~30+ where the
    // effective branching factor — hence the right projection factor — differs.
    // Defaults reproduce the previous behaviour (200% = 2×, from depth 5).
    int tm_next_iter_pct = 200;   // projected next-iter cost = last × this/100
    int tm_min_depth     = 5;     // don't extrapolate below this depth

    // Endgame search regime (gated; eg_pieces = 0 disables the whole thing).
    // Below `eg_pieces` total pieces (popcount of occupied, same phase axis as
    // pattern_jass --phase-weight) the listed pruning/reduction techniques are
    // turned OFF, trading a few nodes for accuracy where the engine is most
    // search-bound (job 0252) and most prone to discarding the one precise
    // winning line (zugzwang for NMP; sharp quiet wins for LMP/LMR).
    // Default = NMP OFF EVERYWHERE (eg_pieces=40 ≥ max 40 pieces). Sweep 0256/0259
    // (mt0.2) was monotone-increasing — disabling NMP below 12 = +29, below 36 =
    // +97 — and confirmation 0262 (mt0.5) gave thr40 = **+106 Elo** [CI +67,+146],
    // i.e. the gain GREW at the slower TC (NMP does not "catch up" at longer time —
    // it hurts more). Null-move pruning is net-negative in jass : draughts is
    // zugzwang-pervasive (you must move; being forced to is often bad) so NMP's
    // "passing is safe" premise fails throughout the game, plus mandatory captures
    // make tempo sharp. eg_no_lmr was -13 (LMR buys the depth the search-bound
    // endgame needs → kept ON) and eg_no_lmp ~0 (kept ON). eg_pieces=0 disables
    // the whole regime (true no-op : popcount short-circuited).
    int  eg_pieces  = 40;         // 0 = off ; else popcount threshold (<=). 40 = always.
    bool eg_no_nmp  = true;       // disable null-move pruning in the endgame regime
    bool eg_no_lmp  = false;      // disable late-move pruning in the endgame regime
    bool eg_no_lmr  = false;      // disable late-move reductions in the endgame regime
};

// Apply a single "key=value" assignment to `p`. Unknown keys are ignored
// (so a tuner can stay forward-compatible). Returns false only on a
// malformed token (no '=').
inline bool apply_search_param(SearchParams& p, std::string_view tok) {
    const auto eq = tok.find('=');
    if (eq == std::string_view::npos) return false;
    const std::string key{tok.substr(0, eq)};
    const std::string val{tok.substr(eq + 1)};
    const int v = std::atoi(val.c_str());
    if      (key == "rfp_max_depth")        p.rfp_max_depth        = v;
    else if (key == "rfp_margin")           p.rfp_margin           = v;
    else if (key == "nmp_min_depth")        p.nmp_min_depth        = v;
    else if (key == "nmp_min_pieces")       p.nmp_min_pieces       = v;
    else if (key == "nmp_r_base")           p.nmp_r_base           = v;
    else if (key == "nmp_r_div")            p.nmp_r_div            = v;
    else if (key == "singular_min_depth")   p.singular_min_depth   = v;
    else if (key == "singular_margin")      p.singular_margin      = v;
    else if (key == "lmr_min_depth")        p.lmr_min_depth        = v;
    else if (key == "lmr_first_full_moves") p.lmr_first_full_moves = v;
    else if (key == "lmr_base")             p.lmr_base             = v;
    else if (key == "lmr_depth_div")        p.lmr_depth_div        = v;
    else if (key == "lmr_idx_div")          p.lmr_idx_div          = v;
    else if (key == "lmp_d1")               p.lmp_d1               = v;
    else if (key == "lmp_d2")               p.lmp_d2               = v;
    else if (key == "lmp_d3")               p.lmp_d3               = v;
    else if (key == "history_max")          p.history_max          = v;
    else if (key == "aspiration_initial")   p.aspiration_initial   = v;
    else if (key == "use_pvs")              p.use_pvs              = (v != 0);
    else if (key == "razor_max_depth")      p.razor_max_depth      = v;
    else if (key == "razor_margin")         p.razor_margin         = v;
    else if (key == "probcut_min_depth")    p.probcut_min_depth    = v;
    else if (key == "probcut_margin")       p.probcut_margin       = v;
    else if (key == "probcut_reduction")    p.probcut_reduction    = v;
    else if (key == "ext_promotion")        p.ext_promotion        = (v != 0);
    else if (key == "use_improving")        p.use_improving        = (v != 0);
    else if (key == "use_conthist")         p.use_conthist         = (v != 0);
    else if (key == "iid_min_depth")        p.iid_min_depth        = v;
    else if (key == "iid_reduction")        p.iid_reduction        = v;
    else if (key == "multicut_min_depth")   p.multicut_min_depth   = v;
    else if (key == "multicut_reduction")   p.multicut_reduction   = v;
    else if (key == "multicut_moves")       p.multicut_moves       = v;
    else if (key == "multicut_cuts")        p.multicut_cuts        = v;
    else if (key == "tm_next_iter_pct")     p.tm_next_iter_pct     = v;
    else if (key == "tm_min_depth")         p.tm_min_depth         = v;
    else if (key == "eg_pieces")            p.eg_pieces            = v;
    else if (key == "eg_no_nmp")            p.eg_no_nmp            = (v != 0);
    else if (key == "eg_no_lmp")            p.eg_no_lmp            = (v != 0);
    else if (key == "eg_no_lmr")            p.eg_no_lmr            = (v != 0);
    // unknown key → silently ignored
    return true;
}

// Parse a full "k=v,k=v,…" spec on top of `base` (defaults to current
// behaviour). Empty / whitespace tokens are skipped.
inline SearchParams parse_search_params(std::string_view spec,
                                        SearchParams base = SearchParams{}) {
    std::size_t i = 0;
    while (i < spec.size()) {
        std::size_t j = spec.find(',', i);
        if (j == std::string_view::npos) j = spec.size();
        std::string_view tok = spec.substr(i, j - i);
        // trim spaces
        while (!tok.empty() && tok.front() == ' ') tok.remove_prefix(1);
        while (!tok.empty() && tok.back()  == ' ') tok.remove_suffix(1);
        if (!tok.empty()) apply_search_param(base, tok);
        i = j + 1;
    }
    return base;
}

// Load overrides from the JASS_SEARCH_PARAMS env var (empty if unset).
inline SearchParams search_params_from_env() {
    const char* env = std::getenv("JASS_SEARCH_PARAMS");
    if (env == nullptr || env[0] == '\0') return SearchParams{};
    return parse_search_params(env);
}

}  // namespace jass

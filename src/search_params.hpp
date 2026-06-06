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
    else if (key == "aspiration_initial")   p.aspiration_initial   = v;
    else if (key == "use_pvs")              p.use_pvs              = (v != 0);
    else if (key == "razor_max_depth")      p.razor_max_depth      = v;
    else if (key == "razor_margin")         p.razor_margin         = v;
    else if (key == "probcut_min_depth")    p.probcut_min_depth    = v;
    else if (key == "probcut_margin")       p.probcut_margin       = v;
    else if (key == "probcut_reduction")    p.probcut_reduction    = v;
    else if (key == "ext_promotion")        p.ext_promotion        = (v != 0);
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

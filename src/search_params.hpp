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
    // lmr_base=0 (was 1) : job 0268 measured +41.9 Elo [CI +9.6,+74.2] for LESS
    // LMR — jass prefers conservative search (zugzwang), like NMP-off. (More
    // aggressive LMR/LMP/RFP all hurt, 0264; less LMP / time-mgmt also hurt, 0268.)
    int lmr_min_depth        = 3;
    int lmr_first_full_moves = 4;
    int lmr_first_full_pv    = 4;   // LMR pv/non-pv asymmetry (Scan : non-PV réduit dès le 2e coup,
    int lmr_first_full_nonpv = 2;   // PV dès le 4e). Réduit le 1er coup d'index >= ce seuil. Les deux=4 => uniforme legacy.
                                    // BAKÉ 2 (2026-07-04, 0562) : composante du coin EBF corner+nmp = +49 Elo movetime sur gen1.
    int lmr_base             = 0;
    int lmr_depth_div        = 6;
    int lmr_idx_div          = 8;
    // History-based LMR (opt-in ; 0 = OFF = legacy). When > 0, the reduction is
    // softened for high-history quiet moves: r -= history / lmr_hist_div (then
    // clamped to >= 0). Reduces good moves less, bad moves at the base rate — a
    // standard tree-shrinker. history_max=16384 → div ~4000-8000 ≈ up to ~2-4 plies.
    int lmr_hist_div         = 0;

    // Logarithmic LMR shape (opt-in ; lmr_formula=0 = linear = legacy default,
    // BYTE-IDENTICAL). When lmr_formula=1 the base reduction is Stockfish-like :
    //   R = lmr_log_base + log(d)*log(move_idx) * lmr_log_mul/100
    // softer at shallow depth / early moves, more aggressive for late moves at
    // high depth → attacks the effective branching factor (EBF) where the tree
    // is most expensive. improving/clamp/history-softening applied AFTER, as for
    // the linear path. lmr_log_mul is the coefficient ×100 (40 = 0.40 ≈ /2.5).
    // EBF chantier 2026-06-29 (memo JFC) — ⚠️ A/B vs 0264/0268 (jass a GAGNÉ +Elo
    // en réduisant MOINS) : décider à TEMPS FIXE + 0 régression Elo.
    int lmr_formula  = 0;     // 0=linear ; 1=log ; 2=Box-Cox ; 3=frozen Scan 3.1 diagnostic
    int lmr_log_base = 0;     // additive base offset for the log formula
    int lmr_log_mul  = 40;    // R coefficient ×100 (40 = 0.40 ≈ divide by 2.5)
    int lmr_bc_ld    = 100;   // Box-Cox (lmr_formula=2) DEPTH exponent ×100 (100=λ1, 50=√, 0=log, <0=récip)
    int lmr_bc_lidx  = 100;   // Box-Cox INDEX exponent ×100

    // Late move pruning (LMP): first late-quiet index to skip at depth 1/2/3.
    int lmp_d1 = 4;
    int lmp_d2 = 8;
    int lmp_d3 = 14;
    // LMP applies for depth <= lmp_max_depth. Default 3 = legacy (only d1/d2/d3).
    // For depths 4..lmp_max_depth the threshold follows a quadratic move-count
    // tail (2 + d + d*d) that continues the d1/d2/d3 trend exactly (4,8,14,22,32…).
    // Deepening LMP is a depth-buyer the old fixed-DEPTH tuning under-valued (0333+).
    int lmp_max_depth = 3;

    // History aging (gated; 0 = legacy unbounded accumulation). When > 0 the
    // butterfly history (and conthist) is updated with a "gravity" rule
    // h += bonus - h*bonus/history_max instead of h += bonus, which CAPS the
    // table at ~history_max and decays large OLD cutoffs toward it — so stale
    // history stops dominating the quiet-move ordering. Default 16384 : job 0269
    // A/B measured +20.9 Elo [CI -11,+53] (best of 8k/16k/32k; 8k/32k were
    // negative). Consistent with the "jass prefers conservative search" theme.
    int history_max = 16384;

    // History malus (opt-in ; 0 = OFF = legacy). On a quiet beta-cutoff, the
    // quiet moves that were tried BEFORE the cutoff move (and failed) get a
    // malus = depth*depth * hist_malus/100 subtracted from their history — so
    // moves that consistently fail sink in the ordering. Standard tree-sharpener
    // (more cutoffs → smaller tree). 100 = malus equal to the bonus magnitude.
    int hist_malus = 0;

    // ---- Probabilistic history ordering (port de Scan sort.cpp ; 0=legacy=byte-identical) ----
    // hist_mode=1 : la table history[from][to] devient une EMA de P(coup bon) dans [0,PROB_ONE),
    //   init a PROB_HALF (2048), good: h += (4096-h)>>prob_shift, bad: h -= h>>prob_shift. Mise a jour
    //   BIDIRECTIONNELLE sur score>alpha_orig (le best_move final) + malus sur TOUS les coups essayes-avant.
    //   Estimateur adaptatif qui oublie vite (contre l'additif depth^2 non borne du legacy).
    int hist_mode  = 1;    // BAKÉ 1 (2026-07-05, 0600 : P1nc +20..+43 Elo movetime hors-IC dilf+généraliste). 0=legacy (additif) ; 1=prob (EMA Scan)
    int prob_shift = 5;    // vitesse EMA (Scan=5 ; balayable 4-6)
    int hist_pure  = 1;    // BAKÉ 1 (2026-07-05, 0600) : EMA prob SEULE (sans killers/CM/conthist au scoring) bat la machinerie complete. (P1) 0=legacy
    int hist_order_captures = 0;  // (E3) 1 => trier AUSSI les captures par history (au lieu de l'ordre de generation)

    // Aspiration window initial half-width (cp).
    int aspiration_initial = 50;

    // Principal Variation Search (zero-window scout on non-first moves).
    // Default ON since 2026-06-06: job 0135 measured +47 ELO at movetime
    // 0.3s and +39 ELO at fixed depth 9 vs use_pvs=0 on v15.
    bool use_pvs = true;

    // Razoring (gated; razor_max_depth = 0 disables). At shallow non-PV
    // quiet nodes, if static eval + razor_margin*depth <= alpha, drop to
    // quiescence; if qsearch confirms <= alpha, prune.
    int razor_max_depth = 4;     // 0 = off ; ON=4 depuis 0336 (combo recherche, +Elo à temps fixe)
    int razor_margin    = 200;   // cp per remaining ply

    // ProbCut (gated; probcut_min_depth = 0 disables). At high-depth
    // non-PV nodes, if a (forced) capture leads to a reduced-depth score
    // >= beta + probcut_margin, cut. NB draughts captures are forced, so
    // this only fires at tactical nodes — value uncertain, hence opt-in.
    int probcut_min_depth = 5;   // 0 = off ; BAKÉ 5 (2026-07-04, 0562, coin corner+nmp +49 Elo movetime gen1)
    int probcut_margin    = 150;
    int probcut_reduction = 4;

    // Promotion extension (gated). Extend by 1 ply when the move crowns a
    // man (Move::promotes) — these are sharp, tactically dense lines.
    bool ext_promotion = false;

    // Forcing extension (gated, default off). Extend by 1 ply any QUIET move
    // that leaves the opponent only captures (a sacrifice / combination
    // starter — FMJD majority rule makes the reply forced). Makes a
    // sac->capture->regain line resolve to full effective depth regardless of
    // the nominal horizon, so fixed-depth tactics (jauge 0440) are not cut by
    // the leaf. DISTINCT from no_reduce_forcing (which only skips LMR/LMP);
    // this ADDS depth, and also implies the no-reduce/no-LMP exemption for the
    // extended move so the extension is not defeated by pruning. Untested
    // lever (0436/0451 isolated pruning/non-reduction, NEVER an extension).
    bool ext_forcing = false;
    // Anti-explosion cap for ext_forcing : max TOTAL extensions accumulated on a
    // single search path (forcing-ext SPEC §3.1 garde-fou). 0 = no cap (only the
    // MAX_PLY backstop). When >0, a forcing extension is skipped once the path has
    // already accumulated this many extensions, bounding the cost of pathological
    // ultra-forcing positions.
    int forcing_ext_cap = 0;
    // Single-reply extension (Scan) : un nœud à EXACTEMENT 1 coup légal est cherché +1 ply
    // (branchement=1 => GRATUIT en largeur). Version ÉTROITE de ext_forcing (qui est large/cher). default off.
    bool ext_single_reply = false;

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
    // validation. cf docs/archives/ROADMAP.md.
    bool use_improving = true;

    // Continuation history. A second history table keyed by the opponent's
    // previous landing square × our move, accumulated like the main history
    // on beta cutoffs and added to the quiet-move ordering score. Captures
    // "after they go there, this reply is good" patterns the flat history
    // misses. ~+15-30 ELO typical.
    bool use_conthist = true;   // baké 2026-06-30 : -9% noeuds @d12 (node-EBF exact 0507) + Elo-neutre (0505/0508 n=610)

    // Internal Iterative Deepening (gated; iid_min_depth = 0 disables). At a
    // deep node with no TT move, run a reduced-depth search first to populate
    // a move to order, instead of searching deep on a blind move order.
    int iid_min_depth = 0;    // 0 = off
    int iid_reduction = 2;

    // Forcing-move exemption (gated; 0 = off = legacy byte-identical). When 1,
    // a QUIET move that leaves the opponent with ONLY captures (a sacrifice /
    // combination starter — by FMJD rule the reply is forced) is exempted from
    // LMR reduction and LMP pruning. Ablation 0446 showed LMR (27%) + LMP (26%)
    // are the mechanisms that hide book combinations from jass at fixed depth ;
    // this un-reduces exactly the forcing lines they were cutting, without
    // touching speed elsewhere. Costs one extra movegen per would-be-reduced
    // late quiet move (only when this is on).
    int no_reduce_forcing = 0;   // 0 = off ; 1 = don't reduce/prune forcing quiets

    // Forcing QUIESCENCE (gated; qs_forcing_depth = 0 disables). Standard
    // quiescence only plays out mandatory CAPTURE chains, so a combination whose
    // SACRIFICE (a quiet, material-losing move that leaves the opponent with only
    // forced captures) falls at/below the horizon is invisible — qsearch returns
    // the static eval without ever trying the sac. This lets the calm-leaf qsearch
    // ALSO try such forcing sacs (bounded to this many consecutive sac plies), so a
    // shot resolves at the horizon regardless of the main search depth. The forced
    // reply keeps the tree narrow → cheap. 0 = off (byte-identical : plain static leaf).
    int qs_forcing_depth = 0;

    // Promotion QUIESCENCE (gated; qs_promo_depth = 0 disables). Companion to
    // forcing quiescence for POSITIONAL sacrifices whose payoff is a PROMOTION a
    // few quiet moves after the forced captures resolve: a static leaf shows a man
    // still one/two rows short of the crown (undervalued) instead of the king it
    // is about to become. When > 0, at a calm leaf we also follow quiet MAN
    // advances that promote now OR land within qs_promo_depth rows of the promotion
    // row (men only move forward → every quiet man move is progress), bounded to
    // this many consecutive promo plies, so the king materialises in the qsearch
    // line and the eval sees its value. 0 = off (byte-identical).
    int qs_promo_depth = 0;

    // Threat EXTENSION in quiescence (gated; false = off = byte-identical). Ported
    // from Scan (src/search.cpp::qs) : at the FIRST quiescence ply, if the position
    // is calm for us but the OPPONENT has a capture available (is_threat = we are
    // under threat of being captured), the static eval is unreliable (a shot is
    // looming) — so run a 1-ply search instead of standing pat, resolving the threat.
    // Cheap (1 ply, gated on being under threat), low blow-up risk.
    // BAKED ON (2026-07-03, JFC) : complete l'architecture quiescence de Scan (qs_sacs +
    // threat-ext ENSEMBLE, comme Scan en prod). L'A/B 0554 (detection + node-EBF + Elo)
    // sert de verification a posteriori.
    // CONFIRME AU JEU (2026-07-04, 0565) : sur le defaut coin corner+nmp, threat_ext=1 vs =0
    // => +108 Elo movetime (IC [0.627,0.674], 1220 games). Co-adaptation : coutait -21 a l'ancien
    // defaut (0554), paie +108 une fois l'EBF reduit par le coin (budget noeuds libere). Defaut ON confirme.
    bool qs_threat_ext = true;

    // Selective SAC quiescence (gated; false = off = byte-identical). Ported from
    // Scan (src/gen.cpp::add_sacs, via src/scan_sacs.cpp — validated bit-for-bit).
    // At a calm leaf, after the stand-pat, generate Scan's SELECTIVE sacrifices (a
    // handful of positionally-gated man sacs, NOT all forcing sacs) and search them.
    // Gated exactly like Scan : only for a men-only board (no king anywhere) and
    // when NOT under threat (the threat case is covered by qs_threat_ext). The
    // selectivity is the point — a naive "all sacs" quiescence explodes the tree.
    // BAKED ON (2026-07-02) : verdict détection combos 0.58->0.67 (d11) et 0.61->0.65
    // (movetime 0.3s, transfère), node-EBF borné ~1.19x médian (vs 5-10x du forcing naïf).
    bool qs_sacs = true;
    // Explosion guard : generate sacs only at the FIRST quiescence ply (default).
    // Scan itself recurses sacs, but bounded ; we start conservative and relax only
    // once node-EBF confirms it stays flat.
    bool qs_sacs_depth0_only = true;


    // Multi-cut pruning (gated; multicut_min_depth = 0 disables). At a deep
    // non-PV quiet node, search the first `multicut_moves` moves at reduced
    // depth; if at least `multicut_cuts` of them fail high, the node almost
    // certainly fails high — cut. Speculative, hence opt-in.
    int multicut_min_depth = 4;   // 0 = off ; BAKÉ 4 (2026-07-04, 0562, coin corner+nmp +49 Elo movetime gen1 ; était 6 depuis 0336)
    int multicut_reduction = 4;
    int multicut_moves     = 8;   // 8 (was 6) — 0335 mc_easy = plus gros gain du sweep
    int multicut_cuts      = 2;   // 2 (was 3) — déclenchement plus facile (0335/0336)

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
    bool eg_no_nmp  = false;      // disable null-move pruning in the endgame regime
                                  // BAKÉ false (2026-07-04, 0562) : NMP réactivé en finale (sound via F1 !tactical), coin corner+nmp +49 Elo movetime gen1.
    bool eg_no_lmp  = false;      // disable late-move pruning in the endgame regime
    bool eg_no_lmr  = false;      // disable late-move reductions in the endgame regime

    // Drawish-material scaling on the network leaf (Scan's one non-linearity).
    // 0 = off (default). 1 = apply ÷8/÷2 toward draw in won-but-drawish endgames.
    // The eval gap vs Scan is localized in the finale (0349) — this is candidate #1.
    int  drawish_scaling = 0;

    // Frozen Scan 3.1 verification pruning (diagnostic, default off).
    // At a non-PV node of depth >= 3, Scan searches the SAME position at
    // 40% depth with a beta margin of 10 * depth.  A verified fail-high
    // returns score-margin.  The constants are deliberately fixed so this
    // switch tests one source-identical mechanism rather than opening a new
    // tuning surface.
    bool scan_verify_pruning = false;

    // Frozen Scan 3.1 threat-node semantics (diagnostic, default off).
    // At the first quiet qsearch ply under threat, Scan re-enters the main
    // search on the SAME position at depth 1 and ply+1.  The historical
    // qs_threat_ext path emulates the line inside quiescence; this switch
    // tests Scan's exact node/window/TT semantics.
    bool scan_threat_reentry = false;

    // Frozen Scan 3.1 causal-attribution switches.  These are deliberately
    // boolean and default-off: each names one source-derived semantic arm and
    // introduces no tunable margin, threshold or sweep surface.
    bool scan_lmr_semantics = false;
    bool scan_probabilistic_ordering = false;
    bool disable_null_move = false;
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
    else if (key == "lmr_first_full_pv")    p.lmr_first_full_pv    = v;
    else if (key == "lmr_first_full_nonpv") p.lmr_first_full_nonpv = v;
    else if (key == "lmr_base")             p.lmr_base             = v;
    else if (key == "lmr_depth_div")        p.lmr_depth_div        = v;
    else if (key == "lmr_idx_div")          p.lmr_idx_div          = v;
    else if (key == "lmr_hist_div")         p.lmr_hist_div         = v;
    else if (key == "lmr_formula")          p.lmr_formula          = v;
    else if (key == "lmr_log_base")         p.lmr_log_base         = v;
    else if (key == "lmr_log_mul")          p.lmr_log_mul          = v;
    else if (key == "lmr_bc_ld")            p.lmr_bc_ld            = v;
    else if (key == "lmr_bc_lidx")          p.lmr_bc_lidx          = v;
    else if (key == "lmp_d1")               p.lmp_d1               = v;
    else if (key == "lmp_d2")               p.lmp_d2               = v;
    else if (key == "lmp_d3")               p.lmp_d3               = v;
    else if (key == "lmp_max_depth")        p.lmp_max_depth        = v;
    else if (key == "history_max")          p.history_max          = v;
    else if (key == "hist_malus")           p.hist_malus           = v;
    else if (key == "hist_mode")            p.hist_mode            = v;
    else if (key == "prob_shift")           p.prob_shift           = v;
    else if (key == "hist_pure")            p.hist_pure            = v;
    else if (key == "hist_order_captures")  p.hist_order_captures  = v;
    else if (key == "aspiration_initial")   p.aspiration_initial   = v;
    else if (key == "use_pvs")              p.use_pvs              = (v != 0);
    else if (key == "razor_max_depth")      p.razor_max_depth      = v;
    else if (key == "razor_margin")         p.razor_margin         = v;
    else if (key == "probcut_min_depth")    p.probcut_min_depth    = v;
    else if (key == "probcut_margin")       p.probcut_margin       = v;
    else if (key == "probcut_reduction")    p.probcut_reduction    = v;
    else if (key == "ext_promotion")        p.ext_promotion        = (v != 0);
    else if (key == "ext_forcing")          p.ext_forcing          = (v != 0);
    else if (key == "forcing_ext_cap")      p.forcing_ext_cap      = v;
    else if (key == "ext_single_reply")     p.ext_single_reply     = (v != 0);
    else if (key == "use_improving")        p.use_improving        = (v != 0);
    else if (key == "use_conthist")         p.use_conthist         = (v != 0);
    else if (key == "iid_min_depth")        p.iid_min_depth        = v;
    else if (key == "iid_reduction")        p.iid_reduction        = v;
    else if (key == "no_reduce_forcing")    p.no_reduce_forcing    = v;
    else if (key == "qs_forcing_depth")     p.qs_forcing_depth     = v;
    else if (key == "qs_promo_depth")       p.qs_promo_depth       = v;
    else if (key == "qs_threat_ext")        p.qs_threat_ext        = (v != 0);
    else if (key == "qs_sacs")              p.qs_sacs              = (v != 0);
    else if (key == "qs_sacs_depth0_only")  p.qs_sacs_depth0_only  = (v != 0);
    else if (key == "multicut_min_depth")   p.multicut_min_depth   = v;
    else if (key == "multicut_reduction")   p.multicut_reduction   = v;
    else if (key == "multicut_moves")       p.multicut_moves       = v;
    else if (key == "multicut_cuts")        p.multicut_cuts        = v;
    else if (key == "tm_next_iter_pct")     p.tm_next_iter_pct     = v;
    else if (key == "tm_min_depth")         p.tm_min_depth         = v;
    else if (key == "drawish_scaling")      p.drawish_scaling      = v;
    else if (key == "eg_pieces")            p.eg_pieces            = v;
    else if (key == "eg_no_nmp")            p.eg_no_nmp            = (v != 0);
    else if (key == "eg_no_lmp")            p.eg_no_lmp            = (v != 0);
    else if (key == "eg_no_lmr")            p.eg_no_lmr            = (v != 0);
    else if (key == "scan_verify_pruning")   p.scan_verify_pruning   = (v != 0);
    else if (key == "scan_threat_reentry")   p.scan_threat_reentry   = (v != 0);
    else if (key == "scan_lmr_semantics")    p.scan_lmr_semantics    = (v != 0);
    else if (key == "scan_probabilistic_ordering")
                                                p.scan_probabilistic_ordering = (v != 0);
    else if (key == "disable_null_move")     p.disable_null_move     = (v != 0);
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

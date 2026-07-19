#!/usr/bin/env bash
# id: ccx33-l3-imbalance2-role-v2-scan-gate
# description: ccx33 plateau-only Gen2 lower / Scan upper final gate
# expected_duration: pending ccx33 calibration; forbidden before approved plateau
set -Eeuo pipefail
: "${EXPECTED_CODE_SHA:?set merged jass SHA}"
: "${CANDIDATE_MODEL_URI:?set immutable plateau candidate URI/path}"
: "${CANDIDATE_MODEL_SHA256:?set candidate gzip SHA256}"
: "${PLATEAU_REPORT_URI:?set immutable plateau report URI/path}"
: "${PLATEAU_REPORT_SHA256:?set plateau report SHA256}"
export FULL_RUN_APPROVED=1 SCIENTIFIC_GO=1 PLATEAU_APPROVED=1
export SCAN_BIN="${SCAN_BIN:-/root/jass-scan/scan_linux}"
export DEPTH=10 NSHARDS=8 PAR=8 MAXPLIES=400 BENCH_PER_STRATUM=24 BASE_SEED=271828
export JASS_BUILD_JOBS=8
export SEARCH_PARAMS="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"
exec bash jobs/templates/l3-imbalance2-scan-gate-v1.sh
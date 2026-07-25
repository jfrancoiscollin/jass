#!/usr/bin/env bash
# Symmetric repaired-engine benchmark: L3-PURE champion F2M vs Gen2-mmto.
# Same code semantics on both sides; only geometry and weights differ.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${M1_PREFIX:?}"; : "${CONFIRMATION_PREFIX:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; IN="$JASS_RESULT_DIR/inputs"
mkdir -p "$W" "$ART" "$IN" "$ART/force"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/stage.txt"
: > "$RES"; echo preflight > "$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "stage=$1"; }
MON=""
monitor(){
  (while true; do
    { date -Is; printf 'stage=%s\n' "$(cat "$STAGE")"; } > "$PROG.tmp"
    mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 60
  done) & MON="$!"
}
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || kill "$MON" 2>/dev/null
  cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -name '*.log' -type f -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build8" "$W/build32" "$IN"
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM

NOPEN=500; NSH_GATE=16; PAR_GATE=8
FORCE_DEPTH=9; MOVETIME=0.1; CACHE_MB=128; OPENING_SEED=223607
F2M_SHA="be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2"
GEN2_GZ_SHA="01cc3ea59e9cc3ced1910d4d9054f88f92c1c4d9d220d5f28b0ebaaad33681a0"
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
[ "$(nproc)" -ge 16 ] || die "HOME requires 16 logical CPUs"
[ "$(tr ',' '\n' <<<"$Q00"|wc -l)" -eq 63 ] || die "Q00 drift"
monitor

stage fetch-and-verify-champions
python3 jobs/tools/fetch_result_files.py --prefix "$CONFIRMATION_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=f2m-confirmation.json \
  --out-dir "$IN" --report "$ART/verified-f2m-confirmation.json" \
  > "$W/fetch-confirmation.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$M1_PREFIX" \
  --file artefacts/f2m.pjtw.gz=f2m.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-f2m.json" > "$W/fetch-f2m.log" 2>&1
python3 jobs/tools/fetch_t1bis_inputs.py --out-dir "$IN" \
  --report "$ART/verified-fixed-inputs.json" > "$W/fetch-gen2.log" 2>&1
[ "$(sha256sum "$IN/gen2.pjtw.gz"|awk '{print $1}')" = "$GEN2_GZ_SHA" ] ||
  die "Gen2 gzip hash drift"
gunzip -c "$IN/f2m.pjtw.gz" > "$W/F2M.pjtw"
gunzip -c "$IN/gen2.pjtw.gz" > "$W/GEN2.pjtw"
[ "$(sha256sum "$W/F2M.pjtw"|awk '{print $1}')" = "$F2M_SHA" ] ||
  die "F2M hash drift"
python3 - "$IN/f2m-confirmation.json" "$ART/verified-fixed-inputs.json" <<'PY'
import json,sys
confirmation,fixed=(json.load(open(p)) for p in sys.argv[1:])
if confirmation.get("verdict")!="F2M_CONFIRMED_FOR_HUMAN_PROMOTION_REVIEW":
    raise SystemExit("F2M confirmation verdict mismatch")
if confirmation.get("selected_generalist_candidate")!="F2M":
    raise SystemExit("F2M is not confirmed")
objects={item["role"]:item for item in fixed.get("objects",[])}
gen2=objects.get("gen2_pattern",{})
if gen2.get("sha256")!="01cc3ea59e9cc3ced1910d4d9054f88f92c1c4d9d220d5f28b0ebaaad33681a0":
    raise SystemExit("Gen2 immutable source mismatch")
PY

stage build-repaired-8cf
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
EGDIR=""
for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cmake -S . -B "$W/build8" $FLAGS > "$W/cmake8.log" 2>&1
cmake --build "$W/build8" -j4 --target jass jass_tests > "$W/build8.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB \
  ctest --test-dir "$W/build8" --output-on-failure > "$W/ctest8.log" 2>&1
J8="$W/build8/jass"

stage build-repaired-32cf
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 > "$W/gen32.log" 2>&1
cmake -S . -B "$W/build32" $FLAGS > "$W/cmake32.log" 2>&1
cmake --build "$W/build32" -j4 --target jass > "$W/build32.log" 2>&1
J32="$W/build32/jass"
for jass in "$J8" "$J32"; do
  [ "$("$jass" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
    die "king-capture dedup witness failed"
  [ "$("$jass" --perft 1 'B:W13,23,25:B6,14,24,K45' | awk '{print $3}')" = 2 ] ||
    die "tablebase-root witness failed"
done
python3 - "$ART/engine-symmetry.json" "$EXPECTED_CODE_SHA" \
  "$(sha256sum "$J8"|awk '{print $1}')" \
  "$(sha256sum "$J32"|awk '{print $1}')" <<'PY'
import json,sys
from pathlib import Path
out,code,j8,j32=sys.argv[1:]
Path(out).write_text(json.dumps({
 "schema":1,"code_sha_both_sides":code,"candidate_geometry":"8cf",
 "incumbent_geometry":"32cf","candidate_binary_sha256":j8,
 "incumbent_binary_sha256":j32,"same_repaired_engine_semantics":True
},indent=2,sort_keys=True)+"\n")
PY

stage independent-opening-pool
for spec in \
  "prior-reinforcement:768:271828" \
  "prior-meta-screen:128:161803" \
  "prior-meta-confirm:256:141421" \
  "prior-f2m-confirm:500:173205"; do
  name="${spec%%:*}"; rest="${spec#*:}"; count="${rest%%:*}"; seed="${rest#*:}"
  "$J8" --gen-opening-pool "$count" "$W/$name.fen" 8 32 20 "$seed" \
    > "$W/open-$name.log" 2>&1
done
"$J8" --gen-opening-pool "$NOPEN" "$W/open-benchmark.fen" 8 32 20 "$OPENING_SEED" \
  > "$W/open-benchmark.log" 2>&1
python3 jobs/tools/validate_opening_pool.py \
  --pool "$W/open-benchmark.fen" --expected "$NOPEN" \
  --exclude data/dilf_combinations.fen \
  --exclude "$W/prior-reinforcement.fen" \
  --exclude "$W/prior-meta-screen.fen" \
  --exclude "$W/prior-meta-confirm.fen" \
  --exclude "$W/prior-f2m-confirm.fen" \
  --generator-seed "$OPENING_SEED" \
  --out "$ART/independent-openings-manifest.json" \
  > "$W/validate-openings.log" 2>&1
sha256sum "$W/open-benchmark.fen" > "$ART/independent-openings.sha256"

run_gate(){
  local view="$1"; local args=()
  [ "$view" = q00 ] && args=(--depth "$FORCE_DEPTH") ||
    args=(--movetime "$MOVETIME")
  timeout 21600 python3 jobs/tools/run_jass_gate_bounded.py \
    --jass-a "$J8" --jass-b "$J32" \
    --pattern-a "$W/F2M.pjtw" --pattern-b "$W/GEN2.pjtw" \
    --search-params-a "$Q00" --search-params-b "$Q00" \
    --openings-file "$W/open-benchmark.fen" "${args[@]}" --pairs 1 \
    --max-plies 160 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
    --timeout 10800 --game-timeout 180 \
    --work-dir "$W/gate-$view-F2M-GEN2" \
    --out "$ART/force/force-$view-F2M-vs-GEN2.json" \
    > "$W/force-$view-F2M-GEN2.log" 2>&1
}

stage repaired-symmetric-q00
run_gate q00
stage repaired-symmetric-native
run_gate native

stage aggregate-human-review
python3 jobs/tools/l3_f2m_gen2_repaired_benchmark.py \
  --confirmation "$IN/f2m-confirmation.json" \
  --force-dir "$ART/force" \
  --opening-manifest "$ART/independent-openings-manifest.json" \
  --engine-code-sha "$EXPECTED_CODE_SHA" \
  --out "$ART/f2m-gen2-repaired-benchmark.json" \
  --summary-out "$ART/JASS_CONTROL_SUMMARY.json" > "$W/aggregate.log" 2>&1
VERDICT="$(python3 - "$ART/f2m-gen2-repaired-benchmark.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["verdict"])
PY
)"
printf '%s\n' "$VERDICT" > "$ART/VERDICT__$VERDICT"
printf '%s\n' GENERAL_CHAMPION_PROMOTION_AUTHORIZED__FALSE \
  > "$ART/GENERAL_CHAMPION_PROMOTION_AUTHORIZED__FALSE"
printf '%s\n' M2_LAUNCH_AUTHORIZED__FALSE \
  > "$ART/M2_LAUNCH_AUTHORIZED__FALSE"
printf '%s\n' AUTOMATIC_NEXT_JOB__NULL \
  > "$ART/AUTOMATIC_NEXT_JOB__NULL"
stage complete
say "$VERDICT general_promotion=false m2_launch=false"

#!/usr/bin/env bash
# L3 — replay préenregistré de la seule cellule décisive de 0812.
#
# Même champion EXACT, même moteur courant, mêmes 63 clés : Q01 ne diffère de
# Q00 que par qs_sacs=1. Les deux diagnostics Scan ajoutés depuis 0812 sont
# explicitement à zéro. Deux vues de force, puis conversion appariée P3/P4
# contre le défenseur Gen2 figé. Aucun enchaînement ni promotion automatique.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART" "$ART/force" "$ART/conversion"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: > "$RES"; : > "$PROG"; echo start > "$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "phase=$1"; }

EXACT_PREFIX="${EXACT_PREFIX:-r2:jass-data/runs/cpx62-1117-l3-exact-fold-refit-v1/20260731T235446Z-970f14de}"
EXPECTED_EXACT_JOB="${EXPECTED_EXACT_JOB:-cpx62-1117-l3-exact-fold-refit-v1}"
EXACT_MODEL_SHA="d84a7fc7c3127d135d3cc150406055b9506daaa881af2959cd3721f6be66eb0a"
OPENING_PREFIX="${OPENING_PREFIX:-r2:jass-data/runs/home-1004-l3-pure-volume8m-preflight-v2/20260727T211936Z-90d3aad1}"
EXPECTED_OPENING_JOB="${EXPECTED_OPENING_JOB:-home-1004-l3-pure-volume8m-preflight-v2}"
OPENING_SHA="94cb6a15e278deebc59035e4e2d5515a8e1dfce2392043ad33873b8e420bcf9b"
GAUGE_PREFIX="${GAUGE_PREFIX:-r2:jass-data/runs/home-0954-l3-pure-m1-abextras-validation-v5/20260724T234944Z-8efd1c45}"
EXPECTED_GAUGE_JOB="${EXPECTED_GAUGE_JOB:-home-0954-l3-pure-m1-abextras-validation-v5}"
GEN2_GZ_SHA="01cc3ea59e9cc3ced1910d4d9054f88f92c1c4d9d220d5f28b0ebaaad33681a0"
P3_GAUGE_SHA="cd92710fec7934d113ccade22180d4cddf029b084dd20c8fa9e30ca686767c91"
P4_GAUGE_SHA="0d925c4fbd7e7928bf6d86bd2cd40f796ee6805e0010e51d5d6483986da2a1ac"
FIXED_DEFENDER_CODE_SHA="9c1d1e8eaaa5b9bbd86105f7f9807a3033784186"

NSH_GATE="${NSH_GATE:-12}"; PAR_GATE="${PAR_GATE:-12}"
NSH_CONV="${NSH_CONV:-4}"; FORCE_DEPTH=9; MOVETIME=0.1
CONV_DEPTH=10; EXPECTED_OPENINGS=1500; EXPECTED_GAMES_PER_VIEW=3000
TARGET_PER_STRATUM=300; MIN_PAIRED_PER_STRATUM=270; CACHE_MB=128
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0,scan_verify_pruning=0,scan_threat_reentry=0"
Q01="${Q00/qs_sacs=0/qs_sacs=1}"
Q00_FIXED="${Q00%,scan_verify_pruning=0,scan_threat_reentry=0}"

MON=""
monitor(){
  ( t0=$(date +%s)
    while true; do
      { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s) - t0) / 60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        printf 'force_views=%s/2\n' "$(find "$ART/force" -name '*.json' 2>/dev/null | wc -l)"
        printf 'conversion_cells=%s/4\n' "$(find "$ART/conversion" -name '*.json' 2>/dev/null | wc -l)"
      } > "$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 120
    done ) &
  MON="$!"
}
restore_src(){ git checkout -- src/ pattern_jass/ 2>/dev/null || true; }
finalize(){
  rc=$?
  trap - EXIT ERR TERM INT
  set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  restore_src
  cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build8" "$W/build32fixed" "$W/fixed-defender-code" \
         "$IN" "$W"/gate-* 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

wait_all(){
  local label="$1"; shift
  local fail=0 pid
  for pid in "$@"; do wait "$pid" || fail=$((fail+1)); done
  [ "$fail" -eq 0 ] || die "$label : $fail worker(s) en échec"
}

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[[ "$JASS_JOB_ID" =~ ^home-([0-9]+)- ]] || die "job id must be home-NNNN-*"
[ "${BASH_REMATCH[1]}" -ge 1200 ] || die "home job number must be >= 1200"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"

stage disk-and-contract-guards
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 8000 ] || die "moins de 8 Go libres (${DFA} Mo)"
NCPU=$(nproc); say "  nproc=$NCPU libre=${DFA}Mo gate=${PAR_GATE}/${NSH_GATE}"
python3 - "$Q00" "$Q01" "$Q00_FIXED" <<'PY' | tee -a "$RES"
import sys
from jobs.tools.l3_quiescence_reopen_verdict import validate_arm_contract
print("  search contract", validate_arm_contract(sys.argv[1], sys.argv[2], sys.argv[3]))
PY
monitor

stage fetch-immutable-inputs
python3 jobs/tools/fetch_result_files.py --prefix "$EXACT_PREFIX" \
  --file artefacts/exact.pjtw.gz=exact.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-exact.json" --expected-state completed \
  > "$W/fetch-exact.log" 2>&1 || die "fetch EXACT KO"
python3 jobs/tools/fetch_result_files.py --prefix "$OPENING_PREFIX" \
  --file artefacts/vol8m-eval-openings.fen=openings.fen \
  --file artefacts/vol8m-eval-openings.json=openings.json \
  --out-dir "$IN" --report "$ART/verified-openings.json" --expected-state completed \
  > "$W/fetch-openings.log" 2>&1 || die "fetch ouvertures KO"
# Le bundle figé fournit Gen2, pas les jauges P3/P4.
python3 jobs/tools/fetch_t1bis_inputs.py --out-dir "$IN" \
  --report "$ART/verified-fixed-inputs.json" > "$W/fetch-fixed.log" 2>&1 ||
  die "fetch bundle figé/Gen2 KO"
python3 jobs/tools/fetch_result_files.py --prefix "$GAUGE_PREFIX" \
  --file artefacts/p3_mince-stable.jnnw.gz=p3.jnnw.gz \
  --file artefacts/p4_egal-stable.jnnw.gz=p4.jnnw.gz \
  --out-dir "$IN" --report "$ART/verified-gauges.json" --expected-state completed \
  > "$W/fetch-gauges.log" 2>&1 || die "fetch jauges P3/P4 KO"

python3 - "$ART/verified-exact.json" "$EXPECTED_EXACT_JOB" \
          "$ART/verified-openings.json" "$EXPECTED_OPENING_JOB" \
          "$ART/verified-gauges.json" "$EXPECTED_GAUGE_JOB" <<'PY'
import json, sys
for report, expected in zip(sys.argv[1::2], sys.argv[2::2]):
    data = json.load(open(report))
    if data.get("job_id") != expected or data.get("result_state") != "completed":
        raise SystemExit(f"producer mismatch: {report} expected {expected}")
PY
gunzip -c "$IN/exact.pjtw.gz" > "$W/EXACT.pjtw"
gunzip -c "$IN/gen2.pjtw.gz" > "$W/GEN2.pjtw"
gunzip -c "$IN/p3.jnnw.gz" > "$W/p3_mince.jnnw"
gunzip -c "$IN/p4.jnnw.gz" > "$W/p4_egal.jnnw"
cp "$IN/openings.fen" "$W/openings.fen"

[ "$(sha256sum "$W/EXACT.pjtw" | awk '{print $1}')" = "$EXACT_MODEL_SHA" ] || die "dérive EXACT"
[ "$(sha256sum "$IN/gen2.pjtw.gz" | awk '{print $1}')" = "$GEN2_GZ_SHA" ] || die "dérive Gen2"
[ "$(sha256sum "$W/openings.fen" | awk '{print $1}')" = "$OPENING_SHA" ] || die "dérive ouvertures"
[ "$(sha256sum "$W/p3_mince.jnnw" | awk '{print $1}')" = "$P3_GAUGE_SHA" ] || die "dérive jauge P3"
[ "$(sha256sum "$W/p4_egal.jnnw" | awk '{print $1}')" = "$P4_GAUGE_SHA" ] || die "dérive jauge P4"
python3 - "$IN/openings.json" "$OPENING_SHA" "$EXPECTED_OPENINGS" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
if d.get("sha256") != sys.argv[2] or d.get("records") != int(sys.argv[3]):
    raise SystemExit("opening manifest mismatch")
if d.get("unique_records") != int(sys.argv[3]) or d.get("overlap_records") != 0:
    raise SystemExit("opening uniqueness/overlap contract mismatch")
PY
NOPEN=$(awk '{sub(/#.*/,""); gsub(/^[ \t]+|[ \t]+$/,""); if (length) n++} END {print n+0}' "$W/openings.fen")
[ "$NOPEN" -eq "$EXPECTED_OPENINGS" ] || die "ouvertures=$NOPEN, attendu $EXPECTED_OPENINGS"
python3 - "$W/EXACT.pjtw" "$W/GEN2.pjtw" <<'PY' | tee -a "$RES"
import struct, sys
for path, wanted, label in ((sys.argv[1], 531441 * 8, "EXACT 8cf"),
                            (sys.argv[2], 531441 * 32, "Gen2 32cf")):
    with open(path, "rb") as handle:
        _, _, _, n_pat, n_ext = struct.unpack("<5I", handle.read(20))
    if (n_pat, n_ext) != (wanted, 120):
        raise SystemExit(f"{label}: geometry {(n_pat, n_ext)}, expected {(wanted, 120)}")
    print(f"  {label} ✓ n_pat={n_pat} n_ext={n_ext}")
PY
say "  producteurs ✓ ; 1500 ouvertures ; jauges P3/P4 explicites"

stage build-current-8cf-and-fixed-defender
EGDIR=""
for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }
done
[ -n "$EGDIR" ] || die "EGDB absente : replay non comparable"
[ -d /root/egdb_intl ] || die "bibliothèque /root/egdb_intl absente"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
grep -q "g_emasks" src/scan_eval.cpp || die "archi: scan_eval sans g_emasks"
grep -q "has_any_capture" src/search.cpp || die "archi: search sans has_any_capture"
grep -q "root_is_drawn" src/search.cpp || die "moteur courant antérieur au correctif racine-nulle"
grep -q "warm_kings_endgame_bitbases" src/hub.cpp || die "moteur courant antérieur au bake movetime"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cmake -S . -B "$W/build8" $FLAGS > "$W/cmake8.log" 2>&1
cmake --build "$W/build8" -j"$NCPU" --target jass > "$W/build8.log" 2>&1
J8="$W/build8/jass"

mkdir -p "$W/fixed-defender-code"
git archive "$FIXED_DEFENDER_CODE_SHA" | tar -x -C "$W/fixed-defender-code"
grep -q "root_is_drawn" "$W/fixed-defender-code/src/search.cpp" || die "défenseur antérieur au correctif"
(cd "$W/fixed-defender-code" && python3 pattern_jass/tools/gen_patterns.py --emit --variant v4) \
  > "$W/gen32fixed.log" 2>&1
cmake -S "$W/fixed-defender-code" -B "$W/build32fixed" $FLAGS > "$W/cmake32fixed.log" 2>&1
cmake --build "$W/build32fixed" -j"$NCPU" --target jass > "$W/build32fixed.log" 2>&1
J32FIXED="$W/build32fixed/jass"
restore_src
for jass in "$J8" "$J32FIXED"; do
  [ -x "$jass" ] || die "binaire manquant $jass"
  [ "$("$jass" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
    die "témoin prise-par-dame en échec sur $jass"
done
printf 'hello\nquit\n' | timeout 60 "$J8" --pattern "$W/EXACT.pjtw" > "$W/load-exact.log" 2>&1
grep -q '^ready' "$W/load-exact.log" || die "EXACT non chargeable"
printf 'hello\nquit\n' | timeout 60 "$J32FIXED" --pattern "$W/GEN2.pjtw" > "$W/load-gen2.log" 2>&1
grep -q '^ready' "$W/load-gen2.log" || die "Gen2 non chargeable"
say "  builds ✓ attaquant courant=$EXPECTED_CODE_SHA défenseur=$FIXED_DEFENDER_CODE_SHA"

run_view(){
  local view="$1" args=()
  [ "$view" = fixed ] && args=(--depth "$FORCE_DEPTH") || args=(--movetime "$MOVETIME")
  timeout 14400 python3 jobs/tools/run_jass_gate_bounded.py \
    --jass-a "$J8" --jass-b "$J8" \
    --pattern-a "$W/EXACT.pjtw" --pattern-b "$W/EXACT.pjtw" \
    --search-params-a "$Q01" --search-params-b "$Q00" \
    --openings-file "$W/openings.fen" "${args[@]}" --pairs 1 \
    --max-plies 160 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
    --timeout 12600 --game-timeout 180 \
    --work-dir "$W/gate-$view" --out "$ART/force/$view-Q01-vs-Q00.json" \
    > "$W/gate-$view.log" 2>&1
}
for view in fixed native; do
  stage "force-$view"
  run_view "$view" || die "vue de force $view KO"
done

run_conv(){
  local arm="$1" stratum="$2" pool="$3" fingerprint="$4"
  local pids=() inputs=() shard out
  for shard in $(seq 0 $((NSH_CONV-1))); do
    out="$W/$arm-$stratum-$shard.json"; inputs+=("$out")
    timeout 14400 python3 jobs/tools/conv_fixed_wdl.py \
      --jass "$J8" --defender-jass "$J32FIXED" \
      --pattern "$W/EXACT.pjtw" --defender-pattern "$W/GEN2.pjtw" \
      --search-params "$fingerprint" --defender-search-params "$Q00_FIXED" \
      --pool-jnnw "$pool" --depth "$CONV_DEPTH" --max-plies 260 \
      --shard "$shard" --nshards "$NSH_CONV" --out "$out" \
      > "$W/$arm-$stratum-$shard.log" 2>&1 &
    pids+=("$!")
  done
  wait_all "$arm/$stratum conversion" "${pids[@]}"
  python3 jobs/tools/aggregate_conv_shards.py --inputs "${inputs[@]}" \
    --expected-shards "$NSH_CONV" --expected-records "$TARGET_PER_STRATUM" \
    --max-error-rate 0.08 --stratum "$stratum" --require-position-results \
    --out "$ART/conversion/$arm-$stratum.json" \
    > "$W/$arm-$stratum-aggregate.log" 2>&1 || die "agrégation $arm/$stratum KO"
}
for stratum in p3_mince p4_egal; do
  stage "conversion-$stratum"
  pids=()
  run_conv Q00 "$stratum" "$W/$stratum.jnnw" "$Q00" & pids+=("$!")
  run_conv Q01 "$stratum" "$W/$stratum.jnnw" "$Q01" & pids+=("$!")
  wait_all "$stratum two-arm wave" "${pids[@]}"
done

stage preregistered-readout
python3 jobs/tools/l3_quiescence_reopen_verdict.py \
  --fixed-gate "$ART/force/fixed-Q01-vs-Q00.json" \
  --native-gate "$ART/force/native-Q01-vs-Q00.json" \
  --conversion-dir "$ART/conversion" --q00 "$Q00" --q01 "$Q01" \
  --defender-q00 "$Q00_FIXED" \
  --expected-games-per-view "$EXPECTED_GAMES_PER_VIEW" \
  --min-paired-per-stratum "$MIN_PAIRED_PER_STRATUM" \
  --bootstrap-samples 20000 --seed 20260802 \
  --out "$ART/quiescence-reopen-verdict.json" > "$W/readout.log" 2>&1 ||
  die "readout contractuel KO"
cp "$ART/quiescence-reopen-verdict.json" "$ART/JASS_CONTROL_SUMMARY.json"
VERDICT=$(python3 - "$ART/quiescence-reopen-verdict.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print(d["scientific_verdict"])
native = d["force"]["native_movetime_0_1"]
conv = d["conversion"]["pooled_p3_p4"]
print(f"native rate={native['rate_q01']} ci97.5={native['ci97_5']}", file=sys.stderr)
print(f"conversion delta={conv['delta_q01_minus_q00']} ci97.5={conv['ci97_5']}", file=sys.stderr)
PY
)
printf '%s\n' "$VERDICT" > "$ART/VERDICT__$VERDICT"
printf 'PROMOTION_AUTHORIZED__FALSE\n' > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf 'AUTOMATIC_NEXT_JOB__NULL\n' > "$ART/AUTOMATIC_NEXT_JOB__NULL"
stage complete
say "$VERDICT promotion=false automatic_next_job=null"

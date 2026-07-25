#!/usr/bin/env bash
# Exact Scan-eval × Jass-depth causal localization on the corrected L3 gauge.
# Diagnostic only: no promotion and no automatic continuation.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${GAUGE_PREFIX:?}"; : "${MATRIX_PREFIX:?}"; : "${CALIBRATION_PREFIX:?}"
: "${ABLATION_PREFIX:?}"; : "${SCAN_BIN:?}"; : "${SCAN_SOURCE_BUNDLE:?}"
: "${EXPECTED_SCAN_SHA256:?}"; : "${EXPECTED_SCAN_RUNTIME_SHA256:?}"
: "${EXPECTED_SCAN_EVAL_SHA256:?}"; : "${EXPECTED_SCAN_BUNDLE_SHA256:?}"
: "${EXPECTED_SCAN_SOURCE_COMMIT:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; IN="$JASS_RESULT_DIR/inputs"
mkdir -p "$W" "$ART" "$IN" "$ART/conversion"
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
  rm -rf "$W/build8-normal" "$W/build8-exact" "$W/build32" \
    "$W/scan-source" "$IN"
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM

NSH=4; TARGET_PER_STRATUM=300; DEFENDER_DEPTH=10; MAX_PLIES=260
GAME_TIMEOUT=600; PAR_CELL_GROUPS=2; BOOTSTRAP_SAMPLES=200000
READOUT_SEED=957001; CACHE_MB=128
STRATA=(p3_mince p4_egal)
NEW_CELLS=(AB_EXTRAS_D12 SCAN_EXACT_D10 SCAN_EXACT_D12)
P3_GAUGE_SHA="cd92710fec7934d113ccade22180d4cddf029b084dd20c8fa9e30ca686767c91"
P4_GAUGE_SHA="0d925c4fbd7e7928bf6d86bd2cd40f796ee6805e0010e51d5d6483986da2a1ac"
AB_EXTRAS_SHA="c86da4bd7ce2d2cb9e1b73ccec9785a770d4727c51b875a03fe9e6edd865ba94"
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

jnnw_count(){ python3 - "$1" <<'PY'
import struct,sys
raw=open(sys.argv[1],"rb").read(8)
if len(raw)!=8 or raw[:4]!=b"JNNW":
    raise SystemExit("invalid JNNW")
print(struct.unpack("<I",raw[4:])[0])
PY
}
wait_all(){
  local label="$1"; shift; local fail=0 pid
  for pid in "$@"; do wait "$pid" || fail=$((fail+1)); done
  [ "$fail" -eq 0 ] || die "$label: $fail workers failed"
}

stage verify-pinned-scan-runtime-and-source
[ -x "$SCAN_BIN" ] || die "Scan binary missing"
[ -f "$SCAN_SOURCE_BUNDLE" ] || die "Scan source bundle missing"
[ "$(sha256sum "$SCAN_BIN"|awk '{print $1}')" = "$EXPECTED_SCAN_SHA256" ] ||
  die "Scan binary hash mismatch"
[ "$(sha256sum "$SCAN_SOURCE_BUNDLE"|awk '{print $1}')" = "$EXPECTED_SCAN_BUNDLE_SHA256" ] ||
  die "Scan source bundle hash mismatch"
SCAN_DIR="$(dirname "$(readlink -f "$SCAN_BIN")")"
[ "$(sha256sum "$SCAN_DIR/data/eval"|awk '{print $1}')" = "$EXPECTED_SCAN_EVAL_SHA256" ] ||
  die "Scan data/eval hash mismatch"
RUNTIME_SHA="$(python3 jobs/tools/scan_runtime_fingerprint.py \
  --scan-dir "$SCAN_DIR" --output "$ART/scan-runtime-manifest.json")"
[ "$RUNTIME_SHA" = "$EXPECTED_SCAN_RUNTIME_SHA256" ] ||
  die "Scan runtime fingerprint mismatch"

stage fetch-immutable-gauge-models-and-source-readouts
python3 jobs/tools/fetch_t1bis_inputs.py --out-dir "$IN" \
  --report "$ART/verified-fixed-inputs.json" > "$W/fetch-fixed.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$GAUGE_PREFIX" \
  --file artefacts/p3_mince-stable.jnnw.gz=p3.jnnw.gz \
  --file artefacts/p4_egal-stable.jnnw.gz=p4.jnnw.gz \
  --file artefacts/holdout-provenance.json=gauge-provenance.json \
  --out-dir "$IN" --report "$ART/verified-gauge.json" > "$W/fetch-gauge.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$ABLATION_PREFIX" \
  --file work/AB_EXTRAS.pjtw=ab-extras.pjtw \
  --file artefacts/ablation-manifest.json=ablation-manifest.json \
  --out-dir "$IN" --report "$ART/verified-abextras.json" > "$W/fetch-ab.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$MATRIX_PREFIX" \
  --file artefacts/corrected-conversion-matrix.json=source-0955.json \
  --file artefacts/conversion/AB_EXTRAS-p3_mince.json=AB_EXTRAS_D10-p3_mince.json \
  --file artefacts/conversion/AB_EXTRAS-p4_egal.json=AB_EXTRAS_D10-p4_egal.json \
  --out-dir "$IN" --report "$ART/verified-0955.json" > "$W/fetch-0955.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$CALIBRATION_PREFIX" \
  --file artefacts/scan-conversion-calibration.json=source-0956.json \
  --file artefacts/conversion/SCAN_D10-p3_mince.json=SCAN_NATIVE_D10-p3_mince.json \
  --file artefacts/conversion/SCAN_D10-p4_egal.json=SCAN_NATIVE_D10-p4_egal.json \
  --file artefacts/conversion/SCAN_D12-p3_mince.json=SCAN_NATIVE_D12-p3_mince.json \
  --file artefacts/conversion/SCAN_D12-p4_egal.json=SCAN_NATIVE_D12-p4_egal.json \
  --out-dir "$IN" --report "$ART/verified-0956.json" > "$W/fetch-0956.log" 2>&1

gunzip -c "$IN/gen2.pjtw.gz" > "$W/GEN2.pjtw"
gunzip -c "$IN/p3.jnnw.gz" > "$W/p3_mince.jnnw"
gunzip -c "$IN/p4.jnnw.gz" > "$W/p4_egal.jnnw"
cp "$IN/ab-extras.pjtw" "$W/AB_EXTRAS.pjtw"
cp "$IN/source-0955.json" "$ART/source-0955.json"
cp "$IN/source-0956.json" "$ART/source-0956.json"
cp "$IN/gauge-provenance.json" "$ART/corrected-gauge-provenance.json"
cp "$IN/ablation-manifest.json" "$ART/ablation-manifest.json"
for f in "$IN"/AB_EXTRAS_D10-*.json "$IN"/SCAN_NATIVE_D*.json; do
  cp "$f" "$ART/conversion/$(basename "$f")"
done

[ "$(sha256sum "$W/AB_EXTRAS.pjtw"|awk '{print $1}')" = "$AB_EXTRAS_SHA" ] ||
  die "AB_EXTRAS hash mismatch"
for spec in "p3_mince:$P3_GAUGE_SHA" "p4_egal:$P4_GAUGE_SHA"; do
  name="${spec%%:*}"; want="${spec#*:}"
  [ "$(sha256sum "$W/$name.jnnw"|awk '{print $1}')" = "$want" ] ||
    die "$name gauge hash mismatch"
  [ "$(jnnw_count "$W/$name.jnnw")" -eq "$TARGET_PER_STRATUM" ] ||
    die "$name gauge count mismatch"
done

stage build-normal-exact-and-defender
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
EXACT_FLAGS="$FLAGS -DJASS_DRAWISH_SCALING=ON -DJASS_SCAN_EXACT_EVAL=ON"
EGDIR=""
for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"

python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cmake -S . -B "$W/build8-normal" $FLAGS > "$W/cmake8-normal.log" 2>&1
cmake -S . -B "$W/build8-exact" $EXACT_FLAGS > "$W/cmake8-exact.log" 2>&1
pids=()
cmake --build "$W/build8-normal" -j4 --target jass > "$W/build8-normal.log" 2>&1 & pids+=("$!")
cmake --build "$W/build8-exact" -j4 --target jass > "$W/build8-exact.log" 2>&1 & pids+=("$!")
wait_all "8cf builds" "${pids[@]}"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 > "$W/gen32.log" 2>&1
cmake -S . -B "$W/build32" $FLAGS > "$W/cmake32.log" 2>&1
cmake --build "$W/build32" -j4 --target jass > "$W/build32.log" 2>&1
J8N="$W/build8-normal/jass"; J8X="$W/build8-exact/jass"; J32="$W/build32/jass"

stage algebraic-port-and-static-parity-gate
python3 jobs/tools/scan_exact_eval_port.py \
  --scan-eval "$SCAN_DIR/data/eval" --expected-sha256 "$EXPECTED_SCAN_EVAL_SHA256" \
  --out "$W/SCAN_EXACT.pjtw" --manifest "$ART/scan-exact-port-manifest.json" \
  > "$W/scan-port.log" 2>&1
gzip -c "$W/SCAN_EXACT.pjtw" > "$ART/scan-exact-8cf.pjtw.gz"

git clone -q "$SCAN_SOURCE_BUNDLE" "$W/scan-source"
[ "$(git -C "$W/scan-source" rev-parse HEAD)" = "$EXPECTED_SCAN_SOURCE_COMMIT" ] ||
  die "Scan source commit mismatch"
cp "$SCAN_DIR/scan.ini" "$W/scan-source/scan.ini"
cp "$SCAN_DIR/data/eval" "$W/scan-source/data/eval"
SCAN_CPP=()
for src in "$W/scan-source"/src/*.cpp; do
  [ "$(basename "$src")" = main.cpp ] || SCAN_CPP+=("$src")
done
g++ -std=c++14 -O2 -mpopcnt -pthread -I"$W/scan-source/src" \
  jobs/tools/scan_static_probe.cpp "${SCAN_CPP[@]}" \
  -o "$W/scan-static-probe" > "$W/scan-probe-build.log" 2>&1
python3 jobs/tools/scan_static_parity.py \
  --pool-jnnw "$W/p3_mince.jnnw" --pool-jnnw "$W/p4_egal.jnnw" \
  --limit-per-pool 0 --scan-probe "$W/scan-static-probe" \
  --scan-cwd "$W/scan-source" --jass "$J8X" --pjtw "$W/SCAN_EXACT.pjtw" \
  --workers 4 --max-abs-diff 0 --out "$ART/scan-static-parity.json" \
  > "$W/static-parity.log" 2>&1

run_cell(){
  local cell="$1" candidate="$2" pattern="$3" depth="$4" stratum="$5" pool="$6"
  local pids=() inputs=() shard out
  for shard in $(seq 0 $((NSH-1))); do
    out="$W/$cell-$stratum-$shard.json"; inputs+=("$out")
    timeout 21600 python3 jobs/tools/conv_fixed_wdl.py \
      --jass "$candidate" --defender-jass "$J32" \
      --pattern "$pattern" --defender-pattern "$W/GEN2.pjtw" \
      --search-params "$Q00" --defender-search-params "$Q00" \
      --pool-jnnw "$pool" --depth "$depth" --defender-depth "$DEFENDER_DEPTH" \
      --max-plies "$MAX_PLIES" \
      --shard "$shard" --nshards "$NSH" --out "$out" \
      > "$W/$cell-$stratum-$shard.log" 2>&1 & pids+=("$!")
  done
  wait_all "$cell/$stratum" "${pids[@]}"
  python3 jobs/tools/aggregate_conv_shards.py --inputs "${inputs[@]}" \
    --expected-shards "$NSH" --expected-records "$TARGET_PER_STRATUM" \
    --max-error-rate 0.02 --stratum "$stratum" --require-position-results \
    --out "$ART/conversion/$cell-$stratum.json" \
    > "$W/$cell-$stratum-aggregate.log" 2>&1
}
run_named_cell(){
  local cell="$1" stratum="$2" pool="$3"
  case "$cell" in
    AB_EXTRAS_D12) run_cell "$cell" "$J8N" "$W/AB_EXTRAS.pjtw" 12 "$stratum" "$pool" ;;
    SCAN_EXACT_D10) run_cell "$cell" "$J8X" "$W/SCAN_EXACT.pjtw" 10 "$stratum" "$pool" ;;
    SCAN_EXACT_D12) run_cell "$cell" "$J8X" "$W/SCAN_EXACT.pjtw" 12 "$stratum" "$pool" ;;
    *) die "unknown cell $cell" ;;
  esac
}

stage causal-conversion-cells
for stratum in "${STRATA[@]}"; do
  pids=()
  for cell in "${NEW_CELLS[@]}"; do
    run_named_cell "$cell" "$stratum" "$W/$stratum.jnnw" & pids+=("$!")
    if [ "${#pids[@]}" -ge "$PAR_CELL_GROUPS" ]; then
      wait_all "$stratum cell batch" "${pids[@]}"; pids=()
    fi
  done
  [ "${#pids[@]}" -eq 0 ] || wait_all "$stratum cell batch" "${pids[@]}"
done

stage aggregate-causal-readout
python3 jobs/tools/l3_scan_gap_causal.py \
  --conversion-dir "$ART/conversion" --strata "${STRATA[@]}" \
  --source-0955 "$ART/source-0955.json" --source-0956 "$ART/source-0956.json" \
  --static-parity "$ART/scan-static-parity.json" \
  --port-manifest "$ART/scan-exact-port-manifest.json" \
  --bootstrap-samples "$BOOTSTRAP_SAMPLES" --seed "$READOUT_SEED" \
  --out "$ART/scan-gap-causal-readout.json" \
  --summary-out "$ART/JASS_CONTROL_SUMMARY.json" | tee -a "$RES"
printf '%s\n' SCAN_GAP_CAUSAL_READOUT_READY_HUMAN_REVIEW \
  > "$ART/VERDICT__SCAN_GAP_CAUSAL_READOUT_READY_HUMAN_REVIEW"
printf '%s\n' PROMOTION_AUTHORIZED__FALSE > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf '%s\n' AUTOMATIC_NEXT_JOB__NULL > "$ART/AUTOMATIC_NEXT_JOB__NULL"
stage complete
say "SCAN_GAP_CAUSAL_READOUT_READY_HUMAN_REVIEW promotion=false"

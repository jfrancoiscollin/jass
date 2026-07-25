#!/usr/bin/env bash
# Scan d10/d12 calibration on the exact corrected 0954 JNNW gauge and
# the same fixed Gen2 Q00 d10 defender used by 0955.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${GAUGE_PREFIX:?}"; : "${MATRIX_PREFIX:?}"; : "${SCAN_BIN:?}"
: "${EXPECTED_SCAN_SHA256:?}"; : "${EXPECTED_SCAN_RUNTIME_SHA256:?}"
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
  rm -rf "$W/build32" "$IN"
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM

NSH=4; TARGET_PER_STRATUM=300; DEFENDER_DEPTH=10; MAX_PLIES=260
GAME_TIMEOUT=600; BOOTSTRAP_SAMPLES=200000; CALIBRATION_SEED=956001
LEARNED=(C0 P1 F500 F2M R2M AB_MAT AB_KING AB_EXTRAS)
SCAN_MODELS=(SCAN_D10 SCAN_D12); STRATA=(p3_mince p4_egal)
P3_GAUGE_SHA="cd92710fec7934d113ccade22180d4cddf029b084dd20c8fa9e30ca686767c91"
P4_GAUGE_SHA="0d925c4fbd7e7928bf6d86bd2cd40f796ee6805e0010e51d5d6483986da2a1ac"
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

stage verify-pinned-scan-runtime
[ -x "$SCAN_BIN" ] || die "Scan binary missing"
[ "$(sha256sum "$SCAN_BIN"|awk '{print $1}')" = "$EXPECTED_SCAN_SHA256" ] ||
  die "Scan binary hash mismatch"
SCAN_DIR="$(dirname "$(readlink -f "$SCAN_BIN")")"
RUNTIME_SHA="$(python3 jobs/tools/scan_runtime_fingerprint.py \
  --scan-dir "$SCAN_DIR" --output "$ART/scan-runtime-manifest.json")"
[ "$RUNTIME_SHA" = "$EXPECTED_SCAN_RUNTIME_SHA256" ] ||
  die "Scan runtime fingerprint mismatch"

stage fetch-corrected-gauge-fixed-defender-and-0955
python3 jobs/tools/fetch_t1bis_inputs.py --out-dir "$IN" \
  --report "$ART/verified-fixed-inputs.json" > "$W/fetch-fixed.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$GAUGE_PREFIX" \
  --file artefacts/p3_mince-stable.jnnw.gz=p3.jnnw.gz \
  --file artefacts/p4_egal-stable.jnnw.gz=p4.jnnw.gz \
  --file artefacts/holdout-provenance.json=gauge-provenance.json \
  --out-dir "$IN" --report "$ART/verified-corrected-gauge.json" \
  > "$W/fetch-gauge.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$MATRIX_PREFIX" \
  --file artefacts/corrected-conversion-matrix.json=source-0955.json \
  --file artefacts/conversion/C0-p3_mince.json=C0-p3_mince.json \
  --file artefacts/conversion/C0-p4_egal.json=C0-p4_egal.json \
  --file artefacts/conversion/P1-p3_mince.json=P1-p3_mince.json \
  --file artefacts/conversion/P1-p4_egal.json=P1-p4_egal.json \
  --file artefacts/conversion/F500-p3_mince.json=F500-p3_mince.json \
  --file artefacts/conversion/F500-p4_egal.json=F500-p4_egal.json \
  --file artefacts/conversion/F2M-p3_mince.json=F2M-p3_mince.json \
  --file artefacts/conversion/F2M-p4_egal.json=F2M-p4_egal.json \
  --file artefacts/conversion/R2M-p3_mince.json=R2M-p3_mince.json \
  --file artefacts/conversion/R2M-p4_egal.json=R2M-p4_egal.json \
  --file artefacts/conversion/AB_MAT-p3_mince.json=AB_MAT-p3_mince.json \
  --file artefacts/conversion/AB_MAT-p4_egal.json=AB_MAT-p4_egal.json \
  --file artefacts/conversion/AB_KING-p3_mince.json=AB_KING-p3_mince.json \
  --file artefacts/conversion/AB_KING-p4_egal.json=AB_KING-p4_egal.json \
  --file artefacts/conversion/AB_EXTRAS-p3_mince.json=AB_EXTRAS-p3_mince.json \
  --file artefacts/conversion/AB_EXTRAS-p4_egal.json=AB_EXTRAS-p4_egal.json \
  --out-dir "$IN" --report "$ART/verified-0955-matrix.json" \
  > "$W/fetch-0955.log" 2>&1
gunzip -c "$IN/gen2.pjtw.gz" > "$W/GEN2.pjtw"
gunzip -c "$IN/p3.jnnw.gz" > "$W/p3_mince.jnnw"
gunzip -c "$IN/p4.jnnw.gz" > "$W/p4_egal.jnnw"
cp "$IN/gauge-provenance.json" "$ART/corrected-gauge-provenance.json"
cp "$IN/source-0955.json" "$ART/source-0955-corrected-matrix.json"

for spec in "p3_mince:$P3_GAUGE_SHA" "p4_egal:$P4_GAUGE_SHA"; do
  name="${spec%%:*}"; want="${spec#*:}"
  [ "$(sha256sum "$W/$name.jnnw"|awk '{print $1}')" = "$want" ] ||
    die "$name gauge hash mismatch"
  [ "$(jnnw_count "$W/$name.jnnw")" -eq "$TARGET_PER_STRATUM" ] ||
    die "$name gauge count mismatch"
done
python3 - "$IN" "$ART/conversion" "$P3_GAUGE_SHA" "$P4_GAUGE_SHA" <<'PY'
import json,shutil,sys
from pathlib import Path
src,dst=Path(sys.argv[1]),Path(sys.argv[2])
expected={"p3_mince":sys.argv[3],"p4_egal":sys.argv[4]}
models=("C0","P1","F500","F2M","R2M","AB_MAT","AB_KING","AB_EXTRAS")
source=json.load(open(src/"source-0955.json"))
if source.get("verdict")!="M1_CORRECTED_CONVERSION_MATRIX_READY_HUMAN_REVIEW":
    raise SystemExit("0955 verdict mismatch")
if source.get("promotion_authorized") is not False:
    raise SystemExit("0955 promotion guard mismatch")
for model in models:
    for stratum,want in expected.items():
        path=src/f"{model}-{stratum}.json"
        doc=json.load(open(path))
        if doc.get("pool_sha256")!=want or doc.get("expected_records")!=300:
            raise SystemExit(f"{path.name}: source pool contract mismatch")
        shutil.copy2(path,dst/path.name)
PY

stage build-exact-32cf-defender
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
EGDIR=""
for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB=128
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 > "$W/gen32.log" 2>&1
cmake -S . -B "$W/build32" $FLAGS > "$W/cmake32.log" 2>&1
cmake --build "$W/build32" -j4 --target jass > "$W/build32.log" 2>&1
J32="$W/build32/jass"

run_scan(){
  local model="$1" depth="$2" stratum="$3" pool="$4"
  local pids=() inputs=() shard out
  for shard in $(seq 0 $((NSH-1))); do
    out="$W/$model-$stratum-$shard.json"; inputs+=("$out")
    timeout 21600 python3 jobs/tools/conv_scan_fixed_wdl.py \
      --scan "$SCAN_BIN" --scan-runtime-sha256 "$RUNTIME_SHA" \
      --jass "$J32" --defender-pattern "$W/GEN2.pjtw" \
      --defender-search-params "$Q00" --pool-jnnw "$pool" \
      --scan-depth "$depth" --defender-depth "$DEFENDER_DEPTH" \
      --max-plies "$MAX_PLIES" --game-timeout "$GAME_TIMEOUT" \
      --shard "$shard" --nshards "$NSH" --out "$out" \
      > "$W/$model-$stratum-$shard.log" 2>&1 & pids+=("$!")
  done
  wait_all "$model/$stratum" "${pids[@]}"
  python3 jobs/tools/aggregate_conv_shards.py --inputs "${inputs[@]}" \
    --expected-shards "$NSH" --expected-records "$TARGET_PER_STRATUM" \
    --max-error-rate 0 --stratum "$stratum" --require-position-results \
    --out "$ART/conversion/$model-$stratum.json" \
    > "$W/$model-$stratum-aggregate.log" 2>&1
}

stage scan-d10-fixed-defender
for stratum in "${STRATA[@]}"; do
  run_scan SCAN_D10 10 "$stratum" "$W/$stratum.jnnw"
done
stage scan-d12-fixed-defender
for stratum in "${STRATA[@]}"; do
  run_scan SCAN_D12 12 "$stratum" "$W/$stratum.jnnw"
done

stage aggregate-scan-calibration
python3 jobs/tools/l3_scan_conversion_calibration.py \
  --conversion-dir "$ART/conversion" --learned-models "${LEARNED[@]}" \
  --scan-models "${SCAN_MODELS[@]}" --strata "${STRATA[@]}" \
  --source-summary "$ART/source-0955-corrected-matrix.json" \
  --bootstrap-samples "$BOOTSTRAP_SAMPLES" --seed "$CALIBRATION_SEED" \
  --out "$ART/scan-conversion-calibration.json" \
  --summary-out "$ART/JASS_CONTROL_SUMMARY.json"
printf '%s\n' SCAN_D10_D12_CORRECTED_GAUGE_CALIBRATION_READY \
  > "$ART/VERDICT__SCAN_D10_D12_CORRECTED_GAUGE_CALIBRATION_READY"
printf '%s\n' PROMOTION_AUTHORIZED__FALSE > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf '%s\n' AUTOMATIC_NEXT_JOB__NULL > "$ART/AUTOMATIC_NEXT_JOB__NULL"
stage complete
say "SCAN_D10_D12_CORRECTED_GAUGE_CALIBRATION_READY promotion=false"

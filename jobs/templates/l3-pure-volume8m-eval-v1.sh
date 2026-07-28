#!/usr/bin/env bash
# L3-PURE VOL8M — independent force/conversion/coverage readout.
#
# Preregistered decision:
# - gain_confirmed: VOL8M CI95 lower bound > .5 vs TURNOVER in Q00 and native,
#   no established force regression vs F2M/M2/Gen2, and no established paired
#   conversion regression vs TURNOVER in P3/P4;
# - directional: both point estimates vs TURNOVER > .5 but the two CIs do not
#   prove superiority;
# - regression: an upper CI95 < .5 vs F2M or GEN2, or paired conversion upper
#   bound < 0 vs TURNOVER;
# - otherwise flat. Holdout loss is diagnostic only.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${TRAIN_PREFIX:?}"; : "${EXPECTED_TRAIN_JOB:?}"; : "${EXPECTED_TRAIN_CODE_SHA:?}"
: "${PREFLIGHT_PREFIX:?}"; : "${EXPECTED_PREFLIGHT_JOB:?}"; : "${EXPECTED_PREFLIGHT_CODE_SHA:?}"
: "${TURNOVER_TRAIN_PREFIX:?}"; : "${EXPECTED_TURNOVER_TRAIN_JOB:?}"
: "${TURNOVER_EVAL_PREFIX:?}"; : "${EXPECTED_TURNOVER_EVAL_JOB:?}"
: "${M2_PREFIX:?}"; : "${EXPECTED_M2_JOB:?}"
: "${M1_PREFIX:?}"; : "${EXPECTED_M1_JOB:?}"
: "${GAUGE_PREFIX:?}"; : "${MATRIX_PREFIX:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; IN="$JASS_RESULT_DIR/inputs"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$ART/force" "$ART/conversion" "$ART/coverage" "$IN" "$GEOM"
RES="$W/RESULTS.txt"; STAGE="$W/stage.txt"; : > "$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "stage=$1"; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e; cp "$RES" "$ART/RESULTS.txt"; rm -rf "$W/build8" "$W/build32" "$W/build32fixed" "$W/fixed-defender-code" "$IN" "$GEOM"; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

NOPEN=1500
FORCE_DEPTH=9
MOVETIME=0.1
NSH_GATE=16
PAR_GATE=4
NSH_CONV=4
CONV_DEPTH=10
TARGET_PER_STRATUM=300
CACHE_MB=128
OPENING_SEED=2236068
F2M_SHA="be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2"
M2_SHA="75ace3c0ad2ffa2b71a9b9073c3c1d1545164e3a5a048e411e91adba23ec3b45"
TURNOVER_SHA="b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16"
GEN2_GZ_SHA="01cc3ea59e9cc3ced1910d4d9054f88f92c1c4d9d220d5f28b0ebaaad33681a0"
P3_GAUGE_SHA="cd92710fec7934d113ccade22180d4cddf029b084dd20c8fa9e30ca686767c91"
P4_GAUGE_SHA="0d925c4fbd7e7928bf6d86bd2cd40f796ee6805e0010e51d5d6483986da2a1ac"
FIXED_DEFENDER_CODE_SHA="038a2001854f2805bc0045acd56c617826e5ff15"
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(nproc)" -ge 16 ] || die "HOME requires 16 logical CPUs"

fetch(){ python3 jobs/tools/fetch_result_files.py "$@"; }
stage fetch-and-authenticate
fetch --prefix "$TRAIN_PREFIX" \
  --file artefacts/vol8m.pjtw.gz=vol8m.pjtw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=training.json \
  --file artefacts/vol8m-optimizer.json=optimizer.json \
  --file artefacts/RESULTS.txt=training-results.txt \
  --out-dir "$IN" --report "$ART/verified-training.json"
fetch --prefix "$PREFLIGHT_PREFIX" \
  --file artefacts/vol8m.jnnw.gz=vol8m.jnnw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=preflight.json \
  --file artefacts/vol8m-eval-openings.fen=openings.fen \
  --file artefacts/vol8m-eval-openings.json=openings.json \
  --file artefacts/vol8m-coverage.json=vol8m-coverage.json \
  --out-dir "$IN" --report "$ART/verified-preflight.json"
fetch --prefix "$TURNOVER_TRAIN_PREFIX" \
  --file artefacts/turnover1to1.pjtw.gz=turnover.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-turnover.json"
fetch --prefix "$TURNOVER_EVAL_PREFIX" \
  --file artefacts/conversion/TURNOVER-p3_mince.json=TURNOVER-p3_mince.json \
  --file artefacts/conversion/TURNOVER-p4_egal.json=TURNOVER-p4_egal.json \
  --file artefacts/conversion/M2-p3_mince.json=M2-p3_mince.json \
  --file artefacts/conversion/M2-p4_egal.json=M2-p4_egal.json \
  --file artefacts/conversion/F2M-p3_mince.json=F2M-p3_mince.json \
  --file artefacts/conversion/F2M-p4_egal.json=F2M-p4_egal.json \
  --file artefacts/coverage/TURNOVER-coverage.json=TURNOVER-coverage.json \
  --file artefacts/coverage/M2-coverage.json=M2-coverage.json \
  --file artefacts/coverage/F2M-coverage.json=F2M-coverage.json \
  --out-dir "$IN" --report "$ART/verified-turnover-eval.json"
fetch --prefix "$M2_PREFIX" --file artefacts/m2.pjtw.gz=m2.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-m2.json"
fetch --prefix "$M1_PREFIX" --file artefacts/f2m.pjtw.gz=f2m.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-f2m.json"
fetch --prefix "$GAUGE_PREFIX" \
  --file artefacts/p3_mince-stable.jnnw.gz=p3.jnnw.gz \
  --file artefacts/p4_egal-stable.jnnw.gz=p4.jnnw.gz \
  --out-dir "$IN" --report "$ART/verified-gauge.json"
fetch --prefix "$MATRIX_PREFIX" --file artefacts/JASS_CONTROL_SUMMARY.json=matrix.json \
  --out-dir "$IN" --report "$ART/verified-matrix.json"
python3 jobs/tools/fetch_t1bis_inputs.py --out-dir "$IN" --report "$ART/verified-fixed-inputs.json"

python3 - "$ART" "$EXPECTED_TRAIN_JOB" "$EXPECTED_PREFLIGHT_JOB" \
  "$EXPECTED_TURNOVER_TRAIN_JOB" "$EXPECTED_TURNOVER_EVAL_JOB" \
  "$EXPECTED_M2_JOB" "$EXPECTED_M1_JOB" \
  "$EXPECTED_TRAIN_CODE_SHA" "$EXPECTED_PREFLIGHT_CODE_SHA" <<'PY'
import json, pathlib, sys
art=pathlib.Path(sys.argv[1])
names=("training","preflight","turnover","turnover-eval","m2","f2m")
for name,want in zip(names,sys.argv[2:]):
    r=json.load(open(art/f"verified-{name}.json"))
    if r.get("job_id")!=want or r.get("result_state")!="completed":
        raise SystemExit(f"{name}: source identity/state mismatch")
training=json.load(open(art/"verified-training.json"))
preflight=json.load(open(art/"verified-preflight.json"))
if training.get("code_sha")!=sys.argv[8] or preflight.get("code_sha")!=sys.argv[9]:
    raise SystemExit("VOL8M source code SHA mismatch")
PY
gunzip -c "$IN/vol8m.pjtw.gz" > "$W/VOL8M.pjtw"
gunzip -c "$IN/vol8m.jnnw.gz" > "$W/VOL8M.jnnw"
gunzip -c "$IN/turnover.pjtw.gz" > "$W/TURNOVER.pjtw"
gunzip -c "$IN/m2.pjtw.gz" > "$W/M2.pjtw"
gunzip -c "$IN/f2m.pjtw.gz" > "$W/F2M.pjtw"
gunzip -c "$IN/gen2.pjtw.gz" > "$W/GEN2.pjtw"
gunzip -c "$IN/p3.jnnw.gz" > "$W/p3_mince.jnnw"
gunzip -c "$IN/p4.jnnw.gz" > "$W/p4_egal.jnnw"
cp "$IN/openings.fen" "$W/openings.fen"
cp "$IN/openings.json" "$ART/independent-openings-manifest.json"
cp "$IN/training.json" "$ART/VOL8M_TRAINING_SUMMARY.json"
cp "$IN/preflight.json" "$ART/VOL8M_PREFLIGHT_SUMMARY.json"
cp "$IN/optimizer.json" "$ART/vol8m-optimizer.json"
cp "$IN/training-results.txt" "$ART/vol8m-training-results.txt"
cp "$IN/vol8m-coverage.json" "$ART/coverage/VOL8M-coverage.json"
for m in TURNOVER M2 F2M; do
  cp "$IN/$m-p3_mince.json" "$ART/conversion/$m-p3_mince.json"
  cp "$IN/$m-p4_egal.json" "$ART/conversion/$m-p4_egal.json"
  cp "$IN/$m-coverage.json" "$ART/coverage/$m-coverage.json"
done

python3 - "$IN" "$W" "$ART" "$OPENING_SEED" "$NOPEN" <<'PY'
import hashlib,json,pathlib,sys
src,w,art=map(pathlib.Path,sys.argv[1:4]); seed,n=int(sys.argv[4]),int(sys.argv[5])
train=json.load(open(src/"training.json")); pre=json.load(open(src/"preflight.json"))
op=json.load(open(src/"openings.json")); opt=json.load(open(src/"optimizer.json"))
raw_cov=json.load(open(src/"vol8m-coverage.json"))
model_sha=hashlib.sha256((w/"VOL8M.pjtw").read_bytes()).hexdigest()
gz_sha=hashlib.sha256((src/"vol8m.jnnw.gz").read_bytes()).hexdigest()
open_sha=hashlib.sha256((src/"openings.fen").read_bytes()).hexdigest()
if train.get("verdict")!="L3_PURE_VOLUME8M_FIT_CONVERGED" or train.get("model",{}).get("sha256")!=model_sha:
    raise SystemExit("training/model certificate mismatch")
if train.get("training",{}).get("records")!=12_000_000 or train.get("training",{}).get("converged") is not True or not opt.get("success"):
    raise SystemExit("convergence contract mismatch")
if train.get("promotion_authorized") is not False or train.get("automatic_next_job") is not None:
    raise SystemExit("continuation guard mismatch")
if pre.get("verdict")!="L3_PURE_VOLUME8M_PREFLIGHT_READY" or pre.get("corpus",{}).get("data_sha256")!=gz_sha:
    raise SystemExit("preflight/corpus certificate mismatch")
raw_coverage=raw_cov.get("coverage",{})
if (raw_cov.get("corpus",{}).get("total_records")!=12_000_000
    or raw_cov.get("geometry",{}).get("trained_buckets_total")!=2_125_768
    or raw_coverage.get("visited_buckets")!=pre.get("coverage",{}).get("visited_buckets")
    or round(100.0*raw_coverage.get("coverage_fraction",0.0),3)!=pre.get("coverage",{}).get("visited_pct")):
    raise SystemExit("coverage certificate mismatch")
if op.get("records")!=n or op.get("unique_records")!=n or op.get("overlap_records")!=0 or op.get("generator_seed")!=seed or op.get("sha256")!=open_sha:
    raise SystemExit("independent opening contract mismatch")
(art/"VOL8M_MODEL_SHA256.txt").write_text(model_sha+"\n")
PY
[ "$(sha256sum "$W/TURNOVER.pjtw" | awk '{print $1}')" = "$TURNOVER_SHA" ] || die "TURNOVER hash drift"
[ "$(sha256sum "$W/M2.pjtw" | awk '{print $1}')" = "$M2_SHA" ] || die "M2 hash drift"
[ "$(sha256sum "$W/F2M.pjtw" | awk '{print $1}')" = "$F2M_SHA" ] || die "F2M hash drift"
[ "$(sha256sum "$IN/gen2.pjtw.gz" | awk '{print $1}')" = "$GEN2_GZ_SHA" ] || die "GEN2 hash drift"
[ "$(sha256sum "$W/p3_mince.jnnw" | awk '{print $1}')" = "$P3_GAUGE_SHA" ] || die "P3 hash drift"
[ "$(sha256sum "$W/p4_egal.jnnw" | awk '{print $1}')" = "$P4_GAUGE_SHA" ] || die "P4 hash drift"

stage build-repaired-engines
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build8" $FLAGS >/dev/null
cmake --build "$W/build8" -j4 --target jass jass_tests >/dev/null
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB ctest --test-dir "$W/build8" --output-on-failure
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4
cmake -S . -B "$W/build32" $FLAGS >/dev/null
cmake --build "$W/build32" -j4 --target jass >/dev/null
mkdir "$W/fixed-defender-code"; git archive "$FIXED_DEFENDER_CODE_SHA" | tar -x -C "$W/fixed-defender-code"
(cd "$W/fixed-defender-code" && python3 pattern_jass/tools/gen_patterns.py --emit --variant v4)
cmake -S "$W/fixed-defender-code" -B "$W/build32fixed" $FLAGS >/dev/null
cmake --build "$W/build32fixed" -j4 --target jass >/dev/null
J8="$W/build8/jass"; J32="$W/build32/jass"; J32FIXED="$W/build32fixed/jass"
grep -q root_is_drawn src/search.cpp || die "drawn-root fix missing"

wait_all(){ label="$1"; shift; fail=0; for pid in "$@"; do wait "$pid" || fail=$((fail+1)); done; [ "$fail" -eq 0 ] || die "$label: $fail workers failed"; }
run_gate(){
  view="$1"; opp="$2"; jb="$J8"; pattern="$W/F2M.pjtw"; args=()
  [ "$opp" = GEN2 ] && { jb="$J32"; pattern="$W/GEN2.pjtw"; }
  [ "$opp" = M2 ] && pattern="$W/M2.pjtw"
  [ "$opp" = TURNOVER ] && pattern="$W/TURNOVER.pjtw"
  [ "$view" = q00 ] && args=(--depth "$FORCE_DEPTH") || args=(--movetime "$MOVETIME")
  timeout 21600 python3 jobs/tools/run_jass_gate_bounded.py \
    --jass-a "$J8" --jass-b "$jb" --pattern-a "$W/VOL8M.pjtw" --pattern-b "$pattern" \
    --search-params-a "$Q00" --search-params-b "$Q00" --openings-file "$W/openings.fen" \
    "${args[@]}" --pairs 1 --max-plies 160 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
    --timeout 10800 --game-timeout 180 --work-dir "$W/gate-$view-$opp" \
    --out "$ART/force/force-$view-VOL8M-vs-$opp.json"
}
for view in q00 native; do stage "force-$view"; pids=(); for opp in M2 TURNOVER F2M GEN2; do run_gate "$view" "$opp" & pids+=("$!"); done; wait_all "$view" "${pids[@]}"; done

run_conv(){
  stratum="$1"; pool="$2"; pids=(); inputs=()
  for shard in $(seq 0 $((NSH_CONV-1))); do out="$W/VOL8M-$stratum-$shard.json"; inputs+=("$out")
    timeout 14400 python3 jobs/tools/conv_fixed_wdl.py --jass "$J8" --defender-jass "$J32FIXED" \
      --pattern "$W/VOL8M.pjtw" --defender-pattern "$W/GEN2.pjtw" \
      --search-params "$Q00" --defender-search-params "$Q00" --pool-jnnw "$pool" \
      --depth "$CONV_DEPTH" --max-plies 260 --shard "$shard" --nshards "$NSH_CONV" --out "$out" &
    pids+=("$!")
  done
  wait_all "$stratum conversion" "${pids[@]}"
  python3 jobs/tools/aggregate_conv_shards.py --inputs "${inputs[@]}" --expected-shards "$NSH_CONV" \
    --expected-records "$TARGET_PER_STRATUM" --max-error-rate 0.08 --stratum "$stratum" \
    --require-position-results --out "$ART/conversion/VOL8M-$stratum.json"
}
stage corrected-fixed-defender-conversion
run_conv p3_mince "$W/p3_mince.jnnw"; run_conv p4_egal "$W/p4_egal.jnnw"

stage aggregate-preregistered-verdict
python3 jobs/tools/l3_volume8m_evaluation.py --artefact-dir "$ART" \
  --training "$IN/training.json" --preflight "$IN/preflight.json" \
  --out "$ART/volume8m-evaluation.json" --summary-out "$ART/JASS_CONTROL_SUMMARY.json"
VERDICT="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/volume8m-evaluation.json")"
printf '%s\n' "$VERDICT" > "$ART/VERDICT__$VERDICT"
printf '%s\n' PROMOTION_AUTHORIZED__FALSE > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf '%s\n' AUTOMATIC_NEXT_JOB__NULL > "$ART/AUTOMATIC_NEXT_JOB__NULL"
stage complete
say "$VERDICT promotion=false automatic_next_job=null"

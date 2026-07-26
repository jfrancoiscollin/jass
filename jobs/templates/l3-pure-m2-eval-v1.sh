#!/usr/bin/env bash
# Independent M2 screen: force, Gen2 guardrail, corrected conversion, coverage.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${M2_PREFIX:?}"; : "${M1_PREFIX:?}"; : "${CHAMPION_PREFIX:?}"
: "${GAUGE_PREFIX:?}"; : "${MATRIX_PREFIX:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; IN="$JASS_RESULT_DIR/inputs"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$ART" "$IN" "$GEOM" "$ART/force" "$ART/conversion" "$ART/coverage"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/stage.txt"
: > "$RES"; echo preflight > "$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "stage=$1"; }
MON=""
monitor(){
  (while true; do
    {
      date -Is
      printf 'stage=%s\n' "$(cat "$STAGE")"
      awk '/MemAvailable:/{printf "mem_available_mb=%d\n",$2/1024}' /proc/meminfo
    } > "$PROG.tmp"
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
  rm -rf "$W/build8" "$W/build32" "$W/build32fixed" \
    "$W/fixed-defender-code" "$IN" "$GEOM"
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM

NOPEN=500; OPENING_CANDIDATES=2000
OPENING_SEED="${OPENING_SEED_OVERRIDE:-244949}"
NSH_GATE=16; PAR_GATE=4; FORCE_DEPTH=9; MOVETIME=0.1
NSH_CONV=4; CONV_DEPTH=10; TARGET_PER_STRATUM=300
CACHE_MB=128; BOOTSTRAP_SAMPLES=200000
EVAL_VARIANT="${EVAL_VARIANT:-M2_STANDARD}"
CANDIDATE_LABEL=M2
M2_SHA="${EXPECTED_CANDIDATE_MODEL_SHA256:-75ace3c0ad2ffa2b71a9b9073c3c1d1545164e3a5a048e411e91adba23ec3b45}"
M2_CORPUS_SHA="${EXPECTED_CANDIDATE_CORPUS_SHA256:-ee8d685cea331940403da82830d7b4cc045fe50acc1e5764d23f0467d4f7ffb8}"
F2M_SHA="be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2"
GEN2_GZ_SHA="01cc3ea59e9cc3ced1910d4d9054f88f92c1c4d9d220d5f28b0ebaaad33681a0"
P3_GAUGE_SHA="cd92710fec7934d113ccade22180d4cddf029b084dd20c8fa9e30ca686767c91"
P4_GAUGE_SHA="0d925c4fbd7e7928bf6d86bd2cd40f796ee6805e0010e51d5d6483986da2a1ac"
MATRIX_CODE_SHA="eacd90ab02b26f0619438ff1f65527d250d3c629"
CHAMPION_CODE_SHA="0c1e04a9574fcd87977f62fe5bd6d71c60c72265"
FIXED_DEFENDER_CODE_SHA="038a2001854f2805bc0045acd56c617826e5ff15"
D8_M2_SHA="75ace3c0ad2ffa2b71a9b9073c3c1d1545164e3a5a048e411e91adba23ec3b45"
D8_M2_CORPUS_SHA="ee8d685cea331940403da82830d7b4cc045fe50acc1e5764d23f0467d4f7ffb8"
D10_SHA="18930613234b4a1a6a933393151a05dd68f71d1af749f058f37c5778bd77960f"
D10_CORPUS_SHA="3351cb8aebd33c417de179d72f4483193ae67f05f723c520190ed2a118fc9297"
M2_INDEPENDENT_OPENINGS_SHA="9a0e46be89655ada7317440e3539b8583ab3d7fe83e400475ae817e77396313c"
D10_INDEPENDENT_OPENINGS_SHA="e41ae3875368112a99d3de2a1e6e40aa8d4d94d5cb66ed5280999a7a4e612965"
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] ||
  die "automatic continuation guard missing"
case "$EVAL_VARIANT" in
  M2_STANDARD) ;;
  D10_CAUSAL)
    CANDIDATE_LABEL=D10
    : "${D8_M2_PREFIX:?}"; : "${M2_EVAL_PREFIX:?}"
    [ "$OPENING_SEED" != 244949 ] || die "D10 evaluation requires a fresh opening seed"
    ;;
  D12_CAUSAL)
    CANDIDATE_LABEL=D12
    : "${EXPECTED_CANDIDATE_JOB:?}"
    : "${D10_TRAIN_PREFIX:?}"; : "${EXPECTED_D10_TRAIN_JOB:?}"
    : "${D10_EVAL_PREFIX:?}"; : "${EXPECTED_D10_EVAL_JOB:?}"
    : "${EXPECTED_OPENING_SHA256:?}"
    [ "$OPENING_SEED" != 244949 ] && [ "$OPENING_SEED" != 314159 ] ||
      die "D12 evaluation requires a fresh opening seed"
    ;;
  *) die "unsupported evaluation variant: $EVAL_VARIANT" ;;
esac
[ "$(nproc)" -ge 16 ] || die "HOME requires 16 logical CPUs"
[ "$(tr ',' '\n' <<<"$Q00"|wc -l)" -eq 63 ] || die "Q00 drift"
monitor

jnnw_count(){ python3 - "$1" <<'PY'
import struct,sys
raw=open(sys.argv[1],"rb").read(8)
if len(raw)!=8 or raw[:4]!=b"JNNW": raise SystemExit("invalid JNNW header")
print(struct.unpack("<I",raw[4:])[0])
PY
}
wait_all(){
  local label="$1"; shift; local fail=0 pid
  for pid in "$@"; do wait "$pid" || fail=$((fail+1)); done
  [ "$fail" -eq 0 ] || die "$label: $fail workers failed"
}

stage fetch-and-verify-immutable-inputs
python3 jobs/tools/fetch_result_files.py --prefix "$M2_PREFIX" \
  --file artefacts/m2.pjtw.gz=m2.pjtw.gz \
  --file artefacts/m2-fresh-2m.jnnw.gz=m2.jnnw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=m2-training.json \
  --out-dir "$IN" --report "$ART/verified-m2.json" > "$W/fetch-m2.log" 2>&1
if [ "$EVAL_VARIANT" = D10_CAUSAL ]; then
  python3 jobs/tools/fetch_result_files.py --prefix "$D8_M2_PREFIX" \
    --file artefacts/m2.pjtw.gz=d8-m2.pjtw.gz \
    --file artefacts/m2-fresh-2m.jnnw.gz=d8-m2.jnnw.gz \
    --file artefacts/JASS_CONTROL_SUMMARY.json=d8-m2-training.json \
    --out-dir "$IN" --report "$ART/verified-d8-m2.json" \
    > "$W/fetch-d8-m2.log" 2>&1
  python3 jobs/tools/fetch_result_files.py --prefix "$M2_EVAL_PREFIX" \
    --file artefacts/JASS_CONTROL_SUMMARY.json=m2-evaluation.json \
    --file artefacts/independent-openings-manifest.json=m2-openings.json \
    --file artefacts/conversion/M2-p3_mince.json=M2-p3_mince.json \
    --file artefacts/conversion/M2-p4_egal.json=M2-p4_egal.json \
    --out-dir "$IN" --report "$ART/verified-m2-evaluation.json" \
    > "$W/fetch-m2-evaluation.log" 2>&1
elif [ "$EVAL_VARIANT" = D12_CAUSAL ]; then
  python3 jobs/tools/fetch_result_files.py --prefix "$D10_TRAIN_PREFIX" \
    --file artefacts/d10.pjtw.gz=d10.pjtw.gz \
    --file artefacts/d10-fresh-2m.jnnw.gz=d10.jnnw.gz \
    --file artefacts/JASS_CONTROL_SUMMARY.json=d10-training.json \
    --out-dir "$IN" --report "$ART/verified-d10-training.json" \
    > "$W/fetch-d10-training.log" 2>&1
  python3 jobs/tools/fetch_result_files.py --prefix "$D10_EVAL_PREFIX" \
    --file artefacts/JASS_CONTROL_SUMMARY.json=d10-evaluation.json \
    --file artefacts/independent-openings-manifest.json=d10-openings.json \
    --file artefacts/conversion/D10-p3_mince.json=D10-p3_mince.json \
    --file artefacts/conversion/D10-p4_egal.json=D10-p4_egal.json \
    --out-dir "$IN" --report "$ART/verified-d10-evaluation.json" \
    > "$W/fetch-d10-evaluation.log" 2>&1
fi
python3 jobs/tools/fetch_result_files.py --prefix "$M1_PREFIX" \
  --file artefacts/f2m.pjtw.gz=f2m.pjtw.gz \
  --file artefacts/common-fresh-500k.jnnw.gz=f2m-common.jnnw.gz \
  --file artefacts/extra-fresh-1500k.jnnw.gz=f2m-extra.jnnw.gz \
  --out-dir "$IN" --report "$ART/verified-f2m.json" > "$W/fetch-f2m.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$CHAMPION_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=champion-benchmark.json \
  --out-dir "$IN" --report "$ART/verified-champion.json" > "$W/fetch-champion.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$GAUGE_PREFIX" \
  --file artefacts/p3_mince-stable.jnnw.gz=p3.jnnw.gz \
  --file artefacts/p4_egal-stable.jnnw.gz=p4.jnnw.gz \
  --out-dir "$IN" --report "$ART/verified-gauge.json" > "$W/fetch-gauge.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$MATRIX_PREFIX" \
  --file artefacts/conversion/F2M-p3_mince.json=F2M-p3_mince.json \
  --file artefacts/conversion/F2M-p4_egal.json=F2M-p4_egal.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=m1-matrix.json \
  --out-dir "$IN" --report "$ART/verified-m1-matrix.json" > "$W/fetch-matrix.log" 2>&1
python3 jobs/tools/fetch_t1bis_inputs.py --out-dir "$IN" \
  --report "$ART/verified-fixed-inputs.json" > "$W/fetch-gen2.log" 2>&1

gunzip -c "$IN/m2.pjtw.gz" > "$W/$CANDIDATE_LABEL.pjtw"
gunzip -c "$IN/f2m.pjtw.gz" > "$W/F2M.pjtw"
gunzip -c "$IN/gen2.pjtw.gz" > "$W/GEN2.pjtw"
gunzip -c "$IN/m2.jnnw.gz" > "$W/$CANDIDATE_LABEL.jnnw"
if [ "$EVAL_VARIANT" = D10_CAUSAL ]; then
  gunzip -c "$IN/d8-m2.pjtw.gz" > "$W/M2.pjtw"
  gunzip -c "$IN/d8-m2.jnnw.gz" > "$W/M2.jnnw"
  cp "$IN/M2-p3_mince.json" "$ART/conversion/M2-p3_mince.json"
  cp "$IN/M2-p4_egal.json" "$ART/conversion/M2-p4_egal.json"
elif [ "$EVAL_VARIANT" = D12_CAUSAL ]; then
  gunzip -c "$IN/d10.pjtw.gz" > "$W/D10.pjtw"
  gunzip -c "$IN/d10.jnnw.gz" > "$W/D10.jnnw"
  cp "$IN/D10-p3_mince.json" "$ART/conversion/D10-p3_mince.json"
  cp "$IN/D10-p4_egal.json" "$ART/conversion/D10-p4_egal.json"
fi
gunzip -c "$IN/f2m-common.jnnw.gz" > "$W/F2M-common.jnnw"
gunzip -c "$IN/f2m-extra.jnnw.gz" > "$W/F2M-extra.jnnw"
gunzip -c "$IN/p3.jnnw.gz" > "$W/p3_mince.jnnw"
gunzip -c "$IN/p4.jnnw.gz" > "$W/p4_egal.jnnw"
cp "$IN/F2M-p3_mince.json" "$ART/conversion/F2M-p3_mince.json"
cp "$IN/F2M-p4_egal.json" "$ART/conversion/F2M-p4_egal.json"

[ "$(sha256sum "$W/$CANDIDATE_LABEL.pjtw"|awk '{print $1}')" = "$M2_SHA" ] ||
  die "$CANDIDATE_LABEL hash drift"
[ "$(sha256sum "$W/F2M.pjtw"|awk '{print $1}')" = "$F2M_SHA" ] || die "F2M hash drift"
[ "$(sha256sum "$IN/gen2.pjtw.gz"|awk '{print $1}')" = "$GEN2_GZ_SHA" ] || die "Gen2 hash drift"
[ "$(sha256sum "$W/$CANDIDATE_LABEL.jnnw"|awk '{print $1}')" = "$M2_CORPUS_SHA" ] ||
  die "$CANDIDATE_LABEL corpus hash drift"
[ "$(jnnw_count "$W/$CANDIDATE_LABEL.jnnw")" -eq 2000000 ] ||
  die "$CANDIDATE_LABEL corpus count drift"
if [ "$EVAL_VARIANT" = D10_CAUSAL ]; then
  [ "$(sha256sum "$W/M2.pjtw"|awk '{print $1}')" = "$D8_M2_SHA" ] ||
    die "D8 M2 hash drift"
  [ "$(sha256sum "$W/M2.jnnw"|awk '{print $1}')" = "$D8_M2_CORPUS_SHA" ] ||
    die "D8 M2 corpus hash drift"
  [ "$(jnnw_count "$W/M2.jnnw")" -eq 2000000 ] || die "D8 M2 corpus count drift"
elif [ "$EVAL_VARIANT" = D12_CAUSAL ]; then
  [ "$(sha256sum "$W/D10.pjtw"|awk '{print $1}')" = "$D10_SHA" ] ||
    die "D10 control hash drift"
  [ "$(sha256sum "$W/D10.jnnw"|awk '{print $1}')" = "$D10_CORPUS_SHA" ] ||
    die "D10 control corpus hash drift"
  [ "$(jnnw_count "$W/D10.jnnw")" -eq 2000000 ] ||
    die "D10 control corpus count drift"
fi
[ $(( $(jnnw_count "$W/F2M-common.jnnw") + $(jnnw_count "$W/F2M-extra.jnnw") )) -eq 2000000 ] ||
  die "F2M corpus count drift"
for spec in "p3_mince:$P3_GAUGE_SHA" "p4_egal:$P4_GAUGE_SHA"; do
  name="${spec%%:*}"; want="${spec#*:}"
  [ "$(sha256sum "$W/$name.jnnw"|awk '{print $1}')" = "$want" ] ||
    die "$name gauge hash drift"
  [ "$(jnnw_count "$W/$name.jnnw")" -eq "$TARGET_PER_STRATUM" ] ||
    die "$name gauge count drift"
done
python3 - "$IN/m2-training.json" "$IN/champion-benchmark.json" \
  "$IN/m1-matrix.json" "$ART/verified-m2.json" \
  "$ART/verified-champion.json" "$ART/verified-m1-matrix.json" \
  "$EVAL_VARIANT" "$M2_SHA" "${EXPECTED_CANDIDATE_JOB:-}" <<'PY'
import json,sys
training,champion,matrix,report,champ_report,matrix_report=(
    json.load(open(p)) for p in sys.argv[1:7]
)
variant, expected_sha, expected_candidate_job = sys.argv[7:]
if report.get("result_state")!="completed":
    raise SystemExit("M2 source is not completed")
if champ_report.get("result_state")!="completed":
    raise SystemExit("champion source is not completed")
if matrix_report.get("result_state")!="completed":
    raise SystemExit("matrix source is not completed")
if training.get("verdict")!="M2_TRAINING_SCREEN_READY":
    raise SystemExit("M2 training verdict mismatch")
if training.get("model_sha256") != expected_sha:
    raise SystemExit("M2 summary hash mismatch")
if variant == "D10_CAUSAL" and (
    training.get("experiment_variant") != "D10_CAUSAL_FRESH2M"
    or training.get("play_depth") != 10
):
    raise SystemExit("D10 training variant/depth mismatch")
if variant == "D12_CAUSAL" and (
    training.get("experiment_variant") != "D12_CAUSAL_FRESH2M"
    or training.get("play_depth") != 12
):
    raise SystemExit("D12 training variant/depth mismatch")
if variant == "D12_CAUSAL" and report.get("job_id") != expected_candidate_job:
    raise SystemExit("D12 training source job mismatch")
if champion.get("verdict")!="F2M_NEW_GENERAL_CHAMPION_HUMAN_REVIEW":
    raise SystemExit("F2M champion certificate mismatch")
if matrix.get("verdict")!="M1_REPAIRED_ENGINE_MATRIX_READY_HUMAN_REVIEW":
    raise SystemExit("M1 repaired matrix mismatch")
PY
if [ "$EVAL_VARIANT" = D10_CAUSAL ]; then
  python3 - "$IN/d8-m2-training.json" "$IN/m2-evaluation.json" \
    "$IN/m2-openings.json" "$ART/verified-d8-m2.json" \
    "$ART/verified-m2-evaluation.json" <<'PY'
import json, sys
d8, evaluation, openings, d8_report, evaluation_report = (
    json.load(open(path)) for path in sys.argv[1:]
)
if d8_report.get("result_state") != "completed":
    raise SystemExit("D8 M2 source is not completed")
if evaluation_report.get("result_state") != "completed":
    raise SystemExit("M2 evaluation source is not completed")
if d8.get("model_sha256") != "75ace3c0ad2ffa2b71a9b9073c3c1d1545164e3a5a048e411e91adba23ec3b45":
    raise SystemExit("D8 M2 certificate hash mismatch")
if evaluation.get("verdict") != "M2_PLATEAU_OR_REGRESSION_REVIEW":
    raise SystemExit("D10 evaluation requires the certified M2 plateau")
if evaluation.get("recommendation") != "stop_same_recipe_and_prepare_d10_causal_arm":
    raise SystemExit("M2 evaluation did not authorize the D10 causal arm")
if openings.get("sha256") != "9a0e46be89655ada7317440e3539b8583ab3d7fe83e400475ae817e77396313c":
    raise SystemExit("M2 independent opening manifest hash mismatch")
PY
elif [ "$EVAL_VARIANT" = D12_CAUSAL ]; then
  python3 - "$IN/d10-training.json" "$IN/d10-evaluation.json" \
    "$IN/d10-openings.json" "$ART/verified-d10-training.json" \
    "$ART/verified-d10-evaluation.json" "$EXPECTED_D10_TRAIN_JOB" \
    "$EXPECTED_D10_EVAL_JOB" <<'PY'
import json, sys
training, evaluation, openings, training_report, evaluation_report = (
    json.load(open(path)) for path in sys.argv[1:6]
)
expected_training_job, expected_evaluation_job = sys.argv[6:]
if (
    training_report.get("result_state") != "completed"
    or training_report.get("job_id") != expected_training_job
):
    raise SystemExit("D10 training source identity/state mismatch")
if (
    evaluation_report.get("result_state") != "completed"
    or evaluation_report.get("job_id") != expected_evaluation_job
):
    raise SystemExit("D10 evaluation source identity/state mismatch")
if (
    training.get("model_sha256") !=
    "18930613234b4a1a6a933393151a05dd68f71d1af749f058f37c5778bd77960f"
    or training.get("training_corpus_sha256") !=
    "3351cb8aebd33c417de179d72f4483193ae67f05f723c520190ed2a118fc9297"
    or training.get("experiment_variant") != "D10_CAUSAL_FRESH2M"
    or training.get("play_depth") != 10
):
    raise SystemExit("D10 training certificate mismatch")
if (
    evaluation.get("verdict") != "D10_PLATEAU_OR_REGRESSION_REVIEW"
    or evaluation.get("recommendation") !=
    "stop_d10_and_prepare_d12_or_d10_d12_mix"
    or not evaluation.get("all_guardrails_pass")
):
    raise SystemExit("D12 evaluation requires the certified D10 plateau")
if openings.get("sha256") != (
    "e41ae3875368112a99d3de2a1e6e40aa8d4d94d5cb66ed5280999a7a4e612965"
):
    raise SystemExit("D10 independent opening manifest hash mismatch")
PY
fi
git diff --quiet "$CHAMPION_CODE_SHA" HEAD -- src pattern_jass/tools ||
  die "engine semantics changed since the symmetric F2M/Gen2 benchmark"
git diff --quiet "$MATRIX_CODE_SHA" HEAD -- src pattern_jass/tools ||
  die "attacker semantics changed since the repaired conversion matrix"

stage build-and-test-repaired-engines
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
EGDIR=""
for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build8" $FLAGS > "$W/cmake8.log" 2>&1
cmake --build "$W/build8" -j4 --target jass jass_tests > "$W/build8.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB \
  ctest --test-dir "$W/build8" --output-on-failure > "$W/ctest8.log" 2>&1
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 > "$W/gen32.log" 2>&1
cmake -S . -B "$W/build32" $FLAGS > "$W/cmake32.log" 2>&1
cmake --build "$W/build32" -j4 --target jass > "$W/build32.log" 2>&1
mkdir -p "$W/fixed-defender-code"
git archive "$FIXED_DEFENDER_CODE_SHA" | tar -x -C "$W/fixed-defender-code"
(cd "$W/fixed-defender-code" &&
  python3 pattern_jass/tools/gen_patterns.py --emit --variant v4) \
  > "$W/gen32fixed.log" 2>&1
cmake -S "$W/fixed-defender-code" -B "$W/build32fixed" $FLAGS \
  > "$W/cmake32fixed.log" 2>&1
cmake --build "$W/build32fixed" -j4 --target jass > "$W/build32fixed.log" 2>&1
J8="$W/build8/jass"; J32="$W/build32/jass"; J32FIXED="$W/build32fixed/jass"
for jass in "$J8" "$J32"; do
  [ "$("$jass" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
    die "king-capture witness failed"
  [ "$("$jass" --perft 1 'B:W13,23,25:B6,14,24,K45' | awk '{print $3}')" = 2 ] ||
    die "tablebase-root witness failed"
done

stage independent-opening-pool
for spec in \
  "prior-reinforcement:768:271828" \
  "prior-meta-screen:128:161803" \
  "prior-meta-confirm:256:141421" \
  "prior-f2m-confirm:500:173205" \
  "prior-f2m-gen2:500:223607"; do
  name="${spec%%:*}"; rest="${spec#*:}"; count="${rest%%:*}"; seed="${rest#*:}"
  "$J8" --gen-opening-pool "$count" "$W/$name.fen" 8 32 20 "$seed" \
    > "$W/open-$name.log" 2>&1
done
if [ "$EVAL_VARIANT" != M2_STANDARD ]; then
  "$J8" --gen-opening-pool "$OPENING_CANDIDATES" \
    "$W/prior-m2-candidates.fen" 8 32 20 244949 \
    > "$W/open-prior-m2.log" 2>&1
  python3 jobs/tools/select_independent_opening_pool.py \
    --candidates "$W/prior-m2-candidates.fen" --expected "$NOPEN" \
    --exclude data/dilf_combinations.fen \
    --exclude "$W/prior-reinforcement.fen" \
    --exclude "$W/prior-meta-screen.fen" \
    --exclude "$W/prior-meta-confirm.fen" \
    --exclude "$W/prior-f2m-confirm.fen" \
    --exclude "$W/prior-f2m-gen2.fen" \
    --generator-seed 244949 \
    --out "$W/prior-m2-independent.fen" \
    --manifest "$W/prior-m2-independent.json" \
    > "$W/select-prior-m2.log" 2>&1
  [ "$(sha256sum "$W/prior-m2-independent.fen"|awk '{print $1}')" = \
    "$M2_INDEPENDENT_OPENINGS_SHA" ] ||
    die "reconstructed M2 independent opening pool hash drift"
fi
if [ "$EVAL_VARIANT" = D12_CAUSAL ]; then
  "$J8" --gen-opening-pool "$OPENING_CANDIDATES" \
    "$W/prior-d10-candidates.fen" 8 32 20 314159 \
    > "$W/open-prior-d10.log" 2>&1
  python3 jobs/tools/select_independent_opening_pool.py \
    --candidates "$W/prior-d10-candidates.fen" --expected "$NOPEN" \
    --exclude data/dilf_combinations.fen \
    --exclude "$W/prior-reinforcement.fen" \
    --exclude "$W/prior-meta-screen.fen" \
    --exclude "$W/prior-meta-confirm.fen" \
    --exclude "$W/prior-f2m-confirm.fen" \
    --exclude "$W/prior-f2m-gen2.fen" \
    --exclude "$W/prior-m2-independent.fen" \
    --generator-seed 314159 \
    --out "$W/prior-d10-independent.fen" \
    --manifest "$W/prior-d10-independent.json" \
    > "$W/select-prior-d10.log" 2>&1
  [ "$(sha256sum "$W/prior-d10-independent.fen"|awk '{print $1}')" = \
    "$D10_INDEPENDENT_OPENINGS_SHA" ] ||
    die "reconstructed D10 independent opening pool hash drift"
fi
"$J8" --gen-opening-pool "$OPENING_CANDIDATES" \
  "$W/open-candidates.fen" 8 32 20 "$OPENING_SEED" \
  > "$W/open-candidate.log" 2>&1
opening_args=(
  --candidates "$W/open-candidates.fen" --expected "$NOPEN"
  --exclude data/dilf_combinations.fen
  --exclude "$W/prior-reinforcement.fen"
  --exclude "$W/prior-meta-screen.fen"
  --exclude "$W/prior-meta-confirm.fen"
  --exclude "$W/prior-f2m-confirm.fen"
  --exclude "$W/prior-f2m-gen2.fen"
)
[ "$EVAL_VARIANT" = M2_STANDARD ] ||
  opening_args+=(--exclude "$W/prior-m2-independent.fen")
[ "$EVAL_VARIANT" != D12_CAUSAL ] ||
  opening_args+=(--exclude "$W/prior-d10-independent.fen")
python3 jobs/tools/select_independent_opening_pool.py "${opening_args[@]}" \
  --generator-seed "$OPENING_SEED" --out "$W/open-eval.fen" \
  --manifest "$ART/independent-openings-manifest.json" \
  > "$W/select-openings.log" 2>&1
if [ "$EVAL_VARIANT" = D10_CAUSAL ]; then
  [ "$(sha256sum "$W/open-eval.fen"|awk '{print $1}')" = \
    "$D10_INDEPENDENT_OPENINGS_SHA" ] ||
    die "D10 independent opening pool hash drift"
elif [ "$EVAL_VARIANT" = D12_CAUSAL ]; then
  [ "$(sha256sum "$W/open-eval.fen"|awk '{print $1}')" = \
    "$EXPECTED_OPENING_SHA256" ] ||
    die "D12 independent opening pool hash drift"
fi

stage exact-corpus-coverage
env PYTHONPATH="$GEOM:pattern_jass/tools" python3 jobs/tools/l3_bucket_visits.py \
  --data "$W/F2M-common.jnnw" "$W/F2M-extra.jnnw" \
  --out "$ART/coverage/F2M-coverage.json" > "$W/coverage-F2M.log" 2>&1
env PYTHONPATH="$GEOM:pattern_jass/tools" python3 jobs/tools/l3_bucket_visits.py \
  --data "$W/$CANDIDATE_LABEL.jnnw" \
  --out "$ART/coverage/$CANDIDATE_LABEL-coverage.json" \
  > "$W/coverage-$CANDIDATE_LABEL.log" 2>&1
if [ "$EVAL_VARIANT" = D10_CAUSAL ]; then
  env PYTHONPATH="$GEOM:pattern_jass/tools" python3 jobs/tools/l3_bucket_visits.py \
    --data "$W/M2.jnnw" \
    --out "$ART/coverage/M2-coverage.json" > "$W/coverage-M2.log" 2>&1
elif [ "$EVAL_VARIANT" = D12_CAUSAL ]; then
  env PYTHONPATH="$GEOM:pattern_jass/tools" python3 jobs/tools/l3_bucket_visits.py \
    --data "$W/D10.jnnw" \
    --out "$ART/coverage/D10-coverage.json" > "$W/coverage-D10.log" 2>&1
fi

run_gate(){
  local view="$1" opponent="$2" jb="$J8" pattern="$W/F2M.pjtw"; local args=()
  [ "$opponent" = GEN2 ] && { jb="$J32"; pattern="$W/GEN2.pjtw"; }
  [ "$opponent" = M2 ] && pattern="$W/M2.pjtw"
  [ "$opponent" = D10 ] && pattern="$W/D10.pjtw"
  [ "$view" = q00 ] && args=(--depth "$FORCE_DEPTH") || args=(--movetime "$MOVETIME")
  timeout 21600 python3 jobs/tools/run_jass_gate_bounded.py \
    --jass-a "$J8" --jass-b "$jb" \
    --pattern-a "$W/$CANDIDATE_LABEL.pjtw" --pattern-b "$pattern" \
    --search-params-a "$Q00" --search-params-b "$Q00" \
    --openings-file "$W/open-eval.fen" "${args[@]}" --pairs 1 \
    --max-plies 160 --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
    --timeout 10800 --game-timeout 180 \
    --work-dir "$W/gate-$view-$CANDIDATE_LABEL-$opponent" \
    --out "$ART/force/force-$view-$CANDIDATE_LABEL-vs-$opponent.json" \
    > "$W/force-$view-$CANDIDATE_LABEL-$opponent.log" 2>&1
}
stage force-q00
run_gate q00 F2M & p_f2m=$!; run_gate q00 GEN2 & p_gen2=$!
if [ "$EVAL_VARIANT" = D10_CAUSAL ]; then
  run_gate q00 M2 & p_control=$!
  wait_all "Q00 force wave" "$p_f2m" "$p_gen2" "$p_control"
elif [ "$EVAL_VARIANT" = D12_CAUSAL ]; then
  run_gate q00 D10 & p_control=$!
  wait_all "Q00 force wave" "$p_f2m" "$p_gen2" "$p_control"
else
  wait_all "Q00 force wave" "$p_f2m" "$p_gen2"
fi
stage force-native
run_gate native F2M & p_f2m=$!; run_gate native GEN2 & p_gen2=$!
if [ "$EVAL_VARIANT" = D10_CAUSAL ]; then
  run_gate native M2 & p_control=$!
  wait_all "native force wave" "$p_f2m" "$p_gen2" "$p_control"
elif [ "$EVAL_VARIANT" = D12_CAUSAL ]; then
  run_gate native D10 & p_control=$!
  wait_all "native force wave" "$p_f2m" "$p_gen2" "$p_control"
else
  wait_all "native force wave" "$p_f2m" "$p_gen2"
fi

run_conv(){
  local stratum="$1" pool="$2"; local pids=() inputs=() shard out
  for shard in $(seq 0 $((NSH_CONV-1))); do
    out="$W/$CANDIDATE_LABEL-$stratum-$shard.json"; inputs+=("$out")
    timeout 14400 python3 jobs/tools/conv_fixed_wdl.py \
      --jass "$J8" --defender-jass "$J32FIXED" \
      --pattern "$W/$CANDIDATE_LABEL.pjtw" --defender-pattern "$W/GEN2.pjtw" \
      --search-params "$Q00" --defender-search-params "$Q00" \
      --pool-jnnw "$pool" --depth "$CONV_DEPTH" --max-plies 260 \
      --shard "$shard" --nshards "$NSH_CONV" --out "$out" \
      > "$W/$CANDIDATE_LABEL-$stratum-$shard.log" 2>&1 & pids+=("$!")
  done
  wait_all "$CANDIDATE_LABEL/$stratum conversion" "${pids[@]}"
  python3 jobs/tools/aggregate_conv_shards.py --inputs "${inputs[@]}" \
    --expected-shards "$NSH_CONV" --expected-records "$TARGET_PER_STRATUM" \
    --max-error-rate 0.08 --stratum "$stratum" --require-position-results \
    --out "$ART/conversion/$CANDIDATE_LABEL-$stratum.json" \
    > "$W/$CANDIDATE_LABEL-$stratum-aggregate.log" 2>&1
}
stage corrected-fixed-defender-conversion
run_conv p3_mince "$W/p3_mince.jnnw"
run_conv p4_egal "$W/p4_egal.jnnw"

stage aggregate-preregistered-verdict
if [ "$EVAL_VARIANT" = D10_CAUSAL ]; then
  python3 jobs/tools/l3_d10_causal_evaluation.py \
    --force-dir "$ART/force" --conversion-dir "$ART/conversion" \
    --coverage-dir "$ART/coverage" \
    --training-summary "$IN/m2-training.json" \
    --d8-training-summary "$IN/d8-m2-training.json" \
    --m2-evaluation "$IN/m2-evaluation.json" \
    --opening-manifest "$ART/independent-openings-manifest.json" \
    --bootstrap-samples "$BOOTSTRAP_SAMPLES" \
    --out "$ART/d10-causal-evaluation.json" \
    --summary-out "$ART/JASS_CONTROL_SUMMARY.json" \
    > "$W/aggregate.log" 2>&1
  VERDICT_SOURCE="$ART/d10-causal-evaluation.json"
elif [ "$EVAL_VARIANT" = D12_CAUSAL ]; then
  python3 jobs/tools/l3_d12_causal_evaluation.py \
    --force-dir "$ART/force" --conversion-dir "$ART/conversion" \
    --coverage-dir "$ART/coverage" \
    --training-summary "$IN/m2-training.json" \
    --d10-training-summary "$IN/d10-training.json" \
    --d10-evaluation "$IN/d10-evaluation.json" \
    --opening-manifest "$ART/independent-openings-manifest.json" \
    --expected-opening-seed "$OPENING_SEED" \
    --expected-opening-sha256 "$EXPECTED_OPENING_SHA256" \
    --bootstrap-samples "$BOOTSTRAP_SAMPLES" \
    --out "$ART/d12-causal-evaluation.json" \
    --summary-out "$ART/JASS_CONTROL_SUMMARY.json" \
    > "$W/aggregate.log" 2>&1
  VERDICT_SOURCE="$ART/d12-causal-evaluation.json"
else
  python3 jobs/tools/l3_m2_evaluation.py \
    --force-dir "$ART/force" --conversion-dir "$ART/conversion" \
    --coverage-dir "$ART/coverage" --training-summary "$IN/m2-training.json" \
    --champion-benchmark "$IN/champion-benchmark.json" \
    --opening-manifest "$ART/independent-openings-manifest.json" \
    --bootstrap-samples "$BOOTSTRAP_SAMPLES" \
    --out "$ART/m2-evaluation.json" --summary-out "$ART/JASS_CONTROL_SUMMARY.json" \
    > "$W/aggregate.log" 2>&1
  VERDICT_SOURCE="$ART/m2-evaluation.json"
fi
VERDICT="$(python3 - "$VERDICT_SOURCE" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["verdict"])
PY
)"
printf '%s\n' "$VERDICT" > "$ART/VERDICT__$VERDICT"
printf '%s\n' PROMOTION_AUTHORIZED__FALSE > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf '%s\n' AUTOMATIC_NEXT_JOB__NULL > "$ART/AUTOMATIC_NEXT_JOB__NULL"
stage complete
say "$VERDICT promotion=false automatic_next_job=null"

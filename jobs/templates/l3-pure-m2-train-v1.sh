#!/usr/bin/env bash
# L3-PURE M2: one fresh 2M self-play generation from the reviewed F2M champion.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_JOB_ID:?}"; : "${M1_PREFIX:?}"; : "${EXPECTED_M1_JOB:?}"
: "${CHAMPION_PREFIX:?}"; : "${EXPECTED_CHAMPION_JOB:?}"
: "${EXPECTED_PARENT_MODEL_SHA256:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; ART="$JASS_ARTEFACT_DIR"; SRC="$JASS_RESULT_DIR/source"
GEOM="$JASS_RESULT_DIR/geom8"; mkdir -p "$W" "$ART" "$SRC" "$GEOM"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; PHASE="$W/phase.txt"
: > "$RES"; : > "$PROG"; echo initializing > "$PHASE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
phase(){ echo "$1" > "$PHASE"; say "phase=$1"; }
ACTIVE=(); MONITOR_PID=""
monitor(){
  (
    while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$PHASE" 2>/dev/null || echo unknown)"
        df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{printf "free_mb=%s\n",$4}'
        awk '/MemAvailable:/{printf "mem_available_mb=%d\n",$2/1024}' /proc/meminfo
      } > "$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 60
    done
  ) & MONITOR_PID="$!"
}
finalize(){
  rc=$?; trap - EXIT ERR INT TERM; set +e
  [ "${#ACTIVE[@]}" -eq 0 ] || kill "${ACTIVE[@]}" 2>/dev/null
  [ -z "$MONITOR_PID" ] || { kill "$MONITOR_PID" 2>/dev/null; wait "$MONITOR_PID" 2>/dev/null; }
  [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$W/test-build" "$W/venv" "$W"/*.feat 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 130' INT
trap 'exit 143' TERM

TOTAL_RECORDS=2000000
PRODUCERS=12
LABEL_DEPTH=4
PLAY_DEPTH="${PLAY_DEPTH_OVERRIDE:-8}"
EXPERIMENT_VARIANT="${EXPERIMENT_VARIANT:-M2_D8_FRESH2M}"
MAXPLIES=260
BASE_SEED=1618033
HOLDOUT_MOD=10
SPLIT_SEED=577215
L2=3e-5
MAXIT=1000
LBFGS_MAXCOR=20
LBFGS_GTOL=1e-3
CHUNK=20000
GEN_TIMEOUT=21600
FIT_TIMEOUT=43200

Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

say "=== $JASS_JOB_ID — L3-PURE $EXPERIMENT_VARIANT 2M training corpus from F2M ==="
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] || die "FULL_RUN_APPROVED=1 missing"
[ "${SCIENTIFIC_GO:-0}" = 1 ] || die "SCIENTIFIC_GO=1 missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "NO_AUTOMATIC_CONTINUATION=1 missing"
case "$EXPERIMENT_VARIANT:$PLAY_DEPTH" in
  M2_D8_FRESH2M:8) ;;
  D10_CAUSAL_FRESH2M:10)
    [ "${D10_CAUSAL_APPROVED:-0}" = 1 ] || die "D10_CAUSAL_APPROVED=1 missing"
    : "${PLATEAU_PREFIX:?}"; : "${EXPECTED_PLATEAU_JOB:?}"
    ;;
  D12_CAUSAL_FRESH2M:12)
    [ "${D12_CAUSAL_APPROVED:-0}" = 1 ] || die "D12_CAUSAL_APPROVED=1 missing"
    : "${D10_EVAL_PREFIX:?}"; : "${EXPECTED_D10_EVAL_JOB:?}"
    : "${EXPECTED_D10_MODEL_SHA256:?}"
    ;;
  D10_D12_MIX_5_1:0)
    [ "${DEPTH_MIX_APPROVED:-0}" = 1 ] || die "DEPTH_MIX_APPROVED=1 missing"
    : "${D10_TRAIN_PREFIX:?}"; : "${EXPECTED_D10_TRAIN_JOB:?}"
    : "${EXPECTED_D10_MODEL_SHA256:?}"; : "${EXPECTED_D10_CORPUS_SHA256:?}"
    : "${EXPECTED_D10_META_SHA256:?}"
    : "${D12_TRAIN_PREFIX:?}"; : "${EXPECTED_D12_TRAIN_JOB:?}"
    : "${EXPECTED_D12_MODEL_SHA256:?}"; : "${EXPECTED_D12_CORPUS_SHA256:?}"
    : "${EXPECTED_D12_META_SHA256:?}"
    : "${D12_EVAL_PREFIX:?}"; : "${EXPECTED_D12_EVAL_JOB:?}"
    : "${EXPECTED_MIX_CORPUS_SHA256:?}"; : "${EXPECTED_MIX_META_SHA256:?}"
    ;;
  *) die "unsupported experiment variant/depth: $EXPERIMENT_VARIANT/$PLAY_DEPTH" ;;
esac
[ "$(nproc)" -ge 16 ] || die "HOME requires 16 logical CPUs"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')" -ge 12000 ] || die "need 12 GiB free"
[ "$(awk '/MemAvailable:/{print int($2/1024)}' /proc/meminfo)" -ge 3500 ] || die "need 3.5 GiB available RAM"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 key count drift"
monitor

phase verify-reviewed-f2m-parent
python3 jobs/tools/fetch_result_files.py \
  --prefix "$M1_PREFIX" \
  --file artefacts/f2m.pjtw.gz=f2m.pjtw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=m1-training-summary.json \
  --out-dir "$SRC" --report "$ART/verified-m1-source.json" > "$W/fetch-m1.log" 2>&1
python3 jobs/tools/fetch_result_files.py \
  --prefix "$CHAMPION_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=champion-summary.json \
  --file artefacts/f2m-gen2-repaired-benchmark.json=champion-benchmark.json \
  --out-dir "$SRC" --report "$ART/verified-champion-source.json" > "$W/fetch-champion.log" 2>&1
gunzip -c "$SRC/f2m.pjtw.gz" > "$W/parent-f2m.pjtw"
python3 - "$SRC" "$W/parent-f2m.pjtw" "$ART" "$EXPECTED_M1_JOB" \
  "$EXPECTED_CHAMPION_JOB" "$EXPECTED_PARENT_MODEL_SHA256" \
  "$EXPERIMENT_VARIANT" <<'PY'
import hashlib, json, sys
from pathlib import Path
src, model, art = map(Path, sys.argv[1:4])
m1_job, champion_job, expected_sha, experiment_variant = sys.argv[4:]
m1_report = json.load(open(art / "verified-m1-source.json"))
champion_report = json.load(open(art / "verified-champion-source.json"))
m1 = json.load(open(src / "m1-training-summary.json"))
champion = json.load(open(src / "champion-summary.json"))
if m1_report.get("job_id") != m1_job or m1_report.get("result_state") != "completed":
    raise SystemExit("M1 source identity/state mismatch")
if champion_report.get("job_id") != champion_job or champion_report.get("result_state") != "completed":
    raise SystemExit("champion source identity/state mismatch")
if m1.get("verdict") != "M1_TRAINING_SCREEN_READY":
    raise SystemExit("unexpected M1 training verdict")
if champion.get("verdict") != "F2M_NEW_GENERAL_CHAMPION_HUMAN_REVIEW":
    raise SystemExit("0965 did not recommend F2M")
if champion.get("recommended_general_champion") != "F2M" or champion.get("m2_parent") != "F2M":
    raise SystemExit("F2M is not the reviewed M2 parent")
actual_sha = hashlib.sha256(model.read_bytes()).hexdigest()
if actual_sha != expected_sha:
    raise SystemExit(f"F2M SHA mismatch: {actual_sha}")
if m1["arms"]["F2M"]["model_sha256"] != expected_sha:
    raise SystemExit("M1 summary F2M SHA mismatch")
payload = {
    "schema": 1,
    "parent": "F2M",
    "parent_model_sha256": actual_sha,
    "m1_source_job": m1_job,
    "champion_certificate_job": champion_job,
    "human_promotion_reviewed": True,
    "training_mode": (
        "certified_fresh_depth_mix"
        if experiment_variant == "D10_D12_MIX_5_1"
        else "fresh_selfplay_only"
    ),
}
(art / "m2-parent-contract.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n"
)
PY

if [ "$EXPERIMENT_VARIANT" = D10_CAUSAL_FRESH2M ]; then
  python3 jobs/tools/fetch_result_files.py \
    --prefix "$PLATEAU_PREFIX" \
    --file artefacts/JASS_CONTROL_SUMMARY.json=plateau-summary.json \
    --out-dir "$SRC" --report "$ART/verified-plateau-source.json" \
    > "$W/fetch-plateau.log" 2>&1
  python3 - "$SRC/plateau-summary.json" "$ART/verified-plateau-source.json" \
    "$EXPECTED_PLATEAU_JOB" <<'PY'
import json, sys
summary_path, report_path, expected_job = sys.argv[1:]
summary = json.load(open(summary_path))
report = json.load(open(report_path))
if report.get("job_id") != expected_job or report.get("result_state") != "completed":
    raise SystemExit("M2 plateau source identity/state mismatch")
if summary.get("verdict") != "M2_PLATEAU_OR_REGRESSION_REVIEW":
    raise SystemExit("D10 requires the certified M2 plateau verdict")
if summary.get("recommendation") != "stop_same_recipe_and_prepare_d10_causal_arm":
    raise SystemExit("M2 plateau did not route to the D10 causal arm")
if not summary.get("all_guardrails_pass"):
    raise SystemExit("M2 plateau guardrails did not pass")
PY
elif [ "$EXPERIMENT_VARIANT" = D12_CAUSAL_FRESH2M ]; then
  python3 jobs/tools/fetch_result_files.py \
    --prefix "$D10_EVAL_PREFIX" \
    --file artefacts/JASS_CONTROL_SUMMARY.json=d10-evaluation-summary.json \
    --out-dir "$SRC" --report "$ART/verified-d10-evaluation-source.json" \
    > "$W/fetch-d10-evaluation.log" 2>&1
  python3 - "$SRC/d10-evaluation-summary.json" \
    "$ART/verified-d10-evaluation-source.json" \
    "$EXPECTED_D10_EVAL_JOB" "$EXPECTED_D10_MODEL_SHA256" <<'PY'
import json, sys
summary_path, report_path, expected_job, expected_model = sys.argv[1:]
summary = json.load(open(summary_path))
report = json.load(open(report_path))
if report.get("job_id") != expected_job or report.get("result_state") != "completed":
    raise SystemExit("D10 evaluation source identity/state mismatch")
if summary.get("verdict") != "D10_PLATEAU_OR_REGRESSION_REVIEW":
    raise SystemExit("D12 requires the certified D10 plateau verdict")
if summary.get("recommendation") != "stop_d10_and_prepare_d12_or_d10_d12_mix":
    raise SystemExit("D10 plateau did not route to the next depth factor")
if not summary.get("all_guardrails_pass"):
    raise SystemExit("D10 plateau guardrails did not pass")
training = summary.get("training_summary", {})
if (
    training.get("model_sha256") != expected_model
    or training.get("experiment_variant") != "D10_CAUSAL_FRESH2M"
    or training.get("play_depth") != 10
):
    raise SystemExit("D10 evaluation training identity mismatch")
PY
elif [ "$EXPERIMENT_VARIANT" = D10_D12_MIX_5_1 ]; then
  python3 jobs/tools/fetch_result_files.py \
    --prefix "$D10_TRAIN_PREFIX" \
    --file artefacts/d10-training-summary.json=d10-training-summary.json \
    --file artefacts/d10-corpus-contract.json=d10-corpus-contract.json \
    --file artefacts/d10-fresh-2m.jnnw.gz=d10-fresh-2m.jnnw.gz \
    --file artefacts/d10-fresh-2m.jsm.gz=d10-fresh-2m.jsm.gz \
    --out-dir "$SRC" --report "$ART/verified-d10-training-source.json" \
    > "$W/fetch-d10-training.log" 2>&1
  python3 jobs/tools/fetch_result_files.py \
    --prefix "$D12_TRAIN_PREFIX" \
    --file artefacts/d12-training-summary.json=d12-training-summary.json \
    --file artefacts/d12-corpus-contract.json=d12-corpus-contract.json \
    --file artefacts/d12-fresh-2m.jnnw.gz=d12-fresh-2m.jnnw.gz \
    --file artefacts/d12-fresh-2m.jsm.gz=d12-fresh-2m.jsm.gz \
    --out-dir "$SRC" --report "$ART/verified-d12-training-source.json" \
    > "$W/fetch-d12-training.log" 2>&1
  python3 jobs/tools/fetch_result_files.py \
    --prefix "$D12_EVAL_PREFIX" \
    --file artefacts/JASS_CONTROL_SUMMARY.json=d12-evaluation-summary.json \
    --out-dir "$SRC" --report "$ART/verified-d12-evaluation-source.json" \
    > "$W/fetch-d12-evaluation.log" 2>&1
  python3 - "$SRC" "$ART" \
    "$EXPECTED_D10_TRAIN_JOB" "$EXPECTED_D12_TRAIN_JOB" "$EXPECTED_D12_EVAL_JOB" \
    "$EXPECTED_D10_MODEL_SHA256" "$EXPECTED_D10_CORPUS_SHA256" \
    "$EXPECTED_D10_META_SHA256" "$EXPECTED_D12_MODEL_SHA256" \
    "$EXPECTED_D12_CORPUS_SHA256" "$EXPECTED_D12_META_SHA256" \
    "$EXPECTED_PARENT_MODEL_SHA256" <<'PY'
import json, sys
from pathlib import Path

src, art = map(Path, sys.argv[1:3])
(
    d10_job, d12_job, eval_job,
    d10_model_sha, d10_corpus_sha, d10_meta_sha,
    d12_model_sha, d12_corpus_sha, d12_meta_sha,
    parent_sha,
) = sys.argv[3:]

for report_name, expected_job in (
    ("verified-d10-training-source.json", d10_job),
    ("verified-d12-training-source.json", d12_job),
    ("verified-d12-evaluation-source.json", eval_job),
):
    report = json.load(open(art / report_name))
    if report.get("job_id") != expected_job or report.get("result_state") != "completed":
        raise SystemExit(f"{report_name}: identity/state mismatch")

d10 = json.load(open(src / "d10-training-summary.json"))
d12 = json.load(open(src / "d12-training-summary.json"))
d10_contract = json.load(open(src / "d10-corpus-contract.json"))
d12_contract = json.load(open(src / "d12-corpus-contract.json"))
evaluation = json.load(open(src / "d12-evaluation-summary.json"))

def check_training(summary, contract, variant, depth, model_sha, corpus_sha, meta_sha):
    if (
        summary.get("verdict") != "M2_TRAINING_SCREEN_READY"
        or summary.get("parent") != "F2M"
        or summary.get("parent_model_sha256") != parent_sha
        or summary.get("model_sha256") != model_sha
        or summary.get("training_corpus_sha256") != corpus_sha
        or summary.get("experiment_variant") != variant
        or summary.get("play_depth") != depth
        or contract.get("experiment_variant") != variant
        or contract.get("parent") != "F2M"
        or contract.get("records") != 2_000_000
        or contract.get("fresh_only") is not True
        or contract.get("play_depth") != depth
        or contract.get("jnnw_sha256") != corpus_sha
        or contract.get("jsm_sha256") != meta_sha
        or contract.get("historical_replay_records") != 0
        or contract.get("top3") is not False
        or contract.get("role_reweight_v2") is not False
    ):
        raise SystemExit(f"{variant}: training/corpus contract mismatch")

check_training(
    d10, d10_contract, "D10_CAUSAL_FRESH2M", 10,
    d10_model_sha, d10_corpus_sha, d10_meta_sha,
)
check_training(
    d12, d12_contract, "D12_CAUSAL_FRESH2M", 12,
    d12_model_sha, d12_corpus_sha, d12_meta_sha,
)
if (
    evaluation.get("verdict") != "D12_PLATEAU_OR_REGRESSION_REVIEW"
    or evaluation.get("recommendation")
    != "stop_single_depth_escalation_and_prepare_distribution_factor"
    or evaluation.get("all_guardrails_pass") is not True
    or evaluation.get("training_summary", {}).get("model_sha256") != d12_model_sha
    or evaluation.get("d10_training_summary", {}).get("model_sha256") != d10_model_sha
):
    raise SystemExit("depth-mix trigger was not satisfied by the D12 evaluation")
PY
fi

phase isolated-runtime-build-and-tests
python3 -m venv "$W/venv"
"$W/venv/bin/python" -m pip install --disable-pip-version-check --only-binary=:all: \
  numpy==1.26.4 scipy==1.14.1 > "$W/pip.log" 2>&1
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen-patterns.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
[ "$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')" -eq 4251528 ] || die "8cf mismatch"
# The unit suite contains explicit stub-contract tests and must run in the
# default build without the external EGDB bridge.
cmake -S . -B "$W/test-build" -DCMAKE_BUILD_TYPE=Release > "$W/cmake-tests.log" 2>&1
cmake --build "$W/test-build" -j4 --target jass_tests > "$W/build-tests.log" 2>&1
ctest --test-dir "$W/test-build" --output-on-failure > "$W/ctest.log" 2>&1
# The scientific binary is a distinct production build with EGDB enabled.
FLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl > "$W/clone.log" 2>&1
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || die "EGDB unavailable"; export JASS_EGDB_PATH="$EGDIR"
cmake -S . -B "$W/build" $FLAGS > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j4 --target jass > "$W/build.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || die "jass binary missing"
[ "$("$J" --perft 1 'W:W40,43,K2:B8,18,29,30' | awk '{print $3}')" = 9 ] ||
  die "king-capture dedup witness failed"
[ "$("$J" --perft 1 'B:W13,23,25:B6,14,24,K45' | awk '{print $3}')" = 2 ] ||
  die "tablebase-root witness failed"

if [ "$EXPERIMENT_VARIANT" = D10_D12_MIX_5_1 ]; then
  phase construct-certified-d10-d12-mix
  gunzip -c "$SRC/d10-fresh-2m.jnnw.gz" > "$W/d10.jnnw"
  gunzip -c "$SRC/d10-fresh-2m.jsm.gz" > "$W/d10.jsm"
  gunzip -c "$SRC/d12-fresh-2m.jnnw.gz" > "$W/d12.jnnw"
  gunzip -c "$SRC/d12-fresh-2m.jsm.gz" > "$W/d12.jsm"
  [ "$(sha256sum "$W/d10.jnnw" | awk '{print $1}')" = "$EXPECTED_D10_CORPUS_SHA256" ] ||
    die "D10 corpus hash drift after decompression"
  [ "$(sha256sum "$W/d10.jsm" | awk '{print $1}')" = "$EXPECTED_D10_META_SHA256" ] ||
    die "D10 metadata hash drift after decompression"
  [ "$(sha256sum "$W/d12.jnnw" | awk '{print $1}')" = "$EXPECTED_D12_CORPUS_SHA256" ] ||
    die "D12 corpus hash drift after decompression"
  [ "$(sha256sum "$W/d12.jsm" | awk '{print $1}')" = "$EXPECTED_D12_META_SHA256" ] ||
    die "D12 metadata hash drift after decompression"
  python3 tools/selfplay_frontier.py mix \
    --source D10 "$W/d10.jnnw" "$W/d10.jsm" 5 \
    --source D12 "$W/d12.jnnw" "$W/d12.jsm" 1 \
    --target-records "$TOTAL_RECORDS" --seed 271828 \
    --out-data "$W/m2.raw.jnnw" --out-meta "$W/m2.raw.jsm" \
    --manifest "$ART/m2-depth-mix.json" > "$W/m2-mix.log" 2>&1
  python3 - "$ART/m2-depth-mix.json" \
    "$EXPECTED_D10_CORPUS_SHA256" "$EXPECTED_D10_META_SHA256" \
    "$EXPECTED_D12_CORPUS_SHA256" "$EXPECTED_D12_META_SHA256" \
    "$EXPECTED_MIX_CORPUS_SHA256" "$EXPECTED_MIX_META_SHA256" <<'PY'
import json, sys
manifest = json.load(open(sys.argv[1]))
d10_data, d10_meta, d12_data, d12_meta, mix_data, mix_meta = sys.argv[2:]
sources = {source["label"]: source for source in manifest.get("sources", [])}
if (
    manifest.get("operation") != "weighted_aligned_mix"
    or manifest.get("selection") != "exact_uniform_record_sample_splitmix64_floyd"
    or manifest.get("seed") != 271828
    or manifest.get("records") != 2_000_000
    or sources.get("D10", {}).get("selected_records") != 1_666_667
    or sources.get("D12", {}).get("selected_records") != 333_333
    or sources.get("D10", {}).get("input_data_sha256") != d10_data
    or sources.get("D10", {}).get("input_meta_sha256") != d10_meta
    or sources.get("D12", {}).get("input_data_sha256") != d12_data
    or sources.get("D12", {}).get("input_meta_sha256") != d12_meta
    or manifest.get("out_data_sha256") != mix_data
    or manifest.get("out_meta_sha256") != mix_meta
    or manifest.get("opening_id_policy")
    != "preserved_across_sources_for_common_holdout_fold"
    or manifest.get("external_teacher_inputs") != 0
):
    raise SystemExit("depth-mix manifest/hash contract mismatch")
overlap = manifest.get("source_opening_id_overlaps", {}).get("D10__D12", 0)
minimum_openings = min(
    sources["D10"]["input_openings"], sources["D12"]["input_openings"]
)
if overlap < 0.95 * minimum_openings:
    raise SystemExit("D10/D12 opening identities are not sufficiently aligned")
PY
else
  phase generate-fresh-2m
  base=$((TOTAL_RECORDS / PRODUCERS)); rem=$((TOTAL_RECORDS % PRODUCERS))
  pairs=(); ACTIVE=()
  for shard in $(seq 0 $((PRODUCERS-1))); do
    count="$base"; [ "$shard" -lt "$rem" ] && count=$((count+1))
    data="$W/m2-s$shard.jnnw"; meta="$W/m2-s$shard.jsm"; log="$W/m2-s$shard.log"
    timeout "$GEN_TIMEOUT" "$J" --gen-data-wdl "$count" "$data" \
      "$LABEL_DEPTH" "$PLAY_DEPTH" "$MAXPLIES" $((BASE_SEED+shard)) \
      --nnue "$W/parent-f2m.pjtw" --search-params-play "$Q00" --wdl-zero-score \
      --random-open-plies 8 --explore-eps 8 --explore-decay-plies 60 \
      --pair-openings --drop-plycap --sample-meta-out "$meta" > "$log" 2>&1 &
    ACTIVE+=("$!"); pairs+=(--pair "$data" "$meta")
  done
  failed=0; for pid in "${ACTIVE[@]}"; do wait "$pid" || failed=$((failed+1)); done; ACTIVE=()
  [ "$failed" -eq 0 ] || die "M2 generation: $failed producer failures"
  for log in "$W"/m2-s*.log; do
    grep -q 'label_score_searches=0' "$log" || die "score-label search in $log"
  done
  python3 tools/selfplay_frontier.py merge "${pairs[@]}" \
    --out-data "$W/m2.raw.jnnw" --out-meta "$W/m2.raw.jsm" \
    --manifest "$ART/m2-fresh-2m-merge.json" > "$W/m2-merge.log" 2>&1
fi
python3 - "$W/m2.raw.jnnw" "$W/m2.raw.jsm" "$ART/m2-corpus-contract.json" \
  "$PLAY_DEPTH" "$EXPERIMENT_VARIANT" <<'PY'
import hashlib, json, struct, sys
from pathlib import Path
data_path, meta_path, out = map(Path, sys.argv[1:4])
play_depth = int(sys.argv[4])
experiment_variant = sys.argv[5]
data = data_path.read_bytes()
meta = meta_path.read_bytes()
is_depth_mix = experiment_variant == "D10_D12_MIX_5_1"
if data[:4] != b"JNNW" or struct.unpack_from("<I", data, 4)[0] != 2_000_000:
    raise SystemExit("M2 JNNW count/header mismatch")
if meta[:4] != b"JSM1":
    raise SystemExit("M2 JSM header mismatch")
payload = {
    "schema": 1,
    "records": 2_000_000,
    "jnnw_sha256": hashlib.sha256(data).hexdigest(),
    "jsm_sha256": hashlib.sha256(meta).hexdigest(),
    "parent": "F2M",
    "fresh_only": True,
    "historical_replay_records": 0,
    "starts": "standard",
    "top3": False,
    "role_reweight_v2": False,
    "geometry": "8cf",
    "search": "Q00",
    "base_seed": None if is_depth_mix else 1_618_033,
    "play_depth": None if is_depth_mix else play_depth,
    "depth_distribution_records": (
        {"d10": 1_666_667, "d12": 333_333} if is_depth_mix else None
    ),
    "new_generation_performed": not is_depth_mix,
    "source_corpora_fresh_only": True,
    "mix_seed": 271_828 if is_depth_mix else None,
    "experiment_variant": experiment_variant,
    "paired_randomization_with_m2_d8": experiment_variant in {
        "D10_CAUSAL_FRESH2M", "D12_CAUSAL_FRESH2M"
    },
    "paired_randomization_with_depth_controls": experiment_variant in {
        "D10_CAUSAL_FRESH2M", "D12_CAUSAL_FRESH2M", "D10_D12_MIX_5_1"
    },
}
out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY
# Publish the expensive corpus before fitting so a fit incident is recoverable.
gzip -n -c "$W/m2.raw.jnnw" > "$ART/m2-fresh-2m.jnnw.gz"
gzip -n -c "$W/m2.raw.jsm" > "$ART/m2-fresh-2m.jsm.gz"

phase split-by-opening-and-fit
python3 tools/selfplay_frontier.py split \
  --data "$W/m2.raw.jnnw" --meta "$W/m2.raw.jsm" \
  --out-data "$W/m2.fit.jnnw" --out-meta "$W/m2.fit.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
  --manifest "$ART/m2-split.json" > "$W/m2-split.log" 2>&1
holdout="$("$W/venv/bin/python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["holdout_records"])' "$ART/m2-split.json")"
[ "$holdout" -gt 0 ] || die "M2 holdout missing"
"$J" --dump-eval-features "$W/m2.fit.jnnw" "$W/m2.feat" > "$W/m2-features.log" 2>&1
set +e
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
  /usr/bin/time -v timeout "$FIT_TIMEOUT" "$W/venv/bin/python" pattern_jass/tools/train_stream.py \
    --data "$W/m2.fit.jnnw" --feat "$W/m2.feat" --out "$W/m2.pjtw" \
    --target wdl --loss logistic --color-fold --tempo-stage \
    --warm-start "$W/parent-f2m.pjtw" --holdout-count "$holdout" \
    --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
    --lbfgs-maxcor "$LBFGS_MAXCOR" --lbfgs-gtol "$LBFGS_GTOL" \
    --optimizer-report "$ART/m2-optimizer.json" \
    > "$W/m2-fit.log" 2> "$W/m2-fit-time.log"
fit_rc=$?
set -e
if [ -s "$W/m2.pjtw" ]; then
  gzip -n -c "$W/m2.pjtw" > "$ART/m2-checkpoint.pjtw.gz"
fi
[ "$fit_rc" -eq 0 ] || die "M2 fit failed rc=$fit_rc; corpus and optional checkpoint preserved"
[ -s "$W/m2.pjtw" ] || die "M2 model missing"
grep -q 'HOLDOUT_LOGLOSS' "$W/m2-fit.log" || die "M2 holdout result missing"
"$W/venv/bin/python" - "$ART/m2-optimizer.json" <<'PY' || die "M2 optimiser did not converge"
import json, sys
if not json.load(open(sys.argv[1])).get("success"):
    raise SystemExit(1)
PY
cp "$ART/m2-checkpoint.pjtw.gz" "$ART/m2.pjtw.gz"

phase publish-training-screen
"$W/venv/bin/python" - "$W" "$ART" "$EXPECTED_CODE_SHA" \
  "$EXPECTED_PARENT_MODEL_SHA256" "$PLAY_DEPTH" "$EXPERIMENT_VARIANT" <<'PY'
import hashlib, json, pathlib, re, sys
w, art = map(pathlib.Path, sys.argv[1:3])
code, parent_sha, play_depth, experiment_variant = sys.argv[3:]
log = (w / "m2-fit.log").read_text()
timing = (w / "m2-fit-time.log").read_text()
corpus = json.load(open(art / "m2-corpus-contract.json"))
split = json.load(open(art / "m2-split.json"))
payload = {
    "schema": 1,
    "verdict": "M2_TRAINING_SCREEN_READY",
    "code_sha": code,
    "parent": "F2M",
    "parent_model_sha256": parent_sha,
    "model_sha256": hashlib.sha256((w / "m2.pjtw").read_bytes()).hexdigest(),
    "training_records": corpus["records"],
    "training_corpus_sha256": corpus["jnnw_sha256"],
    "training_meta_sha256": corpus["jsm_sha256"],
    "fresh_only": corpus["fresh_only"],
    "play_depth": corpus["play_depth"],
    "depth_distribution_records": corpus["depth_distribution_records"],
    "new_generation_performed": corpus["new_generation_performed"],
    "experiment_variant": experiment_variant,
    "holdout_records": split["holdout_records"],
    "iterations": int(re.search(r"iters=(\d+)", log).group(1)),
    "holdout_logloss": float(re.search(r"HOLDOUT_LOGLOSS\s+([0-9.]+)", log).group(1)),
    "max_rss_kib": int(re.search(r"Maximum resident set size \(kbytes\):\s*(\d+)", timing).group(1)),
    "evaluation_authorized": True,
    "promotion_authorized": False,
    "automatic_next_job": None,
}
serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
(art / "m2-training-summary.json").write_text(serialized)
(art / "JASS_CONTROL_SUMMARY.json").write_text(serialized)
(art / "VERDICT__M2_TRAINING_SCREEN_READY").write_text("M2_TRAINING_SCREEN_READY\n")
(art / "PROMOTION_AUTHORIZED__FALSE").write_text("PROMOTION_AUTHORIZED__FALSE\n")
(art / "AUTOMATIC_NEXT_JOB__NULL").write_text("AUTOMATIC_NEXT_JOB__NULL\n")
PY
if [ "$EXPERIMENT_VARIANT" = D10_CAUSAL_FRESH2M ]; then
  cp "$ART/m2.pjtw.gz" "$ART/d10.pjtw.gz"
  cp "$ART/m2-training-summary.json" "$ART/d10-training-summary.json"
  cp "$ART/m2-corpus-contract.json" "$ART/d10-corpus-contract.json"
  cp "$ART/m2-fresh-2m.jnnw.gz" "$ART/d10-fresh-2m.jnnw.gz"
  cp "$ART/m2-fresh-2m.jsm.gz" "$ART/d10-fresh-2m.jsm.gz"
elif [ "$EXPERIMENT_VARIANT" = D12_CAUSAL_FRESH2M ]; then
  cp "$ART/m2.pjtw.gz" "$ART/d12.pjtw.gz"
  cp "$ART/m2-training-summary.json" "$ART/d12-training-summary.json"
  cp "$ART/m2-corpus-contract.json" "$ART/d12-corpus-contract.json"
  cp "$ART/m2-fresh-2m.jnnw.gz" "$ART/d12-fresh-2m.jnnw.gz"
  cp "$ART/m2-fresh-2m.jsm.gz" "$ART/d12-fresh-2m.jsm.gz"
elif [ "$EXPERIMENT_VARIANT" = D10_D12_MIX_5_1 ]; then
  cp "$ART/m2.pjtw.gz" "$ART/depth-mix5to1.pjtw.gz"
  cp "$ART/m2-training-summary.json" "$ART/depth-mix5to1-training-summary.json"
  cp "$ART/m2-corpus-contract.json" "$ART/depth-mix5to1-corpus-contract.json"
  cp "$ART/m2-fresh-2m.jnnw.gz" "$ART/depth-mix5to1.jnnw.gz"
  cp "$ART/m2-fresh-2m.jsm.gz" "$ART/depth-mix5to1.jsm.gz"
fi
phase complete
say "M2_TRAINING_SCREEN_READY variant=$EXPERIMENT_VARIANT evaluation=true promotion=false automatic_next_job=null"

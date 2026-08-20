#!/usr/bin/env bash
# Read-only CTX4 uncertainty-band decision-channel screen.
#
# CURRICULUM remains the only scalar PatternEval value.  The certified 1417
# mapper is evaluated separately on legal children and can only suggest a
# top1->top2 decision flip when the CURRICULUM top-two margin is <=20 cp.
# A pool-preserving permutation of the same context deltas is the paired
# shuffled control.  No model is fitted and no game is played.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
cd "$JASS_CODE_DIR"

MAP_JOB="cpx62-1417-l3-context3-exact-tanh-mapper-screen-v1"
MAP_ATTEMPT="20260819T072356Z-999091b3"
MAP_CODE="999091b34cbbaf4ab1b61e94f70647da21e7ddc1"
MAP_ROOT="r2:jass-data/runs/$MAP_JOB/$MAP_ATTEMPT"

FIT_JOB="cpx62-1427-l3-context3-paired-patterneval-exact-extras-v2"
FIT_ATTEMPT="20260819T224926Z-7fe6c654"
FIT_CODE="7fe6c654de9119fdc70164e6a4e4779cd7fe2e31"
FIT_ROOT="r2:jass-data/runs/$FIT_JOB/$FIT_ATTEMPT"

FORCE_JOB="cpx62-1428-l3-context3-two-pool-force-exact-extras-v2"
FORCE_ATTEMPT="20260820T005123Z-17517b38"
FORCE_CODE="17517b38d8850b4ba1681666498cd510d6b6719f"
FORCE_ROOT="r2:jass-data/runs/$FORCE_JOB/$FORCE_ATTEMPT"

READOUT_JOB="cpx62-1430-l3-context3-1428-readout-publish-v2"
READOUT_ATTEMPT="20260820T044422Z-17517b38"
READOUT_CODE="17517b38d8850b4ba1681666498cd510d6b6719f"
READOUT_ROOT="r2:jass-data/runs/$READOUT_JOB/$READOUT_ATTEMPT"

CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"
CURRICULUM_CODE="18c38a33ae78c9c2e8e2df62fca266da28dacead"
CURRICULUM_ROOT="r2:jass-data/runs/$CURRICULUM_JOB/$CURRICULUM_ATTEMPT"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"

PER_POOL=256
TOTAL=512
NSH=8
CHOICE_DEPTH=9
JUDGE_DEPTH=12
UNCERTAINTY_CP=20
SELECTION_SEED=2026082007
SHUFFLE_SEED=2026082008
BOOTSTRAP_SEED=2026082009
BOOTSTRAP=100000
MIN_TOTAL=48
MIN_PER_POOL=16
MIN_ALIGNED_FLIPS=12
CACHE_MB=128
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
VENV_READY="$VENV/.jass-runtime-ready-v1"
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

W="$JASS_RESULT_DIR/work"
IN="$JASS_RESULT_DIR/inputs"
ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"
SHARDS="$W/shards"
mkdir -p "$W" "$IN" "$ART" "$GEOM" "$SHARDS"
RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
STAGE="$W/.stage"
: >"$RES"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

MON=""
monitor(){
  (t0=$(date +%s); while true; do
    {
      printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
      printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
      printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
      printf 'shards_ready=%s/%s\n' "$(find "$SHARDS" -name 'shard-*.json' | wc -l)" "$NSH"
    } >"$PROG.tmp"
    mv "$PROG.tmp" "$PROG"
    cp "$PROG" "$ART/PROGRESS.txt"
    sleep 120
  done) & MON="$!"
}
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$IN" "$GEOM" "$W/children-work" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-context4-uncertainty-screen-v1$ ]] || die "invalid job nomenclature"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(nproc)" -eq 16 ] || die "16-CPU CPX contract mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic-continuation guard missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] || die "frozen-read guard missing"
[ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] || die "promotion guard missing"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
[ -f "$VENV_READY" ] || die "persistent numeric runtime absent"
PY="$VENV/bin/python"
"$PY" -c 'import numpy; assert numpy.__version__'
DFA=$(df -Pm /root | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 4000 ] || die "disk below 4GB"
monitor
say "mode=ctx4_readonly_uncertainty per_pool=$PER_POOL choice_depth=$CHOICE_DEPTH judge_depth=$JUDGE_DEPTH uncertainty_cp=$UNCERTAINTY_CP"

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_context4_uncertainty_screen.py
"$PY" -m unittest jobs.tests.test_l3_context4_uncertainty_screen >"$W/tests.log" 2>&1

fetch(){
  local root="$1" report="$2"; shift 2
  python3 jobs/tools/fetch_result_files.py --prefix "$root" "$@" \
    --out-dir "$IN" --report "$ART/$report" --expected-state completed
}

stage fetch-and-authenticate-certified-evidence
fetch "$MAP_ROOT" verified-1417.json \
  --file artefacts/context3-exact-tanh-mapper-screen.json=mapper.json >"$W/fetch-1417.log" 2>&1
fetch "$FIT_ROOT" verified-1427.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=fit-summary.json >"$W/fetch-1427.log" 2>&1
fetch "$FORCE_ROOT" verified-1428.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=force-summary.json \
  --file artefacts/pool-certificate.json=pool-certificate.json \
  --file artefacts/model-certificate.json=model-certificate.json \
  --file artefacts/ctx3-force-pool1-openings.fen=pool1.fen \
  --file artefacts/ctx3-force-pool2-openings.fen=pool2.fen >"$W/fetch-1428.log" 2>&1
fetch "$READOUT_ROOT" verified-1430.json \
  --file artefacts/CTX3_1428_READOUT.json=readout.json >"$W/fetch-1430.log" 2>&1
fetch "$CURRICULUM_ROOT" verified-curriculum.json \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz >"$W/fetch-curriculum.log" 2>&1

gunzip -t "$IN/curriculum.pjtw.gz"
gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
[ "$(sha256sum "$W/curriculum.pjtw" | awk '{print $1}')" = "$CURRICULUM_SHA" ] || die "CURRICULUM model drift"

"$PY" - "$IN" "$ART" \
  "$MAP_JOB" "$MAP_ATTEMPT" "$MAP_CODE" \
  "$FIT_JOB" "$FIT_ATTEMPT" "$FIT_CODE" \
  "$FORCE_JOB" "$FORCE_ATTEMPT" "$FORCE_CODE" \
  "$READOUT_JOB" "$READOUT_ATTEMPT" "$READOUT_CODE" \
  "$CURRICULUM_JOB" "$CURRICULUM_ATTEMPT" "$CURRICULUM_CODE" <<'PY'
import json,sys
from pathlib import Path
src,art=map(Path,sys.argv[1:3])
vals=sys.argv[3:]
triples=[tuple(vals[i:i+3]) for i in range(0,len(vals),3)]
names=['verified-1417.json','verified-1427.json','verified-1428.json','verified-1430.json','verified-curriculum.json']
for name,expected in zip(names,triples):
    r=json.load(open(art/name))
    got=(r.get('job_id'),r.get('attempt_id'),r.get('code_sha'))
    if got!=expected or r.get('result_state')!='completed' or r.get('exit_code')!=0:
        raise SystemExit(f'{name}: identity/state drift {got}')
mapper=json.load(open(src/'mapper.json'))
fit=json.load(open(src/'fit-summary.json'))
force=json.load(open(src/'force-summary.json'))
readout=json.load(open(src/'readout.json'))
pools=json.load(open(src/'pool-certificate.json'))
if mapper.get('verdict')!='JASS_CONTEXT3_EXACT_TANH_MAPPER_SCREEN_PASSED' or not mapper.get('screen_passed'):
    raise SystemExit('1417 mapper drift')
if fit.get('verdict')!='JASS_CONTEXT3_PAIRED_PATTERNEVAL_EXACT_EXTRAS_MODELS_READY':
    raise SystemExit('1427 fit verdict drift')
if force.get('verdict')!='JASS_CONTEXT3_ALIGNED_VS_SHUFFLED_NOT_ESTABLISHED':
    raise SystemExit('1428 verdict drift')
if readout.get('classification')!='NONPOSITIVE_CLOSE_CTX3':
    raise SystemExit('1430 did not close scalar CTX3')
if not pools.get('mutually_disjoint') or int(pools.get('historical_exclusion_count',-1))!=17:
    raise SystemExit('1428 pool certificate drift')
if force.get('refits')!=0 or force.get('new_selfplay')!=0 or force.get('frozen_cohorts_read')!=0 or force.get('promotion_authorized') is not False:
    raise SystemExit('1428 scope drift')
PY

stage build-authentic-curriculum-engine
EGDIR=""
for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON \
  -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass jass_tests >"$W/build.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB ctest --test-dir "$W/build" --output-on-failure >"$W/ctest.log" 2>&1
J="$W/build/jass"
printf 'hello\nquit\n' | timeout 60 "$J" --pattern "$W/curriculum.pjtw" >"$W/load-curriculum.log" 2>&1
grep -q '^ready' "$W/load-curriculum.log" || die "CURRICULUM model does not load"

stage deterministic-source-selection
"$PY" jobs/tools/l3_context4_uncertainty_screen.py prepare \
  --pool "POOL1=$IN/pool1.fen" --pool "POOL2=$IN/pool2.fen" \
  --per-pool "$PER_POOL" --seed "$SELECTION_SEED" --out "$ART/selection.json" >"$W/selection.log" 2>&1

stage legal-child-enumeration
mkdir -p "$W/children-work"
"$PY" jobs/tools/l3_context4_uncertainty_screen.py children \
  --selection "$ART/selection.json" --jass "$J" --work-dir "$W/children-work" \
  --out-json "$ART/children.json" --out-jnnw "$W/children.jnnw" >"$W/children.log" 2>&1

stage separate-context-channel
"$J" --dump-conditional-context-v2 "$W/children.jnnw" "$W/children.ctx2.feat" >"$W/context-features.log" 2>&1
"$PY" jobs/tools/l3_context4_uncertainty_screen.py score-context \
  --children "$ART/children.json" --child-jnnw "$W/children.jnnw" \
  --features "$W/children.ctx2.feat" --mapper-report "$IN/mapper.json" \
  --out "$ART/context-scores.json" >"$W/context-score.log" 2>&1

stage parallel-uncertainty-decision-screen
pids=()
for shard in $(seq 0 $((NSH-1))); do
  timeout -k 30s 7200s "$PY" jobs/tools/l3_context4_uncertainty_screen.py worker \
    --selection "$ART/selection.json" --children "$ART/children.json" \
    --context-scores "$ART/context-scores.json" --jass "$J" \
    --curriculum "$W/curriculum.pjtw" --search-params "$Q00" \
    --choice-depth "$CHOICE_DEPTH" --judge-depth "$JUDGE_DEPTH" \
    --uncertainty-cp "$UNCERTAINTY_CP" --shard "$shard" --nshards "$NSH" \
    --out "$SHARDS/shard-$shard.json" >"$W/worker-$shard.log" 2>&1 &
  pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done
[ "$(find "$SHARDS" -name 'shard-*.json' | wc -l)" -eq "$NSH" ] || die "missing worker shard"

stage causal-aligned-vs-shuffled-readout
args=()
for shard in $(seq 0 $((NSH-1))); do args+=(--shard "$SHARDS/shard-$shard.json"); done
"$PY" jobs/tools/l3_context4_uncertainty_screen.py aggregate \
  --selection "$ART/selection.json" --children "$ART/children.json" \
  --context-scores "$ART/context-scores.json" "${args[@]}" \
  --shuffle-seed "$SHUFFLE_SEED" --bootstrap-samples "$BOOTSTRAP" \
  --bootstrap-seed "$BOOTSTRAP_SEED" --min-total "$MIN_TOTAL" \
  --min-per-pool "$MIN_PER_POOL" --min-aligned-flips "$MIN_ALIGNED_FLIPS" \
  --out "$ART/context4-uncertainty-screen.json" >"$W/aggregate.log" 2>&1

"$PY" - "$ART/context4-uncertainty-screen.json" "$ART/JASS_CONTROL_SUMMARY.json" \
  "$ART" "$RES" "$CHOICE_DEPTH" "$JUDGE_DEPTH" "$UNCERTAINTY_CP" <<'PY'
import json,sys
from pathlib import Path
report=Path(sys.argv[1]); summary=Path(sys.argv[2]); art=Path(sys.argv[3]); res=Path(sys.argv[4])
r=json.load(open(report))
r['source_evidence']={
 'mapper':'1417_exact_tanh_mapper',
 'corrected_models':'1427_exact_extras_models',
 'scalar_closure':'1428_force_plus_1430_readout',
 'scalar_baseline':'1341_CURRICULUM',
}
r['protocol']['choice_depth']=int(sys.argv[5])
r['protocol']['judge_depth']=int(sys.argv[6])
r['protocol']['uncertainty_band_cp']=int(sys.argv[7])
r['patterneval_fits_run']=0
r['new_selfplay']=0
r['strength_games_played']=0
r['frozen_cohorts_read']=0
r['promotion_authorized']=False
summary.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
verdict=r['verdict']
(art/f'VERDICT__{verdict}').touch()
(art/('NEXT_STAGE_AUTHORIZED__TRUE' if r['next_stage_authorized'] else 'NEXT_STAGE_AUTHORIZED__FALSE')).touch()
for marker in ('PATTERNEVAL_FITS_RUN__0','NEW_SELFPLAY__0','STRENGTH_GAMES_PLAYED__0',
               'FROZEN_COHORTS_READ__0','PROMOTION_AUTHORIZED__FALSE','CURRICULUM_SCALAR_UNCHANGED__TRUE'):
    (art/marker).touch()
gain=r['aligned_vs_shuffled_gain']
flip=r.get('aligned_flip_judge_gain') or {}
with res.open('a') as f:
    f.write(f"verdict={verdict}\n")
    f.write(f"uncertainty_rows={r['sample']['uncertainty_rows']} aligned_flips={r['sample']['aligned_flips']}\n")
    f.write(f"aligned_vs_shuffled_mean_cp={gain['mean_cp']:.6f} ci95={gain['ci95_cp']} p_positive={gain['probability_positive']:.6f}\n")
    if flip:
        f.write(f"aligned_flip_judge_mean_cp={flip['mean_cp']:.6f} ci95={flip['ci95_cp']}\n")
    f.write(f"guards={json.dumps(r['guards'],sort_keys=True)}\n")
PY

stage completed
say "completed read_only_ctx4_screen"

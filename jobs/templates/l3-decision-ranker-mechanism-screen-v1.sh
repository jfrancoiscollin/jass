#!/usr/bin/env bash
# Preregistered DCR1 mechanistic screen: learn the top-two move decision.
#
# CURRICULUM remains byte-identical and supplies both the depth-9 candidates and
# the depth-12/depth-14 direct pairwise labels.  The only fitted object is a
# small OOF audit ranker over child-context differences.  No PatternEval fit,
# self-play, strength game, frozen read, continuation or promotion occurs.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${SOURCE_1455_ROOT:?immutable completed 1455 R2 root required}"
: "${EXPECTED_1455_ATTEMPT:?immutable 1455 attempt required}"
: "${EXPECTED_1455_CODE_SHA:?immutable 1455 code SHA required}"
cd "$JASS_CODE_DIR"

CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"
CURRICULUM_CODE="18c38a33ae78c9c2e8e2df62fca266da28dacead"
CURRICULUM_ROOT="r2:jass-data/runs/$CURRICULUM_JOB/$CURRICULUM_ATTEMPT"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
SOURCE_1455_JOB="cpx62-1455-l3-replay-context30-target-gate-v1"

PER_POOL=512
TOTAL=1024
NSH=8
CHOICE_DEPTH=9
AUDIT_DEPTH=12
JUDGE_DEPTH=14
UNCERTAINTY_CP=40
JUDGE_DEADBAND_CP=8
SELECTION_SEED=2026082303
FOLDS=5
FOLD_SEED=2026082311
RIDGE=0.1
TARGET_CLIP_CP=200
SHUFFLE_SEED=2026082312
BOOTSTRAP_SEED=2026082313
BOOTSTRAP=100000
MIN_TOTAL=240
MIN_PER_POOL=80
MIN_POSITIVE=30
MIN_NEGATIVE=120
MIN_STABLE_FRACTION=0.65
MIN_INTERVENTIONS=20
MAX_INTERVENTION_RATE=0.35
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
: >"$RES"; : >"$PROG"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

MON=""
monitor(){
  ( t0=$(date +%s); while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
        printf 'shards_ready=%s/%s\n' "$(find "$SHARDS" -name 'shard-*.json' | wc -l)" "$NSH"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
      } >"$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 120
    done ) & MON="$!"
}
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$IN" "$GEOM" "$W/children-work" 2>/dev/null || true
  rm -f "$W/children.jnnw" "$W/children.ctx2.feat" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-decision-ranker-mechanism-screen-v1$ ]] || die "invalid job nomenclature"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic-continuation guard missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] || die "frozen-read guard missing"
[ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] || die "promotion guard missing"
[ "$EXPECTED_1455_CODE_SHA" = "a232e45991fbc35a156eacaa9a0586f1dd947d76" ] || die "1455 code SHA drift"
[ "$CHOICE_DEPTH" -lt "$AUDIT_DEPTH" ] && [ "$AUDIT_DEPTH" -lt "$JUDGE_DEPTH" ] || die "search-depth order drift"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
[ -f "$VENV_READY" ] || die "persistent numeric runtime absent"
PY="$VENV/bin/python"
"$PY" -c 'import numpy; assert numpy.__version__' || die "numeric runtime invalid"
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 6144 ] || die "less than 6 GiB free"
monitor
say "experiment=DCR1 issue=555 learning_object=deep_judge_top2_vs_top1"
say "source_pools=1455 per_pool=$PER_POOL choice=$CHOICE_DEPTH audit=$AUDIT_DEPTH judge=$JUDGE_DEPTH band_cp=$UNCERTAINTY_CP"

stage repository-contract-tests
python3 -m py_compile \
  jobs/tools/l3_decision_ranker_screen.py \
  jobs/tools/l3_context4_uncertainty_screen.py
"$PY" -m unittest \
  jobs.tests.test_l3_decision_ranker_screen \
  jobs.tests.test_l3_context4_uncertainty_screen >"$W/tests.log" 2>&1

fetch(){
  local root="$1" report="$2"; shift 2
  timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$root" "$@" \
    --out-dir "$IN" --report "$ART/$report" --expected-state completed
}

stage fetch-authenticate-curriculum-and-preregistered-1455-pools
fetch "$CURRICULUM_ROOT" verified-curriculum.json \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=curriculum-summary.json \
  >"$W/fetch-curriculum.log" 2>&1
fetch "$SOURCE_1455_ROOT" verified-1455.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=source-1455-summary.json \
  --file artefacts/pool-certificate.json=source-1455-pool-certificate.json \
  --file artefacts/replay-context30-target-pool1-openings.fen=pool1.fen \
  --file artefacts/replay-context30-target-pool2-openings.fen=pool2.fen \
  >"$W/fetch-1455.log" 2>&1

gunzip -t "$IN/curriculum.pjtw.gz"
gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
[ "$(sha256sum "$W/curriculum.pjtw" | awk '{print $1}')" = "$CURRICULUM_SHA" ] || die "CURRICULUM raw hash drift"

"$PY" - "$ART" "$IN" "$EXPECTED_1455_ATTEMPT" "$EXPECTED_1455_CODE_SHA" <<'PY_AUTH'
import hashlib,json,sys
from pathlib import Path
art,src=map(Path,sys.argv[1:3]); attempt,code=sys.argv[3:5]
def load(path): return json.load(open(path))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
cur=load(art/'verified-curriculum.json')
if (cur.get('job_id'),cur.get('attempt_id'),cur.get('code_sha'),cur.get('result_state'),cur.get('exit_code')) != (
 'cpx62-1341-jass-megacorpus-arm-d-fit-v1','20260814T191555Z-18c38a33','18c38a33ae78c9c2e8e2df62fca266da28dacead','completed',0):
 raise SystemExit('CURRICULUM source identity drift')
receipt=load(art/'verified-1455.json')
if (receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'),receipt.get('result_state'),receipt.get('exit_code')) != (
 'cpx62-1455-l3-replay-context30-target-gate-v1',attempt,code,'completed',0):
 raise SystemExit('1455 source identity/state drift')
summary=load(src/'source-1455-summary.json')
allowed={
 'JASS_REPLAY_CONTEXT30_TARGET_ESTABLISHED_POSITIVE',
 'JASS_REPLAY_CONTEXT30_TARGET_ESTABLISHED_NEGATIVE',
 'JASS_REPLAY_CONTEXT30_TARGET_NOT_ESTABLISHED',
}
if summary.get('verdict') not in allowed: raise SystemExit('1455 is not terminal')
if summary.get('games_total')!=24000 or summary.get('refits')!=1 or summary.get('new_selfplay')!=0 or summary.get('frozen_cohorts_read')!=0 or summary.get('promotion_authorized') is not False:
 raise SystemExit('1455 scientific scope drift')
pools=load(src/'source-1455-pool-certificate.json')
if pools.get('verdict')!='JASS_REPLAY_CONTEXT30_TWO_FRESH_POOLS_READY' or pools.get('mutually_disjoint') is not True or pools.get('all_historical_overlaps_zero') is not True or pools.get('historical_exclusion_count')!=23:
 raise SystemExit('1455 pool certificate drift')
rows=pools.get('pools') or []
if len(rows)!=2 or any(row.get('openings')!=3000 for row in rows): raise SystemExit('1455 pool cardinality drift')
for index,row in enumerate(rows,1):
 path=src/f'pool{index}.fen'
 if row.get('sha256')!=sha(path): raise SystemExit(f'1455 pool{index} hash drift')
 lines=[x for raw in path.read_text().splitlines() if (x:=raw.split('#',1)[0].strip())]
 if len(lines)!=3000 or len(set(lines))!=3000: raise SystemExit(f'1455 pool{index} row drift')
left={x for raw in (src/'pool1.fen').read_text().splitlines() if (x:=raw.split('#',1)[0].strip())}
right={x for raw in (src/'pool2.fen').read_text().splitlines() if (x:=raw.split('#',1)[0].strip())}
if left & right: raise SystemExit('1455 pools overlap')
PY_AUTH

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
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
  >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass jass_tests >"$W/build.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB \
  ctest --test-dir "$W/build" --output-on-failure >"$W/ctest.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || die "missing jass binary"
printf 'hello\nquit\n' | timeout 60 "$J" --pattern "$W/curriculum.pjtw" >"$W/load-curriculum.log" 2>&1
grep -q '^ready' "$W/load-curriculum.log" || die "CURRICULUM does not load"

stage deterministic-source-selection
"$PY" jobs/tools/l3_context4_uncertainty_screen.py prepare \
  --pool "POOL1=$IN/pool1.fen" --pool "POOL2=$IN/pool2.fen" \
  --per-pool "$PER_POOL" --seed "$SELECTION_SEED" \
  --out "$ART/selection.json" >"$W/selection.log" 2>&1
"$PY" - "$ART/selection.json" "$TOTAL" <<'PY_SELECTION'
import json,sys
row=json.load(open(sys.argv[1])); expected=int(sys.argv[2])
if row.get('total')!=expected or row.get('per_pool')*2!=expected: raise SystemExit('selection cardinality drift')
if len({x['ordinal'] for x in row.get('rows',[])})!=expected: raise SystemExit('selection ordinal drift')
PY_SELECTION

stage legal-child-enumeration
mkdir -p "$W/children-work"
"$PY" jobs/tools/l3_context4_uncertainty_screen.py children \
  --selection "$ART/selection.json" --jass "$J" --work-dir "$W/children-work" \
  --out-json "$ART/children.json" --out-jnnw "$W/children.jnnw" \
  >"$W/children.log" 2>&1

stage dedicated-child-context-features
"$J" --dump-conditional-context-v2 "$W/children.jnnw" "$W/children.ctx2.feat" \
  >"$W/context-features.log" 2>&1
"$PY" - "$ART/children.json" "$W/children.ctx2.feat" <<'PY_FEATURES'
import json,struct,sys
children=json.load(open(sys.argv[1])); path=sys.argv[2]
with open(path,'rb') as f:
 header=f.read(12)
if len(header)!=12 or header[:4]!=b'FEAT': raise SystemExit('context FEAT header drift')
count,width=struct.unpack('<II',header[4:])
if count!=children.get('child_count') or width!=30: raise SystemExit('context FEAT alignment/width drift')
PY_FEATURES

stage parallel-direct-decision-label-mining
pids=()
for shard in $(seq 0 $((NSH-1))); do
  timeout -k 60s 21600s "$PY" jobs/tools/l3_decision_ranker_screen.py worker \
    --selection "$ART/selection.json" --children "$ART/children.json" \
    --child-jnnw "$W/children.jnnw" --context-features "$W/children.ctx2.feat" \
    --jass "$J" --curriculum "$W/curriculum.pjtw" --search-params "$Q00" \
    --choice-depth "$CHOICE_DEPTH" --audit-depth "$AUDIT_DEPTH" \
    --judge-depth "$JUDGE_DEPTH" --uncertainty-cp "$UNCERTAINTY_CP" \
    --judge-deadband-cp "$JUDGE_DEADBAND_CP" \
    --shard "$shard" --nshards "$NSH" --out "$SHARDS/shard-$shard.json" \
    >"$W/worker-$shard.log" 2>&1 &
  pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done
[ "$(find "$SHARDS" -name 'shard-*.json' | wc -l)" -eq "$NSH" ] || die "missing decision-ranker shard"

stage out-of-fold-ranker-and-aligned-vs-shuffled-screen
args=()
for shard in $(seq 0 $((NSH-1))); do args+=(--shard "$SHARDS/shard-$shard.json"); done
"$PY" jobs/tools/l3_decision_ranker_screen.py aggregate \
  --selection "$ART/selection.json" --children "$ART/children.json" \
  --child-jnnw "$W/children.jnnw" --context-features "$W/children.ctx2.feat" \
  "${args[@]}" --folds "$FOLDS" --fold-seed "$FOLD_SEED" \
  --ridge "$RIDGE" --target-clip-cp "$TARGET_CLIP_CP" \
  --shuffle-seed "$SHUFFLE_SEED" --bootstrap-samples "$BOOTSTRAP" \
  --bootstrap-seed "$BOOTSTRAP_SEED" --min-total "$MIN_TOTAL" \
  --min-per-pool "$MIN_PER_POOL" --min-positive "$MIN_POSITIVE" \
  --min-negative "$MIN_NEGATIVE" --min-stable-fraction "$MIN_STABLE_FRACTION" \
  --min-interventions "$MIN_INTERVENTIONS" \
  --max-intervention-rate "$MAX_INTERVENTION_RATE" \
  --out "$ART/decision-ranker-mechanism-screen.json" >"$W/aggregate.log" 2>&1

stage publish-terminal-mechanistic-verdict
"$PY" - "$ART/decision-ranker-mechanism-screen.json" "$ART/JASS_CONTROL_SUMMARY.json" \
  "$ART" "$RES" "$EXPECTED_1455_ATTEMPT" "$EXPECTED_1455_CODE_SHA" \
  "$CHOICE_DEPTH" "$AUDIT_DEPTH" "$JUDGE_DEPTH" "$UNCERTAINTY_CP" \
  "$JUDGE_DEADBAND_CP" <<'PY_PUBLISH'
import json,sys
from pathlib import Path
report,summary,art,res=map(Path,sys.argv[1:5])
r=json.load(open(report))
r['source_evidence']={
 'source_pools':{'job':'cpx62-1455-l3-replay-context30-target-gate-v1','attempt':sys.argv[5],'code_sha':sys.argv[6]},
 'scalar_and_teacher':{'label':'CURRICULUM','job':'cpx62-1341-jass-megacorpus-arm-d-fit-v1','attempt':'20260814T191555Z-18c38a33','raw_sha256':'319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1'},
}
r['protocol'].update({
 'choice_depth':int(sys.argv[7]),'audit_depth':int(sys.argv[8]),'judge_depth':int(sys.argv[9]),
 'uncertainty_band_cp':int(sys.argv[10]),'judge_deadband_cp':int(sys.argv[11]),
 'source_pool_results_used_as_labels':False,
})
r['patterneval_fits_run']=0
r['ranker_fits_run']=6
r['new_selfplay']=0
r['strength_games_played']=0
r['frozen_cohorts_read']=0
r['promotion_authorized']=False
r['automatic_next_job']=None
summary.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
verdict=r['verdict']
(art/f'VERDICT__{verdict}').touch()
(art/('NEXT_STAGE_AUTHORIZED__TRUE' if r['next_stage_authorized'] else 'NEXT_STAGE_AUTHORIZED__FALSE')).touch()
for marker in (
 'PATTERNEVAL_FITS_RUN__0','RANKER_FITS_RUN__6','NEW_SELFPLAY__0',
 'STRENGTH_GAMES_PLAYED__0','FROZEN_COHORTS_READ__0',
 'PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_NEXT_JOB__NULL',
 'CURRICULUM_SCALAR_UNCHANGED__TRUE','SCAN_LABELS_READ__0',
):
 (art/marker).touch()
gain=r['aligned_vs_shuffled_gain']; flip=r.get('aligned_intervention_judge_gain') or {}
with res.open('a') as f:
 f.write(f"verdict={verdict}\n")
 f.write(f"uncertainty_pairs={r['sample']['uncertainty_pairs']} stable_pairs={r['sample']['stable_non_tie_pairs']} interventions={r['sample']['aligned_interventions']}\n")
 f.write(f"aligned_vs_shuffled_mean_cp={gain['mean_cp']:.6f} ci95={gain['ci95_cp']} p_positive={gain['probability_positive']:.6f}\n")
 if flip: f.write(f"aligned_intervention_gain_cp={flip['mean_cp']:.6f} ci95={flip['ci95_cp']}\n")
 f.write(f"guards={json.dumps(r['guards'],sort_keys=True)}\n")
PY_PUBLISH

stage completed
say "completed DCR1 mechanistic screen; no PatternEval fit, selfplay, force game or promotion"

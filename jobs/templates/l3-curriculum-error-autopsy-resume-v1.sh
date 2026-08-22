#!/usr/bin/env bash
# Resume the sealed CURRICULUM autopsy from 1468's authenticated selection.
# The 1,536 source games are not replayed.  This job performs only the original
# d10/d12 cost preflight, every-decision analysis and sealed aggregation.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
SHARDS="$ART/autopsy-shards"
mkdir -p "$W" "$IN" "$ART" "$SHARDS"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; : >"$PROG"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

SOURCE_JOB="cpx62-1468-l3-curriculum-error-autopsy-v1"
SOURCE_ATTEMPT="20260822T134756Z-746421c7"
SOURCE_CODE="746421c7b08fb907e5e116a6ab8f788425dc51ec"
SOURCE_ROOT="r2:jass-data/runs/$SOURCE_JOB/$SOURCE_ATTEMPT"
CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"
CURRICULUM_CODE="18c38a33ae78c9c2e8e2df62fca266da28dacead"
CURRICULUM_ROOT="r2:jass-data/runs/$CURRICULUM_JOB/$CURRICULUM_ATTEMPT"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
NSH=16
TEACHER_DEPTH=10
JUDGE_DEPTH=12
PREFLIGHT_ROWS_PER_SHARD=4
MAX_PROJECTED_MINUTES=480
CACHE_MB=128
MATCH_SEED=2026082216
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

MON=""
monitor(){
  ( t0=$(date +%s); while true; do
      {
        printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
        printf 'autopsy_shards=%s/16\n' "$(find "$SHARDS" -name 'shard-*.json' 2>/dev/null | wc -l)"
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
  rm -rf "$W/build" "$IN" "$W/preflight" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-autopsy-resume-v1$ ]] || die "invalid job nomenclature"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "execution GO missing"
[ "${NO_SELFPLAY:-0}" = 1 ] || die "self-play guard missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] || die "frozen-read guard missing"
[ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] || die "promotion guard missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guard missing"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
say "experiment=CURRICULUM_ERROR_AUTOPSY_RESUME source=$SOURCE_JOB/$SOURCE_ATTEMPT decisions=79110"
say "campaign_reused=1536 new_selfplay=0 teacher=d10 judge=d12 fit=0 promotion=false"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_curriculum_error_learning.py
python3 -m unittest jobs.tests.test_l3_curriculum_error_learning \
  jobs.tests.test_curriculum_error_seed_schedule >"$W/tests.log" 2>&1

stage fetch-authenticate-sealed-selection-and-curriculum
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$SOURCE_ROOT" \
  --file artefacts/error-selection.json=error-selection.json \
  --file artefacts/champion-certificate.json=champion-certificate.json \
  --file artefacts/search-params.txt=search-params.txt \
  --out-dir "$IN" --report "$ART/verified-1468-selection.json" --expected-state failed \
  >"$W/fetch-selection.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_ROOT" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=curriculum-summary.json \
  --out-dir "$IN" --report "$ART/verified-curriculum.json" --expected-state completed \
  >"$W/fetch-curriculum.log" 2>&1
gunzip -t "$IN/curriculum.pjtw.gz"
gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
printf '%s\n' "$Q00" >"$W/expected-search-params.txt"
cmp -s "$IN/search-params.txt" "$W/expected-search-params.txt" || die "search params differ from 1468"
cp "$IN/search-params.txt" "$ART/search-params.txt"
python3 - "$ART" "$IN" "$W" "$SOURCE_JOB" "$SOURCE_ATTEMPT" "$SOURCE_CODE" \
  "$CURRICULUM_SHA" <<'PY_AUTH'
import hashlib,json,sys
from pathlib import Path
art,src,work=map(Path,sys.argv[1:4]); source=tuple(sys.argv[4:7]); model_sha=sys.argv[7]
receipt=json.load(open(art/'verified-1468-selection.json'))
got=(receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'),receipt.get('result_state'),receipt.get('exit_code'))
if got!=(*source,'failed',1): raise SystemExit(f'1468 source identity drift: {got}')
selection=json.load(open(src/'error-selection.json')); split=selection.get('split',{})
if selection.get('schema')!='jass.l3_curriculum_error_selection.v1': raise SystemExit('selection schema drift')
if selection.get('games')!=1536 or selection.get('decisions')!=79110: raise SystemExit('selection cardinality drift')
if split.get('method')!='exact_state_components_sha256_parity' or split.get('leakage') is not False or split.get('exact_symmetry_state_overlap')!=0:
 raise SystemExit(f'sealed split drift: {split}')
if len(selection.get('sources',[]))!=1536: raise SystemExit('selection source manifest drift')
champ=json.load(open(src/'champion-certificate.json'))
if champ.get('model_raw_sha256')!=model_sha or champ.get('same_model_both_sides') is not True:
 raise SystemExit('champion certificate drift')
actual=hashlib.sha256((work/'curriculum.pjtw').read_bytes()).hexdigest()
if actual!=model_sha: raise SystemExit(f'CURRICULUM raw hash drift: {actual}')
(art/'resume-source-certificate.json').write_text(json.dumps({
 'schema':'jass.curriculum_error_resume_source.v1','verdict':'JASS_CURRICULUM_ERROR_SELECTION_REUSED',
 'source_job':source[0],'source_attempt':source[1],'source_code_sha':source[2],
 'selection_sha256':hashlib.sha256((src/'error-selection.json').read_bytes()).hexdigest(),
 'games':1536,'decisions':79110,'campaign_replayed':False,'new_selfplay_games':0,
 'champion_sha256':actual,'promotion_authorized':False},indent=2,sort_keys=True)+'\n')
PY_AUTH

stage build-current-exact-fold-tempo-engine
EGDIR=""
for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON \
  -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass jass_tests >"$W/build.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB ctest --test-dir "$W/build" --output-on-failure >"$W/ctest.log" 2>&1
J="$W/build/jass"
printf 'hello\nquit\n' | timeout 60 "$J" --pattern "$W/curriculum.pjtw" --search-params "$Q00" >"$W/load.log" 2>&1
grep -q '^ready' "$W/load.log" || die "CURRICULUM does not load"

stage depth10-depth12-cost-preflight
mkdir -p "$W/preflight"
T0=$(date +%s); pids=()
for shard in $(seq 0 $((NSH-1))); do
  python3 jobs/tools/l3_curriculum_error_learning.py worker --selection "$IN/error-selection.json" \
    --jass "$J" --champion "$W/curriculum.pjtw" --search-params "$ART/search-params.txt" \
    --teacher-depth "$TEACHER_DEPTH" --judge-depth "$JUDGE_DEPTH" --symmetry-rows 32 \
    --max-rows "$PREFLIGHT_ROWS_PER_SHARD" --shard "$shard" --nshards "$NSH" \
    --out "$W/preflight/shard-$shard.json" >"$W/preflight-$shard.log" 2>&1 & pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done
T1=$(date +%s)
python3 - "$IN/error-selection.json" "$W/preflight" "$ART/cost-preflight.json" "$((T1-T0))" \
  "$MAX_PROJECTED_MINUTES" <<'PY_COST'
import json,sys
from pathlib import Path
selection=Path(sys.argv[1]); root=Path(sys.argv[2]); out=Path(sys.argv[3])
elapsed=max(int(sys.argv[4]),1); maximum=int(sys.argv[5]); total=json.load(open(selection))['decisions']
shards=[json.load(open(p)) for p in root.glob('shard-*.json')]
rows=sum(len(row['rows']) for row in shards)
captures=sum(row['historical_move_resolution']['endpoint_only_captures'] for row in shards)
if rows!=64: raise SystemExit(f'cost preflight row drift: {rows}')
projected=elapsed*total/rows/60
payload={'schema':'jass.curriculum_error_cost_preflight.v1','sample_rows':rows,'total_decisions':total,
 'elapsed_seconds':elapsed,'projected_minutes':projected,'maximum_minutes':maximum,'passed':projected<=maximum,
 'historical_endpoint_only_captures_resolved':captures,'ambiguous':0,'unresolved':0}
out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
if projected>maximum: raise SystemExit(f'projected autopsy {projected:.1f} min exceeds {maximum}')
PY_COST

stage analyse-every-decision-depth10-depth12
pids=()
for shard in $(seq 0 $((NSH-1))); do
  python3 jobs/tools/l3_curriculum_error_learning.py worker --selection "$IN/error-selection.json" \
    --jass "$J" --champion "$W/curriculum.pjtw" --search-params "$ART/search-params.txt" \
    --teacher-depth "$TEACHER_DEPTH" --judge-depth "$JUDGE_DEPTH" --symmetry-rows 32 \
    --shard "$shard" --nshards "$NSH" --out "$SHARDS/shard-$shard.json" \
    >"$W/autopsy-$shard.log" 2>&1 & pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done
[ "$(find "$SHARDS" -name 'shard-*.json' | wc -l)" -eq "$NSH" ] || die "autopsy shard count drift"

stage aggregate-discovery-confirmation-and-publish-verdict
shard_args=(); for shard in $(seq 0 $((NSH-1))); do shard_args+=(--shard "$SHARDS/shard-$shard.json"); done
python3 jobs/tools/l3_curriculum_error_learning.py aggregate --selection "$IN/error-selection.json" \
  "${shard_args[@]}" --min-regret-cp 50 --max-control-regret-cp 10 \
  --min-error-openings 64 --min-discovery-hits 4 --discovery-risk-ratio 1.5 \
  --confirm-risk-ratio 1.5 --min-confirmed-buckets 8 --max-region-buckets 512 \
  --match-seed "$MATCH_SEED" --report "$ART/error-autopsy.json" \
  --region "$ART/error-region.json" --seeds "$ART/error-seeds.jnnw" >"$W/aggregate.log" 2>&1

python3 - "$ART" "$CURRICULUM_SHA" "$EXPECTED_CODE_SHA" <<'PY_FINAL'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); model_sha=sys.argv[2]; code=sys.argv[3]
report=json.load(open(art/'error-autopsy.json')); region=json.load(open(art/'error-region.json'))
if report['champion_sha256']!=model_sha or region['champion_sha256']!=model_sha: raise SystemExit('champion identity drift')
if report['verdict'] not in {'JASS_CURRICULUM_ERROR_REGION_CONFIRMED','JASS_CURRICULUM_ERROR_REGION_NOT_ESTABLISHED'}: raise SystemExit('verdict drift')
resolution=report.get('historical_move_resolution',{})
if resolution.get('passed') is not True or resolution.get('ambiguous')!=0 or resolution.get('unresolved')!=0: raise SystemExit('historical move resolution drift')
payload={**report,'schema':'jass.curriculum_error_autopsy_resume_terminal.v1','source_code_sha':code,
 'source_campaign':{'job_id':'cpx62-1468-l3-curriculum-error-autopsy-v1','attempt_id':'20260822T134756Z-746421c7',
  'games':1536,'all_trajectories_dumped':True,'selection_reused':True},
 'next_stage_authorized':bool(report['fit_authorized']),'next_stage':'repair_seed_catalogue' if report['fit_authorized'] else None,
 'new_selfplay_games':0,'new_fits':0,'new_strength_games':0,'frozen_cohorts_read':0,
 'promotion_authorized':False,'automatic_promotion':False}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY_FINAL
VERDICT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
: >"$ART/VERDICT__$VERDICT"; : >"$ART/CAMPAIGN_REPLAYED__FALSE"; : >"$ART/NEW_SELFPLAY__0"
: >"$ART/FITS__0"; : >"$ART/STRENGTH_GAMES__0"; : >"$ART/FROZEN_COHORTS_READ__0"
: >"$ART/PROMOTION_AUTHORIZED__FALSE"
stage completed
say "$VERDICT decisions=79110 source_games=1536 new_selfplay=0 fits=0 frozen=0 promotion=false"

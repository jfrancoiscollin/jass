#!/usr/bin/env bash
# One preregistered CTX2 B-vs-C force gate on a certified fresh pool.
# Native 0.1 s is primary; Q00 depth 9 is diagnostic. Models are reused.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${POOL_INDEX:?}"; : "${POOL_PREFIX:?}"; : "${POOL_JOB:?}"
: "${POOL_ATTEMPT:?}"; : "${POOL_CODE_SHA:?}"; : "${POOL_NAME:?}"; : "${POOL_SEED:?}"
: "${AUDIT_PREFIX:?}"; : "${AUDIT_JOB:?}"; : "${AUDIT_ATTEMPT:?}"; : "${AUDIT_CODE_SHA:?}"
cd "$JASS_CODE_DIR"

FIT_PREFIX="r2:jass-data/runs/home-1373-l3-context2-phase-tactical-fit-v1/20260816T214312Z-9e224d6e"
FIT_JOB="home-1373-l3-context2-phase-tactical-fit-v1"
FIT_ATTEMPT="20260816T214312Z-9e224d6e"
FIT_CODE_SHA="9e224d6ec7583d3c041755a35559bf559d380f8f"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"; FORCE="$ART/force"
mkdir -p "$W" "$IN" "$ART" "$GEOM" "$FORCE"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

NOPEN=3000; GAMES_PER_VIEW=6000; NSH=12; PAR=12
FORCE_DEPTH=9; MOVETIME=0.1; BOOTSTRAP=200000
BOOTSTRAP_SEED=$((2026081700 + POOL_INDEX)); CACHE_MB=128; ERROR_LIMIT=120
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
VENV_READY="$VENV/.jass-runtime-ready-v1"
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"

MON=""
monitor(){
 (t0=$(date +%s); while true; do
   { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
     printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
     printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
     printf 'completed_force_files=%s\n' "$(find "$FORCE" -type f -name '*.json' | wc -l)"
   } >"$PROG.tmp"; mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 120
  done) & MON="$!"
}
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e
 [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
 cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
 [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
 (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
 rm -rf "$W/build" "$IN" "$GEOM" "$W"/*.pjtw 2>/dev/null || true; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^(home|cpx62)-([0-9]+)-l3-context2-primary-pool([12])-v1$ ]] || die "invalid job nomenclature"
[ "${BASH_REMATCH[3]}" = "$POOL_INDEX" ] || die "pool index/job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(nproc)" -eq 16 ] || die "16-CPU box contract mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(tr ',' '\n' <<<"$Q00" | wc -l)" -eq 63 ] || die "Q00 drift"
[ -f "$VENV_READY" ] || die "persistent numeric runtime absent; do not reinstall"
PY="$VENV/bin/python"; "$PY" -c 'import numpy; assert numpy.__version__' || die "numeric runtime invalid"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/run_jass_gate_bounded.py jobs/tools/fetch_result_files.py
python3 -m unittest jobs.tests.test_l3_context2_phase_tactical_protocol \
  jobs.tests.test_l3_context2_primary_gate >"$W/tests.log" 2>&1

stage fetch-certified-models-audit-and-pool
python3 jobs/tools/fetch_result_files.py --prefix "$FIT_PREFIX" \
 --file artefacts/JASS_CONTROL_SUMMARY.json=models-summary.json \
 --file artefacts/aligned.pjtw.gz=B.pjtw.gz \
 --file artefacts/shuffled.pjtw.gz=C.pjtw.gz \
 --file artefacts/aligned-convergence.json=B-convergence.json \
 --file artefacts/shuffled-convergence.json=C-convergence.json \
 --out-dir "$IN" --report "$ART/verified-models.json" >"$W/fetch-models.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$AUDIT_PREFIX" \
 --file artefacts/JASS_CONTROL_SUMMARY.json=audit-summary.json \
 --out-dir "$IN" --report "$ART/verified-audit.json" >"$W/fetch-audit.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$POOL_PREFIX" \
 --file "artefacts/$POOL_NAME.fen=openings.fen" \
 --file "artefacts/$POOL_NAME.json=openings.json" \
 --file "artefacts/$POOL_NAME-provenance.json=openings-provenance.json" \
 --file artefacts/JASS_CONTROL_SUMMARY.json=pool-summary.json \
 --out-dir "$IN" --report "$ART/verified-pool.json" >"$W/fetch-pool.log" 2>&1

stage authenticate-inputs
"$PY" - "$IN" "$ART" "$FIT_JOB" "$FIT_ATTEMPT" "$FIT_CODE_SHA" \
 "$AUDIT_JOB" "$AUDIT_ATTEMPT" "$AUDIT_CODE_SHA" \
 "$POOL_JOB" "$POOL_ATTEMPT" "$POOL_CODE_SHA" "$POOL_NAME" "$POOL_SEED" "$POOL_INDEX" <<'PY'
import hashlib,json,sys
from pathlib import Path
src,art=map(Path,sys.argv[1:3])
def load(p): return json.loads(p.read_text(encoding='utf-8'))
def require(ok,msg):
 if not ok: raise SystemExit(msg)
def identity(path,job,attempt,code):
 r=load(path); got=(r.get('job_id'),r.get('attempt_id'),r.get('code_sha'),r.get('result_state'),r.get('exit_code'))
 require(got==(job,attempt,code,'completed',0),f'{job}: identity/state drift {got}')
identity(art/'verified-models.json',*sys.argv[3:6])
identity(art/'verified-audit.json',*sys.argv[6:9])
identity(art/'verified-pool.json',*sys.argv[9:12])
name,seed,index=sys.argv[12],int(sys.argv[13]),int(sys.argv[14])
models=load(src/'models-summary.json'); audit=load(src/'audit-summary.json'); pool=load(src/'pool-summary.json')
require(models.get('verdict')=='JASS_CONTEXT2_PHASE_TACTICAL_MODELS_READY','model verdict drift')
require(models.get('primary_contrast')=='B_vs_C_on_native_two_fresh_disjoint_opening_pools','primary contrast drift')
require(models.get('strength_games_played')==0 and models.get('promotion_authorized') is False,'fit scope drift')
require(audit.get('verdict')=='JASS_CONTEXT2_PHASE_TACTICAL_MODELS_AUDITED','audit verdict drift')
require(audit.get('identity_authenticated') is True and audit.get('symmetry_contract_tests_passed') is True,'audit contract drift')
require(audit.get('models_distinct') is True and audit.get('promotion_authorized') is False,'audit scope drift')
for key,name2 in [('B','B'),('C','C')]:
 conv=load(src/f'{name2}-convergence.json')
 require(conv.get('success') is True and float(conv.get('gradient_inf_norm',1))<=1e-4,f'{key}: convergence drift')
require(pool.get('verdict')=='BIG_OPENING_POOL_READY_3000' and pool.get('openings')==3000,'pool verdict/cardinality drift')
require(pool.get('pool_name')==name and len(pool.get('disjoint_from',[]))>=10,'pool identity/disjunction drift')
rows=[x for raw in (src/'openings.fen').read_text(encoding='utf-8').splitlines() if (x:=raw.split('#',1)[0].strip())]
manifest=load(src/'openings.json'); provenance=load(src/'openings-provenance.json')
digest=hashlib.sha256((src/'openings.fen').read_bytes()).hexdigest()
require(len(rows)==3000 and len(set(rows))==3000,'pool cardinality/uniqueness drift')
require(pool.get('sha256')==digest and manifest.get('sha256')==digest,'pool hash drift')
require(manifest.get('generator_seed')==seed and manifest.get('overlap_records')==0,'pool seed/overlap drift')
require(provenance.get('generator_seed')==seed and provenance.get('overlap_records')==0,'pool provenance drift')
receipt={'schema':'jass.context2.primary_inputs.v1','pool_index':index,
 'models_source':load(art/'verified-models.json'),'audit_source':load(art/'verified-audit.json'),
 'pool_source':load(art/'verified-pool.json'),'opening_sha256':digest,'openings':3000,
 'opening_seed':seed,'disjoint_from':sorted(pool['disjoint_from'])}
(art/'input-certificate.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
PY

for arm in B C; do gunzip -c "$IN/$arm.pjtw.gz" >"$W/$arm.pjtw"; done
"$PY" - "$IN/models-summary.json" "$W" "$ART/model-certificate.json" <<'PY'
import hashlib,json,sys
from pathlib import Path
s=json.load(open(sys.argv[1])); root=Path(sys.argv[2]); rows={}
for key,name in [('B','B'),('C','C')]:
 p=root/f'{name}.pjtw'; digest=hashlib.sha256(p.read_bytes()).hexdigest()
 if digest!=s['arms'][key]['model_raw_sha256']: raise SystemExit(f'{key}: raw hash drift')
 rows[key]=digest
if len(set(rows.values()))!=2: raise SystemExit('B/C models identical: empty causal gate')
json.dump({'schema':'jass.context2.primary_models.v1','models':rows,'distinct':True},open(sys.argv[3],'w'),indent=2,sort_keys=True)
open(sys.argv[3],'a').write('\n')
PY

stage build-common-certified-8cf-engine
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
for arm in B C; do
 printf 'hello\nquit\n' | timeout 60 "$J" --pattern "$W/$arm.pjtw" >"$W/load-$arm.log" 2>&1
 grep -q '^ready' "$W/load-$arm.log" || die "$arm model does not load"
done

run_gate(){
 local view="$1"; local budget=()
 [ "$view" = native ] && budget=(--movetime "$MOVETIME") || budget=(--depth "$FORCE_DEPTH")
 timeout -k 120s 25200s "$PY" jobs/tools/run_jass_gate_bounded.py \
  --jass "$J" --pattern-a "$W/B.pjtw" --pattern-b "$W/C.pjtw" \
  --search-params-a "$Q00" --search-params-b "$Q00" \
  --openings-file "$IN/openings.fen" "${budget[@]}" --pairs 1 \
  --max-plies 160 --nshards "$NSH" --max-parallel "$PAR" \
  --timeout 21600 --game-timeout 180 \
  --paired-bootstrap-samples "$BOOTSTRAP" --paired-bootstrap-seed "$BOOTSTRAP_SEED" \
  --work-dir "$W/gate-$view" --out "$FORCE/force-$view-B_vs_C-pool$POOL_INDEX.json" \
  >"$W/force-$view.log" 2>&1
}
for view in native q00; do
 stage "B-vs-C-pool$POOL_INDEX-$view-${GAMES_PER_VIEW}-games"
 run_gate "$view" || die "B-vs-C pool$POOL_INDEX/$view failed"
 say "B-vs-C pool$POOL_INDEX/$view complete n=$GAMES_PER_VIEW"
done

stage publish-single-pool-certificate
"$PY" - "$FORCE" "$ART" "$POOL_INDEX" "$BOOTSTRAP_SEED" <<'PY'
import json,math,sys
from pathlib import Path
force,art=map(Path,sys.argv[1:3]); index=int(sys.argv[3]); seed=int(sys.argv[4])
def require(ok,msg):
 if not ok: raise SystemExit(msg)
views={}
for view in ('native','q00'):
 raw=json.load(open(force/f'force-{view}-B_vs_C-pool{index}.json')); pair=raw.get('paired_opening',{})
 w,d,l=int(raw['wins_a']),int(raw['draws']),int(raw['wins_b']); rate=(w+0.5*d)/6000
 require(raw.get('complete') is True and raw.get('n')==6000 and w+d+l==6000,f'{view}: incomplete/WDL')
 require(math.isclose(float(raw['rate']),rate,abs_tol=5e-7) and math.isclose(float(pair['rate']),rate,abs_tol=1e-6),f'{view}: rate drift')
 require(pair.get('method')=='paired_colour_opening_cluster_bootstrap' and pair.get('n_openings')==3000,f'{view}: paired method drift')
 require(pair.get('games_per_opening')==2 and pair.get('bootstrap_samples')==200000 and pair.get('seed')==seed,f'{view}: bootstrap drift')
 require(len(pair.get('per_opening_scores',[]))==3000 and int(pair.get('error_draws',0))<=120,f'{view}: evidence/error drift')
 require(raw.get('pairs')==1 and raw.get('nshards')==12 and raw.get('max_parallel')==12,f'{view}: execution budget drift')
 require(raw.get('jass_a')==raw.get('jass_b') and Path(raw['pattern_a']).name=='B.pjtw' and Path(raw['pattern_b']).name=='C.pjtw',f'{view}: model/engine drift')
 require(raw.get('search_params_a')==raw.get('search_params_b') and len(raw.get('search_params_a','').split(','))==63,f'{view}: search drift')
 if view=='native': require(raw.get('depth') is None and math.isclose(float(raw.get('movetime')),0.1),'native budget drift')
 else: require(raw.get('depth')==9 and raw.get('movetime') is None,'q00 budget drift')
 views[view]={'wins':w,'draws':d,'losses':l,'n':6000,'rate':float(pair['rate']),
  'ci_low':float(pair['ci_low']),'ci_high':float(pair['ci_high']),
  'probability_rate_gt_half':float(pair['probability_rate_gt_half']),
  'error_draws':int(pair.get('error_draws',0))}
payload={'schema':'jass.context2.primary_single_pool.v1',
 'verdict':f'JASS_CONTEXT2_PRIMARY_POOL{index}_READY',
 'scientific_status':'SINGLE_POOL_MEASURED_PRIMARY_DECISION_REQUIRES_TWO_POOLS',
 'contrast':'B_vs_C','pool_index':index,'views':views,
 'protocol':{'primary_view':'native_movetime_0.1','diagnostic_view':'Q00_depth9',
  'openings':3000,'games_per_view':6000,'games_total':12000,'paired_colours':True,
  'paired_bootstrap_samples':200000,'paired_bootstrap_seed':seed,'max_error_fraction':0.02,
  'models_reused':True,'refits':0,'new_selfplay':0,'frozen_cohorts_read':0},
 'decision':{'primary_not_evaluated_until_both_pools':True,
  'single_pool_native_positive':views['native']['rate']>0.5,
  'single_pool_native_established_positive':views['native']['ci_low']>0.5,
  'q00_diagnostic_positive':views['q00']['rate']>0.5},
 'model_certificate':json.load(open(art/'model-certificate.json')),
 'input_certificate':json.load(open(art/'input-certificate.json')),
 'promotion_authorized':False,'automatic_next_job':None}
(art/f'primary-pool{index}-readout.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/f'VERDICT__JASS_CONTEXT2_PRIMARY_POOL{index}_READY').touch()
(art/'GAMES_TOTAL__12000').touch(); (art/'MODELS_REUSED__TRUE').touch(); (art/'REFITS__0').touch()
(art/'NEW_SELFPLAY__0').touch(); (art/'FROZEN_COHORTS_READ__0').touch()
(art/'PROMOTION_AUTHORIZED__FALSE').touch(); (art/'AUTOMATIC_NEXT_JOB__NULL').touch()
print(json.dumps(payload,sort_keys=True))
PY
say "JASS_CONTEXT2_PRIMARY_POOL${POOL_INDEX}_READY games=12000 refits=0 promotion=false"

#!/usr/bin/env bash
# Independent audit of the immutable CTX2 phase+tactical fit certificate.
# No fit, self-play, frozen read, force game, promotion or continuation.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
cd "$JASS_CODE_DIR"

FIT_PREFIX="r2:jass-data/runs/home-1373-l3-context2-phase-tactical-fit-v1/20260816T214312Z-9e224d6e"
FIT_JOB="home-1373-l3-context2-phase-tactical-fit-v1"
FIT_ATTEMPT="20260816T214312Z-9e224d6e"
FIT_CODE_SHA="9e224d6ec7583d3c041755a35559bf559d380f8f"
CTX1_PREFIX="r2:jass-data/runs/cpx62-1340-jass-megacorpus-comparative-fit-v1/20260814T123246Z-2ce07222"
CTX1_JOB="cpx62-1340-jass-megacorpus-comparative-fit-v1"
CTX1_ATTEMPT="20260814T123246Z-2ce07222"
CTX1_CODE_SHA="2ce07222f86c1468a1081fbdc53e9e17a0c5326e"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ say "phase=$1"; }
finalize(){ rc=$?; trap - EXIT ERR; set +e
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$IN" "$W"/*.pjtw 2>/dev/null || true; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^(home|cpx62)-([0-9]+)-l3-context2-phase-tactical-audit-v1$ ]] ||
  die "invalid job nomenclature"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(nproc)" -eq 16 ] || die "16-CPU box contract mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"

stage repository-and-symmetry-contracts
python3 -m py_compile jobs/tools/fetch_result_files.py jobs/tools/l3_conditional_targets.py \
  jobs/tools/verify_optimizer_convergence.py
python3 -m unittest jobs.tests.test_l3_context2_phase_tactical_protocol \
  jobs.tests.test_l3_context2_phase_tactical_audit >"$W/python-tests.log" 2>&1
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
# The CTest registry also contains smoke tests that invoke the engine binary;
# building only jass_tests makes those tests appear as missing executables.
cmake --build "$W/build" -j8 --target jass jass_tests >"$W/build.log" 2>&1
ctest --test-dir "$W/build" --output-on-failure >"$W/ctest.log" 2>&1

stage fetch-immutable-fit-and-ctx1-arm
python3 jobs/tools/fetch_result_files.py --prefix "$FIT_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=summary.json \
  --file artefacts/conditional-targets.json=targets.json \
  --file artefacts/split.json=split.json \
  --file artefacts/aligned-optimizer.json=aligned-optimizer.json \
  --file artefacts/aligned-convergence.json=aligned-convergence.json \
  --file artefacts/aligned-target-consumption.json=aligned-consumption.json \
  --file artefacts/aligned.pjtw.gz=aligned.pjtw.gz \
  --file artefacts/shuffled-optimizer.json=shuffled-optimizer.json \
  --file artefacts/shuffled-convergence.json=shuffled-convergence.json \
  --file artefacts/shuffled-target-consumption.json=shuffled-consumption.json \
  --file artefacts/shuffled.pjtw.gz=shuffled.pjtw.gz \
  --file artefacts/verified-turnover.json=verified-turnover.json \
  --file artefacts/verified-l2low.json=verified-l2low.json \
  --file artefacts/verified-ctx1.json=verified-ctx1.json \
  --out-dir "$IN" --report "$ART/verified-fit.json" >"$W/fetch-fit.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$CTX1_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=ctx1-summary.json \
  --file artefacts/current_2m.pjtw.gz=ctx1.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-ctx1-source.json" >"$W/fetch-ctx1.log" 2>&1

for arm in ctx1 aligned shuffled; do gunzip -c "$IN/$arm.pjtw.gz" >"$W/$arm.pjtw"; done

stage audit-identities-context-targets-and-models
python3 - "$IN" "$ART" "$FIT_JOB" "$FIT_ATTEMPT" "$FIT_CODE_SHA" \
  "$CTX1_JOB" "$CTX1_ATTEMPT" "$CTX1_CODE_SHA" <<'PY'
import hashlib,json,math,struct,sys
from pathlib import Path
src,art=map(Path,sys.argv[1:3])
def load(name): return json.loads((src/name).read_text(encoding='utf-8'))
def require(ok,msg):
 if not ok: raise SystemExit(msg)
def identity(name,job,attempt,code):
 r=json.loads((art/name).read_text(encoding='utf-8'))
 got=(r.get('job_id'),r.get('attempt_id'),r.get('code_sha'),r.get('result_state'),r.get('exit_code'))
 require(got==(job,attempt,code,'completed',0),f'{name}: identity/state drift {got}')
identity('verified-fit.json',*sys.argv[3:6])
identity('verified-ctx1-source.json',*sys.argv[6:9])

summary=load('summary.json'); targets=load('targets.json'); split=load('split.json')
require(summary.get('schema')=='jass.l3_context2_phase_tactical_models.v1','summary schema drift')
require(summary.get('verdict')=='JASS_CONTEXT2_PHASE_TACTICAL_MODELS_READY','fit verdict drift')
require(summary.get('code_sha')==sys.argv[5],'summary code drift')
require(summary.get('corpus')=='TURNOVER_CURRENT_2M' and summary.get('records')==2_000_000,'corpus drift')
require(summary.get('parent')=='L2LOW' and summary.get('architecture')=='8cf_exact_fold_tempo_120_extras','architecture drift')
require(summary.get('split')=={'seed':577215,'holdout_mod':10,'holdout_records':199204},'summary split drift')
recipe=summary.get('recipe',{})
require(recipe=={'alpha':0.3,'prior_mean':'L2LOW','prior_decay':0,'l2':1e-5,'gtol':1e-4,'max_iterations':2000},'recipe drift')
require(summary.get('primary_contrast')=='B_vs_C_on_native_two_fresh_disjoint_opening_pools','primary contrast drift')
require(summary.get('secondary_contrast')=='B_vs_A_only_if_B_vs_C_is_established_positive','secondary contrast drift')
require(summary.get('diagnostic_view')=='Q00_d9','diagnostic view drift')
require(summary.get('strength_games_played')==0 and summary.get('new_selfplay_generated') is False,'fit scope drift')
require(summary.get('frozen_cohorts_read')==0 and summary.get('promotion_authorized') is False,'frozen/promotion drift')
require(summary.get('automatic_next_job') is None,'automatic continuation drift')

require(split.get('records')==2_000_000 and split.get('holdout_records')==199_204,'split size drift')
require(targets.get('schema')=='jass.l3_conditional_targets.v2','target schema drift')
require(targets.get('context_schema')=='ctx2-phase-tactical-30' and targets.get('feature_width')==30,'CTX2 width drift')
require(targets.get('records')==2_000_000 and targets.get('holdout_records')==199_204,'target rows drift')
t=targets.get('target',{})
require(math.isclose(float(t.get('alpha',-1)),0.3) and t.get('output_pov')=='black','target alpha/POV drift')
require(t.get('exact_legal_move_context') is True and t.get('new_selfplay_generated') is False,'target source drift')
m=targets.get('mapping',{}); folds=m.get('folds',[]); matrix=m.get('matrix_diagnostics',{})
require(len(m.get('components',[]))==30 and m.get('fold_count')==5,'context dimensions/folds drift')
require(m.get('fold_group')=='opening_id' and m.get('row_weighting')=='game_equal','group/weights drift')
require(m.get('fold_local_rms') is True and m.get('each_game_total_weight_equal') is True,'RMS/weights drift')
require(m.get('all_games_fold_disjoint') is True and m.get('all_groups_fold_disjoint') is True,'fold disjunction drift')
require(m.get('train_holdout_game_overlap')==0 and m.get('train_holdout_group_overlap')==0,'holdout overlap drift')
require(len(folds)==5 and all(r.get('game_disjoint') and r.get('group_disjoint') and r.get('rms_fitted_on_training_rows_only') for r in folds),'per-fold isolation drift')
fits=[r.get('fit',{}) for r in folds]+[m.get('final_train_fit',{}).get('fit',{})]
require(all(r.get('converged') is True for r in fits),'conditional mapper convergence drift')
require(matrix.get('dimension')==30 and 0<int(matrix.get('effective_rank',0))<=30,'matrix rank drift')
require(len(matrix.get('weighted_feature_variance',[]))==30 and len(matrix.get('correlation',[]))==30,'matrix diagnostics drift')
s=targets.get('shuffle_control',{})
require(s.get('stratification')=='terminal_wdl_black_x_tempo_phase_4_bins','shuffle strata drift')
require(s.get('phase_bin_count')==4 and len(s.get('phase_bin_counts',{}))==4,'phase bins drift')
require(s.get('fixed_point_count')==0 and s.get('all_sources_within_same_cohort') is True,'shuffle source drift')
require(s.get('all_sources_within_same_fold') is True and s.get('all_sources_within_same_stratum') is True,'shuffle boundary drift')
require(s.get('all_cohort_fold_marginals_preserved') is True and s.get('all_final_target_marginals_preserved') is True,'target marginals drift')
cert=summary.get('target_certificate',{})
require(cert.get('aligned_sha256')==targets['outputs']['aligned_sha256'] and cert.get('shuffled_sha256')==targets['outputs']['shuffled_sha256'],'target hash certificate drift')

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def structure(path):
 magic,version,scale,npats,nextra=struct.unpack('<5I',path.read_bytes()[:20])
 require(magic==0x57544A50 and (version&0xff)==3 and scale>0,'PJTW header drift')
 require(npats==4_251_528 and nextra==120 and path.stat().st_size==20+8*(npats+nextra),'PJTW shape drift')
 return {'version':version,'scale':scale,'n_patterns':npats,'n_extras':nextra,'size_bytes':path.stat().st_size}
ctx1_source=load('ctx1-summary.json')
require(ctx1_source.get('verdict')=='JASS_MEGACORPUS_ABC_FITS_READY','CTX1 source verdict drift')
arms=summary.get('arms',{}); hashes={}
for key,name in [('A','ctx1'),('B','aligned'),('C','shuffled')]:
 p=Path(sys.argv[1]).parent/'work'/f'{name}.pjtw'
 # Work and input dirs are siblings under the result root.
 if not p.exists(): p=src.parent/'work'/f'{name}.pjtw'
 hashes[key]=sha(p); require(hashes[key]==arms[key]['model_raw_sha256'],f'{key}: raw model hash drift')
 require(structure(p)==arms[key]['structure'],f'{key}: model structure drift')
require(hashes['A']==ctx1_source['arms']['CURRENT_2M']['model_raw_sha256'],'A: CTX1 reuse drift')
require(len(set(hashes.values()))==3,'A/B/C models are not distinct')
for key,name in [('B','aligned'),('C','shuffled')]:
 require(sha(src/f'{name}.pjtw.gz')==arms[key]['model_gz_sha256'],f'{key}: gz model hash drift')
 conv=load(f'{name}-convergence.json'); opt=load(f'{name}-optimizer.json')
 require(conv.get('success') is True and conv.get('status')==0 and float(conv.get('gradient_inf_norm',1))<=1e-4,f'{key}: convergence drift')
 require(opt.get('success') is True and opt.get('status')==0 and int(opt.get('max_iterations',0))==2000 and int(opt.get('maxcor',0))==20,f'{key}: optimizer drift')
 require(float(opt.get('gtol',0))==1e-4 and float(opt.get('gradient_inf_norm',1))<=1e-4,f'{key}: optimizer gradient drift')
 consume=load(f'{name}-consumption.json')
 require(consume.get('operation')=='train_stream_external_targets','target consumption drift')
 require(consume['source']['sha256']==targets['outputs'][f'{name}_sha256'],'consumed target hash drift')
 require(consume['source']['dtype']=='float32' and consume['source']['shape']==[2_000_000],'consumed target shape drift')
 require(consume['split']['holdout_records']==199_204 and consume['split']['holdout_uses_external_targets'] is True,'holdout target drift')
 require(consume['validation']['finite'] is True and consume['validation']['clipping_applied'] is False,'target validation drift')

payload={'schema':'jass.l3_context2_phase_tactical_audit.v1',
 'verdict':'JASS_CONTEXT2_PHASE_TACTICAL_MODELS_AUDITED',
 'source':{'job_id':sys.argv[3],'attempt_id':sys.argv[4],'code_sha':sys.argv[5]},
 'identity_authenticated':True,'symmetry_contract_tests_passed':True,
 'context':{'dimensions':30,'effective_rank':matrix['effective_rank'],
  'high_abs_correlation_pairs_ge_0_98':matrix['high_absolute_correlation_pairs_ge_0_98'],
  'folds':5,'fold_group':'opening_id','fold_local_rms':True,'row_weighting':'game_equal',
  'all_mapper_fits_converged':True,'shuffle_stratification':s['stratification'],
  'fixed_points':0,'target_marginals_preserved':True},
 'models':{k:{'raw_sha256':v,'target':arms[k]['target']} for k,v in hashes.items()},
 'models_distinct':True,'fit_refits':2,'strength_games_played':0,'new_selfplay':0,
 'frozen_cohorts_read':0,'promotion_authorized':False,'automatic_next_job':None,
 'next_protocol':{'primary':'B_vs_C_native_on_two_fresh_disjoint_pools',
  'diagnostic':'B_vs_C_Q00_d9','secondary':'B_vs_A_only_after_primary_positive'}}
(art/'context2-model-audit.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/'VERDICT__JASS_CONTEXT2_PHASE_TACTICAL_MODELS_AUDITED').touch()
(art/'PROMOTION_AUTHORIZED__FALSE').touch(); (art/'AUTOMATIC_NEXT_JOB__NULL').touch()
print(json.dumps(payload,sort_keys=True))
PY
say "JASS_CONTEXT2_PHASE_TACTICAL_MODELS_AUDITED promotion=false automatic_next_job=null"

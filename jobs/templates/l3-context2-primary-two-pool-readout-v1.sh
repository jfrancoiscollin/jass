#!/usr/bin/env bash
# Hierarchical readout of the two preregistered CTX2 B-vs-C pools.
# Native 0.1 s decides whether the B-vs-A secondary gate may be measured.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${POOL1_GATE_PREFIX:?}"; : "${POOL1_GATE_JOB:?}"; : "${POOL1_GATE_ATTEMPT:?}"; : "${POOL1_GATE_CODE_SHA:?}"
: "${POOL2_GATE_PREFIX:?}"; : "${POOL2_GATE_JOB:?}"; : "${POOL2_GATE_ATTEMPT:?}"; : "${POOL2_GATE_CODE_SHA:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"; RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }; die(){ say "ABORT: $*"; exit 1; }; stage(){ say "phase=$1"; }
finalize(){ rc=$?; trap - EXIT ERR; set +e; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true; rm -rf "$IN" "$W" 2>/dev/null || true; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^(home|cpx62)-([0-9]+)-l3-context2-primary-two-pool-readout-v1$ ]] || die "invalid job nomenclature"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(nproc)" -eq 16 ] || die "16-CPU box contract mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
[ -f "$VENV/.jass-runtime-ready-v1" ] || die "persistent numeric runtime absent"
PY="$VENV/bin/python"

stage fetch-two-immutable-pool-gates
for index in 1 2; do
 eval "prefix=\$POOL${index}_GATE_PREFIX"
 python3 jobs/tools/fetch_result_files.py --prefix "$prefix" \
  --file artefacts/JASS_CONTROL_SUMMARY.json="pool${index}-summary.json" \
  --file artefacts/model-certificate.json="pool${index}-models.json" \
  --file artefacts/input-certificate.json="pool${index}-inputs.json" \
  --file "artefacts/force/force-native-B_vs_C-pool${index}.json=pool${index}-native.json" \
  --file "artefacts/force/force-q00-B_vs_C-pool${index}.json=pool${index}-q00.json" \
  --out-dir "$IN" --report "$ART/verified-pool${index}-gate.json" >"$W/fetch-pool${index}.log" 2>&1
done

stage authenticate-combine-and-decide
"$PY" - "$IN" "$ART" \
 "$POOL1_GATE_JOB" "$POOL1_GATE_ATTEMPT" "$POOL1_GATE_CODE_SHA" \
 "$POOL2_GATE_JOB" "$POOL2_GATE_ATTEMPT" "$POOL2_GATE_CODE_SHA" <<'PY'
import json,math,sys
from pathlib import Path
import numpy as np
src,art=map(Path,sys.argv[1:3])
def load(name): return json.loads((src/name).read_text(encoding='utf-8'))
def require(ok,msg):
 if not ok: raise SystemExit(msg)
def identity(index,job,attempt,code):
 r=json.loads((art/f'verified-pool{index}-gate.json').read_text())
 got=(r.get('job_id'),r.get('attempt_id'),r.get('code_sha'),r.get('result_state'),r.get('exit_code'))
 require(got==(job,attempt,code,'completed',0),f'pool{index}: identity/state drift {got}')
identity(1,*sys.argv[3:6]); identity(2,*sys.argv[6:9])
summaries=[load(f'pool{i}-summary.json') for i in (1,2)]
models=[load(f'pool{i}-models.json') for i in (1,2)]
inputs=[load(f'pool{i}-inputs.json') for i in (1,2)]
for i,s in enumerate(summaries,1):
 require(s.get('verdict')==f'JASS_CONTEXT2_PRIMARY_POOL{i}_READY',f'pool{i}: verdict drift')
 require(s.get('contrast')=='B_vs_C' and s.get('pool_index')==i,f'pool{i}: contrast/index drift')
 p=s.get('protocol',{})
 require(p.get('primary_view')=='native_movetime_0.1' and p.get('diagnostic_view')=='Q00_depth9',f'pool{i}: view drift')
 require(p.get('openings')==3000 and p.get('games_total')==12000 and p.get('models_reused') is True,f'pool{i}: budget drift')
 require(p.get('refits')==0 and p.get('new_selfplay')==0 and p.get('frozen_cohorts_read')==0,f'pool{i}: scope drift')
 require(s.get('promotion_authorized') is False and s.get('automatic_next_job') is None,f'pool{i}: promotion drift')
require(models[0]==models[1] and models[0].get('distinct') is True,'B/C model identity drift across pools')
require(inputs[0]['opening_sha256']!=inputs[1]['opening_sha256'],'opening pools are identical')
require('pool-context2-primary-first3000' in inputs[1]['disjoint_from'],'pool2 is not certified disjoint from pool1')

def evidence(index,view):
 raw=load(f'pool{index}-{view}.json'); pair=raw.get('paired_opening',{})
 scores=np.asarray(pair.get('per_opening_scores',[]),dtype=np.float64)
 require(raw.get('complete') is True and raw.get('n')==6000 and scores.shape==(3000,),f'pool{index}/{view}: evidence drift')
 require(np.all(np.isin(scores,[0,.25,.5,.75,1.])),f'pool{index}/{view}: score support drift')
 require(math.isclose(float(scores.mean()),float(pair['rate']),abs_tol=1e-12),f'pool{index}/{view}: paired rate drift')
 return raw,pair,scores

def combine(view,seed):
 rows=[evidence(i,view) for i in (1,2)]; scores=[x[2] for x in rows]
 means=[float(x.mean()) for x in scores]
 ses=[float(x.std(ddof=1)/math.sqrt(len(x))) for x in scores]
 denom=math.sqrt(ses[0]**2+ses[1]**2)
 z=0.0 if denom==0 and means[0]==means[1] else (math.inf if denom==0 else (means[0]-means[1])/denom)
 compatible=abs(z)<=1.959963984540054
 rng=np.random.default_rng(seed); samples=200_000; chunk=500; boot=np.empty(samples,dtype=np.float64)
 done=0
 while done<samples:
  take=min(chunk,samples-done)
  left=scores[0][rng.integers(0,3000,size=(take,3000))].mean(axis=1)
  right=scores[1][rng.integers(0,3000,size=(take,3000))].mean(axis=1)
  boot[done:done+take]=0.5*(left+right); done+=take
 combined=float(np.concatenate(scores).mean())
 return {'pool_rates':means,'pool_standard_errors':ses,'inter_pool_z':float(z),
  'inter_pool_compatible_95':compatible,'rate':combined,
  'ci_low':float(np.quantile(boot,.025)),'ci_high':float(np.quantile(boot,.975)),
  'probability_rate_gt_half':float(np.mean(boot>.5)),
  'bootstrap_samples':samples,'bootstrap_seed':seed,'openings':6000,'games':12000}

native=combine('native',2026081703); q00=combine('q00',2026081704)
primary=(all(x>.5 for x in native['pool_rates']) and native['inter_pool_compatible_95']
         and native['ci_low']>.5 and native['probability_rate_gt_half']>=.975)
verdict=('JASS_CONTEXT2_B_VS_C_ESTABLISHED_POSITIVE' if primary
         else 'JASS_CONTEXT2_B_VS_C_NOT_ESTABLISHED')
payload={'schema':'jass.context2.primary_two_pool_readout.v1','verdict':verdict,
 'scientific_status':verdict,'contrast':'B_vs_C','primary_view':'native_movetime_0.1',
 'native':native,'q00_d9_diagnostic':q00,
 'decision':{'both_native_pool_points_positive':all(x>.5 for x in native['pool_rates']),
  'native_inter_pool_compatible_95':native['inter_pool_compatible_95'],
  'combined_native_ci_excludes_half':native['ci_low']>.5,
  'combined_native_probability_ge_0_975':native['probability_rate_gt_half']>=.975,
  'primary_established_positive':primary,
  'secondary_B_vs_A_measurement_authorized':primary},
 'protocol':{'two_fresh_disjoint_pools':True,'openings_total':6000,
  'native_games_total':12000,'q00_diagnostic_games_total':12000,'games_total':24000,
  'models_reused':True,'refits':0,'new_selfplay':0,'frozen_cohorts_read':0},
 'sources':[json.loads((art/f'verified-pool{i}-gate.json').read_text()) for i in (1,2)],
 'model_certificate':models[0],'promotion_authorized':False,'automatic_next_job':None}
(art/'primary-two-pool-readout.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/f'VERDICT__{verdict}').touch(); (art/'GAMES_TOTAL__24000').touch()
(art/'REFITS__0').touch(); (art/'NEW_SELFPLAY__0').touch(); (art/'FROZEN_COHORTS_READ__0').touch()
(art/'PROMOTION_AUTHORIZED__FALSE').touch(); (art/'AUTOMATIC_NEXT_JOB__NULL').touch()
(art/('SECONDARY_B_VS_A_AUTHORIZED__TRUE' if primary else 'SECONDARY_B_VS_A_AUTHORIZED__FALSE')).touch()
print(json.dumps(payload,sort_keys=True))
PY
say "CTX2 two-pool primary readout ready; no promotion or automatic continuation"

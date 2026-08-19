#!/usr/bin/env bash
# Read-only terminal audit of the preregistered CTX3 two-pool force gate.
# Recomputes the published 1419 readout from its four immutable raw gate files
# and exposes all decision metrics as status-visible marker filenames.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
cd "$JASS_CODE_DIR"

SOURCE_JOB="cpx62-1419-l3-context3-two-pool-force-v1"
SOURCE_ATTEMPT="20260819T112556Z-8adc506a"
SOURCE_CODE_SHA="8adc506a8ec95b1f170bc706def1fe052eca0d98"
SOURCE_PREFIX="r2:jass-data/runs/$SOURCE_JOB/$SOURCE_ATTEMPT"

W="$JASS_RESULT_DIR/work"
IN="$JASS_RESULT_DIR/inputs"
ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
RES="$W/RESULTS.txt"
: >"$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
finalize(){ rc=$?; trap - EXIT ERR; set +e
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  rm -rf "$IN" "$W" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-context3-terminal-audit-v1$ ]] || die "invalid job nomenclature"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(nproc)" -eq 16 ] || die "16-CPU CPX contract mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"

VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
[ -f "$VENV/.jass-runtime-ready-v1" ] || die "persistent numeric runtime absent; do not reinstall"
PY="$VENV/bin/python"
"$PY" -c 'import numpy; assert numpy.__version__' || die "numeric runtime invalid"

say "phase=fetch-and-authenticate-immutable-1419"
python3 jobs/tools/fetch_result_files.py --prefix "$SOURCE_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=source-summary.json \
  --file artefacts/model-certificate.json=model-certificate.json \
  --file artefacts/pool-certificate.json=pool-certificate.json \
  --file artefacts/force/pool1-native.json=pool1-native.json \
  --file artefacts/force/pool1-q00.json=pool1-q00.json \
  --file artefacts/force/pool2-native.json=pool2-native.json \
  --file artefacts/force/pool2-q00.json=pool2-q00.json \
  --out-dir "$IN" --report "$ART/verified-source-1419.json" --expected-state completed \
  >"$W/fetch.log" 2>&1 || die "1419 fetch failed"

say "phase=recompute-exact-readout"
"$PY" jobs/tools/l3_context3_two_pool_force_readout.py \
  --pool1-native "$IN/pool1-native.json" --pool1-q00 "$IN/pool1-q00.json" \
  --pool2-native "$IN/pool2-native.json" --pool2-q00 "$IN/pool2-q00.json" \
  --pool-certificate "$IN/pool-certificate.json" \
  --model-certificate "$IN/model-certificate.json" \
  --gate-bootstrap-seed-pool1 2026081909 \
  --gate-bootstrap-seed-pool2 2026081910 \
  --combined-native-seed 2026081911 --combined-q00-seed 2026081912 \
  --bootstrap-samples 200000 --out "$ART/recomputed-1419-readout.json" \
  >"$W/recompute.log" 2>&1 || die "1419 readout recomputation failed"

say "phase=audit-classify-and-publish"
"$PY" - "$IN" "$ART" "$SOURCE_JOB" "$SOURCE_ATTEMPT" "$SOURCE_CODE_SHA" <<'PY'
import hashlib,json,math,sys
from pathlib import Path

src,art=map(Path,sys.argv[1:3]); expected=tuple(sys.argv[3:6])
def load(path): return json.loads(path.read_text(encoding='utf-8'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def require(ok,msg):
 if not ok: raise SystemExit(msg)
def token(value):
 return f'{float(value):.6f}'.replace('-','m').replace('.','p')

receipt=load(art/'verified-source-1419.json')
got=(receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'))
require(got==expected,f'1419 identity drift: {got}')
require(receipt.get('result_state')=='completed' and receipt.get('exit_code')==0,'1419 completion drift')
source=load(src/'source-summary.json')
recomputed=load(art/'recomputed-1419-readout.json')
require(source==recomputed,'1419 source summary differs from exact raw-evidence recomputation')
require(source.get('schema')=='jass.l3_context3_two_pool_force_readout.v1','1419 schema drift')
require(source.get('verdict')=='JASS_CONTEXT3_ALIGNED_VS_SHUFFLED_NOT_ESTABLISHED','1419 verdict drift')
require(source.get('contrast')=='CTX3_ALIGNED_vs_CTX3_SHUFFLED','1419 contrast drift')
require(source.get('primary_view')=='native_movetime_0.1','1419 primary view drift')
require(source.get('diagnostic_view')=='Q00_depth9','1419 diagnostic view drift')
require(source.get('pool_certificate')==load(src/'pool-certificate.json'),'1419 pool certificate mismatch')
require(source.get('model_certificate')==load(src/'model-certificate.json'),'1419 model certificate mismatch')
require(source['pool_certificate'].get('mutually_disjoint') is True,'1419 pools not disjoint')
require(source['pool_certificate'].get('all_historical_overlaps_zero') is True,'1419 historical pool overlap drift')
require(source['model_certificate'].get('distinct') is True,'1419 model distinction drift')
require(source['model_certificate'].get('reused_without_refit') is True,'1419 model reuse drift')
p=source.get('protocol') or {}
require(p=={'two_fresh_disjoint_pools':True,'openings_total':6000,
 'native_games_total':12000,'q00_diagnostic_games_total':12000,'games_total':24000,
 'paired_colours':True,'models_reused':True,'refits':0,'new_selfplay':0,
 'frozen_cohorts_read':0},'1419 protocol drift')
require(source.get('promotion_authorized') is False and source.get('automatic_next_job') is None,
 '1419 promotion/continuation drift')

evidence=source.get('per_pool_evidence') or {}
for pool in ('pool1','pool2'):
 for view in ('native','q00'):
  row=evidence[pool][view]
  w,d,l=(int(row[k]) for k in ('wins','draws','losses'))
  require(w+d+l==6000,f'{pool}/{view}: WDL drift')
  require(math.isclose((w+0.5*d)/6000,float(row['rate']),abs_tol=1e-12),f'{pool}/{view}: rate drift')
  require(int(row.get('error_draws',0))<=120,f'{pool}/{view}: error limit drift')
  raw=src/f'{pool}-{view}.json'
  require(sha(raw)==row['raw_sha256'],f'{pool}/{view}: raw hash drift')
  (art/f'{pool.upper()}_{view.upper()}_WDL__{w}_{d}_{l}').touch()
  (art/f'{pool.upper()}_{view.upper()}_RATE__{token(row["rate"])}').touch()
  (art/f'{pool.upper()}_{view.upper()}_CI95__{token(row["ci_low"])}__{token(row["ci_high"])}').touch()
  (art/f'{pool.upper()}_{view.upper()}_ERROR_DRAWS__{int(row.get("error_draws",0))}').touch()

native=source['native']; q00=source['q00_d9_diagnostic']; decision=source['decision']
require(native.get('bootstrap_samples')==200000 and native.get('bootstrap_seed')==2026081911,
 'native combined bootstrap drift')
require(q00.get('bootstrap_samples')==200000 and q00.get('bootstrap_seed')==2026081912,
 'Q00 combined bootstrap drift')
require(decision.get('q00_can_override_primary') is False,'Q00 override drift')
require(decision.get('primary_established_positive') is False,'unexpected positive primary decision')

if not decision['both_native_pool_points_positive']:
 classification=('BOTH_NATIVE_POINT_ESTIMATES_NONPOSITIVE'
  if all(float(x)<=0.5 for x in native['pool_rates']) else 'ONE_NATIVE_POOL_NONPOSITIVE')
elif not decision['native_inter_pool_compatible_95']:
 classification='NATIVE_INTER_POOL_HETEROGENEITY'
elif not decision['combined_native_ci_excludes_half']:
 classification='COMBINED_NATIVE_NEUTRAL'
elif not decision['combined_native_probability_ge_0_975']:
 classification='COMBINED_NATIVE_PROBABILITY_BELOW_GATE'
else:
 classification='PREREGISTERED_GATE_FAILURE_OTHER'

payload={
 'schema':'jass.l3_context3_terminal_audit.v1',
 'verdict':'JASS_CONTEXT3_TERMINAL_AUDIT_READY',
 'source_verdict':source['verdict'],
 'scientific_conclusion':'CTX3_INDEPENDENT_INFORMATION_CONFIRMED_BUT_PATTERN_EVAL_FORCE_NOT_ESTABLISHED',
 'classification':classification,
 'source':receipt,
 'source_summary_sha256':sha(src/'source-summary.json'),
 'raw_readout_recomputed_exactly':True,
 'per_pool_evidence':evidence,
 'native':native,
 'q00_d9_diagnostic':q00,
 'decision':decision,
 'protocol':p,
 'pool_certificate':source['pool_certificate'],
 'model_certificate':source['model_certificate'],
 'promotion_authorized':False,
 'automatic_next_job':None,
}
(art/'context3-terminal-audit.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n',encoding='utf-8')
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n',encoding='utf-8')
(art/'VERDICT__JASS_CONTEXT3_TERMINAL_AUDIT_READY').touch()
(art/f'SOURCE_VERDICT__{source["verdict"]}').touch()
(art/f'CLASSIFICATION__{classification}').touch()
for label,row in (('NATIVE',native),('Q00',q00)):
 (art/f'{label}_COMBINED_RATE__{token(row["rate"])}').touch()
 (art/f'{label}_COMBINED_CI95__{token(row["ci_low"])}__{token(row["ci_high"])}').touch()
 (art/f'{label}_COMBINED_P_GT_HALF__{token(row["probability_rate_gt_half"])}').touch()
 (art/f'{label}_INTER_POOL_Z__{token(row["inter_pool_z"])}').touch()
(art/'SOURCE_GAMES_AUDITED__24000').touch()
(art/'GAMES_REPLAYED__0').touch(); (art/'REFITS__0').touch(); (art/'NEW_SELFPLAY__0').touch()
(art/'FROZEN_COHORTS_READ__0').touch(); (art/'PROMOTION_AUTHORIZED__FALSE').touch()
(art/'AUTOMATIC_NEXT_JOB__NULL').touch(); (art/'RAW_READOUT_RECOMPUTED_EXACTLY__TRUE').touch()
print(json.dumps(payload,sort_keys=True))
PY

say "JASS_CONTEXT3_TERMINAL_AUDIT_READY; read-only audit complete"


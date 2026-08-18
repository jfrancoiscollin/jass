#!/usr/bin/env bash
# Build the preregistered D-optimal CTX2-Intervention-v1 corpus plan from the
# authenticated paired-seed knob pilot and fixed CURRENT_2M contribution audit.
# Read-only planning: no self-play, fit, force game, frozen read or promotion.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; : >"$PROG"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; cp "$STAGE" "$ART/STAGE.txt"; }
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  for log in "$W"/*.log; do
    [ -f "$log" ] && cp "$log" "$ART/$(basename "$log")"
  done
  if [ "$rc" -ne 0 ]; then
    python3 - "$ART" <<'PY' || true
import re
import sys
from pathlib import Path

artefacts = Path(sys.argv[1])
for log in sorted(artefacts.glob("*.log")):
    lines = [
        line.strip()
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip()
    ]
    for index, line in enumerate(lines[-20:]):
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", line).strip("_")[:160] or "EMPTY"
        (artefacts / f"FAILTRACE__{log.stem}__{index:02d}__{slug}").touch()
PY
  fi
  rm -rf "$IN" "$W" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

ATTRIBUTION_ROOT="r2:jass-data/runs/home-1395-l3-context2-knob-attribution-v1/20260817T211534Z-f4e9fe1e"
ATTRIBUTION_JOB="home-1395-l3-context2-knob-attribution-v1"
ATTRIBUTION_ATTEMPT="20260817T211534Z-f4e9fe1e"
ATTRIBUTION_CODE="f4e9fe1ef103fb52e7e3a2c10e967bc736e934f7"
CONTRIBUTION_ROOT="r2:jass-data/runs/home-1397-l3-context2-fixed-contribution-audit-v1/20260817T222724Z-f60336ca"
CONTRIBUTION_JOB="home-1397-l3-context2-fixed-contribution-audit-v1"
CONTRIBUTION_ATTEMPT="20260817T222724Z-f60336ca"
CONTRIBUTION_CODE="f60336ca7b29e976e14c47eba92223fedd30eebf"
CELLS="BASE BASEBIS ROP16 EPS16 DECAY120 NODECAY TOPK3M30 DEPTH10"
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-([0-9]+)-l3-context2-intervention-plan-v1$ ]] ||
  die "invalid job nomenclature"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "explicit execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ -f "$VENV/.jass-runtime-ready-v1" ] || die "persistent numeric runtime absent; do not reinstall"
PY="$VENV/bin/python"; "$PY" -c 'import numpy; assert numpy.__version__' || die "NumPy runtime invalid"
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 3072 ] || die "less than 3 GiB free ($DFA MiB)"
say "host=$(hostname) nproc=$(nproc) free_mb=$DFA mode=ctx2_intervention_plan eta_minutes=10"

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_context2_intervention_plan.py
"$PY" -m unittest jobs.tests.test_l3_context2_intervention_plan \
  jobs.tests.test_l3_context2_intervention_plan_template >"$W/tests.log" 2>&1

stage fetch-authenticated-pilot-and-current-diagnosis
fetch_args=(--file artefacts/JASS_CONTROL_SUMMARY.json=attribution-summary.json)
for cell in $CELLS; do
  fetch_args+=(--file "artefacts/cells/$cell-activation.json=$cell-activation.json")
done
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$ATTRIBUTION_ROOT" \
  "${fetch_args[@]}" --out-dir "$IN" --report "$ART/verified-attribution.json" \
  --expected-state completed >"$W/fetch-attribution.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CONTRIBUTION_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=contribution-summary.json \
  --file artefacts/fixed-current2m-contribution-audit.json=contribution-audit.json \
  --out-dir "$IN" --report "$ART/verified-contribution.json" \
  --expected-state completed >"$W/fetch-contribution.log" 2>&1

"$PY" - "$ART" "$IN" <<'PY'
import json,sys
from pathlib import Path
art,src=map(Path,sys.argv[1:3])
expected={
 'verified-attribution.json':('home-1395-l3-context2-knob-attribution-v1',
  '20260817T211534Z-f4e9fe1e','f4e9fe1ef103fb52e7e3a2c10e967bc736e934f7'),
 'verified-contribution.json':('home-1397-l3-context2-fixed-contribution-audit-v1',
  '20260817T222724Z-f60336ca','f60336ca7b29e976e14c47eba92223fedd30eebf')}
for name,identity in expected.items():
 row=json.load(open(art/name)); got=(row.get('job_id'),row.get('attempt_id'),row.get('code_sha'))
 if got!=identity or row.get('result_state')!='completed' or row.get('exit_code')!=0:
  raise SystemExit(f'{name}: source identity/state drift {got}')
a=json.load(open(src/'attribution-summary.json'))
c=json.load(open(src/'contribution-summary.json'))
if a.get('verdict')!='JASS_CONTEXT2_KNOB_ATTRIBUTION_READY' or a.get('records_per_cell')!=250000:
 raise SystemExit('attribution source contract drift')
if c.get('verdict')!='JASS_CONTEXT2_FIXED_CONTRIBUTION_AUDITED':
 raise SystemExit('contribution source contract drift')
if c.get('new_selfplay_generated') or c.get('fits_run') or c.get('frozen_read'):
 raise SystemExit('contribution source scope drift')
PY

stage enumerate-preregistered-D-optimal-mixture
cell_args=()
for cell in $CELLS; do cell_args+=(--cell "$cell=$IN/$cell-activation.json"); done
timeout 600s "$PY" jobs/tools/l3_context2_intervention_plan.py \
  --attribution-summary "$IN/attribution-summary.json" \
  --contribution-audit "$IN/contribution-audit.json" "${cell_args[@]}" \
  --total-records 2000000 --weight-step 0.05 \
  --min-base-weight 0.15 --min-intervention-weight 0.05 --max-cell-weight 0.30 \
  --max-relative-draw-shift 0.15 --max-wdl-side-skew 0.02 \
  --tempo-mid-min 0.45 --tempo-mid-max 0.55 \
  --output "$ART/context2-intervention-plan.json" >"$W/plan.log" 2>&1

stage publish-plan-certificate
"$PY" - "$ART" "$EXPECTED_CODE_SHA" <<'PY' | tee -a "$RES"
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); code=sys.argv[2]
plan=json.load(open(art/'context2-intervention-plan.json'))
if plan.get('verdict')!='JASS_CONTEXT2_INTERVENTION_PLAN_READY':
 raise SystemExit(f"design did not authorize generation: {plan.get('verdict')}")
corpus=plan['corpus']; predicted=plan['predicted_design']; constraints=plan['constraints']
if corpus['target_records']!=2000000 or sum(corpus['record_quotas'].values())!=2000000:
 raise SystemExit('record quota drift')
if set(corpus['weights'])!={'BASE','ROP16','EPS16','DECAY120','TOPK3M30','DEPTH10'}:
 raise SystemExit('generator cell set drift')
if 'NODECAY' in corpus['weights'] or predicted['logdet_gain_vs_base']<=0:
 raise SystemExit('invalid D-optimal design')
if predicted['relative_draw_shift_vs_base']>constraints['maximum_relative_draw_shift_vs_base']:
 raise SystemExit('draw shift guard drift')
if predicted['wdl_side_skew']>constraints['maximum_wdl_side_skew']:
 raise SystemExit('WDL side skew guard drift')
payload={'schema':'jass.l3_context2_intervention_plan_job.v1',
 'verdict':'JASS_CONTEXT2_INTERVENTION_PLAN_READY','code_sha':code,
 'plan':plan,'sources':{
  'knob_attribution':json.load(open(art/'verified-attribution.json')),
  'fixed_current2m_contribution':json.load(open(art/'verified-contribution.json'))},
 'estimated_runtime_minutes':10,'selfplay_generated':False,'fits_run':0,
 'force_games_played':0,'frozen_read':False,'promotion_authorized':False,
 'automatic_next_job':None}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
def ppm(value): return int(round(float(value)*1_000_000))
def milli(value): return int(round(float(value)*1000))
(art/'VERDICT__JASS_CONTEXT2_INTERVENTION_PLAN_READY').touch()
for cell,weight in sorted(corpus['weights'].items()):
 (art/f'WEIGHT__{cell}__PPM_{ppm(weight)}__RECORDS_{corpus["record_quotas"][cell]}').touch()
(art/f'LOGDET_GAIN_VS_BASE__MICRO_{int(round(predicted["logdet_gain_vs_base"]*1_000_000))}').touch()
(art/f'EFFECTIVE_COVARIANCE_DIMENSION__MILLI_{milli(predicted["effective_covariance_dimension"])}').touch()
(art/f'MAX_ABS_PAIR_CORRELATION__PPM_{ppm(predicted["maximum_absolute_pair_correlation"])}').touch()
(art/f'RELATIVE_DRAW_SHIFT__PPM_{ppm(predicted["relative_draw_shift_vs_base"])}').touch()
(art/f'WDL_SIDE_SKEW__PPM_{ppm(predicted["wdl_side_skew"])}').touch()
for name in ('SELFPLAY_GENERATED__FALSE','FITS_RUN__0','FORCE_GAMES_PLAYED__0',
             'FROZEN_READ__FALSE','PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_NEXT_JOB__NULL'):
 (art/name).touch()
print(json.dumps(payload,sort_keys=True))
PY
say "JASS_CONTEXT2_INTERVENTION_PLAN_READY records=2000000 generated=false fits=0 promotion=false"

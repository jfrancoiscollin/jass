#!/usr/bin/env bash
# CTX2 component contribution audit on the exact immutable CURRENT_2M final
# stage of CURRICULUM. Reuses certified features, targets and mapper coefficients.
# Read-only diagnostic: no self-play, mapper refit, PatternEval fit, force or promotion.
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
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

TURNOVER_ROOT="r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/20260726T071254Z-336bb984"
CTX2_ROOT="r2:jass-data/runs/home-1373-l3-context2-phase-tactical-fit-v1/20260816T214312Z-9e224d6e"
TURNOVER_SHA="9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
META_SHA="acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682"
EXPECTED_RECORDS=2000000; EXPECTED_HOLDOUT=199204
SPLIT_SEED=577215; HOLDOUT_MOD=10
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
VENV_READY="$VENV/.jass-runtime-ready-v1"

MON=""
monitor(){
  ( t0=$(date +%s)
    while true; do
      { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s) - t0) / 60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
      } >"$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 120
    done ) &
  MON="$!"
}
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -maxdepth 1 -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$IN" 2>/dev/null || true
  rm -f "$W"/*.feat "$W"/*.npy "$W"/*.jnnw "$W"/*.jsm 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^home-([0-9]+)-l3-context2-fixed-contribution-audit-v1$ ]] ||
  die "invalid job nomenclature"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "explicit execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" != cpx62 ] && [ "$(nproc)" -eq 16 ] || die "Home 16-CPU contract mismatch"
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 12288 ] || die "less than 12 GiB free ($DFA MiB)"
[ -f "$VENV_READY" ] || die "persistent numeric runtime absent; do not reinstall"
PY="$VENV/bin/python"
"$PY" -c 'import numpy; assert numpy.__version__' || die "persistent numeric runtime invalid"
say "host=$(hostname) nproc=$(nproc) free_mb=$DFA mode=ctx2_fixed_contribution_audit"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_context2_fixed_contribution_audit.py
"$PY" -m unittest jobs.tests.test_l3_context2_fixed_contribution_audit \
  jobs.tests.test_l3_context2_fixed_contribution_template >"$W/tests.log" 2>&1

stage fetch-authenticated-fixed-corpus-and-ctx2
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_ROOT" \
  --file artefacts/turnover1to1.jnnw.gz=turnover.jnnw.gz \
  --file artefacts/turnover1to1.jsm.gz=turnover.jsm.gz \
  --out-dir "$IN" --report "$ART/verified-turnover.json" >"$W/fetch-turnover.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CTX2_ROOT" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=ctx2-summary.json \
  --file artefacts/split.json=source-split.json \
  --file artefacts/conditional-targets.json=conditional-targets.json \
  --file artefacts/ctx2-context.feat.gz=ctx2-context.feat.gz \
  --file artefacts/ctx2-aligned-target.npy.gz=ctx2-aligned-target.npy.gz \
  --out-dir "$IN" --report "$ART/verified-ctx2.json" >"$W/fetch-ctx2.log" 2>&1

"$PY" - "$ART" "$IN/ctx2-summary.json" <<'PY'
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); summary=json.load(open(sys.argv[2]))
turn=json.load(open(art/'verified-turnover.json')); ctx=json.load(open(art/'verified-ctx2.json'))
if turn.get('job_id')!='home-0977-l3-pure-turnover1to1-train-v1' or turn.get('result_state')!='completed' or turn.get('exit_code')!=0:
 raise SystemExit('TURNOVER source identity/state drift')
if (ctx.get('job_id'),ctx.get('attempt_id'),ctx.get('code_sha')) != (
 'home-1373-l3-context2-phase-tactical-fit-v1','20260816T214312Z-9e224d6e',
 '9e224d6ec7583d3c041755a35559bf559d380f8f'):
 raise SystemExit('CTX2 source identity drift')
if ctx.get('result_state')!='completed' or ctx.get('exit_code')!=0:
 raise SystemExit('CTX2 source state drift')
if summary.get('verdict')!='JASS_CONTEXT2_PHASE_TACTICAL_MODELS_READY':
 raise SystemExit('CTX2 source verdict drift')
PY

gunzip -c "$IN/turnover.jnnw.gz" >"$W/turnover.raw.jnnw"
gunzip -c "$IN/turnover.jsm.gz" >"$W/turnover.raw.jsm"
gunzip -c "$IN/ctx2-context.feat.gz" >"$W/current.ctx2.feat"
gunzip -c "$IN/ctx2-aligned-target.npy.gz" >"$W/aligned.npy"
[ "$(sha256sum "$W/turnover.raw.jnnw" | awk '{print $1}')" = "$TURNOVER_SHA" ] || die "TURNOVER data drift"
[ "$(sha256sum "$W/turnover.raw.jsm" | awk '{print $1}')" = "$META_SHA" ] || die "TURNOVER meta drift"

stage reconstruct-exact-current2m-positions
python3 tools/selfplay_frontier.py split \
  --data "$W/turnover.raw.jnnw" --meta "$W/turnover.raw.jsm" \
  --out-data "$W/current.jnnw" --out-meta "$W/current.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
  --manifest "$ART/split.json" >"$W/split.log" 2>&1
cmp "$ART/split.json" "$IN/source-split.json" || die "CURRENT_2M split manifest drift"
read -r RECORDS TRAIN HOLDOUT < <("$PY" - "$ART/split.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1])); print(r['records'],r['train_records'],r['holdout_records'])
PY
)
[ "$RECORDS" -eq "$EXPECTED_RECORDS" ] && [ "$HOLDOUT" -eq "$EXPECTED_HOLDOUT" ] ||
  die "CURRENT_2M sizing drift"

stage replay-fold-local-component-contributions
timeout 7200s "$PY" jobs/tools/l3_context2_fixed_contribution_audit.py \
  --data "$W/current.jnnw" --meta "$W/current.jsm" \
  --feat "$W/current.ctx2.feat" --aligned-target "$W/aligned.npy" \
  --conditional-report "$IN/conditional-targets.json" --chunk-size 20000 \
  --report "$ART/fixed-current2m-contribution-audit.json" >"$W/audit.log" 2>&1

stage publish-audited-diagnostic
"$PY" - "$ART" "$EXPECTED_CODE_SHA" <<'PY'
import json,math,sys
from pathlib import Path
art=Path(sys.argv[1]); code=sys.argv[2]
audit=json.load(open(art/'fixed-current2m-contribution-audit.json'))
if audit.get('verdict')!='JASS_CONTEXT2_FIXED_CONTRIBUTION_AUDIT_READY':
 raise SystemExit('fixed contribution verdict drift')
src=audit['source']; protocol=audit['protocol']
if (src['records'],src['holdout_records'],src['alpha'],src['fold_count'],src['fold_seed']) != (2_000_000,199_204,0.30,5,20260811):
 raise SystemExit('fixed contribution protocol drift')
if not (protocol['same_fixed_positions'] and protocol['fold_local_oof_coefficients_replayed']
        and protocol['row_weighting']=='game_equal'):
 raise SystemExit('fixed position replay contract failed')
if protocol['new_selfplay_generated'] or protocol['mapper_refit'] or protocol['patterneval_fit']:
 raise SystemExit('read-only audit contract failed')
if audit['prediction_recovery_max_absolute_error']>2e-6:
 raise SystemExit('prediction recovery drift')

train=audit['cohorts']['train_oof']; base=train['base_15_components']; raw=train['raw_30_components']
def ppm(value): return int(round(float(value)*1_000_000))
def ppb(value): return int(round(float(value)*1_000_000_000))
def signed(value,scale=1_000_000):
 if value is None: return 'NA'
 n=int(round(float(value)*scale)); return ('P' if n>0 else ('N' if n<0 else 'Z'))+str(abs(n))
for rank,row in enumerate(sorted(base,key=lambda r:r['mean_absolute_alpha_target_probability_effect'],reverse=True),1):
 marker=(f"BASECOMP__RANK_{rank:02d}__{row['component']}"
         f"__TARGETABS_PPB_{ppb(row['mean_absolute_alpha_target_probability_effect'])}"
         f"__LOGITSHARE_PPM_{ppm(row['absolute_logit_share'])}"
         f"__DOMRATE_PPM_{ppm(row['dominant_position_rate'])}"
         f"__CORROUT_{signed(row['correlation_with_terminal_outcome'])}"
         f"__CORRPRED_{signed(row['correlation_with_conditional_prediction'])}")
 (art/marker).touch()
for rank,row in enumerate(sorted(raw,key=lambda r:r['mean_absolute_alpha_target_probability_effect'],reverse=True)[:10],1):
 (art/f"RAWCOMP__RANK_{rank:02d}__{row['component']}__TARGETABS_PPB_{ppb(row['mean_absolute_alpha_target_probability_effect'])}__LOGITSHARE_PPM_{ppm(row['absolute_logit_share'])}").touch()
phase=train['phase_bank_absolute_logit_share']; conc=train['base_15_concentration']
(art/f"PHASESHARE__MID_PPM_{ppm(phase['tempo_mid'])}__END_PPM_{ppm(phase['tempo_end'])}").touch()
(art/f"CONCENTRATION__TOP1_PPM_{ppm(conc['largest_share'])}__TOP3_PPM_{ppm(conc['top3_share'])}__EFFECTIVE_MILLI_{int(round(conc['effective_component_count']*1000))}").touch()
flips=audit['train_oof_rankings']['raw_coefficient_sign_flip_components']
(art/f"COEFFICIENT_SIGN_FLIPS__COUNT_{len(flips)}").touch()
for name in flips: (art/f"COEFFICIENT_SIGN_FLIP__{name}").touch()
pairs=train['base_contribution_correlation']['high_absolute_pairs_ge_0_90']
(art/f"HIGH_CORRELATION_PAIRS_GE_090__COUNT_{len(pairs)}").touch()
for row in pairs:
 (art/f"HIGHCORR__{row['left']}__{row['right']}__R_{signed(row['r'])}").touch()
(art/f"RECOVERY_MAX_PICO_{int(round(audit['prediction_recovery_max_absolute_error']*1e12))}").touch()
shift=train['alpha_target_probability_shift']
(art/f"TARGET_SHIFT__MEANABS_PPB_{ppb(shift['mean_absolute'])}__RMS_PPB_{ppb(shift['rms'])}").touch()
payload={'schema':'jass.l3_context2_fixed_contribution_job.v1',
 'verdict':'JASS_CONTEXT2_FIXED_CONTRIBUTION_AUDITED','code_sha':code,
 'source_job':'home-1373-l3-context2-phase-tactical-fit-v1',
 'source_attempt':'20260816T214312Z-9e224d6e','audit':audit,
 'diagnostic_only':True,'new_selfplay_generated':False,'fits_run':0,
 'force_games_played':0,'frozen_read':False,'promotion_authorized':False,
 'automatic_next_job':None}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/'VERDICT__JASS_CONTEXT2_FIXED_CONTRIBUTION_AUDITED').touch()
(art/'PROMOTION_AUTHORIZED__FALSE').write_text('false\n')
(art/'AUTOMATIC_NEXT_JOB__NULL').write_text('null\n')
PY
say "JASS_CONTEXT2_FIXED_CONTRIBUTION_AUDITED corpus=CURRENT_2M positions=$RECORDS fit=0 selfplay=0 promotion=false"

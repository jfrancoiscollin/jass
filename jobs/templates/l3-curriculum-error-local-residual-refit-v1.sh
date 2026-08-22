#!/usr/bin/env bash
# Conditional rank-one CURRICULUM repair from the sealed residual atlas.
# No game, self-play, frozen read or promotion is permitted in this stage.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; : >"$PROG"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; cp "$STAGE" "$ART/STAGE.txt"; }

ATLAS_JOB="cpx62-1485-l3-curriculum-error-residual-atlas-v2"
ATLAS_ATTEMPT="20260822T192236Z-2e028428"
ATLAS_CODE="2e0284287657ca6b9325cb76e12e28376c873b0c"
ATLAS_ROOT="r2:jass-data/runs/$ATLAS_JOB/$ATLAS_ATTEMPT"
CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"
CURRICULUM_CODE="18c38a33ae78c9c2e8e2df62fca266da28dacead"
CURRICULUM_ROOT="r2:jass-data/runs/$CURRICULUM_JOB/$CURRICULUM_ATTEMPT"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
NSHARDS=16
PAIRS=353
INFORMATIVE=290
RECLASSIFIED=63
TRUST_GRID="0,1,2,4,8,16,32,64"
SPLIT_SEED=2026082223
BOOTSTRAP_SEED=2026082224
BOOTSTRAP_SAMPLES=100000

MON=""
monitor(){
  ( t0=$(date +%s); while true; do
      { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
        [ -f "$ART/local-residual-refit.json" ] && printf 'refit_report_ready=1\n'
      } >"$PROG.tmp"; mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 60
    done ) & MON="$!"
}
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-curriculum-error-local-residual-refit-v1$ ]] || die "invalid job nomenclature"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "execution GO missing"
[ "${LOCAL_RESIDUAL_REFIT_ONLY:-0}" = 1 ] || die "local-refit-only guard missing"
[ "${NO_SELFPLAY:-0}" = 1 ] || die "self-play guard missing"
[ "${NO_STRENGTH_GAMES:-0}" = 1 ] || die "strength-game guard missing"
[ "${NO_FROZEN_READ:-0}" = 1 ] || die "frozen-read guard missing"
[ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] || die "promotion guard missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "continuation guard missing"
say "experiment=CURRICULUM_ERROR_LOCAL_RESIDUAL_REFIT atlas=$ATLAS_JOB/$ATLAS_ATTEMPT"
say "source_pairs=$PAIRS informative=$INFORMATIVE reclassified=$RECLASSIFIED strength_games=0 selfplay=0 frozen=0"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_curriculum_error_local_residual_refit.py
python3 -m unittest jobs.tests.test_l3_curriculum_error_local_residual_refit \
  jobs.tests.test_l3_curriculum_error_residual_atlas >"$W/python-tests.log" 2>&1

stage fetch-authenticate-atlas-and-curriculum
atlas_files=(
  --file artefacts/JASS_CONTROL_SUMMARY.json=atlas-summary.json
  --file artefacts/residual-atlas.json=residual-atlas.json
  --file artefacts/error-residual-region.json=error-residual-region.json
)
for shard in $(seq 0 $((NSHARDS-1))); do
  atlas_files+=(--file "artefacts/residual-shards/shard-$shard.json=residual-shard-$shard.json")
done
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$ATLAS_ROOT" \
  "${atlas_files[@]}" --out-dir "$IN" --report "$ART/verified-atlas.json" \
  --expected-state completed >"$W/fetch-atlas.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_ROOT" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=curriculum-summary.json \
  --out-dir "$IN" --report "$ART/verified-curriculum.json" \
  --expected-state completed >"$W/fetch-curriculum.log" 2>&1
gunzip -t "$IN/curriculum.pjtw.gz"
gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
[ "$(sha256sum "$W/curriculum.pjtw" | awk '{print $1}')" = "$CURRICULUM_SHA" ] || die "CURRICULUM raw hash drift"

python3 - "$IN" "$ART" "$ATLAS_JOB" "$ATLAS_ATTEMPT" "$ATLAS_CODE" \
  "$CURRICULUM_JOB" "$CURRICULUM_ATTEMPT" "$CURRICULUM_CODE" \
  "$CURRICULUM_SHA" "$PAIRS" "$INFORMATIVE" "$RECLASSIFIED" "$NSHARDS" <<'PY'
import hashlib,json,sys
from pathlib import Path
src,art=map(Path,sys.argv[1:3]); atlas_identity=tuple(sys.argv[3:6]); curriculum_identity=tuple(sys.argv[6:9])
champion=sys.argv[9]; pairs,informative,reclassified,nsh=map(int,sys.argv[10:14])
for name,want in (("verified-atlas.json",atlas_identity),("verified-curriculum.json",curriculum_identity)):
 row=json.load(open(art/name)); got=(row.get('job_id'),row.get('attempt_id'),row.get('code_sha'))
 if got!=want or row.get('result_state')!='completed' or row.get('exit_code')!=0:
  raise SystemExit(f'{name}: identity/state drift {got!r}')
report=json.load(open(src/'residual-atlas.json')); summary=json.load(open(src/'atlas-summary.json'))
region=json.load(open(src/'error-residual-region.json'))
if report.get('verdict')!='JASS_CURRICULUM_ERROR_RESIDUAL_REGION_CONFIRMED' or report.get('passed') is not True:
 raise SystemExit('atlas did not authorize refit')
if summary.get('verdict')!=report.get('verdict') or summary.get('fit_authorized') is not True:
 raise SystemExit('atlas summary/report authorization drift')
if report.get('pairs')!=pairs or report.get('informative_error_pairs')!=informative:
 raise SystemExit('atlas pair cardinality drift')
if report.get('reclassified_exact_non_errors',{}).get('total')!=reclassified:
 raise SystemExit('atlas reclassification cardinality drift')
if report.get('champion_sha256')!=champion or region.get('champion_sha256')!=champion:
 raise SystemExit('atlas champion identity drift')
if region.get('fit_authorized') is not True or region.get('promotion_authorized') is not False:
 raise SystemExit('region authorization drift')
for shard in range(nsh):
 row=json.load(open(src/f'residual-shard-{shard}.json'))
 if row.get('schema')!='jass.l3_curriculum_error_residual_leaf_shard.v1' or row.get('shard')!=shard or row.get('nshards')!=nsh:
  raise SystemExit(f'residual shard {shard} identity drift')
 if row.get('champion_sha256')!=champion: raise SystemExit(f'residual shard {shard} champion drift')
if hashlib.sha256((src/'curriculum.pjtw.gz').read_bytes()).hexdigest()==champion:
 raise SystemExit('compressed and raw champion hashes unexpectedly alias')
PY

stage rank-one-error-versus-sham-local-refit
shard_args=(); for shard in $(seq 0 $((NSHARDS-1))); do shard_args+=(--shard "$IN/residual-shard-$shard.json"); done
python3 jobs/tools/l3_curriculum_error_local_residual_refit.py \
  --atlas-report "$IN/residual-atlas.json" --region "$IN/error-residual-region.json" \
  "${shard_args[@]}" --champion "$W/curriculum.pjtw" \
  --error-out "$ART/error-residual.pjtw" --sham-out "$ART/sham-residual.pjtw" \
  --sham-region "$ART/sham-region.json" --report "$ART/local-residual-refit.json" \
  --trust-grid "$TRUST_GRID" --rank-scale 1.0 --control-anchor 0.25 \
  --trust-anchor 0.01 --control-tolerance 0.002 --split-seed "$SPLIT_SEED" \
  --bootstrap-samples "$BOOTSTRAP_SAMPLES" --bootstrap-seed "$BOOTSTRAP_SEED" \
  >"$W/refit.log" 2>&1

stage terminal-audit
python3 - "$ART/local-residual-refit.json" "$W/curriculum.pjtw" "$ART" \
  "$PAIRS" "$INFORMATIVE" "$RECLASSIFIED" <<'PY'
import hashlib,json,re,sys
from pathlib import Path
report_path,champion_path,art=Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3])
pairs,informative,reclassified=map(int,sys.argv[4:7]); report=json.load(open(report_path))
allowed={'JASS_CURRICULUM_ERROR_LOCAL_RESIDUAL_REFIT_READY','JASS_CURRICULUM_ERROR_LOCAL_RESIDUAL_REFIT_NOT_ESTABLISHED'}
if report.get('schema')!='jass.l3_curriculum_error_local_residual_refit.v2' or report.get('verdict') not in allowed:
 raise SystemExit('refit terminal schema/verdict drift')
if (report.get('source_pairs'),report.get('informative_error_pairs'),report.get('reclassified_exact_non_error_pairs_excluded'))!=(pairs,informative,reclassified):
 raise SystemExit('refit pair partition drift')
if report.get('reclassified_pairs_used_in_fit_or_statistics')!=0:
 raise SystemExit('reclassified pair leaked into refit statistics')
if report.get('split',{}).get('sham_matching_used_calibration') is not False:
 raise SystemExit('sham direction leaked calibration rows')
if report.get('gates',{}).get('discovery_nonzero_step_authorized') is not passed:
 raise SystemExit('nonzero-step gate/pass drift')
if any(int(report.get(key,-1))!=0 for key in ('strength_games','selfplay_games','frozen_reads')):
 raise SystemExit('forbidden action counter drift')
if report.get('promotion_authorized') is not False: raise SystemExit('promotion guard drift')
passed=report.get('passed') is True
if bool(report.get('models')) != passed or int(report.get('fit_count',-1)) != (2 if passed else 0):
 raise SystemExit('model publication/pass drift')
if passed:
 source=champion_path.read_bytes()
 for arm,name in (('error','error-residual.pjtw'),('sham','sham-residual.pjtw')):
  path=art/name; raw=path.read_bytes(); audit=report['models'][arm]
  if raw[:20]!=source[:20] or len(raw)!=len(source): raise SystemExit(f'{arm}: header/geometry drift')
  if hashlib.sha256(raw).hexdigest()!=audit.get('sha256'): raise SystemExit(f'{arm}: report hash drift')
  if audit.get('changed_outside_region')!=0 or audit.get('frozen_region_exact') is not True or audit.get('exact_fold_orbits_coherent') is not True:
   raise SystemExit(f'{arm}: exact frozen-region audit failed')
readout={'schema':'jass.curriculum_error_local_residual_refit_terminal.v1','verdict':report['verdict'],
 'passed':passed,'source_pairs':pairs,'informative_error_pairs':informative,
 'reclassified_exact_non_error_pairs_excluded':reclassified,'split':report['split'],
 'directions':report['directions'],'trust_region':report['trust_region'],
 'calibration':report['calibration'],'confirm':report['confirm'],'gates':report['gates'],
 'failed_gates':report['failed_gates'],'fit_count':report['fit_count'],'strength_games':0,
 'selfplay_games':0,'frozen_reads':0,'promotion_authorized':False,
 'next_stage':report['next_stage']}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(readout,indent=2,sort_keys=True)+'\n')
clean=lambda value: re.sub(r'[^A-Za-z0-9.+-]+','_',str(value)).strip('_')
markers={report['verdict'],f"SELECTED_TICKS__{report['trust_region']['selected_ticks']}",
 f"ERROR_BUCKETS__{report['directions']['error_buckets']}",f"SHAM_BUCKETS__{report['directions']['sham_buckets']}",
 f"FAILED_GATES__{clean('+'.join(report['failed_gates']) or 'NONE')}",
 'SOURCE_PAIRS__353','INFORMATIVE_ERROR_PAIRS__290','RECLASSIFIED_EXACT_NON_ERRORS_EXCLUDED__63',
 'STRENGTH_GAMES__0','NEW_SELFPLAY__0','FROZEN_READS__0','PROMOTION_AUTHORIZED__FALSE',
 ('NEXT_STAGE_RECOMMENDED__FRESH_ERROR_REPLAY_VALIDATION' if passed else 'NEXT_STAGE__NONE')}
for marker in markers: (art/marker).touch()
PY

if [ -f "$ART/error-residual.pjtw" ]; then
  gzip -c "$ART/error-residual.pjtw" >"$ART/error-residual.pjtw.gz"
  gzip -c "$ART/sham-residual.pjtw" >"$ART/sham-residual.pjtw.gz"
fi
cp "$ART/JASS_CONTROL_SUMMARY.json" "$ART/JASS_CURRICULUM_ERROR_LOCAL_RESIDUAL_REFIT_READY.json"
verdict=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
say "verdict=$verdict strength_games=0 selfplay=0 frozen=0 promotion=false automatic_continuation=false"
stage complete

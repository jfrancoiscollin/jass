#!/usr/bin/env bash
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"; : "${JASS_STAGE_SPEC:?}"
: "${JASS_JOB_ID:?}"; : "${D4_INVALID_RECOVERY_GO:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "TECHNICAL_ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

PY="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}/bin/python"
[ -x "$PY" ] || die "numeric venv missing"
SPEC_CODE=$("$PY" - "$JASS_STAGE_SPEC" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))['code_sha'])
PY
)
[ "$(git rev-parse HEAD)" = "$SPEC_CODE" ] || die "stage spec / HEAD mismatch"
[ "$(hostname)" = cpx62 ] || die "recovery readout must run on cpx62"
[ "$(nproc)" -eq 16 ] || die "cpx62 nproc drift"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree must be detached and clean"
[ "$D4_INVALID_RECOVERY_GO" = 1 ] || die "recovery GO missing"

SRC_JOB="cpx62-1862-l3-decision-math-d4-search-utility-offline-cardinality-recovery-requeue-v1"
SRC_ATTEMPT="20260907T182914Z-1c779cc8"
SRC_CODE="1c779cc87608a12b26432cad6a23872aeb5eabe8"
SRC_ROOT="r2:jass-data/runs/$SRC_JOB/$SRC_ATTEMPT"
MODEL_SHA="e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0"

say "D4 invalid recovery readout start source=$SRC_JOB/$SRC_ATTEMPT searches=0 fits=0 games=0"
python3 jobs/tools/fetch_result_files.py --prefix "$SRC_ROOT" --expected-state failed \
  --file artefacts/d4-example-prepare.json=d4-example-prepare.json \
  --file artefacts/d4-teacher-aggregate.json=d4-teacher-aggregate.json \
  --file artefacts/d4-root-pool-provenance.json=d4-root-pool-provenance.json \
  --out-dir "$IN" --report "$ART/verified-1862.json" >"$W/fetch.log" 2>&1

"$PY" - "$ART/verified-1862.json" "$IN/d4-example-prepare.json" "$IN/d4-teacher-aggregate.json" \
 "$IN/d4-root-pool-provenance.json" "$SRC_JOB" "$SRC_ATTEMPT" "$SRC_CODE" "$SPEC_CODE" "$MODEL_SHA" "$ART/scientific-summary.json" <<'PY'
import json,sys
verified=json.load(open(sys.argv[1])); prepare=json.load(open(sys.argv[2])); teacher=json.load(open(sys.argv[3])); roots=json.load(open(sys.argv[4]))
src_job,src_attempt,src_code,out_code,model_sha,out_path=sys.argv[5:]
got=(verified.get('job_id'),verified.get('attempt_id'),verified.get('code_sha'),verified.get('result_state'),verified.get('exit_code'))
if got != (src_job,src_attempt,src_code,'failed',4):
    raise SystemExit(f'1862 source identity/exit drift: {got}')
if prepare.get('schema')!='jass.d4.search_utility_prepare.v1' or prepare.get('verdict')!='D4_SEARCH_UTILITY_OFFLINE_INVALID_V1':
    raise SystemExit('prepare report is not frozen support INVALID')
if prepare.get('fits')!=0 or prepare.get('strength_games')!=0 or prepare.get('promotions')!=0 or prepare.get('bakes')!=0:
    raise SystemExit('prepare side-effect drift')
if teacher.get('schema')!='jass.d4.search_utility_teacher_aggregate.v1' or teacher.get('verdict')!='D4_SEARCH_UTILITY_TEACHER_COMPLETE_V1':
    raise SystemExit('teacher aggregate drift')
if teacher.get('roots')!=4000 or teacher.get('teacher_searches')!=4000 or teacher.get('exact_nodes_per_root')!=50000:
    raise SystemExit('teacher cardinality drift')
for key in ('game_outcome_reads','qscore_reads','search_decision_trace_reads','full_ladder_1843_reads','d3_score_reads'):
    if prepare.get(key)!=0 or teacher.get(key)!=0:
        raise SystemExit(f'forbidden read drift: {key}')
if roots.get('selected_roots')!=4000:
    raise SystemExit('root provenance cardinality drift')
out={
 'schema':'jass.d4.search_utility_offline_terminal.v1',
 'verdict':'D4_SEARCH_UTILITY_OFFLINE_INVALID_V1',
 'reason':'exact_or_phase_support_insufficient_after_frozen_selection',
 'code_sha':src_code,
 'recovery_readout_code_sha':out_code,
 'source_job':src_job,
 'source_attempt':src_attempt,
 'science':{'target':'observed_beta_cutoff_causing_move_within_legacy_top4_non_tt','model_width':96,'value_model_sha256':model_sha,'fits':0,'model_searches':0},
 'prepare':prepare,
 'teacher_searches':teacher['teacher_searches'],
 'strength_games':0,'promotions':0,'bakes':0,
 'equal_node_authorized':False,'next_stage':'STOP_D4_OFFLINE',
 'game_outcome_reads':0,'qscore_reads':0,'search_decision_trace_reads':0,
 'full_ladder_1843_reads':0,'d3_score_reads':0,
 'recovery':{'source_state':'failed','source_exit_code':4,'new_searches':0,'new_fits':0,'new_games':0}
}
open(out_path,'w').write(json.dumps(out,indent=2,sort_keys=True)+'\n')
PY

cp "$IN/d4-example-prepare.json" "$ART/d4-example-prepare.json"
cp "$IN/d4-teacher-aggregate.json" "$ART/d4-teacher-aggregate.json"
printf 'D4_SEARCH_UTILITY_OFFLINE_INVALID_V1\n' >"$ART/VERDICT__D4_SEARCH_UTILITY_OFFLINE_INVALID_V1"
printf '0\n' >"$ART/FULL_FITS__0"; printf '0\n' >"$ART/STRENGTH_GAMES__0"
printf 'false\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"; printf 'false\n' >"$ART/BAKE_AUTHORIZED__FALSE"
say "D4_SEARCH_UTILITY_OFFLINE_INVALID_V1 recovered from sealed 1862 support report; new searches=0 fits=0 games=0"

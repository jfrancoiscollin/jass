#!/usr/bin/env bash
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"; : "${JASS_STAGE_SPEC:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true; (cd "$W" && find . -maxdepth 1 -name '*.log' -type f -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true; rm -rf "$IN" "$W"/*.jsonl 2>/dev/null || true; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "TECHNICAL_ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

SOURCE_JOB="cpx62-1857-l3-decision-math-d3-runtime-equal-node-prereg-recovery-requeue-v1"
SOURCE_ATTEMPT="20260907T155344Z-fcdcd217"
SOURCE_CODE="fcdcd217cccb9d94aa7351b453dad725f3d816b1"
SOURCE_ROOT="r2:jass-data/runs/$SOURCE_JOB/$SOURCE_ATTEMPT"
SPEC_CODE=$(python3 - "$JASS_STAGE_SPEC" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))['code_sha'])
PY
)
[ "$(git rev-parse HEAD)" = "$SPEC_CODE" ] || die "stage spec / HEAD mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX62 contract mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree must be detached and clean"

grep -Fq 'Diagnostic-only post-terminal autopsy' docs/experiments/L3_D3_RUNTIME_TERMINAL_AUTOPSY_V1_20260907.md
grep -Fq 'strength_games = 0' docs/experiments/L3_D3_RUNTIME_TERMINAL_AUTOPSY_V1_20260907.md
grep -Fq 'equal_time_authorized = false' docs/experiments/L3_D3_RUNTIME_TERMINAL_AUTOPSY_V1_20260907.md
say "D3 runtime terminal autopsy start job=$JASS_JOB_ID code=$SPEC_CODE games=0 fits=0 searches=0"

FETCH=(--prefix "$SOURCE_ROOT" --expected-state completed
  --file artefacts/scientific-summary.json=source-summary.json
  --file artefacts/d3-equal-node-pool-provenance.json=pool-provenance.json)
for s in 00 01 02 03 04 05 06 07; do
  FETCH+=(--file "artefacts/shards/s${s}/primary-games.jsonl=primary-s${s}.jsonl")
  FETCH+=(--file "artefacts/shards/s${s}/harness-games.jsonl=harness-s${s}.jsonl")
done
timeout 1800s python3 jobs/tools/fetch_result_files.py "${FETCH[@]}" \
  --out-dir "$IN" --report "$ART/verified-source.json" >"$W/fetch-source.log" 2>&1

python3 - "$ART/verified-source.json" "$IN/source-summary.json" <<'PY'
import json,sys
v=json.load(open(sys.argv[1])); s=json.load(open(sys.argv[2]))
expected=('cpx62-1857-l3-decision-math-d3-runtime-equal-node-prereg-recovery-requeue-v1','20260907T155344Z-fcdcd217','fcdcd217cccb9d94aa7351b453dad725f3d816b1','completed')
if (v.get('job_id'),v.get('attempt_id'),v.get('code_sha'),v.get('result_state')) != expected:
 raise SystemExit('1857 source identity drift')
if s.get('verdict')!='D3_RUNTIME_EQUAL_NODE_NOT_ESTABLISHED_V1' or s.get('next_stage')!='STOP':
 raise SystemExit('1857 terminal verdict drift')
if s.get('strength_games')!=1700 or s.get('fits')!=0 or s.get('promotion_authorized') is not False or s.get('bake_authorized') is not False:
 raise SystemExit('1857 terminal authority drift')
PY

python3 -m unittest jobs.tests.test_d3_runtime_terminal_autopsy >"$W/unit-tests.log" 2>&1
ARGS=(--source-summary "$IN/source-summary.json" --pool-provenance "$IN/pool-provenance.json" --out "$ART/D3_RUNTIME_TERMINAL_AUTOPSY.json")
for s in 00 01 02 03 04 05 06 07; do
  ARGS+=(--primary "$IN/primary-s${s}.jsonl" --harness "$IN/harness-s${s}.jsonl")
done
python3 jobs/tools/d3_runtime_terminal_autopsy.py "${ARGS[@]}" >"$W/autopsy.log" 2>&1
cp "$ART/D3_RUNTIME_TERMINAL_AUTOPSY.json" "$ART/scientific-summary.json"
python3 - "$ART/D3_RUNTIME_TERMINAL_AUTOPSY.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]))
if r.get('verdict')!='D3_RUNTIME_TERMINAL_AUTOPSY_COMPLETE_V1': raise SystemExit('autopsy verdict drift')
for k in ('fits','model_searches','teacher_searches','strength_games','searches','promotions','bakes'):
 if r.get(k)!=0: raise SystemExit(f'forbidden side effect counter {k}')
if r.get('equal_time_authorized') is not False or r.get('next_stage')!='D4_SEARCH_UTILITY_PREREGISTRATION_ONLY':
 raise SystemExit('autopsy authority drift')
PY
printf '0\n' >"$ART/FULL_FITS__0"; printf '0\n' >"$ART/STRENGTH_GAMES__0"; printf '0\n' >"$ART/SEARCHES__0"
printf 'FALSE\n' >"$ART/EQUAL_TIME_AUTHORIZED__FALSE"; printf 'FALSE\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"; printf 'FALSE\n' >"$ART/BAKE_AUTHORIZED__FALSE"
say "D3_RUNTIME_TERMINAL_AUTOPSY_COMPLETE_V1 games=0 fits=0 searches=0 next=D4_SEARCH_UTILITY_PREREGISTRATION_ONLY"

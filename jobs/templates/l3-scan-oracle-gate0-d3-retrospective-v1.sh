#!/usr/bin/env bash
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"; : "${JASS_STAGE_SPEC:?}"
: "${JASS_JOB_ID:?}"; : "${SCAN_ORACLE_GATE0_GO:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
phase(){ echo "$1" >"$STAGE"; say "phase=$1"; }
MON=""
monitor(){ (t0=$(date +%s); while true; do
  { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')";
    printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)";
    printf 'elapsed_min=%d\n' "$((($(date +%s)-t0)/60))";
    printf 'scan_searches_planned=0\nparents=512\narms=2\nnodes_per_parent_arm=20000\nstrength_games=0\n';
  } >"$PROG.tmp"; mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 120;
done) & MON="$!"; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt" 2>/dev/null || true
  (cd "$W" && find . -maxdepth 2 -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/control-src" "$W/candidate-src" "$W/build-control" "$W/build-candidate" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "TECHNICAL_ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"; PY="$VENV/bin/python"
[ -x "$PY" ] || die "numeric venv missing"
SPEC_CODE=$("$PY" - "$JASS_STAGE_SPEC" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))['code_sha'])
PY
)
[ "$(git rev-parse HEAD)" = "$SPEC_CODE" ] || die "stage spec / HEAD mismatch"
[ "$(hostname)" = User ] || die "Gate0 retrospective must run on HOME/User"
[ "$(nproc)" -eq 16 ] || die "HOME nproc drift"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree must be detached and clean"
[ "$SCAN_ORACLE_GATE0_GO" = 1 ] || die "Gate0 execution GO missing"

SEL_JOB="home-1651-l3-scan-ceiling-selection-v1"
SEL_ATTEMPT="20260829T133348Z-28e12fba"
SEL_CODE="28e12fba0ead14def244ffc442b15937f65edc0e"
SEL_ROOT="r2:jass-data/runs/$SEL_JOB/$SEL_ATTEMPT"
SCAN_JOB="home-1657-l3-scan-ceiling-scan-base-v1"
SCAN_ATTEMPT="20260829T144418Z-46623b26"
SCAN_CODE="46623b26b8d684f5685475d81fbb36f215ba4ac2"
SCAN_ROOT="r2:jass-data/runs/$SCAN_JOB/$SCAN_ATTEMPT"
D1_JOB="cpx62-1849-l3-decision-math-d1-wdl-listwise-fit-stage-env-recovery-requeue-v1"
D1_ATTEMPT="20260906T222203Z-08fd187a"
D1_CODE="08fd187aa187f26bd7179df2c68056a74e28355d"
D1_ROOT="r2:jass-data/runs/$D1_JOB/$D1_ATTEMPT"
D3_JOB="cpx62-1854-l3-decision-math-d3-relational-action-fit-v1"
D3_ATTEMPT="20260907T073241Z-1bea99d0"
D3_CODE="1bea99d04ba1b4a2d79e36af8d4a1bc9be930453"
D3_ROOT="r2:jass-data/runs/$D3_JOB/$D3_ATTEMPT"
MODEL_SHA="e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0"
ADAPTER_SHA="03cd2aa6b2a61ef8ce11dc878eb0ba13a56c8e587b49b19158135a1b64bfd4c3"

say "Gate0 D3 retrospective start job=$JASS_JOB_ID code=$SPEC_CODE scan_searches=0 games=0"
monitor
phase authenticate-existing-oracle
python3 jobs/tools/fetch_result_files.py --prefix "$SEL_ROOT" --expected-state completed \
  --file artefacts/parents.jnnw.gz=parents.jnnw.gz \
  --file artefacts/siblings.tsv=siblings.tsv \
  --file artefacts/selection-report.json=selection-report.json \
  --out-dir "$IN" --report "$ART/verified-selection.json" >"$W/fetch-selection.log" 2>&1
scan_args=()
for i in $(seq -w 0 15); do
  scan_args+=(--file "artefacts/scores/scan-base-shard-${i}-scores.tsv.gz=scan-${i}.tsv.gz")
done
python3 jobs/tools/fetch_result_files.py --prefix "$SCAN_ROOT" --expected-state completed \
  "${scan_args[@]}" --out-dir "$IN" --report "$ART/verified-scan.json" >"$W/fetch-scan.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$D1_ROOT" --expected-state completed \
  --file artefacts/WDL_CONTROL.pjtw.gz=WDL_CONTROL.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-d1.json" >"$W/fetch-d1.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$D3_ROOT" --expected-state completed \
  --file artefacts/D3_RELATIONAL_ADAPTER.npy=D3_RELATIONAL_ADAPTER.npy \
  --out-dir "$IN" --report "$ART/verified-d3.json" >"$W/fetch-d3.log" 2>&1

gunzip -c "$IN/parents.jnnw.gz" >"$W/parents.jnnw"
gunzip -c "$IN/WDL_CONTROL.pjtw.gz" >"$W/WDL_CONTROL.pjtw"
[ "$(sha256sum "$W/WDL_CONTROL.pjtw" | awk '{print $1}')" = "$MODEL_SHA" ] || die "WDL_CONTROL byte drift"
[ "$(sha256sum "$IN/D3_RELATIONAL_ADAPTER.npy" | awk '{print $1}')" = "$ADAPTER_SHA" ] || die "D3 adapter byte drift"
"$PY" - "$ART/verified-selection.json" "$ART/verified-scan.json" "$ART/verified-d1.json" "$ART/verified-d3.json" \
 "$SEL_JOB" "$SEL_ATTEMPT" "$SEL_CODE" "$SCAN_JOB" "$SCAN_ATTEMPT" "$SCAN_CODE" \
 "$D1_JOB" "$D1_ATTEMPT" "$D1_CODE" "$D3_JOB" "$D3_ATTEMPT" "$D3_CODE" <<'PY'
import json,sys
paths=sys.argv[1:5]; ids=sys.argv[5:]
expected=[tuple(ids[i:i+3]) for i in range(0,len(ids),3)]
for p,exp in zip(paths,expected):
 r=json.load(open(p)); got=(r.get('job_id'),r.get('attempt_id'),r.get('code_sha'),r.get('result_state'))
 if got != (*exp,'completed'): raise SystemExit(f'source identity drift {p}: {got} != {exp}')
PY

phase target-blind-512-selection
"$PY" jobs/tools/scan_oracle_gate0_select.py --groups "$IN/siblings.tsv" \
  --out-ids "$ART/gate0-parent-ids.txt" --report "$ART/gate0-selection.json" >"$W/select.log" 2>&1

phase locate-runtime
EGDIR=""
for directory in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$directory"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$directory"; break; }
done
[ -n "$EGDIR" ] || die "real HOME EGDB data unavailable"
[ -d /root/egdb_intl ] || die "HOME egdb_intl source checkout unavailable"

phase isolated-build
for arm in control candidate; do
  mkdir -p "$W/$arm-src"
  git archive HEAD | tar -x -C "$W/$arm-src"
  "$PY" "$W/$arm-src/jobs/tools/scan_oracle_gate0_render.py" --cmake "$W/$arm-src/CMakeLists.txt"
done
"$PY" "$W/candidate-src/jobs/tools/d3_runtime_render.py" \
  --src "$W/candidate-src/src/search.cpp" --out "$W/candidate-search.cpp"
mv "$W/candidate-search.cpp" "$W/candidate-src/src/search.cpp"
for arm in control candidate; do
  cmake -S "$W/$arm-src" -B "$W/build-$arm" -DCMAKE_BUILD_TYPE=Release \
    -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
    >"$W/cmake-$arm.log" 2>&1
  cmake --build "$W/build-$arm" -j16 --target jass_scan_oracle_gate0_runtime >"$W/build-$arm.log" 2>&1
done
"$PY" - "$W/control-src" "$W/candidate-src" <<'PY'
import hashlib,sys
from pathlib import Path
a,b=map(Path,sys.argv[1:])
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
changed=[]
for p in sorted(x.relative_to(a) for x in a.rglob('*') if x.is_file()):
 q=b/p
 if not q.is_file() or sha(a/p)!=sha(q): changed.append(str(p))
if changed != ['src/search.cpp']:
 raise SystemExit(f'candidate/control source delta drift: {changed}')
PY

phase exact-node-control
unset JASS_D3_RUNTIME_ADAPTER JASS_D3_RUNTIME_BASE_MODEL JASS_DSSD_MOVE_ORDER_POLICY JASS_TB_MOVE_ORDER_POLICY JASS_T3_F6_MODEL || true
timeout 900s "$W/build-control/jass_scan_oracle_gate0_runtime" "$W/parents.jnnw" "$ART/gate0-parent-ids.txt" \
  "$ART/gate0-control.tsv" "$ART/gate0-control-report.json" "$W/WDL_CONTROL.pjtw" "$EGDIR" 20000 CONTROL \
  >"$W/control.log" 2>&1

phase exact-node-d3
export JASS_D3_RUNTIME_ADAPTER="$IN/D3_RELATIONAL_ADAPTER.npy"
export JASS_D3_RUNTIME_BASE_MODEL="$W/WDL_CONTROL.pjtw"
timeout 1800s "$W/build-candidate/jass_scan_oracle_gate0_runtime" "$W/parents.jnnw" "$ART/gate0-parent-ids.txt" \
  "$ART/gate0-d3.tsv" "$ART/gate0-d3-report.json" "$W/WDL_CONTROL.pjtw" "$EGDIR" 20000 D3 \
  >"$W/d3.log" 2>&1
unset JASS_D3_RUNTIME_ADAPTER JASS_D3_RUNTIME_BASE_MODEL

"$PY" - "$ART/gate0-control-report.json" "$ART/gate0-d3-report.json" <<'PY'
import json,sys
a,b=map(lambda p:json.load(open(p)),sys.argv[1:])
for x,name in ((a,'CONTROL'),(b,'D3')):
 if x.get('arm')!=name or x.get('processed_rows')!=512 or x.get('exact_budget_failures')!=0 or x.get('budget_nodes')!=20000:
  raise SystemExit(f'{name} runtime report drift')
if a.get('d3_feature_calls')!=0: raise SystemExit('CONTROL unexpectedly exercised D3')
if not (b.get('d3_feature_calls',0)>0): raise SystemExit('D3 treatment not exercised')
PY

phase oracle-readout
scan_read_args=()
for i in $(seq -w 0 15); do scan_read_args+=(--scan-score "$IN/scan-${i}.tsv.gz"); done
"$PY" jobs/tools/scan_oracle_gate0_readout.py --groups "$IN/siblings.tsv" --ids "$ART/gate0-parent-ids.txt" \
  "${scan_read_args[@]}" --control "$ART/gate0-control.tsv" --candidate "$ART/gate0-d3.tsv" \
  --candidate-name D3 --out "$ART/scan-oracle-gate0-readout.json" >"$W/readout.log" 2>&1

VERDICT=$("$PY" - "$ART/scan-oracle-gate0-readout.json" <<'PY'
import json,sys
p=json.load(open(sys.argv[1])); print(p['gate']['verdict'])
PY
)
case "$VERDICT" in GATE0_SUPPORTED|GATE0_NOT_SUPPORTED) ;; *) die "unregistered Gate0 verdict";; esac
printf '%s\n' "$VERDICT" >"$ART/VERDICT__${VERDICT}"
printf '0\n' >"$ART/STRENGTH_GAMES__0"; printf '0\n' >"$ART/SCAN_SEARCHES__0"
printf 'false\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"; printf 'false\n' >"$ART/BAKE_AUTHORIZED__FALSE"
phase complete
say "Gate0 D3 retrospective complete verdict=$VERDICT scan_searches=0 strength_games=0"

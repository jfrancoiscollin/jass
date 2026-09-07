#!/usr/bin/env bash
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"; : "${JASS_STAGE_SPEC:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true; (cd "$W" && find . -maxdepth 1 -name '*.log' -type f -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true; rm -rf "$IN" "$W/candidate-src" "$W/build-control" 2>/dev/null || true; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

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

SPEC_CODE=$(python3 - "$JASS_STAGE_SPEC" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))['code_sha'])
PY
)
[ "$(git rev-parse HEAD)" = "$SPEC_CODE" ] || die "stage spec / HEAD mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX62 contract mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree must be detached and clean"

say "D3 runtime zero-game preflight start code=$SPEC_CODE"
unset JASS_D3_RUNTIME_ADAPTER JASS_D3_RUNTIME_BASE_MODEL JASS_DSSD_MOVE_ORDER_POLICY JASS_TB_MOVE_ORDER_POLICY || true

timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$D1_ROOT" \
  --file artefacts/WDL_CONTROL.pjtw.gz=WDL_CONTROL.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-d1-control.json" >"$W/fetch-d1.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$D3_ROOT" \
  --file artefacts/D3_RELATIONAL_ADAPTER.npy=D3_RELATIONAL_ADAPTER.npy \
  --file artefacts/scientific-summary.json=d3-offline-summary.json \
  --out-dir "$IN" --report "$ART/verified-d3.json" >"$W/fetch-d3.log" 2>&1

gunzip -c "$IN/WDL_CONTROL.pjtw.gz" >"$W/WDL_CONTROL.pjtw"
[ "$(sha256sum "$W/WDL_CONTROL.pjtw" | awk '{print $1}')" = "$MODEL_SHA" ] || die "WDL_CONTROL SHA drift"
[ "$(sha256sum "$IN/D3_RELATIONAL_ADAPTER.npy" | awk '{print $1}')" = "$ADAPTER_SHA" ] || die "D3 adapter SHA drift"
python3 - "$ART/verified-d1-control.json" "$ART/verified-d3.json" "$IN/d3-offline-summary.json" <<'PY'
import json,sys
v1,v3,s=map(lambda p:json.load(open(p)),sys.argv[1:])
assert (v1['job_id'],v1['attempt_id'],v1['code_sha'],v1['result_state']) == ('cpx62-1849-l3-decision-math-d1-wdl-listwise-fit-stage-env-recovery-requeue-v1','20260906T222203Z-08fd187a','08fd187aa187f26bd7179df2c68056a74e28355d','completed')
assert (v3['job_id'],v3['attempt_id'],v3['code_sha'],v3['result_state']) == ('cpx62-1854-l3-decision-math-d3-relational-action-fit-v1','20260907T073241Z-1bea99d0','1bea99d04ba1b4a2d79e36af8d4a1bc9be930453','completed')
assert s['verdict']=='D3_RELATIONAL_ACTION_TRANSFER_ESTABLISHED_V1'
PY

# Build pristine control.
cmake -S . -B "$W/build-control" -DCMAKE_BUILD_TYPE=Release \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake-control.log" 2>&1
cmake --build "$W/build-control" -j16 --target jass >"$W/build-control.log" 2>&1
CONTROL="$W/build-control/jass"

# Render candidate in an isolated source copy; repository search.cpp is never mutated.
mkdir -p "$W/candidate-src"
git archive HEAD | tar -x -C "$W/candidate-src"
python3 jobs/tools/d3_runtime_render.py --src "$W/candidate-src/src/search.cpp" --out "$W/candidate-search.cpp" >"$W/render.log" 2>&1
mv "$W/candidate-search.cpp" "$W/candidate-src/src/search.cpp"
cmake -S "$W/candidate-src" -B "$W/candidate-src/build" -DCMAKE_BUILD_TYPE=Release \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake-candidate.log" 2>&1
cmake --build "$W/candidate-src/build" -j16 --target jass >"$W/build-candidate.log" 2>&1
CANDIDATE="$W/candidate-src/build/jass"

# Frozen deterministic fixtures. Two generation passes must be byte-identical.
for pass in a b; do
  "$CONTROL" --gen-opening-pool 128 "$W/fixtures-$pass.fen" 8 32 20 2026111299 >"$W/fixtures-$pass.log" 2>&1
done
cmp -s "$W/fixtures-a.fen" "$W/fixtures-b.fen" || die "fixture generation not deterministic"
cp "$W/fixtures-a.fen" "$ART/d3-runtime-preflight-fixtures.fen"

PYTHONPATH=jobs/tools:. python3 jobs/tools/d3_runtime_preflight.py \
  --control "$CONTROL" --candidate "$CANDIDATE" --model "$W/WDL_CONTROL.pjtw" \
  --adapter "$IN/D3_RELATIONAL_ADAPTER.npy" --fixtures "$W/fixtures-a.fen" \
  --expected-model-sha "$MODEL_SHA" --expected-adapter-sha "$ADAPTER_SHA" \
  --out "$ART/D3_RUNTIME_PREFLIGHT.json" >"$W/preflight.log" 2>&1
cp "$ART/D3_RUNTIME_PREFLIGHT.json" "$ART/scientific-summary.json"
printf '0\n' >"$ART/FULL_FITS__0"; printf '0\n' >"$ART/STRENGTH_GAMES__0"
printf 'FALSE\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"; printf 'FALSE\n' >"$ART/BAKE_AUTHORIZED__FALSE"
say "D3_RUNTIME_MOVE_ORDERING_PREFLIGHT_COMPLETE_V1 fits=0 strength_games=0"

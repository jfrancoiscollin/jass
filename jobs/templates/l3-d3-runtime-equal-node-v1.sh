#!/usr/bin/env bash
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"; : "${JASS_STAGE_SPEC:?}"
: "${D3_RUNTIME_PREFLIGHT_JOB:?}"; : "${D3_RUNTIME_PREFLIGHT_ATTEMPT:?}"; : "${D3_RUNTIME_PREFLIGHT_CODE:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"; SHARDS="$W/shards"
mkdir -p "$W" "$IN" "$ART" "$SHARDS" "$ART/shards"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
MON=""
monitor(){ (t0=$(date +%s); while true; do
  reports=$(find "$SHARDS" -type f -name '*-report.json' 2>/dev/null | wc -l)
  { echo "elapsed_min=$((($(date +%s)-t0)/60))"; echo "shard_reports=$reports/16"; echo "planned_strength_games=1700"; } >"$PROG.tmp"
  mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 300
done) & MON="$!"; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt" 2>/dev/null || true
  (cd "$W" && find . -maxdepth 1 -name '*.log' -type f -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$IN" "$W/control-src" "$W/candidate-src" "$W/build-control" "$W/build-candidate" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "TECHNICAL_ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

D1_JOB="cpx62-1849-l3-decision-math-d1-wdl-listwise-fit-stage-env-recovery-requeue-v1"
D1_ATTEMPT="20260906T222203Z-08fd187a"
D1_CODE="08fd187aa187f26bd7179df2c68056a74e28355d"
D1_ROOT="r2:jass-data/runs/$D1_JOB/$D1_ATTEMPT"
D3_JOB="cpx62-1854-l3-decision-math-d3-relational-action-fit-v1"
D3_ATTEMPT="20260907T073241Z-1bea99d0"
D3_CODE="1bea99d04ba1b4a2d79e36af8d4a1bc9be930453"
D3_ROOT="r2:jass-data/runs/$D3_JOB/$D3_ATTEMPT"
C_JOB="cpx62-1845-l3-decision-math-c-sibling-dataset-v2-v1"
C_ATTEMPT="20260906T191758Z-4ae3fca8"
C_CODE="4ae3fca82f19338132911811978761b91bd39573"
C_ROOT="r2:jass-data/runs/$C_JOB/$C_ATTEMPT"
HIST_JOB="cpx62-1773-l3-decision-math-b2-historical-identities-v1"
HIST_ATTEMPT="20260905T012244Z-1490b353"
HIST_CODE="1490b3536f6943ec5eab62578ea7d42a29395a27"
HIST_ROOT="r2:jass-data/runs/$HIST_JOB/$HIST_ATTEMPT"
P_ROOT="r2:jass-data/runs/$D3_RUNTIME_PREFLIGHT_JOB/$D3_RUNTIME_PREFLIGHT_ATTEMPT"
MODEL_SHA="e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0"
ADAPTER_SHA="03cd2aa6b2a61ef8ce11dc878eb0ba13a56c8e587b49b19158135a1b64bfd4c3"
HIST_UNION_SHA="3a751ba967276f6e2562bfa7257dfa36fbe562e33cd710dd49abcfe51afdfc8f"
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"; PY="$VENV/bin/python"

SPEC_CODE=$("$PY" - "$JASS_STAGE_SPEC" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["code_sha"])
PY
)
[ "$(git rev-parse HEAD)" = "$SPEC_CODE" ] || die "stage spec / HEAD mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX62 contract mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree must be detached and clean"
[ -x "$PY" ] || die "numeric venv missing"
[ "$D3_RUNTIME_PREFLIGHT_JOB" = "cpx62-1855-l3-decision-math-d3-runtime-move-ordering-preflight-v1" ] || die "preflight job drift"
[ "$D3_RUNTIME_PREFLIGHT_ATTEMPT" = "20260907T144944Z-1621930e" ] || die "preflight attempt drift"
[ "$D3_RUNTIME_PREFLIGHT_CODE" = "1621930e74db8dfd5f3c0370c31f47f8d3c298c7" ] || die "preflight code drift"
unset JASS_D3_RUNTIME_ADAPTER JASS_D3_RUNTIME_BASE_MODEL JASS_DSSD_MOVE_ORDER_POLICY JASS_TB_MOVE_ORDER_POLICY || true

grep -Fq '2026111301' docs/experiments/L3_D3_RUNTIME_MOVE_ORDERING_PREREGISTRATION_V1_20260907.md
grep -Fq '2026111302:' docs/experiments/L3_D3_RUNTIME_MOVE_ORDERING_PREREGISTRATION_V1_20260907.md
grep -Fq '2026111303' docs/experiments/L3_D3_RUNTIME_MOVE_ORDERING_PREREGISTRATION_V1_20260907.md
grep -Fq '20,000' docs/experiments/L3_D3_RUNTIME_MOVE_ORDERING_PREREGISTRATION_V1_20260907.md
grep -Fq '51 - sq' docs/experiments/L3_D3_RUNTIME_MOVE_ORDERING_PREREGISTRATION_V1_20260907.md

say "D3 runtime equal-node start job=$JASS_JOB_ID code=$SPEC_CODE fits=0 strength_games=1700"
monitor

timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$P_ROOT" --expected-state completed \
  --file artefacts/D3_RUNTIME_PREFLIGHT.json=D3_RUNTIME_PREFLIGHT.json \
  --file artefacts/d3-runtime-preflight-fixtures.fen=d3-runtime-preflight-fixtures.fen \
  --out-dir "$IN" --report "$ART/verified-runtime-preflight.json" >"$W/fetch-preflight.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$D1_ROOT" --expected-state completed \
  --file artefacts/WDL_CONTROL.pjtw.gz=WDL_CONTROL.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-d1-control.json" >"$W/fetch-d1.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$D3_ROOT" --expected-state completed \
  --file artefacts/D3_RELATIONAL_ADAPTER.npy=D3_RELATIONAL_ADAPTER.npy \
  --file artefacts/scientific-summary.json=d3-offline-summary.json \
  --out-dir "$IN" --report "$ART/verified-d3.json" >"$W/fetch-d3.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$C_ROOT" --expected-state completed \
  --file artefacts/sibling-dataset-v2.jsonl=c-dataset.jsonl \
  --file artefacts/scientific-summary.json=c-summary.json \
  --out-dir "$IN" --report "$ART/verified-c.json" >"$W/fetch-c.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$HIST_ROOT" --expected-state completed \
  --file artefacts/historical-parent-canonical-union.txt=historical-parent-canonical-union.txt \
  --file artefacts/scientific-summary.json=historical-summary.json \
  --out-dir "$IN" --report "$ART/verified-historical.json" >"$W/fetch-historical.log" 2>&1

gunzip -c "$IN/WDL_CONTROL.pjtw.gz" >"$W/WDL_CONTROL.pjtw"
[ "$(sha256sum "$W/WDL_CONTROL.pjtw" | awk '{print $1}')" = "$MODEL_SHA" ] || die "WDL_CONTROL byte drift"
[ "$(sha256sum "$IN/D3_RELATIONAL_ADAPTER.npy" | awk '{print $1}')" = "$ADAPTER_SHA" ] || die "D3 adapter byte drift"
[ "$(sha256sum "$IN/historical-parent-canonical-union.txt" | awk '{print $1}')" = "$HIST_UNION_SHA" ] || die "historical union byte drift"

"$PY" - "$ART/verified-runtime-preflight.json" "$ART/verified-d1-control.json" \
 "$ART/verified-d3.json" "$ART/verified-c.json" "$ART/verified-historical.json" \
 "$IN/D3_RUNTIME_PREFLIGHT.json" "$IN/d3-offline-summary.json" "$IN/c-summary.json" "$IN/historical-summary.json" \
 "$D3_RUNTIME_PREFLIGHT_JOB" "$D3_RUNTIME_PREFLIGHT_ATTEMPT" "$D3_RUNTIME_PREFLIGHT_CODE" \
 "$D1_JOB" "$D1_ATTEMPT" "$D1_CODE" "$D3_JOB" "$D3_ATTEMPT" "$D3_CODE" \
 "$C_JOB" "$C_ATTEMPT" "$C_CODE" "$HIST_JOB" "$HIST_ATTEMPT" "$HIST_CODE" <<'PY'
import json,sys
vp,vd1,vd3,vc,vh,pre,d3s,cs,hs,pj,pa,pc,d1j,d1a,d1c,d3j,d3a,d3c,cj,ca,cc,hj,ha,hc=sys.argv[1:]
def load(p): return json.load(open(p))
for path,expect in [
 (vp,(pj,pa,pc)),(vd1,(d1j,d1a,d1c)),(vd3,(d3j,d3a,d3c)),
 (vc,(cj,ca,cc)),(vh,(hj,ha,hc))]:
 r=load(path)
 if (r.get("job_id"),r.get("attempt_id"),r.get("code_sha"),r.get("result_state")) != (*expect,"completed"):
  raise SystemExit(f"source identity drift: {path}")
p=load(pre)
if p.get("verdict")!="D3_RUNTIME_MOVE_ORDERING_PREFLIGHT_COMPLETE_V1" or p.get("strength_games")!=0 or p.get("fits")!=0:
 raise SystemExit("runtime preflight authority drift")
if p.get("adapter_sha256")!="03cd2aa6b2a61ef8ce11dc878eb0ba13a56c8e587b49b19158135a1b64bfd4c3":
 raise SystemExit("runtime adapter provenance drift")
if p.get("value_model_sha256")!="e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0":
 raise SystemExit("runtime WDL provenance drift")
if p.get("control_candidate_off_identity",{}).get("mismatches")!=0:
 raise SystemExit("runtime control identity drift")
if p.get("support",{}).get("below9_runtime_identity") is not True:
 raise SystemExit("runtime support amendment drift")
if load(d3s).get("verdict")!="D3_RELATIONAL_ACTION_TRANSFER_ESTABLISHED_V1":
 raise SystemExit("offline D3 terminal drift")
if load(cs).get("verdict")!="C_SIBLING_DATASET_V2_AUTHENTICATED_V1":
 raise SystemExit("C source drift")
h=load(hs)
if h.get("fresh_parent_generation")!=0 or h.get("new_fits")!=0:
 raise SystemExit("historical identity source drift")
PY

for pass in a b; do
  cmake -S . -B "$W/generator-build-$pass" -DCMAKE_BUILD_TYPE=Release \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
    >"$W/generator-cmake-$pass.log" 2>&1
  cmake --build "$W/generator-build-$pass" -j16 --target jass >"$W/generator-build-$pass.log" 2>&1
  "$W/generator-build-$pass/jass" --gen-opening-pool 30000 "$W/d3-equal-node-candidates-$pass.fen" 8 32 20 2026111301 \
    >"$W/generate-$pass.log" 2>&1
done
cmp -s "$W/d3-equal-node-candidates-a.fen" "$W/d3-equal-node-candidates-b.fen" || die "fresh generator replay drift"

"$PY" jobs/tools/d3_runtime_equal_node_pool.py \
  --candidates "$W/d3-equal-node-candidates-a.fen" \
  --exclude-canonical-file "$IN/historical-parent-canonical-union.txt" \
  --exclude-c-parent-jsonl "$IN/c-dataset.jsonl" \
  --exclude-fen "$IN/d3-runtime-preflight-fixtures.fen" \
  --out-primary "$ART/d3-equal-node-primary-openings.fen" \
  --out-harness "$ART/d3-equal-node-harness-openings.fen" \
  --manifest "$ART/d3-equal-node-selection-manifest.jsonl" \
  --report "$ART/d3-equal-node-pool-provenance.json" >"$W/pool-select.log" 2>&1

for arm in control candidate; do
  mkdir -p "$W/$arm-src"
  git archive HEAD | tar -x -C "$W/$arm-src"
done
"$PY" jobs/tools/d3_runtime_equal_node_render.py \
  --hub "$W/control-src/src/hub.cpp" --out-hub "$W/control-hub.cpp"
mv "$W/control-hub.cpp" "$W/control-src/src/hub.cpp"

"$PY" jobs/tools/d3_runtime_render.py --src "$W/candidate-src/src/search.cpp" --out "$W/candidate-search.cpp"
mv "$W/candidate-search.cpp" "$W/candidate-src/src/search.cpp"
"$PY" jobs/tools/d3_runtime_equal_node_render.py \
  --candidate \
  --hub "$W/candidate-src/src/hub.cpp" --out-hub "$W/candidate-hub.cpp" \
  --d3-header "$W/candidate-src/src/d3_runtime_move_order.hpp" --out-d3-header "$W/candidate-d3.hpp"
mv "$W/candidate-hub.cpp" "$W/candidate-src/src/hub.cpp"
mv "$W/candidate-d3.hpp" "$W/candidate-src/src/d3_runtime_move_order.hpp"

"$PY" - "$W/control-src" "$W/candidate-src" <<'PY'
import hashlib,sys
from pathlib import Path
a,b=map(Path,sys.argv[1:])
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
changed=[]
for p in sorted(x.relative_to(a) for x in a.rglob("*") if x.is_file()):
 q=b/p
 if not q.is_file() or digest(a/p)!=digest(q): changed.append(str(p))
if set(changed)!={"src/search.cpp","src/hub.cpp","src/d3_runtime_move_order.hpp"}:
 raise SystemExit(f"candidate/control source delta drift: {changed}")
PY

for arm in control candidate; do
  cmake -S "$W/$arm-src" -B "$W/build-$arm" -DCMAKE_BUILD_TYPE=Release \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
    >"$W/cmake-$arm.log" 2>&1
  cmake --build "$W/build-$arm" -j8 --target jass >"$W/build-$arm.log" 2>&1
done
CONTROL="$W/build-control/jass"; CANDIDATE="$W/build-candidate/jass"
[ -x "$CONTROL" ] && [ -x "$CANDIDATE" ] || die "equal-node binaries missing"

"$PY" -m py_compile jobs/tools/d3_runtime_equal_node_render.py jobs/tools/d3_runtime_equal_node_pool.py \
 jobs/tools/d3_runtime_equal_node.py jobs/tools/d3_runtime_equal_node_readout.py
"$PY" -m unittest jobs.tests.test_d3_runtime_equal_node >"$W/unit-tests.log" 2>&1
for f in jobs/tools/d3_runtime_equal_node.py jobs/tools/d3_runtime_equal_node_pool.py jobs/tools/d3_runtime_equal_node_readout.py; do
  ! grep -E -- '--qscore|SearchDecisionTrace|cpx62-1843|--teacher|--model-search' "$f" >/dev/null
done

make_shard(){
  s="$1"; d="$SHARDS/s$(printf '%02d' "$s")"; mkdir -p "$d"
  ps=$((750*s/8)); pe=$((750*(s+1)/8)); pn=$((pe-ps))
  hs=$((100*s/8)); he=$((100*(s+1)/8)); hn=$((he-hs))
  cat >"$d/run.sh" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
"$PY" jobs/tools/d3_runtime_equal_node.py --mode primary \
 --openings "$ART/d3-equal-node-primary-openings.fen" --start $ps --count $pn \
 --control "$CONTROL" --candidate "$CANDIDATE" --model "$W/WDL_CONTROL.pjtw" \
 --adapter "$IN/D3_RELATIONAL_ADAPTER.npy" \
 --out-games "$d/primary-games.jsonl" --out-report "$d/primary-report.json"
"$PY" jobs/tools/d3_runtime_equal_node.py --mode harness \
 --openings "$ART/d3-equal-node-harness-openings.fen" --start $hs --count $hn \
 --control "$CONTROL" --candidate "$CANDIDATE" --model "$W/WDL_CONTROL.pjtw" \
 --adapter "$IN/D3_RELATIONAL_ADAPTER.npy" \
 --out-games "$d/harness-games.jsonl" --out-report "$d/harness-report.json"
EOF
  chmod 0700 "$d/run.sh"
}
pids=(); labels=()
for s in $(seq 0 7); do
  make_shard "$s"; d="$SHARDS/s$(printf '%02d' "$s")"
  timeout -k 60s 7200s bash "$d/run.sh" >"$d/shard.log" 2>&1 &
  pids+=("$!"); labels+=("$s")
done
FAIL=0
for i in "${!pids[@]}"; do
  if ! wait "${pids[$i]}"; then say "SHARD_FAILED s=${labels[$i]}"; FAIL=1; fi
done
[ "$FAIL" -eq 0 ] || die "one or more equal-node shards failed; no game converted to draw"
[ "$(find "$SHARDS" -name '*-report.json' -type f | wc -l)" -eq 16 ] || die "shard report cardinality drift"
cp -a "$SHARDS"/* "$ART/shards/"

ARGS=(--preflight "$IN/D3_RUNTIME_PREFLIGHT.json" --pool-provenance "$ART/d3-equal-node-pool-provenance.json" \
      --code-sha "$SPEC_CODE" --out "$ART/D3_RUNTIME_EQUAL_NODE.json")
for s in $(seq 0 7); do d="$SHARDS/s$(printf '%02d' "$s")"
  ARGS+=(--primary-games "$d/primary-games.jsonl" --harness-games "$d/harness-games.jsonl")
done
"$PY" jobs/tools/d3_runtime_equal_node_readout.py "${ARGS[@]}" >"$W/readout.log" 2>&1
cp "$ART/D3_RUNTIME_EQUAL_NODE.json" "$ART/scientific-summary.json"
VERDICT=$("$PY" - "$ART/D3_RUNTIME_EQUAL_NODE.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["verdict"])
PY
)
printf '0\n' >"$ART/FULL_FITS__0"
printf '1700\n' >"$ART/STRENGTH_GAMES__1700"
printf 'FALSE\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"
printf 'FALSE\n' >"$ART/BAKE_AUTHORIZED__FALSE"
printf 'phase=done\nstrength_games=1700\nfits=0\nverdict=%s\n' "$VERDICT" >"$PROG"
say "D3 equal-node terminal verdict=$VERDICT strength_games=1700 fits=0 promotion=false bake=false"

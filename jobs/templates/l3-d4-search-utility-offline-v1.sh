#!/usr/bin/env bash
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"; : "${JASS_STAGE_SPEC:?}"
: "${JASS_JOB_ID:?}"; : "${D4_OFFLINE_EXECUTION_GO:?}"; : "${D4_TEACHER_SHARD_TIMEOUT_SECONDS:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART" "$W/teacher" "$ART/teacher-reports"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
phase(){ echo "$1" >"$STAGE"; say "phase=$1"; }

MON=""
monitor(){
  (t0=$(date +%s); while true; do
    done_shards=$(find "$W/teacher" -maxdepth 1 -name 's*-report.json' -type f 2>/dev/null | wc -l)
    {
      printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
      printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
      printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
      printf 'teacher_shards_done=%s/16\n' "$done_shards"
      printf 'teacher_roots_planned=4000\n'
      printf 'teacher_exact_nodes_per_root=50000\n'
      printf 'fits_planned=1\n'
      printf 'strength_games_planned=0\n'
    } >"$PROG.tmp"
    mv "$PROG.tmp" "$PROG"
    cp "$PROG" "$ART/PROGRESS.txt"
    sleep 300
  done) & MON="$!"
}
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt" 2>/dev/null || true
  (cd "$W" && find . -maxdepth 2 -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "TECHNICAL_ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
DFA=$(df -Pm /root | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 3000 ] || { say "ABORT disque <3Go"; exit 3; }
say "disk_free_mb=$DFA"

VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
PY="$VENV/bin/python"
[ -x "$PY" ] || die "numeric venv missing"
"$PY" -c 'import numpy, scipy' || die "numeric venv lacks NumPy/SciPy"

SPEC_CODE=$("$PY" - "$JASS_STAGE_SPEC" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["code_sha"])
PY
)
[ "$(git rev-parse HEAD)" = "$SPEC_CODE" ] || die "stage spec / HEAD mismatch"
[ "$(hostname)" = cpx62 ] || die "host must be cpx62"
[ "$(nproc)" -eq 16 ] || die "cpx62 nproc drift"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "worktree must be clean"
[ "$D4_OFFLINE_EXECUTION_GO" = 1 ] || die "D4 offline execution GO missing"
[[ "$D4_TEACHER_SHARD_TIMEOUT_SECONDS" =~ ^[0-9]+$ ]] || die "bad shard timeout"
[ "$D4_TEACHER_SHARD_TIMEOUT_SECONDS" -ge 60 ] && [ "$D4_TEACHER_SHARD_TIMEOUT_SECONDS" -le 3600 ] \
  || die "D4 shard timeout outside [60,3600]"

arch_assert(){
  local ref="$1" scratch="$W/arch-ref"
  mkdir -p "$scratch/src"
  for file in src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/movegen.cpp src/movegen.hpp; do
    git show "$ref:$file" >"$scratch/$file" || die "cannot materialize arch ref $ref:$file"
    cmp -s "$scratch/$file" "$file" || die "arch source is not byte-exact: $file"
  done
  grep -q 'g_emasks' src/scan_eval.cpp || die "arch guard: scan_eval missing g_emasks"
  grep -q 'has_any_capture' src/search.cpp || die "arch guard: search missing has_any_capture"
  grep -q 'has_any_capture' src/movegen.cpp || die "arch guard: movegen missing has_any_capture"
  say "arch_guard=PASS ref=$ref byte_exact=5 g_emasks=1 has_any_capture=2"
}
arch_assert "$SPEC_CODE"

"$PY" - docs/experiments/L3_D4_SEARCH_UTILITY_ORDERING_PREREGISTRATION_V1_20260907.json <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
assert p["schema"]=="jass.d4.search_utility_ordering_preregistration.v1"
assert p["dataset"]["candidate_roots"]==30000
assert p["dataset"]["generation_seed"]==2026111501
assert p["dataset"]["selector_prefix"]=="2026111502:"
assert p["dataset"]["selected_roots"]==4000
assert p["dataset"]["root_split"]=={"train":3200,"valid":400,"test":400}
assert p["dataset"]["teacher_exact_nodes"]==50000
assert p["dataset"]["examples"]=={"train":96000,"valid":12000,"test":12000}
assert p["model"]["trainable_parameters"]==96 and p["model"]["fits"]==1
assert p["model"]["l2"]==0.001 and p["model"]["max_iter"]==500
assert p["model"]["maxcor"]==10 and p["model"]["gtol"]==1e-6
assert p["offline_gate"]["bootstrap_repetitions"]==200000
assert p["offline_gate"]["bootstrap_seed"]==2026111503
assert p["runtime"]["scope"]=="first_up_to_4_legacy_non_tt_moves"
assert p["authorization"]=="implementation_and_preflight_plumbing_only_no_execution"
PY

D1_JOB="cpx62-1849-l3-decision-math-d1-wdl-listwise-fit-stage-env-recovery-requeue-v1"
D1_ATTEMPT="20260906T222203Z-08fd187a"
D1_CODE="08fd187aa187f26bd7179df2c68056a74e28355d"
D1_ROOT="r2:jass-data/runs/$D1_JOB/$D1_ATTEMPT"
MODEL_SHA="e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0"

C_JOB="cpx62-1845-l3-decision-math-c-sibling-dataset-v2-v1"
C_ATTEMPT="20260906T191758Z-4ae3fca8"
C_CODE="4ae3fca82f19338132911811978761b91bd39573"
C_ROOT="r2:jass-data/runs/$C_JOB/$C_ATTEMPT"

HIST_JOB="cpx62-1773-l3-decision-math-b2-historical-identities-v1"
HIST_ATTEMPT="20260905T012244Z-1490b353"
HIST_CODE="1490b3536f6943ec5eab62578ea7d42a29395a27"
HIST_ROOT="r2:jass-data/runs/$HIST_JOB/$HIST_ATTEMPT"
HIST_UNION_SHA="3a751ba967276f6e2562bfa7257dfa36fbe562e33cd710dd49abcfe51afdfc8f"

P_JOB="cpx62-1855-l3-decision-math-d3-runtime-move-ordering-preflight-v1"
P_ATTEMPT="20260907T144944Z-1621930e"
P_CODE="1621930e74db8dfd5f3c0370c31f47f8d3c298c7"
P_ROOT="r2:jass-data/runs/$P_JOB/$P_ATTEMPT"

EN_JOB="cpx62-1857-l3-decision-math-d3-runtime-equal-node-prereg-recovery-requeue-v1"
EN_ATTEMPT="20260907T155344Z-fcdcd217"
EN_CODE="fcdcd217cccb9d94aa7351b453dad725f3d816b1"
EN_ROOT="r2:jass-data/runs/$EN_JOB/$EN_ATTEMPT"

A_JOB="cpx62-1860-l3-decision-math-d3-runtime-terminal-autopsy-recovery-requeue-v1"
A_ATTEMPT="20260907T164613Z-0beb8796"
A_CODE="0beb8796be01a7977f1c6fe97efa4aac9fbae860"
A_ROOT="r2:jass-data/runs/$A_JOB/$A_ATTEMPT"

monitor
phase source-authentication
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$D1_ROOT" --expected-state completed \
  --file artefacts/WDL_CONTROL.pjtw.gz=WDL_CONTROL.pjtw.gz \
  --out-dir "$IN" --report "$ART/verified-d1-control.json" >"$W/fetch-d1.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$C_ROOT" --expected-state completed \
  --file artefacts/sibling-dataset-v2.jsonl=c-dataset.jsonl \
  --out-dir "$IN" --report "$ART/verified-c.json" >"$W/fetch-c.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$HIST_ROOT" --expected-state completed \
  --file artefacts/historical-parent-canonical-union.txt=historical-parent-canonical-union.txt \
  --out-dir "$IN" --report "$ART/verified-historical.json" >"$W/fetch-historical.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$P_ROOT" --expected-state completed \
  --file artefacts/d3-runtime-preflight-fixtures.fen=d3-runtime-preflight-fixtures.fen \
  --out-dir "$IN" --report "$ART/verified-d3-preflight.json" >"$W/fetch-preflight.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$EN_ROOT" --expected-state completed \
  --file artefacts/d3-equal-node-primary-openings.fen=d3-equal-node-primary-openings.fen \
  --file artefacts/d3-equal-node-harness-openings.fen=d3-equal-node-harness-openings.fen \
  --out-dir "$IN" --report "$ART/verified-d3-equal-node-openings.json" >"$W/fetch-equal-node-openings.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$A_ROOT" --expected-state completed \
  --file artefacts/scientific-summary.json=d3-autopsy-summary.json \
  --out-dir "$IN" --report "$ART/verified-d3-autopsy.json" >"$W/fetch-autopsy.log" 2>&1

gunzip -c "$IN/WDL_CONTROL.pjtw.gz" >"$W/WDL_CONTROL.pjtw"
[ "$(sha256sum "$W/WDL_CONTROL.pjtw" | awk '{print $1}')" = "$MODEL_SHA" ] || die "WDL_CONTROL byte drift"
[ "$(sha256sum "$IN/historical-parent-canonical-union.txt" | awk '{print $1}')" = "$HIST_UNION_SHA" ] \
  || die "historical union byte drift"

"$PY" - "$ART/verified-d1-control.json" "$ART/verified-c.json" "$ART/verified-historical.json" \
 "$ART/verified-d3-preflight.json" "$ART/verified-d3-equal-node-openings.json" "$ART/verified-d3-autopsy.json" \
 "$IN/d3-autopsy-summary.json" \
 "$D1_JOB" "$D1_ATTEMPT" "$D1_CODE" "$C_JOB" "$C_ATTEMPT" "$C_CODE" \
 "$HIST_JOB" "$HIST_ATTEMPT" "$HIST_CODE" "$P_JOB" "$P_ATTEMPT" "$P_CODE" \
 "$EN_JOB" "$EN_ATTEMPT" "$EN_CODE" "$A_JOB" "$A_ATTEMPT" "$A_CODE" <<'PY'
import json,sys
reports=list(map(lambda p:json.load(open(p)),sys.argv[1:7]))
aut=json.load(open(sys.argv[7]))
ids=sys.argv[8:]
expected=[tuple(ids[i:i+3]) for i in range(0,len(ids),3)]
for report, exp in zip(reports, expected):
    got=(report.get("job_id"),report.get("attempt_id"),report.get("code_sha"),report.get("result_state"))
    if got != (*exp,"completed"):
        raise SystemExit(f"source identity drift got={got} exp={exp}")
if aut.get("verdict")!="D3_RUNTIME_TERMINAL_AUTOPSY_COMPLETE_V1":
    raise SystemExit("D3 autopsy authority drift")
if aut.get("classification")!="BROAD_EQUAL_NODE_SEARCH_EFFICIENCY_DEGRADATION":
    raise SystemExit("D3 autopsy classification drift")
if aut.get("equal_time_authorized") is not False:
    raise SystemExit("D3 equal-time authority drift")
PY

phase contract-smoke
python3 -m py_compile \
  jobs/tools/d4_search_utility_pool.py \
  jobs/tools/d4_search_utility_trace_render.py \
  jobs/tools/d4_search_utility_offline.py \
  jobs/tools/d4_search_utility_teacher_aggregate.py
"$PY" -m unittest jobs.tests.test_d4_search_utility_offline -v >"$W/d4-unit-tests.log" 2>&1

phase fresh-root-generation
cmake -S . -B "$W/generator-build" -DCMAKE_BUILD_TYPE=Release \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
  >"$W/generator-cmake.log" 2>&1
cmake --build "$W/generator-build" -j16 --target jass >"$W/generator-build.log" 2>&1
timeout 900s "$W/generator-build/jass" --gen-opening-pool 30000 "$W/d4-root-candidates.fen" \
  8 32 20 2026111501 >"$W/generate-roots.log" 2>&1
[ "$(grep -cve '^[[:space:]]*$' "$W/d4-root-candidates.fen")" -eq 30000 ] \
  || die "D4 fresh root candidate cardinality drift"

phase target-blind-root-selection
"$PY" jobs/tools/d4_search_utility_pool.py \
  --candidates "$W/d4-root-candidates.fen" \
  --exclude-canonical-file "$IN/historical-parent-canonical-union.txt" \
  --exclude-c-parent-jsonl "$IN/c-dataset.jsonl" \
  --exclude-fen "$IN/d3-runtime-preflight-fixtures.fen" \
  --exclude-fen "$IN/d3-equal-node-primary-openings.fen" \
  --exclude-fen "$IN/d3-equal-node-harness-openings.fen" \
  --out-roots "$ART/d4-search-utility-roots.tsv" \
  --report "$ART/d4-root-pool-provenance.json" >"$W/root-select.log" 2>&1

phase isolated-teacher-build
mkdir -p "$W/teacher-src"
git archive HEAD | tar -x -C "$W/teacher-src"
"$PY" jobs/tools/d4_search_utility_trace_render.py --root "$W/teacher-src" \
  >"$W/teacher-render.log" 2>&1
cmake -S "$W/teacher-src" -B "$W/teacher-build" -DCMAKE_BUILD_TYPE=Release \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
  >"$W/teacher-cmake.log" 2>&1
cmake --build "$W/teacher-build" -j16 --target d4_search_utility_trace_export \
  >"$W/teacher-build.log" 2>&1

phase teacher-shard-manifests
for s in $(seq 0 15); do
  sid=$(printf '%02d' "$s")
  awk -F'\t' -v s="$s" 'NR==1{print $0;next} (($1 % 16)==s){print $0}' \
    "$ART/d4-search-utility-roots.tsv" >"$W/teacher/roots-s${sid}.tsv"
  [ "$(($(wc -l <"$W/teacher/roots-s${sid}.tsv")-1))" -eq 250 ] \
    || die "teacher shard $sid root cardinality drift"
done

phase teacher-searches
pids=()
for s in $(seq 0 15); do
  sid=$(printf '%02d' "$s")
  (
    set +e
    timeout "${D4_TEACHER_SHARD_TIMEOUT_SECONDS}s" \
      "$W/teacher-build/d4_search_utility_trace_export" \
      "$W/teacher/roots-s${sid}.tsv" \
      "$W/teacher/s${sid}-events.jsonl" \
      "$W/teacher/s${sid}-report.json" \
      "$W/WDL_CONTROL.pjtw" "$SPEC_CODE" "$MODEL_SHA" \
      >"$W/teacher-s${sid}.log" 2>&1
    rc=$?
    if [ "$rc" -eq 0 ]; then
      gzip -9 "$W/teacher/s${sid}-events.jsonl"
      rc=$?
    fi
    echo "$rc" >"$W/teacher/s${sid}.rc"
    exit 0
  ) &
  pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid"; done
for s in $(seq 0 15); do
  sid=$(printf '%02d' "$s")
  [ -f "$W/teacher/s${sid}.rc" ] || die "teacher shard $sid missing rc"
  [ "$(cat "$W/teacher/s${sid}.rc")" -eq 0 ] || die "teacher shard $sid failed rc=$(cat "$W/teacher/s${sid}.rc")"
  [ -s "$W/teacher/s${sid}-events.jsonl.gz" ] || die "teacher shard $sid empty events"
  [ -s "$W/teacher/s${sid}-report.json" ] || die "teacher shard $sid missing report"
  cp "$W/teacher/s${sid}-report.json" "$ART/teacher-reports/"
done

agg_args=()
prep_args=()
for s in $(seq 0 15); do
  sid=$(printf '%02d' "$s")
  agg_args+=(--report "$W/teacher/s${sid}-report.json")
  prep_args+=(--teacher "$W/teacher/s${sid}-events.jsonl.gz")
done
"$PY" jobs/tools/d4_search_utility_teacher_aggregate.py \
  "${agg_args[@]}" --code-sha "$SPEC_CODE" --model-sha256 "$MODEL_SHA" \
  --out "$ART/d4-teacher-aggregate.json" >"$W/teacher-aggregate.log" 2>&1

phase example-selection
set +e
"$PY" jobs/tools/d4_search_utility_offline.py prepare \
  --roots "$ART/d4-search-utility-roots.tsv" "${prep_args[@]}" \
  --train "$W/d4-train.jsonl" --valid "$W/d4-valid.jsonl" --test "$W/d4-test.jsonl" \
  --report "$ART/d4-example-prepare.json" >"$W/example-prepare.log" 2>&1
prep_rc=$?
set -e
if [ "$prep_rc" -eq 4 ]; then
  "$PY" - "$ART/d4-example-prepare.json" "$ART/d4-teacher-aggregate.json" "$SPEC_CODE" "$MODEL_SHA" "$ART/scientific-summary.json" <<'PY'
import json,sys
prepare=json.load(open(sys.argv[1])); teacher=json.load(open(sys.argv[2]))
out={
 "schema":"jass.d4.search_utility_offline_terminal.v1",
 "verdict":"D4_SEARCH_UTILITY_OFFLINE_INVALID_V1",
 "reason":"exact_or_phase_support_insufficient_after_frozen_selection",
 "code_sha":sys.argv[3],
 "science":{"target":"observed_beta_cutoff_causing_move_within_legacy_top4_non_tt",
            "model_width":96,"value_model_sha256":sys.argv[4],"fits":0,"model_searches":0},
 "prepare":prepare,
 "teacher_searches":teacher["teacher_searches"],
 "strength_games":0,"promotions":0,"bakes":0,
 "equal_node_authorized":False,"next_stage":"STOP_D4_OFFLINE",
 "game_outcome_reads":0,"qscore_reads":0,"search_decision_trace_reads":0,
 "full_ladder_1843_reads":0,"d3_score_reads":0,
}
json.dump(out,open(sys.argv[5],"w"),indent=2,sort_keys=True); open(sys.argv[5],"a").write("\n")
PY
  printf '0\n' >"$ART/FULL_FITS__0"
  printf '0\n' >"$ART/STRENGTH_GAMES__0"
  printf 'FALSE\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"
  printf 'FALSE\n' >"$ART/BAKE_AUTHORIZED__FALSE"
  say "D4_SEARCH_UTILITY_OFFLINE_INVALID_V1 support_insufficient fits=0 strength_games=0"
  rm -rf "$W/teacher-src" "$W/teacher-build" "$W/generator-build" "$W/teacher" 2>/dev/null || true
  exit 0
elif [ "$prep_rc" -ne 0 ]; then
  die "D4 example preparation technical failure rc=$prep_rc"
fi

phase single-train-fit
timeout 1800s "$PY" jobs/tools/d4_search_utility_offline.py fit \
  --train "$W/d4-train.jsonl" \
  --model "$W/D4_SEARCH_UTILITY_MODEL.npy" \
  --report "$ART/d4-fit-report.json" >"$W/d4-fit.log" 2>&1

phase heldout-terminal-readout
timeout 3600s "$PY" jobs/tools/d4_search_utility_offline.py readout \
  --model "$W/D4_SEARCH_UTILITY_MODEL.npy" \
  --valid "$W/d4-valid.jsonl" --test "$W/d4-test.jsonl" \
  --prepare-report "$ART/d4-example-prepare.json" \
  --fit-report "$ART/d4-fit-report.json" \
  --teacher-report "$ART/d4-teacher-aggregate.json" \
  --wdl-sha256 "$MODEL_SHA" \
  --report "$ART/scientific-summary.json" >"$W/d4-readout.log" 2>&1

cp "$W/D4_SEARCH_UTILITY_MODEL.npy" "$ART/D4_SEARCH_UTILITY_MODEL.npy"
gzip -9 -c "$W/d4-train.jsonl" >"$ART/d4-train-selected.jsonl.gz"
gzip -9 -c "$W/d4-valid.jsonl" >"$ART/d4-valid-selected.jsonl.gz"
gzip -9 -c "$W/d4-test.jsonl" >"$ART/d4-test-selected.jsonl.gz"
printf '1\n' >"$ART/FULL_FITS__1"
printf '0\n' >"$ART/STRENGTH_GAMES__0"
printf 'FALSE\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"
printf 'FALSE\n' >"$ART/BAKE_AUTHORIZED__FALSE"

VERDICT=$("$PY" - "$ART/scientific-summary.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]))
assert r["verdict"] in (
 "D4_SEARCH_UTILITY_OFFLINE_ESTABLISHED_V1",
 "D4_SEARCH_UTILITY_OFFLINE_NOT_ESTABLISHED_V1",
)
assert r["teacher_searches"]==4000 and r["strength_games"]==0
assert r["promotions"]==0 and r["bakes"]==0
print(r["verdict"])
PY
)
say "$VERDICT fits=1 teacher_searches=4000 strength_games=0"

rm -rf "$W/teacher-src" "$W/teacher-build" "$W/generator-build" "$W/teacher" 2>/dev/null || true
phase complete

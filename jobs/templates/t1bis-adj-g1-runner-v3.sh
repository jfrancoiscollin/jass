#!/usr/bin/env bash
# T1-bis ADJ+G1 launcher for runner-v3.
# The scientific shard counts and all model/gate parameters are preserved.
# Only simultaneous process counts and filesystem routing are changed.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?runner v3 must provide JASS_CODE_DIR}"
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
: "${JASS_ARTEFACT_DIR:?runner v3 must provide JASS_ARTEFACT_DIR}"
: "${JASS_JOB_ID:?runner v3 must provide JASS_JOB_ID}"
: "${NSH_GEN_TOTAL:?baseline generation shard count required}"
: "${NSH_RELABEL_TOTAL:?baseline relabel shard count required}"
: "${NSH_CONV_TOTAL:?baseline conversion shard count required}"
: "${NSH_GATE_TOTAL:?baseline gate shard count required}"

cd "$JASS_CODE_DIR"
JOB_ID="$JASS_JOB_ID"
PARENT_PJTW_GZ="${PARENT_PJTW_GZ:?export PARENT_PJTW_GZ}"
FIXED_PJTW_GZ="${FIXED_PJTW_GZ:-$PARENT_PJTW_GZ}"

PAR_GEN="${PAR_GEN:-8}"
PAR_RELABEL="${PAR_RELABEL:-8}"
PAR_CONV="${PAR_CONV:-4}"
PAR_GATE="${PAR_GATE:-4}"
JASS_BUILD_JOBS="${JASS_BUILD_JOBS:-8}"
GATE_WAIT_SECONDS="${GATE_WAIT_SECONDS:-86400}"
export PAR_GEN PAR_RELABEL PAR_CONV PAR_GATE JASS_BUILD_JOBS

W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
RUNTIME="$JASS_RESULT_DIR/t1bis-adj-g1-runtime.sh"
mkdir -p "$W" "$ART" "$JASS_RESULT_DIR/geom"
cp jobs/templates/t1bis-adj-g1-v2.sh "$RUNTIME"

python3 - "$RUNTIME" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"unexpected {label}: occurrences={count}")
    text = text.replace(old, new, 1)


replace_once("set -euo pipefail", "set -Eeuo pipefail", "strict mode")
replace_once("cd /root/jass", 'cd "${JASS_CODE_DIR:?}"', "code directory")
replace_once('exec 9>"/root/.jass-${JOB_ID}.lock"', 'exec 9>"${JASS_RESULT_DIR:?}/job.lock"', "lock path")
replace_once("NCPU=$(nproc)", 'NCPU="${JASS_BUILD_JOBS:-$(nproc)}"', "build concurrency")
replace_once('NSH_GEN="${NSH_GEN:-$NCPU}"', 'NSH_GEN="${NSH_GEN_TOTAL:?}"', "generation shards")
replace_once('NSH_RELABEL="${NSH_RELABEL:-$NCPU}"', 'NSH_RELABEL="${NSH_RELABEL_TOTAL:?}"', "relabel shards")
replace_once('NSH_CONV="${NSH_CONV:-8}"', 'NSH_CONV="${NSH_CONV_TOTAL:?}"', "conversion shards")
replace_once('NSH_GATE="${NSH_GATE:-$NCPU}"', 'NSH_GATE="${NSH_GATE_TOTAL:?}"', "gate shards")
replace_once('ART="/root/jass/jobs/results/$JOB_ID/artefacts"', 'ART="${JASS_ARTEFACT_DIR:?}"', "artefact path")
replace_once('W="/root/cw-$JOB_ID"', 'W="${JASS_RESULT_DIR:?}/work"', "work path")
replace_once('GEOM="/root/geom-$JOB_ID"', 'GEOM="${JASS_RESULT_DIR:?}/geom"', "geometry path")

old_diag = '''say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
'''
new_diag = '''say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
'''
replace_once(old_diag, new_diag, "diagnostic block")

old_openings = '''grep -v '^[[:space:]]*#' data/dilf_combinations.fen | sed 's/#.*//' | awk 'NF' | head -"$NOPEN" > "$W/open.fen"'''
new_openings = '''awk -v limit="$NOPEN" '\n  /^[[:space:]]*#/ { next }\n  {\n    sub(/#.*/, "")\n    if (NF) {\n      print\n      count++\n      if (count >= limit) exit\n    }\n  }\n' data/dilf_combinations.fen > "$W/open.fen"\n[ "$(wc -l < "$W/open.fen")" -eq "$NOPEN" ] || die "openings insuffisantes: $(wc -l < "$W/open.fen")/$NOPEN"'''
replace_once(old_openings, new_openings, "openings pipeline")

old_generation = '''pids=()
for shard in $(seq 0 $((NSH_GEN-1))); do
  timeout "$SHARD_TIMEOUT" python3 tools/scan_selfplay_gen.py \\
    --jass "$J" --player-jass-bin "$J" --player-pattern "$W/parent.pjtw" \\
    --seeds "$W/seeds.jnnw" --out "$W/sp.$shard" --games "$GAMES" \\
    --max-plies "$MAXPLIES" --min-pieces "$MINPC" --sample-every 1 --depth "$PLAYD" \\
    --seed 72800 --nshards "$NSH_GEN" --shard "$shard" \\
    --seed-pool "$W/g1_pool.fen" --seed-frac "$SEEDFRAC" \\
    --cap-arbiter d14 --egdb-dir "$EGDIR" --arb-depth "$ARB_DEPTH" \\
    --label-src-out "$W/lab.$shard" > "$W/sp.$shard.log" 2>&1 &
  pids+=("$!")
done
run_pids generation "${pids[@]}"'''
new_generation = '''pids=()
for shard in $(seq 0 $((NSH_GEN-1))); do
  timeout "$SHARD_TIMEOUT" python3 tools/scan_selfplay_gen.py \\
    --jass "$J" --player-jass-bin "$J" --player-pattern "$W/parent.pjtw" \\
    --seeds "$W/seeds.jnnw" --out "$W/sp.$shard" --games "$GAMES" \\
    --max-plies "$MAXPLIES" --min-pieces "$MINPC" --sample-every 1 --depth "$PLAYD" \\
    --seed 72800 --nshards "$NSH_GEN" --shard "$shard" \\
    --seed-pool "$W/g1_pool.fen" --seed-frac "$SEEDFRAC" \\
    --cap-arbiter d14 --egdb-dir "$EGDIR" --arb-depth "$ARB_DEPTH" \\
    --label-src-out "$W/lab.$shard" > "$W/sp.$shard.log" 2>&1 &
  pids+=("$!")
  if [ "${#pids[@]}" -ge "$PAR_GEN" ]; then
    run_pids generation-batch "${pids[@]}"
    pids=()
  fi
done
run_pids generation "${pids[@]}"'''
replace_once(old_generation, new_generation, "generation batching")

old_relabel = '''pids=()
for shard in $(seq 0 $((NSH_RELABEL-1))); do
  timeout "$RELABEL_TIMEOUT" "$J" --deep-relabel "$W/rs.$shard.jnnw" "$W/rr.$shard.jnnw" "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb "$CACHE_MB_RELABEL" > "$W/rr.$shard.log" 2>&1 &
  pids+=("$!")
done
run_pids relabel "${pids[@]}"'''
new_relabel = '''pids=()
for shard in $(seq 0 $((NSH_RELABEL-1))); do
  timeout "$RELABEL_TIMEOUT" "$J" --deep-relabel "$W/rs.$shard.jnnw" "$W/rr.$shard.jnnw" "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb "$CACHE_MB_RELABEL" > "$W/rr.$shard.log" 2>&1 &
  pids+=("$!")
  if [ "${#pids[@]}" -ge "$PAR_RELABEL" ]; then
    run_pids relabel-batch "${pids[@]}"
    pids=()
  fi
done
run_pids relabel "${pids[@]}"'''
replace_once(old_relabel, new_relabel, "relabel batching")

old_conversion = '''    pids+=("$!")
  done
  run_pids "conversion $stratum" "${pids[@]}"'''
new_conversion = '''    pids+=("$!")
    if [ "${#pids[@]}" -ge "$PAR_CONV" ]; then
      run_pids "conversion $stratum batch" "${pids[@]}"
      pids=()
    fi
  done
  run_pids "conversion $stratum" "${pids[@]}"'''
replace_once(old_conversion, new_conversion, "conversion batching")

count = text.count("python3 jobs/tools/run_jass_gate.py")
if count != 0:
    raise SystemExit(f"unexpected embedded gate runner in base template: occurrences={count}")

path.write_text(text, encoding="utf-8")
PY

chmod 0700 "$RUNTIME"
bash -n "$RUNTIME"
python3 -m py_compile jobs/tools/run_jass_gate_bounded.py

cat > "$W/gate_parent.json" <<'JSON'
{"wins_a":0,"draws":0,"wins_b":0,"n":0,"rate":null,"ci_low":null,"ci_high":null,"complete":false}
JSON
cp "$W/gate_parent.json" "$W/gate_fixed.json"
python3 jobs/tests/test_run_jass_gate.py >"$W/test_run_jass_gate.log" 2>&1

GATE_WORKER_PID=""
finalize(){
  rc=$?
  trap - EXIT
  set +e
  if [ -n "$GATE_WORKER_PID" ] && kill -0 "$GATE_WORKER_PID" 2>/dev/null; then
    kill "$GATE_WORKER_PID" 2>/dev/null || true
    wait "$GATE_WORKER_PID" 2>/dev/null || true
  fi
  cp "$RUNTIME" "$ART/runtime-script.sh" 2>/dev/null || true
  [ -f "$W/RESULTS.txt" ] && cp "$W/RESULTS.txt" "$ART/RESULTS.txt"
  for f in gate_parent.json gate_fixed.json promotion_input.json open.fen; do
    [ -f "$W/$f" ] && cp "$W/$f" "$ART/$f"
  done
  for f in candidate.pjtw gen.jnnw deep.jnnw adj.jnnw; do
    [ -s "$W/$f" ] && gzip -c "$W/$f" > "$ART/$f.gz"
  done
  if [ -d "$W" ]; then
    (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  fi
  {
    printf 'job_id=%s\n' "$JOB_ID"
    printf 'code_sha=%s\n' "$(git -C "$JASS_CODE_DIR" rev-parse HEAD 2>/dev/null || true)"
    printf 'nsh_gen_total=%s\n' "$NSH_GEN_TOTAL"
    printf 'nsh_relabel_total=%s\n' "$NSH_RELABEL_TOTAL"
    printf 'nsh_conv_total=%s\n' "$NSH_CONV_TOTAL"
    printf 'nsh_gate_total=%s\n' "$NSH_GATE_TOTAL"
    printf 'parallel_gen=%s\n' "$PAR_GEN"
    printf 'parallel_relabel=%s\n' "$PAR_RELABEL"
    printf 'parallel_conv=%s\n' "$PAR_CONV"
    printf 'parallel_gate=%s\n' "$PAR_GATE"
    printf 'exit_code=%s\n' "$rc"
  } > "$ART/runtime-profile.txt"
  exit "$rc"
}
trap finalize EXIT

(
  set -euo pipefail
  for _ in $(seq 1 "$GATE_WAIT_SECONDS"); do
    if [ -s "$W/build/jass" ] && [ -s "$W/candidate.pjtw" ] && \
       [ -s "$W/parent.pjtw" ] && [ -s "$W/fixed.pjtw" ] && [ -s "$W/open.fen" ]; then
      break
    fi
    sleep 1
  done
  [ -s "$W/candidate.pjtw" ] || exit 21

  python3 jobs/tools/run_jass_gate_bounded.py \
    --jass "$W/build/jass" \
    --pattern-a "$W/candidate.pjtw" \
    --pattern-b "$W/parent.pjtw" \
    --openings-file "$W/open.fen" \
    --search-params "${QS:-qs_forcing_depth=6,qs_promo_depth=6}" \
    --depth "${DEPTH:-9}" --pairs "${PAIRS:-1}" \
    --nshards "$NSH_GATE_TOTAL" --max-parallel "$PAR_GATE" \
    --timeout "${SHARD_TIMEOUT:-7000}" \
    --work-dir "$W/gate-parent" --out "$W/gate_parent.new.json"
  mv "$W/gate_parent.new.json" "$W/gate_parent.json"

  if cmp -s "$W/parent.pjtw" "$W/fixed.pjtw"; then
    cp "$W/gate_parent.json" "$W/gate_fixed.json"
  else
    python3 jobs/tools/run_jass_gate_bounded.py \
      --jass "$W/build/jass" \
      --pattern-a "$W/candidate.pjtw" \
      --pattern-b "$W/fixed.pjtw" \
      --openings-file "$W/open.fen" \
      --search-params "${QS:-qs_forcing_depth=6,qs_promo_depth=6}" \
      --depth "${DEPTH:-9}" --pairs "${PAIRS:-1}" \
      --nshards "$NSH_GATE_TOTAL" --max-parallel "$PAR_GATE" \
      --timeout "${SHARD_TIMEOUT:-7000}" \
      --work-dir "$W/gate-fixed" --out "$W/gate_fixed.new.json"
    mv "$W/gate_fixed.new.json" "$W/gate_fixed.json"
  fi
) >"$W/gate-worker.log" 2>&1 &
GATE_WORKER_PID=$!

bash "$RUNTIME"
wait "$GATE_WORKER_PID" || {
  echo "WARN: gate worker failed; promotion remains fail-closed" >&2
  exit 4
}

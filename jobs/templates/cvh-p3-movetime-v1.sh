#!/usr/bin/env bash
# id: cvh-p3-movetime-v1
# description: CVH Gen2-MMTO stage 2. Equal-time C10 vs bare Gen2 on a
# deterministic opening set disjoint from the common-search screen.
# TEMPLATE ONLY: queue only after stage-1 pass, measured ETA and explicit JFC go.
set -euo pipefail
cd /root/jass

CODE_SHA="${CODE_SHA:-6bfc700fcf4dd512e3383bc04abbdce2b382e688}"
JASS_JOB_ID="${JASS_JOB_ID:-ccx33-cvh-p3-movetime}"
: "${GEN2_A:?bare Gen2 PJTW required}"
: "${GEN2_C10:?lambda=10 PJTW copy required}"
: "${OPENINGS_FILE:?generalist opening FEN file required}"
: "${PRIOR_COMMON_VERDICT:?stage-1 common-verdict.json required}"
: "${PRIOR_COMMON_OPENINGS:?stage-1 common-openings.fen required for disjointness}"
: "${APPROVED_ETA_MIN:?approved numeric ETA required before queueing}"
: "${JFC_GO:?set JFC_GO=1 only after explicit approval}"
[[ "$JFC_GO" == 1 ]] || { echo "ABORT: explicit JFC go missing" >&2; exit 2; }

NCPU=$(nproc); SHARDS="${SHARDS:-$NCPU}"
MOVETIME="${MOVETIME:-0.10}"
MOVETIME_OPENINGS="${MOVETIME_OPENINGS:-48}"
MOVETIME_MIN_N="${MOVETIME_MIN_N:-64}"
MOVETIME_MIN_RATE="${MOVETIME_MIN_RATE:-0.49}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-3600}"
SEARCH_PARAMS="${SEARCH_PARAMS:-}"

abs_path(){ python3 - "$1" <<'PY'
import os,sys
print(os.path.abspath(sys.argv[1]))
PY
}
A_SRC=$(abs_path "$GEN2_A"); C10_SRC=$(abs_path "$GEN2_C10")
OPEN_SRC=$(abs_path "$OPENINGS_FILE"); PRIOR_JSON=$(abs_path "$PRIOR_COMMON_VERDICT")
PRIOR_OPEN=$(abs_path "$PRIOR_COMMON_OPENINGS")
for f in "$A_SRC" "$C10_SRC" "$C10_SRC.cvh" "$OPEN_SRC" "$PRIOR_JSON" "$PRIOR_OPEN"; do
  [[ -f "$f" ]] || { echo "ABORT missing $f" >&2; exit 2; }
done
[[ ! -e "$A_SRC.cvh" ]] || { echo "ABORT A must be bare" >&2; exit 2; }
python3 - "$PRIOR_JSON" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
if x.get('stage')!='common_search' or x.get('pass') is not True:
    raise SystemExit('prior common-search gate did not pass')
print('prior common-search pass verified')
PY

W="/root/cw-${JASS_JOB_ID}"; OUT_DIR="${OUT_DIR:-/root/jass/jobs/results/${JASS_JOB_ID}/artefacts}"
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
DFA=$(df -Pm /root | awk 'NR==2{print $4}'); [[ "${DFA:-0}" -gt 3000 ]] || { echo "ABORT disk <3GB" >&2; exit 3; }
rm -rf "$W"; mkdir -p "$W" "$OUT_DIR"; RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; : >"$RES"; : >"$PROG"
say(){ echo "$*" | tee -a "$RES"; }
cleanup(){ touch "$W/.stopmon" 2>/dev/null || true; if [[ -n "${MON_PID:-}" ]]; then wait "$MON_PID" 2>/dev/null || true; fi; git -C /root/jass worktree remove --force "$W/src" >/dev/null 2>&1 || true; }
trap cleanup EXIT
say "=== $JASS_JOB_ID code=$CODE_SHA nproc=$NCPU shards=$SHARDS approved_eta_min=$APPROVED_ETA_MIN ==="
say "movetime=$MOVETIME openings=$MOVETIME_OPENINGS"

git cat-file -e "$CODE_SHA^{commit}" 2>/dev/null || git fetch origin "$CODE_SHA"
git worktree add --detach "$W/src" "$CODE_SHA" >/dev/null
grep -q 'Cheap gate pre-check from popcounts only' "$W/src/src/conversion_head.cpp" || { say "ABORT architecture guard"; exit 4; }
cp "$A_SRC" "$W/A.pjtw"; cp "$C10_SRC" "$W/C10.pjtw"; cp "$C10_SRC.cvh" "$W/C10.pjtw.cvh"
cmp -s "$W/A.pjtw" "$W/C10.pjtw" || { say "ABORT A/C10 PJTW differ"; exit 4; }
export TMPDIR="$W/tmp"; mkdir -p "$TMPDIR"
cmake -S "$W/src" -B "$W/build" -DCMAKE_BUILD_TYPE=Release >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -30 "$W/build.log"|tee -a "$RES"; exit 6; }
J="$W/build/jass"

# New deterministic set, with exact FEN exclusion against stage 1.
python3 - "$OPEN_SRC" "$PRIOR_OPEN" "$W/movetime-openings.fen" "$MOVETIME_OPENINGS" <<'PY'
import random,sys
src,used,out,n=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4])
def rows(path):
    xs=[ln.split('#',1)[0].strip() for ln in open(path,encoding='utf-8')]
    return [x for x in xs if x]
old=set(rows(used)); pool=[x for x in rows(src) if x not in old]
if len(pool)<n: raise SystemExit(f'need {n} disjoint openings, found {len(pool)}')
r=random.Random(161803); r.shuffle(pool)
open(out,'w',encoding='utf-8').write('\n'.join(pool[:n])+'\n')
PY

# Smoke one opening pair validates movetime reporting before the full match.
head -n 1 "$W/movetime-openings.fen" >"$W/smoke-openings.fen"
smoke=(python3 "$W/src/tools/jass_vs_jass_arch.py" --jass-a "$J" --pattern-a "$W/C10.pjtw"
       --jass-b "$J" --pattern-b "$W/A.pjtw" --movetime "$MOVETIME" --pairs 1
       --max-plies 220 --shard 0 --nshards 1 --quiet --openings-file "$W/smoke-openings.fen")
[[ -z "$SEARCH_PARAMS" ]] || smoke+=(--search-params-a "$SEARCH_PARAMS" --search-params-b "$SEARCH_PARAMS")
timeout 300 "${smoke[@]}" >"$W/smoke.log" 2>&1
python3 "$W/src/jobs/tools/cvh_followup_verdict.py" aggregate-match "$W/smoke.log" --out "$W/smoke.json" >/dev/null
python3 - "$W/smoke.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); assert x['n']==2
print('movetime smoke write/read OK')
PY

(
  while [[ ! -e "$W/.stopmon" ]]; do
    sleep 600; [[ -e "$W/.stopmon" ]] && break
    python3 "$W/src/jobs/tools/cvh_followup_verdict.py" aggregate-match "$W"/movetime.*.log --out "$W/movetime-partial.json" >"$PROG" 2>/dev/null || true
    cp "$PROG" "$OUT_DIR/PROGRESS.txt" 2>/dev/null || true
  done
) & MON_PID=$!

pids=(); rcs=0
for s in $(seq 0 $((SHARDS-1))); do
  cmd=(python3 "$W/src/tools/jass_vs_jass_arch.py" --jass-a "$J" --pattern-a "$W/C10.pjtw"
       --jass-b "$J" --pattern-b "$W/A.pjtw" --movetime "$MOVETIME" --pairs 1
       --max-plies 220 --shard "$s" --nshards "$SHARDS" --quiet
       --openings-file "$W/movetime-openings.fen" --progress-file "$W/movetime.$s.progress")
  [[ -z "$SEARCH_PARAMS" ]] || cmd+=(--search-params-a "$SEARCH_PARAMS" --search-params-b "$SEARCH_PARAMS")
  ( timeout "$SHARD_TIMEOUT" "${cmd[@]}" >"$W/movetime.$s.log" 2>&1 ) & pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid" || rcs=1; done
touch "$W/.stopmon"; wait "$MON_PID" 2>/dev/null || true; unset MON_PID
[[ "$rcs" -eq 0 ]] || { say "ABORT movetime shard failure/timeout"; exit 7; }

python3 "$W/src/jobs/tools/cvh_followup_verdict.py" aggregate-match "$W"/movetime.*.log --out "$W/movetime-match.json" | tee -a "$RES"
if ! python3 "$W/src/jobs/tools/cvh_followup_verdict.py" match-gate --match "$W/movetime-match.json" \
    --stage movetime --min-n "$MOVETIME_MIN_N" --min-rate "$MOVETIME_MIN_RATE" \
    --out "$W/movetime-verdict.json" | tee -a "$RES"; then
  say "STOP: movetime regression; do not run high-N P3 confirmation"
  cp "$W"/*.json "$RES" "$W/movetime-openings.fen" "$OUT_DIR"/ 2>/dev/null || true
  exit 3
fi
say "PASS: C10 eligible for separate high-N paired P3 confirmation"
cp "$W"/*.json "$RES" "$W/movetime-openings.fen" "$OUT_DIR"/
say "=== end $JASS_JOB_ID ==="

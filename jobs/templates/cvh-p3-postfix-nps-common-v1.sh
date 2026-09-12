#!/usr/bin/env bash
# id: cvh-p3-postfix-nps-common-v1
# description: CVH Gen2-MMTO stage 1 after 6bfc700fc: paired A/Z/C10
# fixed-depth speed on off-gate and P3 positions, then light common-search.
# TEMPLATE ONLY: do not copy to jobs/queue without measured ETA and explicit JFC go.
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$REPO_ROOT"
CODE_SHA="${CODE_SHA:-6bfc700fcf4dd512e3383bc04abbdce2b382e688}"
HARNESS_SHA="${HARNESS_SHA:-$(git rev-parse HEAD)}"
JASS_JOB_ID="${JASS_JOB_ID:-ccx33-cvh-p3-postfix-common}"
: "${GEN2_A:?absolute or repo-relative bare Gen2 PJTW required}"
: "${GEN2_Z:?lambda=0 PJTW copy required}"
: "${GEN2_C10:?lambda=10 PJTW copy required}"
: "${NPS_CORPUS:?JNNW containing both off-gate and P3 positions required}"
: "${OPENINGS_FILE:?generalist opening FEN file required}"
: "${APPROVED_ETA_MIN:?approved numeric ETA required before queueing}"
: "${JFC_GO:?set JFC_GO=1 only after explicit approval}"
[[ "$JFC_GO" == 1 ]] || { echo "ABORT: explicit JFC go missing" >&2; exit 2; }

NCPU=$(nproc)
SHARDS="${SHARDS:-$NCPU}"
NPS_N="${NPS_N:-40}"
NPS_DEPTHS="${NPS_DEPTHS:-9,12}"
COMMON_OPENINGS="${COMMON_OPENINGS:-48}"
COMMON_DEPTH="${COMMON_DEPTH:-10}"
COMMON_MIN_N="${COMMON_MIN_N:-64}"
COMMON_MIN_RATE="${COMMON_MIN_RATE:-0.49}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-2700}"
SEARCH_PARAMS="${SEARCH_PARAMS:-}"

abs_path(){ python3 - "$1" <<'PY'
import os,sys
print(os.path.abspath(sys.argv[1]))
PY
}
A_SRC=$(abs_path "$GEN2_A"); Z_SRC=$(abs_path "$GEN2_Z"); C10_SRC=$(abs_path "$GEN2_C10")
NPS_SRC=$(abs_path "$NPS_CORPUS"); OPEN_SRC=$(abs_path "$OPENINGS_FILE")
for f in "$A_SRC" "$Z_SRC" "$C10_SRC" "$NPS_SRC" "$OPEN_SRC" "$Z_SRC.cvh" "$C10_SRC.cvh"; do
  [[ -f "$f" ]] || { echo "ABORT missing $f" >&2; exit 2; }
done
[[ ! -e "$A_SRC.cvh" ]] || { echo "ABORT A must be bare (no .cvh)" >&2; exit 2; }

W="/root/cw-${JASS_JOB_ID}"
OUT_DIR="${OUT_DIR:-$REPO_ROOT/jobs/results/${JASS_JOB_ID}/artefacts}"
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
DFA=$(df -Pm /root | awk 'NR==2{print $4}')
[[ "${DFA:-0}" -gt 3000 ]] || { echo "ABORT disk <3GB" >&2; exit 3; }
rm -rf "$W"; mkdir -p "$W" "$OUT_DIR"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; : >"$RES"; : >"$PROG"
say(){ echo "$*" | tee -a "$RES"; }
cleanup(){
  touch "$W/.stopmon" 2>/dev/null || true
  if [[ -n "${MON_PID:-}" ]]; then wait "$MON_PID" 2>/dev/null || true; fi
  git -C "$REPO_ROOT" worktree remove --force "$W/src" >/dev/null 2>&1 || true
  git -C "$REPO_ROOT" worktree remove --force "$W/harness" >/dev/null 2>&1 || true
}
trap cleanup EXIT

say "=== $JASS_JOB_ID ==="
say "code_sha=$CODE_SHA harness_sha=$HARNESS_SHA nproc=$NCPU shards=$SHARDS approved_eta_min=$APPROVED_ETA_MIN"
say "nps_n=$NPS_N depths=$NPS_DEPTHS common_openings=$COMMON_OPENINGS common_depth=$COMMON_DEPTH"

git cat-file -e "$CODE_SHA^{commit}" 2>/dev/null || git fetch origin "$CODE_SHA"
git cat-file -e "$HARNESS_SHA^{commit}" 2>/dev/null || git fetch origin "$HARNESS_SHA"
git worktree add --detach "$W/src" "$CODE_SHA" >/dev/null
git worktree add --detach "$W/harness" "$HARNESS_SHA" >/dev/null
H="$W/harness"
grep -q 'Cheap gate pre-check from popcounts only' "$W/src/src/conversion_head.cpp" || {
  say "ABORT architecture guard: 6bfc pre-gate absent"; exit 4; }
for f in "$H/tools/cvh_nps_ab.py" "$H/jobs/tools/cvh_followup_verdict.py" "$H/tools/jass_vs_jass_arch.py"; do
  [[ -f "$f" ]] || { say "ABORT harness missing $f at $HARNESS_SHA"; exit 4; }
done

cp "$A_SRC" "$W/A.pjtw"
cp "$Z_SRC" "$W/Z.pjtw"; cp "$Z_SRC.cvh" "$W/Z.pjtw.cvh"
cp "$C10_SRC" "$W/C10.pjtw"; cp "$C10_SRC.cvh" "$W/C10.pjtw.cvh"
cmp -s "$W/A.pjtw" "$W/Z.pjtw" || { say "ABORT A/Z PJTW differ"; exit 4; }
cmp -s "$W/A.pjtw" "$W/C10.pjtw" || { say "ABORT A/C10 PJTW differ"; exit 4; }
python3 - "$W/Z.pjtw.cvh" "$W/C10.pjtw.cvh" <<'PY'
import struct,sys
vals=[]
for p in sys.argv[1:]:
    b=open(p,'rb').read()
    if len(b)!=244 or b[:4]!=b'CVH1': raise SystemExit(f'bad CVH1 {p}')
    vals.append(struct.unpack_from('<f',b,16)[0])
if abs(vals[0])>1e-7 or abs(vals[1]-10.0)>1e-6:
    raise SystemExit(f'bad lambdas Z/C10={vals}')
print(f'CVH lambdas OK Z={vals[0]} C10={vals[1]}')
PY

export TMPDIR="$W/tmp"; mkdir -p "$TMPDIR"
cmake -S "$W/src" -B "$W/build" -DCMAKE_BUILD_TYPE=Release >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || {
  say "BUILD FAIL"; tail -30 "$W/build.log" | tee -a "$RES"; exit 6; }
J="$W/build/jass"
python3 -m py_compile "$H/tools/cvh_nps_ab.py" "$H/jobs/tools/cvh_followup_verdict.py"
sha256sum "$H/tools/cvh_nps_ab.py" "$H/jobs/tools/cvh_followup_verdict.py" "$H/tools/jass_vs_jass_arch.py" | tee -a "$RES"

SMOKE=(python3 "$H/tools/cvh_nps_ab.py" --jass "$J"
  --cell A="$W/A.pjtw" --cell Z="$W/Z.pjtw" --cell C10="$W/C10.pjtw"
  --positions "$NPS_SRC" --filter offgate --n 2 --depths 4 --warmup 0)
[[ -z "$SEARCH_PARAMS" ]] || SMOKE+=(--search-params "$SEARCH_PARAMS")
"${SMOKE[@]}" --out "$W/smoke-nps.json" >/dev/null
python3 - "$W/smoke-nps.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
assert set(x['cells'])=={'A','Z','C10'}
assert x['az_common_searches']>0 and x['az_move_mismatches']==0
assert all(v['searches']>0 and v['errors']==0 for v in x['cells'].values())
print('smoke write/read OK')
PY

say "--- paired fixed-depth speed ---"
COMMON_NPS=(--jass "$J" --cell A="$W/A.pjtw" --cell Z="$W/Z.pjtw" --cell C10="$W/C10.pjtw"
  --positions "$NPS_SRC" --n "$NPS_N" --depths "$NPS_DEPTHS" --seed 314159)
[[ -z "$SEARCH_PARAMS" ]] || COMMON_NPS+=(--search-params "$SEARCH_PARAMS")
python3 "$H/tools/cvh_nps_ab.py" "${COMMON_NPS[@]}" --filter offgate --out "$W/nps-general.json" | tee -a "$RES"
python3 "$H/tools/cvh_nps_ab.py" "${COMMON_NPS[@]}" --filter p3 --out "$W/nps-p3.json" | tee -a "$RES"
if ! python3 "$H/jobs/tools/cvh_followup_verdict.py" nps-gate \
    --general "$W/nps-general.json" --p3 "$W/nps-p3.json" --out "$W/nps-verdict.json" | tee -a "$RES"; then
  say "STOP: NPS gate failed; common-search not run"
  cp "$W"/*.json "$RES" "$OUT_DIR"/ 2>/dev/null || true
  exit 3
fi

python3 - "$OPEN_SRC" "$W/common-openings.fen" "$COMMON_OPENINGS" <<'PY'
import random,sys
src,out,n=sys.argv[1],sys.argv[2],int(sys.argv[3])
rows=[ln.split('#',1)[0].strip() for ln in open(src,encoding='utf-8')]
rows=[x for x in rows if x]
if len(rows)<n: raise SystemExit(f'need {n} openings, found {len(rows)}')
r=random.Random(271828); r.shuffle(rows)
open(out,'w',encoding='utf-8').write('\n'.join(rows[:n])+'\n')
PY
EXPECTED_GAMES=$((2 * COMMON_OPENINGS))
say "--- common-search C10(A) vs Gen2(B): expected_games=$EXPECTED_GAMES ---"

(
  while [[ ! -e "$W/.stopmon" ]]; do
    sleep 600
    [[ -e "$W/.stopmon" ]] && break
    python3 "$H/jobs/tools/cvh_followup_verdict.py" aggregate-match "$W"/common.*.log \
      --out "$W/common-partial.json" >"$PROG" 2>/dev/null || true
    cp "$PROG" "$OUT_DIR/PROGRESS.txt" 2>/dev/null || true
  done
) & MON_PID=$!

pids=(); rcs=0
for s in $(seq 0 $((SHARDS-1))); do
  cmd=(python3 "$H/tools/jass_vs_jass_arch.py" --jass-a "$J" --pattern-a "$W/C10.pjtw"
       --jass-b "$J" --pattern-b "$W/A.pjtw" --depth "$COMMON_DEPTH" --pairs 1
       --max-plies 220 --shard "$s" --nshards "$SHARDS" --quiet
       --openings-file "$W/common-openings.fen" --progress-file "$W/common.$s.progress")
  [[ -z "$SEARCH_PARAMS" ]] || cmd+=(--search-params-a "$SEARCH_PARAMS" --search-params-b "$SEARCH_PARAMS")
  ( timeout "$SHARD_TIMEOUT" "${cmd[@]}" >"$W/common.$s.log" 2>&1 ) & pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid" || rcs=1; done
touch "$W/.stopmon"; wait "$MON_PID" 2>/dev/null || true; unset MON_PID
[[ "$rcs" -eq 0 ]] || { say "ABORT common-search shard failure/timeout"; exit 7; }

python3 "$H/jobs/tools/cvh_followup_verdict.py" aggregate-match "$W"/common.*.log \
  --out "$W/common-match.json" | tee -a "$RES"
if ! python3 "$H/jobs/tools/cvh_followup_verdict.py" match-gate \
    --match "$W/common-match.json" --stage common_search --min-n "$COMMON_MIN_N" \
    --min-rate "$COMMON_MIN_RATE" --out "$W/common-verdict.json" | tee -a "$RES"; then
  say "STOP: common-search regression; do not run movetime"
  cp "$W"/*.json "$RES" "$OUT_DIR"/ 2>/dev/null || true
  exit 3
fi

say "PASS: C10 eligible for separate movetime job"
cp "$W"/*.json "$RES" "$W/common-openings.fen" "$OUT_DIR"/
say "=== end $JASS_JOB_ID ==="

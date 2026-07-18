#!/usr/bin/env bash
# id: cvh-p3-confirm-v1
# description: CVH Gen2-MMTO stage 3. High-N paired P3 conversion confirmation
# after both common-search and movetime non-regression gates pass.
# TEMPLATE ONLY: queue only after measured ETA and explicit JFC go.
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$REPO_ROOT"

CODE_SHA="${CODE_SHA:-6bfc700fcf4dd512e3383bc04abbdce2b382e688}"
HARNESS_SHA="${HARNESS_SHA:-$(git rev-parse HEAD)}"
JASS_JOB_ID="${JASS_JOB_ID:-ccx33-cvh-p3-confirm}"
: "${GEN2_A:?bare Gen2 PJTW required}"
: "${GEN2_C10:?lambda=10 PJTW copy required}"
: "${P3_CONFIRM_POOL:?independent JNNW confirmation pool required}"
: "${PRIOR_MOVETIME_VERDICT:?stage-2 movetime-verdict.json required}"
: "${APPROVED_ETA_MIN:?approved numeric ETA required before queueing}"
: "${JFC_GO:?set JFC_GO=1 only after explicit approval}"
[[ "$JFC_GO" == 1 ]] || { echo "ABORT: explicit JFC go missing" >&2; exit 2; }

NCPU=$(nproc); SHARDS="${SHARDS:-$NCPU}"
CONFIRM_N="${CONFIRM_N:-600}"
CONFIRM_MIN_N="${CONFIRM_MIN_N:-400}"
CONFIRM_DEPTH="${CONFIRM_DEPTH:-10}"
CONFIRM_MIN_DELTA="${CONFIRM_MIN_DELTA:-0.02}"
MAX_PLIES="${MAX_PLIES:-260}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-5400}"
SEARCH_PARAMS="${SEARCH_PARAMS:-}"

abs_path(){ python3 - "$1" <<'PY'
import os,sys
print(os.path.abspath(sys.argv[1]))
PY
}
A_SRC=$(abs_path "$GEN2_A"); C10_SRC=$(abs_path "$GEN2_C10")
POOL_SRC=$(abs_path "$P3_CONFIRM_POOL"); PRIOR_JSON=$(abs_path "$PRIOR_MOVETIME_VERDICT")
for f in "$A_SRC" "$C10_SRC" "$C10_SRC.cvh" "$POOL_SRC" "$PRIOR_JSON"; do
  [[ -f "$f" ]] || { echo "ABORT missing $f" >&2; exit 2; }
done
[[ ! -e "$A_SRC.cvh" ]] || { echo "ABORT A must be bare" >&2; exit 2; }
python3 - "$PRIOR_JSON" <<'PY'
import json,sys
x=json.load(open(sys.argv[1]))
if x.get('stage')!='movetime' or x.get('pass') is not True:
    raise SystemExit('prior movetime gate did not pass')
print('prior movetime pass verified')
PY

W="/root/cw-${JASS_JOB_ID}"; OUT_DIR="${OUT_DIR:-$REPO_ROOT/jobs/results/${JASS_JOB_ID}/artefacts}"
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
DFA=$(df -Pm /root | awk 'NR==2{print $4}'); [[ "${DFA:-0}" -gt 3000 ]] || { echo "ABORT disk <3GB" >&2; exit 3; }
rm -rf "$W"; mkdir -p "$W" "$OUT_DIR"; RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; : >"$RES"; : >"$PROG"
say(){ echo "$*" | tee -a "$RES"; }
cleanup(){ touch "$W/.stopmon" 2>/dev/null || true; if [[ -n "${MON_PID:-}" ]]; then wait "$MON_PID" 2>/dev/null || true; fi; git -C "$REPO_ROOT" worktree remove --force "$W/src" >/dev/null 2>&1 || true; git -C "$REPO_ROOT" worktree remove --force "$W/harness" >/dev/null 2>&1 || true; }
trap cleanup EXIT
say "=== $JASS_JOB_ID code=$CODE_SHA harness=$HARNESS_SHA nproc=$NCPU shards=$SHARDS approved_eta_min=$APPROVED_ETA_MIN ==="
say "confirm_n=$CONFIRM_N min_paired_n=$CONFIRM_MIN_N depth=$CONFIRM_DEPTH min_delta=$CONFIRM_MIN_DELTA"

git cat-file -e "$CODE_SHA^{commit}" 2>/dev/null || git fetch origin "$CODE_SHA"
git cat-file -e "$HARNESS_SHA^{commit}" 2>/dev/null || git fetch origin "$HARNESS_SHA"
git worktree add --detach "$W/src" "$CODE_SHA" >/dev/null
git worktree add --detach "$W/harness" "$HARNESS_SHA" >/dev/null
H="$W/harness"
grep -q 'Cheap gate pre-check from popcounts only' "$W/src/src/conversion_head.cpp" || { say "ABORT architecture guard"; exit 4; }
for f in "$H/jobs/tools/conv_fixed_wdl.py" "$H/jobs/tools/cvh_followup_verdict.py"; do
  [[ -f "$f" ]] || { say "ABORT harness missing $f at $HARNESS_SHA"; exit 4; }
done
cp "$A_SRC" "$W/A.pjtw"; cp "$C10_SRC" "$W/C10.pjtw"; cp "$C10_SRC.cvh" "$W/C10.pjtw.cvh"
cmp -s "$W/A.pjtw" "$W/C10.pjtw" || { say "ABORT A/C10 PJTW differ"; exit 4; }
export TMPDIR="$W/tmp"; mkdir -p "$TMPDIR"
cmake -S "$W/src" -B "$W/build" -DCMAKE_BUILD_TYPE=Release >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -30 "$W/build.log"|tee -a "$RES"; exit 6; }
J="$W/build/jass"
python3 -m py_compile "$H/jobs/tools/conv_fixed_wdl.py" "$H/jobs/tools/cvh_followup_verdict.py"
sha256sum "$H/jobs/tools/conv_fixed_wdl.py" "$H/jobs/tools/cvh_followup_verdict.py" | tee -a "$RES"

# Freeze an independent P3 subset where the material leader is certified as the
# winner. This matches the auxiliary target and ensures conv_fixed_wdl assigns
# the candidate to the leader rather than to a materially trailing winner.
python3 - "$POOL_SRC" "$W/p3-confirm.jnnw" "$CONFIRM_N" <<'PY'
import random,struct,sys
src,out,n=sys.argv[1],sys.argv[2],int(sys.argv[3]); raw=open(src,'rb').read()
if len(raw)<8 or raw[:4]!=b'JNNW': raise SystemExit('bad JNNW')
cnt=struct.unpack_from('<I',raw,4)[0]; body=raw[8:]; rec=38
if len(body)!=cnt*rec: raise SystemExit('truncated JNNW')
keep=[]
for i in range(cnt):
    r=body[i*rec:(i+1)*rec]
    wm,wk,bm,bk=struct.unpack_from('<QQQQ',r,0)
    stm=r[32]
    wdl=struct.unpack_from('<b',r,37)[0]
    pieces=sum(x.bit_count() for x in (wm,wk,bm,bk))
    white_value=wm.bit_count()+3*wk.bit_count()
    black_value=bm.bit_count()+3*bk.bit_count()
    margin=abs(black_value-white_value)
    if wdl == 0 or margin != 1 or not (8 <= pieces < 20):
        continue
    leader=1 if black_value > white_value else 0
    winner=stm if wdl > 0 else 1-stm
    if winner == leader:
        keep.append(r)
if len(keep)<n: raise SystemExit(f'need {n} certified leader-winning P3 records, found {len(keep)}')
rng=random.Random(141421); rng.shuffle(keep); keep=keep[:n]
open(out,'wb').write(b'JNNW'+struct.pack('<I',len(keep))+b''.join(keep))
print(f'frozen certified leader-winning P3 subset n={len(keep)}')
PY
sha256sum "$W/p3-confirm.jnnw" | tee -a "$RES"

# Tiny write/read smoke for both cells.
python3 - "$W/p3-confirm.jnnw" "$W/smoke.jnnw" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(); body=b[8:8+4*38]
open(sys.argv[2],'wb').write(b'JNNW'+struct.pack('<I',4)+body)
PY
for cell in A C10; do
  patt="$W/${cell}.pjtw"
  cmd=(python3 "$H/jobs/tools/conv_fixed_wdl.py" --jass "$J" --pattern "$patt"
       --defender-pattern "$W/A.pjtw" --pool-jnnw "$W/smoke.jnnw" --depth 4
       --max-plies 80 --out "$W/smoke-${cell}.json")
  [[ -z "$SEARCH_PARAMS" ]] || cmd+=(--search-params "$SEARCH_PARAMS" --defender-search-params "$SEARCH_PARAMS")
  timeout 300 "${cmd[@]}" >/dev/null
  python3 - "$W/smoke-${cell}.json" <<'PY'
import json,sys
x=json.load(open(sys.argv[1])); assert x['n_pos']>0 and len(x['position_results'])==4
PY
done
say "smoke write/read OK"

run_cell(){
  local cell="$1" patt="$2"; local -a pids=(); local rc=0
  say "--- conversion cell=$cell ---"
  rm -f "$W/.stopmon"
  (
    while [[ ! -e "$W/.stopmon" ]]; do
      sleep 600; [[ -e "$W/.stopmon" ]] && break
      python3 - "$W" "$cell" "$SHARDS" >"$PROG" <<'PY' || true
import json,sys,glob
w,cell,shards=sys.argv[1],sys.argv[2],int(sys.argv[3]); n=wins=0
for p in glob.glob(f'{w}/{cell}.*.json'):
    try:
        x=json.load(open(p)); n+=x.get('n_pos',0); wins+=x.get('n_win',0)
    except Exception: pass
completed=len(glob.glob(f'{w}/{cell}.*.json'))
print(f'{cell}: completed_shards={completed}/{shards} n={n} wins={wins}')
PY
      cp "$PROG" "$OUT_DIR/PROGRESS.txt" 2>/dev/null || true
    done
  ) & MON_PID=$!
  for s in $(seq 0 $((SHARDS-1))); do
    cmd=(python3 "$H/jobs/tools/conv_fixed_wdl.py" --jass "$J" --pattern "$patt"
         --defender-pattern "$W/A.pjtw" --pool-jnnw "$W/p3-confirm.jnnw"
         --depth "$CONFIRM_DEPTH" --max-plies "$MAX_PLIES" --shard "$s" --nshards "$SHARDS"
         --out "$W/${cell}.$s.json")
    [[ -z "$SEARCH_PARAMS" ]] || cmd+=(--search-params "$SEARCH_PARAMS" --defender-search-params "$SEARCH_PARAMS")
    ( timeout "$SHARD_TIMEOUT" "${cmd[@]}" >"$W/${cell}.$s.log" 2>&1 ) & pids+=("$!")
  done
  for pid in "${pids[@]}"; do wait "$pid" || rc=1; done
  touch "$W/.stopmon"; wait "$MON_PID" 2>/dev/null || true; unset MON_PID
  [[ "$rc" -eq 0 ]] || { say "ABORT $cell shard failure/timeout"; exit 7; }
}
run_cell A "$W/A.pjtw"
run_cell C10 "$W/C10.pjtw"

if ! python3 "$H/jobs/tools/cvh_followup_verdict.py" confirm \
    --baseline "$W"/A.*.json --candidate "$W"/C10.*.json \
    --min-n "$CONFIRM_MIN_N" --min-delta "$CONFIRM_MIN_DELTA" \
    --out "$W/confirmation-verdict.json" | tee -a "$RES"; then
  say "VERDICT: p3_not_confirmed"
  cp "$W"/*.json "$RES" "$W/p3-confirm.jnnw" "$OUT_DIR"/ 2>/dev/null || true
  exit 3
fi
say "VERDICT: candidate_for_l3_fork"
cp "$W"/*.json "$RES" "$W/p3-confirm.jnnw" "$OUT_DIR"/
say "=== end $JASS_JOB_ID ==="

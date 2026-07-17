#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Generate a new, candidate-blind P3/P4 conversion holdout from fixed T0 play.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?runner v3 must provide JASS_CODE_DIR}"
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
: "${JASS_ARTEFACT_DIR:?runner v3 must provide JASS_ARTEFACT_DIR}"
: "${STRONG_INPUTS_PREFIX:?immutable T0 input bundle required}"
: "${TEACHER_SMOKE_RUN_PREFIX:?completed teacher smoke required}"
: "${MTC_AUDIT_RUN_PREFIX:?completed host MTC audit required}"
: "${JASS_EGDB_MTC_PATH:?exact audited MTC path required}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
INPUTS="$JASS_RESULT_DIR/inputs"
PRE="$JASS_RESULT_DIR/prechecks"
GEOM="$JASS_RESULT_DIR/geom"
mkdir -p "$W" "$ART" "$INPUTS" "$PRE" "$GEOM"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: instance active" >&2; exit 3; }

GAMES="${HOLDOUT_GAMES:-12000}"
PLAYD="${HOLDOUT_PLAY_DEPTH:-10}"
MAXPLIES="${HOLDOUT_MAX_PLIES:-220}"
MINPC="${HOLDOUT_SEED_MIN_PIECES:-36}"
SEED="${HOLDOUT_SEED:-77801}"
NSH_GEN="${NSH_GEN_TOTAL:-8}"
PAR_GEN="${PAR_GEN:-8}"
ARB_DEPTH="${ARB_DEPTH:-14}"
CACHE_MB="${CACHE_MB_RELABEL:-384}"
N_CAND_MAX="${P3_CANDIDATES_MAX:-60000}"
MIN_P4="${MIN_P4_HOLDOUT:-400}"
MIN_DELTA="${MIN_P3_DELTA:-0.02}"
TARGET_POWER="${P3_TARGET_POWER:-0.80}"
ALPHA="${P3_ALPHA:-0.05}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-10000}"
JOBS="${JASS_BUILD_JOBS:-8}"

die(){ echo "ABORT: $*" >&2; exit 1; }
jnnw_count(){ python3 - "$1" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(8)
if len(b)!=8 or b[:4]!=b'JNNW': raise SystemExit(2)
print(struct.unpack('<I',b[4:8])[0])
PY
}
merge_jnnw(){ python3 - "$1" "$2" <<'PY'
import glob,re,struct,sys
out,prefix=sys.argv[1:]
def key(path):
    match=re.search(r'\.(\d+)$',path); return int(match.group(1)) if match else 10**9
files=sorted(glob.glob(prefix+'*'),key=key)
if not files: raise SystemExit('no JNNW shards')
body=bytearray(); total=0
for path in files:
    raw=open(path,'rb').read()
    if raw[:4]!=b'JNNW': raise SystemExit(f'{path}: invalid JNNW')
    n=struct.unpack_from('<I',raw,4)[0]
    if len(raw)!=8+n*38: raise SystemExit(f'{path}: truncated JNNW')
    total+=n; body+=raw[8:]
open(out,'wb').write(b'JNNW'+struct.pack('<I',total)+body)
print(total)
PY
}
run_pids(){
  local fail=0 pid
  for pid in "$@"; do wait "$pid" || fail=$((fail+1)); done
  [ "$fail" -eq 0 ] || die "$fail generation shards failed"
}

finalize(){
  rc=$?
  trap - EXIT
  set +e
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$INPUTS" "$PRE" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT

python3 jobs/tools/fetch_t1bis_inputs.py --remote-prefix "$STRONG_INPUTS_PREFIX" \
  --out-dir "$INPUTS" --report "$ART/verified-strong-inputs.json" \
  > "$W/fetch-inputs.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$TEACHER_SMOKE_RUN_PREFIX" \
  --file artefacts/teacher-smoke-decision.json=teacher-smoke-decision.json \
  --file artefacts/conversion/A/p3_mince.json=A-p3.json \
  --out-dir "$PRE" --report "$ART/verified-smoke-result.json" \
  > "$W/fetch-smoke.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$MTC_AUDIT_RUN_PREFIX" \
  --file artefacts/mtc-audit.json=mtc-audit.json \
  --out-dir "$PRE" --report "$ART/verified-mtc-audit.json" \
  > "$W/fetch-mtc.log" 2>&1
python3 jobs/tools/mtc_audit.py --verify-manifest "$PRE/mtc-audit.json" \
  --expected-path "$JASS_EGDB_MTC_PATH" --out "$ART/mtc-verification.json"
python3 - "$PRE/teacher-smoke-decision.json" "$PRE/mtc-audit.json" <<'PY'
import json,socket,sys
smoke=json.load(open(sys.argv[1])); mtc=json.load(open(sys.argv[2]))
if smoke.get('decision')!='confirm' or smoke.get('winner') not in ('B1','B2','B3'):
    raise SystemExit('teacher smoke did not authorize a confirmation')
if not mtc.get('audit_ok') or mtc.get('audit_level')!='complete' or mtc.get('concurrent_smoke_ok') is not True:
    raise SystemExit('MTC audit is not complete and green')
if mtc.get('host') != socket.gethostname():
    raise SystemExit(f'MTC audit host mismatch: {mtc.get("host")} != {socket.gethostname()}')
PY
python3 jobs/tools/conversion_confirmation_gate.py plan \
  --baseline-report "$PRE/A-p3.json" --min-delta "$MIN_DELTA" \
  --alpha "$ALPHA" --power "$TARGET_POWER" --out "$ART/p3-power.json"
REQUIRED="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["required_n_per_arm"])' \
  "$ART/p3-power.json")"
N_CAND=$((REQUIRED * 4))
[ "$N_CAND" -le "$N_CAND_MAX" ] || N_CAND="$N_CAND_MAX"
python3 jobs/tools/cache_guard.py --cache-mb "$CACHE_MB" \
  --procs "$((PAR_GEN * 2))" > "$ART/p3-cache-guard.json"

gunzip -c "$INPUTS/parent.pjtw.gz" > "$W/T0.pjtw"
gunzip -c "$INPUTS/seeds.jnnw.gz" > "$W/seeds.jnnw"
cat "$INPUTS/gauge.fen" "$INPUTS/g1_pool.fen" > "$W/exclusions.fen"
: > "$W/empty.fen"

[ -d /root/egdb_intl ] || \
  git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl \
    > "$W/clone-egdb.log" 2>&1
WLD="${JASS_EGDB_PATH:-}"
if [ -z "$WLD" ]; then
  for candidate in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
    if ls "$candidate"/db*.idx1 >/dev/null 2>&1; then WLD="$candidate"; break; fi
  done
fi
[ -n "$WLD" ] || die "WLD EGDB not found"
export JASS_EGDB_PATH="$WLD" JASS_EGDB_CACHE_MB="$CACHE_MB"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON \
  -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
  > "$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || die "build without EGDB"
cmake --build "$W/build" -j"$JOBS" --target jass > "$W/build.log" 2>&1
J="$W/build/jass"

echo "=== candidate-blind fresh self-play: T0, seed=$SEED, games=$GAMES ==="
pids=()
for shard in $(seq 0 $((NSH_GEN-1))); do
  timeout "$SHARD_TIMEOUT" python3 tools/scan_selfplay_gen.py \
    --jass "$J" --player-jass-bin "$J" --player-pattern "$W/T0.pjtw" \
    --seeds "$W/seeds.jnnw" --out "$W/sp.$shard" --games "$GAMES" \
    --max-plies "$MAXPLIES" --min-pieces "$MINPC" --sample-every 1 \
    --depth "$PLAYD" --seed "$SEED" --nshards "$NSH_GEN" --shard "$shard" \
    --cap-arbiter d14 --egdb-dir "$WLD" --arb-depth "$ARB_DEPTH" \
    > "$W/sp.$shard.log" 2>&1 &
  pids+=("$!")
  if [ "${#pids[@]}" -ge "$PAR_GEN" ]; then run_pids "${pids[@]}"; pids=(); fi
done
[ "${#pids[@]}" -eq 0 ] || run_pids "${pids[@]}"
merge_jnnw "$W/fresh.jnnw" "$W/sp."

python3 tools/mine_conversion_pool.py extract --corpus "$W/fresh.jnnw" \
  --out "$W/p3p4-candidates.jnnw" --n-cand "$N_CAND" --max-over 3 \
  --val-margin-max 1 > "$W/extract.log"
[ "$(jnnw_count "$W/p3p4-candidates.jnnw")" -gt 0 ] || die "no fresh P3/P4 candidates"
"$J" --deep-relabel "$W/p3p4-candidates.jnnw" "$W/p3p4-certified.jnnw" \
  "$ARB_DEPTH" --egdb "$WLD" --cache-mb "$CACHE_MB" > "$W/relabel.log" 2>&1
python3 tools/mine_conversion_pool.py filter \
  --certified "$W/p3p4-certified.jnnw" --thermo "$W/exclusions.fen" \
  --eval-set-in "$W/empty.fen" --value-adv --eval-n 0 \
  --out-pool "$W/certified-pool.fen" --out-eval "$W/unused-eval.fen" \
  --manifest "$W/certification-manifest.json" > "$W/filter.log"
python3 tools/mine_conversion_pool.py carve --pool "$W/certified-pool.fen" \
  --per-palier "$REQUIRED" --holdout-only \
  --out-eval "$ART/p3-holdout.fen" --out-train "$W/unused-train.fen" \
  --manifest "$ART/p3-holdout-manifest.json" > "$W/carve.log"

python3 - "$ART/p3-holdout-manifest.json" "$ART/p3-power.json" \
  "$ART/p3-holdout-decision.json" "$MIN_P4" "$SEED" "$W/exclusions.fen" \
  "$W/fresh.jnnw" <<'PY'
import hashlib,json,sys
from pathlib import Path
manifest=json.load(open(sys.argv[1])); power=json.load(open(sys.argv[2]))
minimum_p4=int(sys.argv[4]); counts=manifest['eval_par_palier']
required=int(power['required_n_per_arm'])
ready=counts.get('p3_mince',0)>=required and counts.get('p4_egal',0)>=minimum_p4
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
manifest.update({
  'schema':1, 'blind_to_teacher_candidate':True, 'generator':'fixed_T0',
  'generation_seed':int(sys.argv[5]), 'exclusions_sha256':sha(sys.argv[6]),
  'fresh_corpus_sha256':sha(sys.argv[7]), 'required_p3_per_arm':required,
  'minimum_p4':minimum_p4,
})
Path(sys.argv[1]).write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
decision={
  'schema':1, 'decision':'ready' if ready else 'insufficient_positions',
  'scientific_status':'ready_for_confirmation' if ready else 'complete_underpowered_holdout',
  'required_p3_per_arm':required, 'minimum_p4':minimum_p4,
  'available':counts, 'blind_to_teacher_candidate':True,
}
Path(sys.argv[3]).write_text(json.dumps(decision,indent=2,sort_keys=True)+'\n')
PY
cp "$ART/p3-holdout-decision.json" "$ART/scientific-summary.json"
echo "fresh holdout prepared; see p3-holdout-decision.json"

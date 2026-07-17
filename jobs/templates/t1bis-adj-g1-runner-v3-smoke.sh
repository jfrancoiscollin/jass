#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Fail-closed technical smoke for the native T1-bis runner-v3 launcher.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"
: "${JASS_RESULT_DIR:?}"
: "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"
: "${JASS_OBJSTORE_REMOTE:?}"
cd "$JASS_CODE_DIR"

W="$JASS_RESULT_DIR/smoke"
INPUTS="$JASS_RESULT_DIR/inputs"
ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$INPUTS" "$ART"
trap 'rc=$?; printf "exit_code=%s\n" "$rc" > "$ART/smoke-runtime.txt"; exit "$rc"' EXIT

[ "$(git branch --show-current)" = "" ]
python3 -m py_compile \
  jobs/tools/fetch_t1bis_inputs.py \
  tools/scan_selfplay_gen.py \
  jobs/tools/calibrate_vs_scan.py \
  jobs/tools/run_jass_gate_bounded.py
python3 jobs/tests/test_run_jass_gate.py > "$W/test-run-gate.log" 2>&1

python3 jobs/tools/fetch_t1bis_inputs.py \
  --out-dir "$INPUTS" \
  --report "$ART/verified-inputs.json" \
  > "$W/fetch-inputs.log" 2>&1
for f in parent.pjtw.gz fixed.pjtw.gz gen2.pjtw.gz seeds.jnnw.gz g1_pool.fen gauge.fen; do
  [ -s "$INPUTS/$f" ]
done
gunzip -c "$INPUTS/parent.pjtw.gz" > "$W/parent.pjtw"
gunzip -c "$INPUTS/seeds.jnnw.gz" > "$W/seeds.jnnw"

FLAGS_EGDB="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
[ -d /root/egdb_intl ]
EGDIR=""
for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }
done
[ -n "$EGDIR" ]
cmake -S . -B "$W/build" $FLAGS_EGDB > "$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log"
cmake --build "$W/build" -j"${JASS_BUILD_JOBS:-4}" --target jass > "$W/build.log" 2>&1
J="$W/build/jass"

# One real, bounded generation shard.  This exercises the engine, parent pattern,
# seed corpus, generator imports and output/sidecar alignment without claiming a
# scientific result.
timeout 600 python3 tools/scan_selfplay_gen.py \
  --jass "$J" --player-jass-bin "$J" --player-pattern "$W/parent.pjtw" \
  --seeds "$W/seeds.jnnw" --out "$W/smoke.jnnw" --games 1 \
  --max-plies 12 --min-pieces 36 --sample-every 1 --depth 1 \
  --seed 72800 --nshards 1 --shard 0 \
  --cap-arbiter none --label-src-out "$W/smoke.tags" \
  > "$W/generation.log" 2>&1

python3 - "$W/smoke.jnnw" "$W/smoke.tags" "$ART/smoke-verdict.json" <<'PY'
import json,struct,sys
from pathlib import Path
jnnw,tags,out=map(Path,sys.argv[1:])
raw=jnnw.read_bytes()
if len(raw)<8 or raw[:4]!=b'JNNW': raise SystemExit('invalid JNNW')
n=struct.unpack('<I',raw[4:8])[0]
if n<=0 or len(raw)!=8+n*38: raise SystemExit('invalid JNNW size')
if tags.stat().st_size!=n: raise SystemExit('sidecar misaligned')
result={'state':'completed','kind':'t1bis-native-smoke','positions':n,'sidecar_bytes':tags.stat().st_size}
out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps(result,indent=2,sort_keys=True))
PY

cp "$W/cmake.log" "$ART/cmake.log"
cp "$W/generation.log" "$ART/generation.log"
printf 'T1-BIS NATIVE SMOKE GREEN\n' > "$ART/VERDICT.txt"

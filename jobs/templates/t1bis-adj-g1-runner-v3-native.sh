#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Native runner-v3 T1-bis ADJ+G1 launcher.
# Scientific defaults match the historical T1-bis baseline.  Only process
# concurrency, filesystem routing and immutable input transport are operational.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?runner v3 must provide JASS_CODE_DIR}"
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
: "${JASS_ARTEFACT_DIR:?runner v3 must provide JASS_ARTEFACT_DIR}"
: "${JASS_JOB_ID:?runner v3 must provide JASS_JOB_ID}"
: "${JASS_OBJSTORE_REMOTE:?runner v3 must provide JASS_OBJSTORE_REMOTE}"
: "${NSH_GEN_TOTAL:?baseline generation shard count required}"
: "${NSH_RELABEL_TOTAL:?baseline relabel shard count required}"
: "${NSH_CONV_TOTAL:?baseline conversion shard count required}"
: "${NSH_GATE_TOTAL:?baseline gate shard count required}"

cd "$JASS_CODE_DIR"
JOB_ID="$JASS_JOB_ID"
TOUR="${TOUR:-T1-bis}"
GYM_MIN_POS="${GYM_MIN_POS:?quota minimum de positions G1 pré-engagé}"
TIP_CERTS_JSONL="${TIP_CERTS_JSONL:-}"
MIN_PROTECTED_TIP_RATE="${MIN_PROTECTED_TIP_RATE:-0.0}"
ALLOW_MTC_SKIP="${ALLOW_MTC_SKIP:-0}"

NSH_GEN="$NSH_GEN_TOTAL"
NSH_RELABEL="$NSH_RELABEL_TOTAL"
NSH_CONV="$NSH_CONV_TOTAL"
NSH_GATE="$NSH_GATE_TOTAL"
PAR_GEN="${PAR_GEN:-8}"
PAR_RELABEL="${PAR_RELABEL:-8}"
PAR_CONV="${PAR_CONV:-4}"
PAR_GATE="${PAR_GATE:-4}"
JASS_BUILD_JOBS="${JASS_BUILD_JOBS:-8}"
CACHE_MB_RELABEL="${CACHE_MB_RELABEL:-384}"
CACHE_MB_CONV="${CACHE_MB_CONV:-192}"
GATE_WAIT_SECONDS="${GATE_WAIT_SECONDS:-86400}"
export JASS_EGDB_CACHE_MB="$CACHE_MB_CONV"

# Scientific defaults: unchanged from the historical T1-bis template.
GAMES="${GAMES:-300}"
PLAYD="${PLAYD:-10}"
MAXPLIES="${MAXPLIES:-200}"
MINPC="${MINPC:-36}"
SEEDFRAC="${SEEDFRAC:-0.18}"
ARB_DEPTH="${ARB_DEPTH:-14}"
ANCHOR="${ANCHOR:-0.05}"
MAXIT="${MAXIT:-60}"
CHUNK="${CHUNK:-1000000}"
CONV_DEPTH="${CONV_DEPTH:-10}"
NOPEN="${NOPEN:-300}"
PAIRS="${PAIRS:-1}"
DEPTH="${DEPTH:-9}"
QS="${QS:-qs_forcing_depth=6,qs_promo_depth=6}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-7000}"
RELABEL_TIMEOUT="${RELABEL_TIMEOUT:-4000}"

W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom"
INPUTS="$JASS_RESULT_DIR/inputs"
mkdir -p "$W" "$ART" "$GEOM" "$INPUTS"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: instance active" >&2; exit 3; }
RES="$W/RESULTS.txt"
: > "$RES"

say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }

jnnw_count(){ python3 - "$1" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(8)
if len(b)!=8 or b[:4]!=b'JNNW': raise SystemExit(2)
print(struct.unpack('<I',b[4:8])[0])
PY
}

run_pids(){
  local label="$1"; shift
  local -a pids=("$@")
  local fail=0
  local pid
  for pid in "${pids[@]}"; do
    if ! wait "$pid"; then fail=$((fail+1)); fi
  done
  [ "$fail" -eq 0 ] || die "$label: $fail processus en échec"
}

merge_jnnw(){ python3 - "$1" "$2" <<'PY'
import glob,re,struct,sys
out,prefix=sys.argv[1:]
def key(p):
    m=re.search(r'\.(\d+)(?:\.jnnw)?$',p); return int(m.group(1)) if m else 10**9
files=sorted(glob.glob(prefix+'*'),key=key)
if not files: raise SystemExit('aucun shard JNNW')
body=bytearray(); total=0
for path in files:
    raw=open(path,'rb').read()
    if raw[:4]!=b'JNNW': raise SystemExit(f'{path}: magic invalide')
    n=struct.unpack('<I',raw[4:8])[0]
    if len(raw)!=8+n*38: raise SystemExit(f'{path}: taille invalide')
    body += raw[8:]; total += n
open(out,'wb').write(b'JNNW'+struct.pack('<I',total)+body)
print(total)
PY
}

merge_bytes(){ python3 - "$1" "$2" <<'PY'
import glob,re,sys
out,prefix=sys.argv[1:]
def key(p):
    m=re.search(r'\.(\d+)$',p); return int(m.group(1)) if m else 10**9
files=sorted(glob.glob(prefix+'*'),key=key)
if not files: raise SystemExit('aucun shard sidecar')
open(out,'wb').write(b''.join(open(p,'rb').read() for p in files))
PY
}

GATE_WORKER_PID=""
finalize(){
  rc=$?
  trap - EXIT
  set +e
  if [ -n "$GATE_WORKER_PID" ] && kill -0 "$GATE_WORKER_PID" 2>/dev/null; then
    kill "$GATE_WORKER_PID" 2>/dev/null || true
    wait "$GATE_WORKER_PID" 2>/dev/null || true
  fi
  [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt"
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
    printf 'nsh_gen_total=%s\n' "$NSH_GEN"
    printf 'nsh_relabel_total=%s\n' "$NSH_RELABEL"
    printf 'nsh_conv_total=%s\n' "$NSH_CONV"
    printf 'nsh_gate_total=%s\n' "$NSH_GATE"
    printf 'parallel_gen=%s\n' "$PAR_GEN"
    printf 'parallel_relabel=%s\n' "$PAR_RELABEL"
    printf 'parallel_conv=%s\n' "$PAR_CONV"
    printf 'parallel_gate=%s\n' "$PAR_GATE"
    printf 'exit_code=%s\n' "$rc"
  } > "$ART/runtime-profile.txt"
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

say "=== $JOB_ID / $TOUR — préflight natif runner-v3 ==="
[ "$(git branch --show-current)" = "" ] || die "worktree non détaché"
python3 -m py_compile \
  jobs/tools/fetch_t1bis_inputs.py \
  tools/scan_selfplay_gen.py \
  tools/calibrate_vs_scan.py \
  jobs/tools/oracle_cert.py \
  jobs/tools/apply_label_policy.py \
  jobs/tools/aggregate_conv_shards.py \
  jobs/tools/split_stratified_fen.py \
  jobs/tools/promotion_gate.py \
  jobs/tools/conv_fixed_wdl.py \
  jobs/tools/run_jass_gate_bounded.py

EXPECTED_SCAN_BLOB="1a19b30cded45281a628d2f9b631f2719d7fbc51"
ACTUAL_SCAN_BLOB="$(git rev-parse HEAD:tools/scan_selfplay_gen.py)"
[ "$ACTUAL_SCAN_BLOB" = "$EXPECTED_SCAN_BLOB" ] || die "générateur scientifique inattendu: $ACTUAL_SCAN_BLOB"

for test in \
  test_oracle_cert test_promotion_gate test_probe_mining test_cache_guard \
  test_apply_label_policy test_aggregate_conv_shards test_split_stratified_fen; do
  python3 "jobs/tests/$test.py" > "$W/$test.log" 2>&1 || die "test rouge: $test"
done
python3 jobs/tests/test_run_jass_gate.py > "$W/test_run_jass_gate.log" 2>&1 || die "test gate rouge"

python3 jobs/tools/fetch_t1bis_inputs.py \
  --out-dir "$INPUTS" \
  --report "$ART/verified-inputs.json" \
  > "$W/fetch-inputs.log" 2>&1 || die "entrées R2 absentes ou non vérifiables"

for f in parent.pjtw.gz fixed.pjtw.gz gen2.pjtw.gz seeds.jnnw.gz g1_pool.fen gauge.fen; do
  [ -s "$INPUTS/$f" ] || die "entrée vérifiée absente: $f"
done
gunzip -c "$INPUTS/parent.pjtw.gz" > "$W/parent.pjtw"
gunzip -c "$INPUTS/fixed.pjtw.gz" > "$W/fixed.pjtw"
gunzip -c "$INPUTS/gen2.pjtw.gz" > "$W/gen2.pjtw"
gunzip -c "$INPUTS/seeds.jnnw.gz" > "$W/seeds.jnnw"
cp "$INPUTS/g1_pool.fen" "$W/g1_pool.fen"
cp "$INPUTS/gauge.fen" "$W/gauge.fen"

python3 jobs/tools/cache_guard.py --cache-mb "$CACHE_MB_RELABEL" --procs "$PAR_RELABEL" > "$ART/cache_relabel.json" || die "cache relabel"
python3 jobs/tools/cache_guard.py --cache-mb "$CACHE_MB_CONV" --procs "$((PAR_CONV*3))" > "$ART/cache_conv.json" || die "cache conversion"
if ! python3 jobs/tools/mtc_audit.py --cache-mb "$CACHE_MB_RELABEL" --procs "$PAR_RELABEL" --smoke-ok skip --out "$ART/mtc_audit.json"; then
  [ "$ALLOW_MTC_SKIP" = 1 ] || die "audit MTC non vert"
  say "WARN: audit MTC explicitement ignoré"
fi

FLAGS_EGDB="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl > "$W/clone-egdb.log" 2>&1
EGDIR=""
for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }
done
[ -n "$EGDIR" ] || die "EGDB introuvable"
export JASS_EGDB_PATH="$EGDIR"
cmake -S . -B "$W/build" $FLAGS_EGDB > "$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || die "build sans EGDB"
cmake --build "$W/build" -j"$JASS_BUILD_JOBS" --target jass > "$W/build.log" 2>&1 || die "build"
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"

awk -v limit="$NOPEN" '
  /^[[:space:]]*#/ { next }
  {
    sub(/#.*/, "")
    if (NF) {
      print
      count++
      if (count >= limit) exit
    }
  }
' data/dilf_combinations.fen > "$W/open.fen"
[ "$(wc -l < "$W/open.fen")" -eq "$NOPEN" ] || die "openings insuffisantes"

cat > "$W/gate_parent.json" <<'JSON'
{"wins_a":0,"draws":0,"wins_b":0,"n":0,"rate":null,"ci_low":null,"ci_high":null,"complete":false}
JSON
cp "$W/gate_parent.json" "$W/gate_fixed.json"
(
  set -Eeuo pipefail
  for _ in $(seq 1 "$GATE_WAIT_SECONDS"); do
    if [ -s "$J" ] && [ -s "$W/candidate.pjtw" ] && [ -s "$W/parent.pjtw" ] && \
       [ -s "$W/fixed.pjtw" ] && [ -s "$W/open.fen" ]; then
      break
    fi
    sleep 1
  done
  [ -s "$W/candidate.pjtw" ] || exit 21
  python3 jobs/tools/run_jass_gate_bounded.py \
    --jass "$J" \
    --pattern-a "$W/candidate.pjtw" \
    --pattern-b "$W/parent.pjtw" \
    --openings-file "$W/open.fen" \
    --search-params "$QS" \
    --depth "$DEPTH" --pairs "$PAIRS" \
    --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
    --timeout "$SHARD_TIMEOUT" \
    --work-dir "$W/gate-parent" --out "$W/gate_parent.new.json"
  mv "$W/gate_parent.new.json" "$W/gate_parent.json"
  if cmp -s "$W/parent.pjtw" "$W/fixed.pjtw"; then
    cp "$W/gate_parent.json" "$W/gate_fixed.json"
  else
    python3 jobs/tools/run_jass_gate_bounded.py \
      --jass "$J" \
      --pattern-a "$W/candidate.pjtw" \
      --pattern-b "$W/fixed.pjtw" \
      --openings-file "$W/open.fen" \
      --search-params "$QS" \
      --depth "$DEPTH" --pairs "$PAIRS" \
      --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
      --timeout "$SHARD_TIMEOUT" \
      --work-dir "$W/gate-fixed" --out "$W/gate_fixed.new.json"
    mv "$W/gate_fixed.new.json" "$W/gate_fixed.json"
  fi
) > "$W/gate-worker.log" 2>&1 &
GATE_WORKER_PID=$!

say "=== génération ADJ+G1 ==="
pids=()
for shard in $(seq 0 $((NSH_GEN-1))); do
  timeout "$SHARD_TIMEOUT" python3 tools/scan_selfplay_gen.py \
    --jass "$J" --player-jass-bin "$J" --player-pattern "$W/parent.pjtw" \
    --seeds "$W/seeds.jnnw" --out "$W/sp.$shard" --games "$GAMES" \
    --max-plies "$MAXPLIES" --min-pieces "$MINPC" --sample-every 1 --depth "$PLAYD" \
    --seed 72800 --nshards "$NSH_GEN" --shard "$shard" \
    --seed-pool "$W/g1_pool.fen" --seed-frac "$SEEDFRAC" \
    --cap-arbiter d14 --egdb-dir "$EGDIR" --arb-depth "$ARB_DEPTH" \
    --label-src-out "$W/lab.$shard" > "$W/sp.$shard.log" 2>&1 &
  pids+=("$!")
  if [ "${#pids[@]}" -ge "$PAR_GEN" ]; then
    run_pids generation-batch "${pids[@]}"
    pids=()
  fi
done
run_pids generation "${pids[@]}"
for shard in $(seq 0 $((NSH_GEN-1))); do
  [ -s "$W/sp.$shard" ] && [ -s "$W/lab.$shard" ] || die "sortie génération shard $shard absente"
done
NPOS="$(merge_jnnw "$W/gen.jnnw" "$W/sp.")"
merge_bytes "$W/source.tags" "$W/lab."
[ "$(wc -c < "$W/source.tags")" -eq "$NPOS" ] || die "sidecar source désaligné"
GYM_POS="$(python3 - "$W/source.tags" <<'PY'
from pathlib import Path
b=Path(__import__('sys').argv[1]).read_bytes(); print(sum(x==1 for x in b))
PY
)"
[ "$GYM_POS" -ge "$GYM_MIN_POS" ] || die "quota G1 positions non atteint: $GYM_POS < $GYM_MIN_POS"
say "positions=$NPOS ; G1=$GYM_POS"

say "=== relabel profond strict ==="
python3 - "$W/gen.jnnw" "$W/rs" "$NSH_RELABEL" <<'PY'
import struct,sys
raw=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',raw[4:8])[0]; body=raw[8:]; nsh=int(sys.argv[3]); per=(n+nsh-1)//nsh
for s in range(nsh):
    seg=body[s*per*38:(s+1)*per*38]
    open(f'{sys.argv[2]}.{s}.jnnw','wb').write(b'JNNW'+struct.pack('<I',len(seg)//38)+seg)
PY
pids=()
for shard in $(seq 0 $((NSH_RELABEL-1))); do
  timeout "$RELABEL_TIMEOUT" "$J" --deep-relabel "$W/rs.$shard.jnnw" "$W/rr.$shard.jnnw" "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb "$CACHE_MB_RELABEL" > "$W/rr.$shard.log" 2>&1 &
  pids+=("$!")
  if [ "${#pids[@]}" -ge "$PAR_RELABEL" ]; then
    run_pids relabel-batch "${pids[@]}"
    pids=()
  fi
done
run_pids relabel "${pids[@]}"
for shard in $(seq 0 $((NSH_RELABEL-1))); do [ -s "$W/rr.$shard.jnnw" ] || die "relabel shard $shard absent"; done
merge_jnnw "$W/deep.jnnw" "$W/rr." >/dev/null
[ "$(jnnw_count "$W/deep.jnnw")" -eq "$NPOS" ] || die "relabel incomplet"

POLICY_ARGS=(--original "$W/gen.jnnw" --relabelled "$W/deep.jnnw" --source-tags "$W/source.tags" --out "$W/adj.jnnw" --manifest "$ART/label_policy.json" --min-protected-tip-rate "$MIN_PROTECTED_TIP_RATE")
if [ -n "$TIP_CERTS_JSONL" ]; then POLICY_ARGS+=(--certificates "$TIP_CERTS_JSONL"); fi
python3 jobs/tools/apply_label_policy.py "${POLICY_ARGS[@]}" || die "politique labels"

say "=== fit ancré ==="
"$J" --dump-eval-features "$W/adj.jnnw" "$W/feat" > "$W/dump.log" 2>&1
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
  python3 pattern_jass/tools/wdl_finetune.py --champion "$W/parent.pjtw" --data "$W/adj.jnnw" --feat "$W/feat" \
  --out "$W/candidate.pjtw" --tools pattern_jass/tools --anchor "$ANCHOR" --color-fold --tempo-stage \
  --max-iter "$MAXIT" --chunk "$CHUNK" --verify-jass "$J" --verify-n 80 > "$W/fit.log" 2>&1
[ -s "$W/candidate.pjtw" ] || die "candidate absent"

say "=== jauge p1-p4 ==="
python3 jobs/tools/split_stratified_fen.py --input "$W/gauge.fen" --out-dir "$W/strata" --manifest "$ART/gauge_strata.json"
mkdir -p "$ART/conversion"
for stratum in p1_net p2_moyen p3_mince p4_egal; do
  python3 jobs/tools/jnnw_doe.py fen-to-jnnw --input "$W/strata/$stratum.fen" --output "$W/$stratum.raw.jnnw" >/dev/null
  "$J" --deep-relabel "$W/$stratum.raw.jnnw" "$W/$stratum.rel.jnnw" "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb "$CACHE_MB_RELABEL" > "$W/$stratum.rel.log" 2>&1
  python3 jobs/tools/jnnw_doe.py keep-decisive --input "$W/$stratum.rel.jnnw" --output "$W/$stratum.dec.jnnw" >/dev/null
  EXPECTED="$(jnnw_count "$W/$stratum.dec.jnnw")"
  [ "$EXPECTED" -gt 0 ] || die "$stratum sans position décisive"
  pids=(); inputs=()
  for shard in $(seq 0 $((NSH_CONV-1))); do
    out="$W/$stratum.conv.$shard.json"; inputs+=("$out")
    timeout "$SHARD_TIMEOUT" python3 jobs/tools/conv_fixed_wdl.py --jass "$J" --pattern "$W/candidate.pjtw" \
      --defender-pattern "$W/gen2.pjtw" --pool-jnnw "$W/$stratum.dec.jnnw" --calibrate-tool tools/calibrate_vs_scan.py \
      --depth "$CONV_DEPTH" --max-plies 260 --shard "$shard" --nshards "$NSH_CONV" --out "$out" > "$W/$stratum.conv.$shard.log" 2>&1 &
    pids+=("$!")
    if [ "${#pids[@]}" -ge "$PAR_CONV" ]; then
      run_pids "conversion $stratum batch" "${pids[@]}"
      pids=()
    fi
  done
  run_pids "conversion $stratum" "${pids[@]}"
  python3 jobs/tools/aggregate_conv_shards.py --inputs "${inputs[@]}" --expected-shards "$NSH_CONV" \
    --expected-records "$EXPECTED" --max-error-rate 0.08 --stratum "$stratum" --out "$ART/conversion/$stratum.json" || die "agrégation $stratum"
done

python3 - "$ART/conversion" "$ART/conversion.json" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]); reports={p.stem:json.loads(p.read_text()) for p in root.glob('*.json')}
required={'p1_net','p2_moyen','p3_mince','p4_egal'}
assert set(reports)==required, (set(reports),required)
n=sum(r['n_pos'] for r in reports.values()); w=sum(r['n_win'] for r in reports.values())
out={'global': None if not n else round(w/n,6), **{k:v['conversion'] for k,v in reports.items()}, 'reports':reports}
Path(sys.argv[2]).write_text(json.dumps(out,indent=2))
PY

say "=== gates + promotion jeune ==="
if ! wait "$GATE_WORKER_PID"; then
  GATE_WORKER_PID=""
  die "gate worker en échec"
fi
GATE_WORKER_PID=""
[ -s "$W/gate_parent.json" ] || die "gate_parent.json absent"
[ -s "$W/gate_fixed.json" ] || die "gate_fixed.json absent"
python3 - "$W/gate_parent.json" "$W/gate_fixed.json" "$ART/conversion.json" "$W/promotion_input.json" <<'PY'
import json,sys
p,f,c,out=sys.argv[1:]; conv=json.load(open(c))
json.dump({'vs_parent':json.load(open(p)),'vs_fixed_reference':json.load(open(f)),'conversion':conv},open(out,'w'),indent=2)
PY
python3 jobs/tools/promotion_gate.py --regime young --tour "$TOUR" --input "$W/promotion_input.json" --out "$ART/promotion.json" || die "promotion rejetée/technique"

say "=== $JOB_ID terminé : pipeline natif, entrées R2 vérifiées, aucun faux PASS possible ==="

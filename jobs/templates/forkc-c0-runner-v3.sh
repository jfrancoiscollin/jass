#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Cheap, fail-closed fork-C basin diagnostic.  A scientific stop is a
# successful job with c0-decision.json decision=reject; technical gaps fail.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?runner v3 must provide JASS_CODE_DIR}"
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
: "${JASS_ARTEFACT_DIR:?runner v3 must provide JASS_ARTEFACT_DIR}"
: "${JASS_OBJSTORE_REMOTE:?runner v3 must provide JASS_OBJSTORE_REMOTE}"
: "${JASS_JOB_ID:?runner v3 must provide JASS_JOB_ID}"
: "${FORKC_WEAK_INPUTS_PREFIX:?immutable weak bundle required}"
: "${FORKC_STRONG_INPUTS_PREFIX:?immutable strong bundle required}"
: "${FORKC_BASELINE_RUN_PREFIX:?completed T1 baseline result required}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
WEAK="$JASS_RESULT_DIR/inputs-weak"
STRONG="$JASS_RESULT_DIR/inputs-strong"
BASE="$JASS_RESULT_DIR/baseline"
GEOM="$JASS_RESULT_DIR/geom"
mkdir -p "$W" "$ART" "$WEAK" "$STRONG" "$BASE" "$GEOM"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: instance active" >&2; exit 3; }

DEPTH="${DEPTH:-9}"
POLICY_LIMIT="${POLICY_LIMIT:-600}"
NOPEN="${NOPEN:-300}"
PAIRS="${PAIRS:-1}"
NSH_GATE="${NSH_GATE_TOTAL:-4}"
PAR_GATE="${PAR_GATE:-4}"
NSH_CONV="${NSH_CONV_TOTAL:-4}"
PAR_CONV="${PAR_CONV:-4}"
ARB_DEPTH="${ARB_DEPTH:-14}"
CACHE_MB="${CACHE_MB_RELABEL:-384}"
CONV_DEPTH="${CONV_DEPTH:-10}"
ANCHOR="${ANCHOR:-0.05}"
MAXIT="${MAXIT:-60}"
CHUNK="${CHUNK:-1000000}"
QS="${QS:-qs_forcing_depth=6,qs_promo_depth=6}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-7000}"
MIN_POLICY_DIVERGENCE="${MIN_POLICY_DIVERGENCE:-0.05}"
MIN_HARD_DELTA="${MIN_HARD_DELTA:-0.02}"
RCLONE="${RCLONE_BIN:-rclone}"
RES="$W/RESULTS.txt"
: > "$RES"

say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
run_pids(){
  local label="$1"; shift
  local fail=0 pid
  for pid in "$@"; do wait "$pid" || fail=$((fail+1)); done
  [ "$fail" -eq 0 ] || die "$label: $fail processus en échec"
}
jnnw_count(){ python3 - "$1" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(8)
if len(b)!=8 or b[:4]!=b'JNNW': raise SystemExit(2)
print(struct.unpack('<I',b[4:8])[0])
PY
}

finalize(){
  rc=$?
  trap - EXIT
  set +e
  [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt"
  [ -s "$W/refit.pjtw" ] && gzip -n -c "$W/refit.pjtw" > "$ART/refit.pjtw.gz"
  if [ -d "$W" ]; then
    (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  fi
  rm -rf "$W/build" "$WEAK" "$STRONG" "$BASE" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

say "=== ${JASS_JOB_ID} — fork C / C0 ==="
python3 -m py_compile jobs/tools/policy_agreement.py jobs/tools/forkc_c0_gate.py \
  jobs/tools/fetch_result_files.py
for test in test_forkc_c0 test_promotion_gate; do
  python3 "jobs/tests/$test.py" > "$W/$test.log" 2>&1 || die "test rouge: $test"
done

python3 jobs/tools/fetch_t1bis_inputs.py --remote-prefix "$FORKC_WEAK_INPUTS_PREFIX" \
  --out-dir "$WEAK" --report "$ART/verified-weak-inputs.json" > "$W/fetch-weak.log" 2>&1
python3 jobs/tools/fetch_t1bis_inputs.py --remote-prefix "$FORKC_STRONG_INPUTS_PREFIX" \
  --out-dir "$STRONG" --report "$ART/verified-strong-inputs.json" > "$W/fetch-strong.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$FORKC_BASELINE_RUN_PREFIX" \
  --file artefacts/adj.jnnw.gz=adj.jnnw.gz \
  --file artefacts/conversion.json=conversion.json \
  --out-dir "$BASE" --report "$ART/verified-baseline-result.json" > "$W/fetch-baseline.log" 2>&1

gunzip -c "$WEAK/parent.pjtw.gz" > "$W/weak.pjtw"
gunzip -c "$STRONG/parent.pjtw.gz" > "$W/strong.pjtw"
gunzip -c "$STRONG/gen2.pjtw.gz" > "$W/gen2.pjtw"
gunzip -c "$BASE/adj.jnnw.gz" > "$W/adj.jnnw"
cp "$STRONG/gauge.fen" "$W/gauge.fen"
cp "$BASE/conversion.json" "$ART/baseline-conversion.json"
for f in weak.pjtw strong.pjtw gen2.pjtw adj.jnnw gauge.fen; do
  [ -s "$W/$f" ] || die "entrée C0 absente: $f"
done

FLAGS_EGDB="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl > "$W/clone-egdb.log" 2>&1
EGDIR=""
for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }
done
[ -n "$EGDIR" ] || die "EGDB introuvable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
cmake -S . -B "$W/build" $FLAGS_EGDB > "$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || die "build sans EGDB"
cmake --build "$W/build" -j"${JASS_BUILD_JOBS:-8}" --target jass > "$W/build.log" 2>&1
J="$W/build/jass"
python3 pattern_jass/tools/gen_patterns.py --emit --variant v4 >/dev/null 2>&1 || true
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"

say "=== shared-corpus refit depuis le bootstrap faible ==="
"$J" --dump-eval-features "$W/adj.jnnw" "$W/feat" > "$W/dump.log" 2>&1
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
  python3 pattern_jass/tools/wdl_finetune.py \
  --champion "$W/weak.pjtw" --data "$W/adj.jnnw" --feat "$W/feat" \
  --out "$W/refit.pjtw" --tools pattern_jass/tools --anchor "$ANCHOR" \
  --color-fold --tempo-stage --max-iter "$MAXIT" --chunk "$CHUNK" \
  --verify-jass "$J" --verify-n 80 > "$W/refit.log" 2>&1
[ -s "$W/refit.pjtw" ] || die "refit C0 absent"

say "=== divergence politique raw/refit ==="
python3 jobs/tools/policy_agreement.py --jass "$J" --pattern-a "$W/weak.pjtw" \
  --pattern-b "$W/strong.pjtw" --fens "$W/gauge.fen" --depth "$DEPTH" \
  --limit "$POLICY_LIMIT" --search-params "$QS" --out "$ART/policy-raw.json" \
  > "$W/policy-raw.log" 2>&1
python3 jobs/tools/policy_agreement.py --jass "$J" --pattern-a "$W/refit.pjtw" \
  --pattern-b "$W/strong.pjtw" --fens "$W/gauge.fen" --depth "$DEPTH" \
  --limit "$POLICY_LIMIT" --search-params "$QS" --out "$ART/policy-refit.json" \
  > "$W/policy-refit.log" 2>&1

awk -v limit="$NOPEN" '
  /^[[:space:]]*#/ { next }
  { sub(/#.*/, ""); if (NF) { print; count++; if (count >= limit) exit } }
' data/dilf_combinations.fen > "$W/open.fen"
[ "$(wc -l < "$W/open.fen")" -eq "$NOPEN" ] || die "openings insuffisantes"
say "=== gates raw/refit vs référence forte ==="
python3 jobs/tools/run_jass_gate_bounded.py --jass "$J" \
  --pattern-a "$W/weak.pjtw" --pattern-b "$W/strong.pjtw" \
  --openings-file "$W/open.fen" --search-params "$QS" --depth "$DEPTH" --pairs "$PAIRS" \
  --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" --timeout "$SHARD_TIMEOUT" \
  --work-dir "$W/gate-raw" --out "$ART/gate-raw-weak-vs-strong.json" > "$W/gate-raw.log" 2>&1
python3 jobs/tools/run_jass_gate_bounded.py --jass "$J" \
  --pattern-a "$W/refit.pjtw" --pattern-b "$W/strong.pjtw" \
  --openings-file "$W/open.fen" --search-params "$QS" --depth "$DEPTH" --pairs "$PAIRS" \
  --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" --timeout "$SHARD_TIMEOUT" \
  --work-dir "$W/gate-refit" --out "$ART/gate-refit-vs-strong.json" > "$W/gate-refit.log" 2>&1

say "=== conversion C0 p3/p4 seulement ==="
python3 jobs/tools/split_stratified_fen.py --input "$W/gauge.fen" \
  --out-dir "$W/strata" --manifest "$ART/gauge-strata.json"
mkdir -p "$ART/conversion"
for stratum in p3_mince p4_egal; do
  python3 jobs/tools/jnnw_doe.py fen-to-jnnw --input "$W/strata/$stratum.fen" \
    --output "$W/$stratum.raw.jnnw" >/dev/null
  "$J" --deep-relabel "$W/$stratum.raw.jnnw" "$W/$stratum.rel.jnnw" \
    "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb "$CACHE_MB" > "$W/$stratum.rel.log" 2>&1
  python3 jobs/tools/jnnw_doe.py keep-decisive --input "$W/$stratum.rel.jnnw" \
    --output "$W/$stratum.dec.jnnw" >/dev/null
  EXPECTED="$(jnnw_count "$W/$stratum.dec.jnnw")"
  [ "$EXPECTED" -gt 0 ] || die "$stratum sans position décisive"
  pids=(); inputs=()
  for shard in $(seq 0 $((NSH_CONV-1))); do
    out="$W/$stratum.conv.$shard.json"; inputs+=("$out")
    timeout "$SHARD_TIMEOUT" python3 jobs/tools/conv_fixed_wdl.py --jass "$J" \
      --pattern "$W/refit.pjtw" --defender-pattern "$W/gen2.pjtw" \
      --pool-jnnw "$W/$stratum.dec.jnnw" --calibrate-tool jobs/tools/calibrate_vs_scan.py \
      --depth "$CONV_DEPTH" --max-plies 260 --shard "$shard" --nshards "$NSH_CONV" \
      --out "$out" > "$W/$stratum.conv.$shard.log" 2>&1 &
    pids+=("$!")
    if [ "${#pids[@]}" -ge "$PAR_CONV" ]; then run_pids "$stratum batch" "${pids[@]}"; pids=(); fi
  done
  run_pids "$stratum" "${pids[@]}"
  python3 jobs/tools/aggregate_conv_shards.py --inputs "${inputs[@]}" \
    --expected-shards "$NSH_CONV" --expected-records "$EXPECTED" --max-error-rate 0.08 \
    --stratum "$stratum" --out "$ART/conversion/$stratum.json"
done
python3 - "$ART/conversion" "$ART/refit-conversion.json" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]); out={}
for name in ('p3_mince','p4_egal'):
    out[name]=json.loads((root/f'{name}.json').read_text())['conversion']
Path(sys.argv[2]).write_text(json.dumps(out,indent=2)+'\n')
PY

say "=== décision C0 pré-engagée ==="
set +e
python3 jobs/tools/forkc_c0_gate.py \
  --policy-raw "$ART/policy-raw.json" --policy-refit "$ART/policy-refit.json" \
  --gate-raw-weak-vs-strong "$ART/gate-raw-weak-vs-strong.json" \
  --gate-refit-vs-strong "$ART/gate-refit-vs-strong.json" \
  --conversion-baseline "$ART/baseline-conversion.json" \
  --conversion-refit "$ART/refit-conversion.json" \
  --min-policy-divergence "$MIN_POLICY_DIVERGENCE" --min-hard-delta "$MIN_HARD_DELTA" \
  --out "$ART/c0-decision.json" > "$W/c0-gate.log" 2>&1
C0_RC=$?
set -e
case "$C0_RC" in
  0) say "C0: signal suffisant — T1-C peut être soumis" ;;
  3) say "C0: stop scientifique — T1-C reste préparé mais ne doit pas être soumis" ;;
  *) die "C0 technique/incomplet (rc=$C0_RC)" ;;
esac

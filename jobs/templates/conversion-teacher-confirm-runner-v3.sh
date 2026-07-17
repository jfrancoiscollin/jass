#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Confirm exactly one smoke-selected teacher arm on a powered fresh P3 holdout.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?runner v3 must provide JASS_CODE_DIR}"
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
: "${JASS_ARTEFACT_DIR:?runner v3 must provide JASS_ARTEFACT_DIR}"
: "${TEACHER_SMOKE_RUN_PREFIX:?completed teacher smoke required}"
: "${P3_HOLDOUT_RUN_PREFIX:?ready fresh holdout required}"
: "${MTC_AUDIT_RUN_PREFIX:?complete audit from this host required}"
: "${STRONG_INPUTS_PREFIX:?immutable T0 input bundle required}"
: "${JASS_EGDB_MTC_PATH:?exact audited MTC path required}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
SMOKE="$JASS_RESULT_DIR/smoke"
HOLDOUT="$JASS_RESULT_DIR/holdout"
PRE="$JASS_RESULT_DIR/prechecks"
INPUTS="$JASS_RESULT_DIR/inputs"
mkdir -p "$W" "$ART" "$SMOKE" "$HOLDOUT" "$PRE" "$INPUTS"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: instance active" >&2; exit 3; }

ARB_DEPTH="${ARB_DEPTH:-14}"
CACHE_MB="${CACHE_MB_RELABEL:-384}"
CONV_DEPTH="${CONV_DEPTH:-10}"
NSH_CONV="${NSH_CONV_TOTAL:-8}"
PAR_CONV="${PAR_CONV:-8}"
NSH_GATE="${NSH_GATE_TOTAL:-8}"
PAR_GATE="${PAR_GATE:-8}"
NOPEN="${NOPEN:-600}"
PAIRS="${PAIRS:-2}"
DEPTH="${DEPTH:-9}"
QS="${QS:-qs_forcing_depth=6,qs_promo_depth=6}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-10000}"
MIN_DELTA="${MIN_P3_DELTA:-0.02}"
P4_MARGIN="${P4_NON_REGRESSION_MARGIN:-0.02}"
TARGET_POWER="${P3_TARGET_POWER:-0.80}"
ALPHA="${P3_ALPHA:-0.05}"
JOBS="${JASS_BUILD_JOBS:-8}"

die(){ echo "ABORT: $*" >&2; exit 1; }
jnnw_count(){ python3 - "$1" <<'PY'
import struct,sys
b=open(sys.argv[1],'rb').read(8)
if len(b)!=8 or b[:4]!=b'JNNW': raise SystemExit(2)
print(struct.unpack('<I',b[4:8])[0])
PY
}
run_pids(){
  local label="$1"; shift
  local fail=0 pid
  for pid in "$@"; do wait "$pid" || fail=$((fail+1)); done
  [ "$fail" -eq 0 ] || die "$label: $fail shard failures"
}
finalize(){
  rc=$?
  trap - EXIT
  set +e
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$SMOKE" "$HOLDOUT" "$PRE" "$INPUTS" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT

python3 jobs/tools/fetch_result_files.py --prefix "$TEACHER_SMOKE_RUN_PREFIX" \
  --file artefacts/teacher-smoke-decision.json=teacher-smoke-decision.json \
  --file artefacts/A.pjtw.gz=A.pjtw.gz --file artefacts/B1.pjtw.gz=B1.pjtw.gz \
  --file artefacts/B2.pjtw.gz=B2.pjtw.gz --file artefacts/B3.pjtw.gz=B3.pjtw.gz \
  --out-dir "$SMOKE" --report "$ART/verified-smoke-result.json" \
  > "$W/fetch-smoke.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$P3_HOLDOUT_RUN_PREFIX" \
  --file artefacts/p3-holdout.fen=p3-holdout.fen \
  --file artefacts/p3-holdout-manifest.json=p3-holdout-manifest.json \
  --file artefacts/p3-holdout-decision.json=p3-holdout-decision.json \
  --file artefacts/p3-power.json=p3-power.json \
  --out-dir "$HOLDOUT" --report "$ART/verified-holdout-result.json" \
  > "$W/fetch-holdout.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$MTC_AUDIT_RUN_PREFIX" \
  --file artefacts/mtc-audit.json=mtc-audit.json \
  --out-dir "$PRE" --report "$ART/verified-mtc-audit.json" \
  > "$W/fetch-mtc.log" 2>&1
python3 jobs/tools/fetch_t1bis_inputs.py --remote-prefix "$STRONG_INPUTS_PREFIX" \
  --out-dir "$INPUTS" --report "$ART/verified-strong-inputs.json" \
  > "$W/fetch-inputs.log" 2>&1
python3 jobs/tools/mtc_audit.py --verify-manifest "$PRE/mtc-audit.json" \
  --expected-path "$JASS_EGDB_MTC_PATH" --out "$ART/mtc-verification.json"

WINNER="$(python3 - "$SMOKE/teacher-smoke-decision.json" \
  "$HOLDOUT/p3-holdout-decision.json" "$PRE/mtc-audit.json" <<'PY'
import json,socket,sys
smoke=json.load(open(sys.argv[1])); holdout=json.load(open(sys.argv[2])); mtc=json.load(open(sys.argv[3]))
winner=smoke.get('winner')
if smoke.get('decision')!='confirm' or smoke.get('scientific_status')!=f'confirm_{str(winner).lower()}':
    raise SystemExit('smoke does not authorize one winner')
if winner not in ('B1','B2','B3'): raise SystemExit('invalid smoke winner')
if holdout.get('decision')!='ready' or not holdout.get('blind_to_teacher_candidate'):
    raise SystemExit('fresh holdout is not ready/blind')
if not mtc.get('audit_ok') or mtc.get('audit_level')!='complete' or mtc.get('concurrent_smoke_ok') is not True:
    raise SystemExit('MTC audit is not complete')
if mtc.get('host') != socket.gethostname():
    raise SystemExit(f'MTC audit host mismatch: {mtc.get("host")} != {socket.gethostname()}')
print(winner)
PY
)"
CACHE_PROCS=$((PAR_CONV * 3))
[ "$((PAR_GATE * 3))" -le "$CACHE_PROCS" ] || CACHE_PROCS=$((PAR_GATE * 3))
python3 jobs/tools/cache_guard.py --cache-mb "$CACHE_MB" --procs "$CACHE_PROCS" \
  > "$ART/teacher-confirm-cache-guard.json"
gunzip -c "$SMOKE/A.pjtw.gz" > "$W/A.pjtw"
gunzip -c "$SMOKE/$WINNER.pjtw.gz" > "$W/candidate.pjtw"
gunzip -c "$INPUTS/parent.pjtw.gz" > "$W/absolute.pjtw"
gunzip -c "$INPUTS/gen2.pjtw.gz" > "$W/gen2.pjtw"

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

awk -v limit="$NOPEN" '
  /^[[:space:]]*#/ { next }
  { sub(/#.*/, ""); if (NF) { print; count++; if (count >= limit) exit } }
' data/dilf_combinations.fen > "$W/open.fen"
[ "$(wc -l < "$W/open.fen")" -eq "$NOPEN" ] || die "not enough gate openings"
mkdir -p "$ART/gates"
python3 jobs/tools/run_jass_gate_bounded.py --jass "$J" \
  --pattern-a "$W/candidate.pjtw" --pattern-b "$W/A.pjtw" \
  --openings-file "$W/open.fen" --search-params "$QS" --depth "$DEPTH" \
  --pairs "$PAIRS" --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
  --timeout "$SHARD_TIMEOUT" --work-dir "$W/gate-vs-A" \
  --out "$ART/gates/winner-vs-A.json" > "$W/gate-vs-A.log" 2>&1
if cmp -s "$W/A.pjtw" "$W/absolute.pjtw"; then
  cp "$ART/gates/winner-vs-A.json" "$ART/gates/winner-vs-absolute.json"
else
  python3 jobs/tools/run_jass_gate_bounded.py --jass "$J" \
    --pattern-a "$W/candidate.pjtw" --pattern-b "$W/absolute.pjtw" \
    --openings-file "$W/open.fen" --search-params "$QS" --depth "$DEPTH" \
    --pairs "$PAIRS" --nshards "$NSH_GATE" --max-parallel "$PAR_GATE" \
    --timeout "$SHARD_TIMEOUT" --work-dir "$W/gate-vs-absolute" \
    --out "$ART/gates/winner-vs-absolute.json" > "$W/gate-vs-absolute.log" 2>&1
fi

python3 jobs/tools/split_stratified_fen.py --input "$HOLDOUT/p3-holdout.fen" \
  --out-dir "$W/strata" --manifest "$ART/p3-holdout-strata.json" \
  --required-strata p3_mince p4_egal
for stratum in p3_mince p4_egal; do
  python3 jobs/tools/jnnw_doe.py fen-to-jnnw --input "$W/strata/$stratum.fen" \
    --output "$W/$stratum.raw.jnnw" >/dev/null
  "$J" --deep-relabel "$W/$stratum.raw.jnnw" "$W/$stratum.rel.jnnw" \
    "$ARB_DEPTH" --egdb "$WLD" --cache-mb "$CACHE_MB" > "$W/$stratum.rel.log" 2>&1
  python3 jobs/tools/jnnw_doe.py keep-decisive --input "$W/$stratum.rel.jnnw" \
    --output "$W/$stratum.dec.jnnw" >/dev/null
done

mkdir -p "$ART/conversion"
for cell in A candidate; do
  pattern="$W/$cell.pjtw"
  mkdir -p "$ART/conversion/$cell"
  for stratum in p3_mince p4_egal; do
    expected="$(jnnw_count "$W/$stratum.dec.jnnw")"
    [ "$expected" -gt 0 ] || die "$stratum has no decisive positions"
    pids=(); inputs=()
    for shard in $(seq 0 $((NSH_CONV-1))); do
      out="$W/$cell.$stratum.$shard.json"; inputs+=("$out")
      timeout "$SHARD_TIMEOUT" python3 jobs/tools/conv_fixed_wdl.py --jass "$J" \
        --pattern "$pattern" --defender-pattern "$W/gen2.pjtw" \
        --pool-jnnw "$W/$stratum.dec.jnnw" \
        --calibrate-tool jobs/tools/calibrate_vs_scan.py --depth "$CONV_DEPTH" \
        --max-plies 260 --shard "$shard" --nshards "$NSH_CONV" --out "$out" \
        > "$W/$cell.$stratum.$shard.log" 2>&1 &
      pids+=("$!")
      if [ "${#pids[@]}" -ge "$PAR_CONV" ]; then
        run_pids "$cell/$stratum" "${pids[@]}"; pids=()
      fi
    done
    [ "${#pids[@]}" -eq 0 ] || run_pids "$cell/$stratum" "${pids[@]}"
    python3 jobs/tools/aggregate_conv_shards.py --inputs "${inputs[@]}" \
      --expected-shards "$NSH_CONV" --expected-records "$expected" \
      --max-error-rate 0.08 --stratum "$stratum" \
      --out "$ART/conversion/$cell/$stratum.json"
  done
done

python3 - "$ART" "$SMOKE/teacher-smoke-decision.json" "$WINNER" \
  "$W/confirmation-input.json" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1])
payload={
  'smoke_decision':json.load(open(sys.argv[2])), 'winner':sys.argv[3],
  'baseline_p3':json.load(open(root/'conversion/A/p3_mince.json')),
  'candidate_p3':json.load(open(root/'conversion/candidate/p3_mince.json')),
  'baseline_p4':json.load(open(root/'conversion/A/p4_egal.json')),
  'candidate_p4':json.load(open(root/'conversion/candidate/p4_egal.json')),
  'vs_a':json.load(open(root/'gates/winner-vs-A.json')),
  'vs_absolute':json.load(open(root/'gates/winner-vs-absolute.json')),
}
Path(sys.argv[4]).write_text(json.dumps(payload,indent=2)+'\n')
PY
python3 jobs/tools/conversion_confirmation_gate.py confirm \
  --input "$W/confirmation-input.json" --min-delta "$MIN_DELTA" \
  --p4-margin "$P4_MARGIN" --alpha "$ALPHA" --power "$TARGET_POWER" \
  --out "$ART/teacher-confirmation-decision.json"
cp "$ART/teacher-confirmation-decision.json" "$ART/scientific-summary.json"
echo "teacher confirmation complete: winner=$WINNER"

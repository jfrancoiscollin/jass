#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Matched post-probe A/B1/B2/B3 teacher smoke.  Prepared only; launch after a
# mining result with enough certified parents.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?runner v3 must provide JASS_CODE_DIR}"
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
: "${JASS_ARTEFACT_DIR:?runner v3 must provide JASS_ARTEFACT_DIR}"
: "${JASS_JOB_ID:?runner v3 must provide JASS_JOB_ID}"
: "${SOURCE_RUN_PREFIX:?same promoted probe source used by mining required}"
: "${TEACHER_CORPUS_RUN_PREFIX:?completed teacher-mining result required}"
: "${STRONG_INPUTS_PREFIX:?immutable strong v1 bundle required}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
SRC="$JASS_RESULT_DIR/source"
INPUTS="$JASS_RESULT_DIR/inputs"
MINE="$JASS_RESULT_DIR/mining"
GEOM="$JASS_RESULT_DIR/geom"
mkdir -p "$W" "$ART" "$SRC" "$INPUTS" "$MINE" "$GEOM"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: instance active" >&2; exit 3; }

MIN_TEACHER_PARENTS="${MIN_TEACHER_PARENTS:-50}"
WDL_ANCHOR="${WDL_ANCHOR:-0.05}"
RANK_ANCHOR="${RANK_ANCHOR:-0.001}"
RANK_LAM="${RANK_LAM:-0.3}"
MAXIT="${MAXIT:-60}"
CHUNK="${CHUNK:-1000000}"
MIN_PAIRS="${MIN_PAIRS:-2}"
ARB_DEPTH="${ARB_DEPTH:-14}"
CACHE_MB="${CACHE_MB_RELABEL:-384}"
CONV_DEPTH="${CONV_DEPTH:-10}"
NSH_CONV="${NSH_CONV_TOTAL:-4}"
PAR_CONV="${PAR_CONV:-4}"
NSH_GATE="${NSH_GATE_TOTAL:-4}"
PAR_GATE="${PAR_GATE:-4}"
NOPEN="${NOPEN:-300}"
PAIRS="${PAIRS:-1}"
DEPTH="${DEPTH:-9}"
QS="${QS:-qs_forcing_depth=6,qs_promo_depth=6}"
SHARD_TIMEOUT="${SHARD_TIMEOUT:-7000}"
MIN_HARD_DELTA="${MIN_HARD_DELTA:-0.02}"
SIMPLICITY_TOLERANCE="${SIMPLICITY_TOLERANCE:-0.005}"
RES="$W/RESULTS.txt"; : > "$RES"

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
  local fail=0 pid
  for pid in "$@"; do wait "$pid" || fail=$((fail+1)); done
  [ "$fail" -eq 0 ] || die "$label: $fail processus en échec"
}

finalize(){
  rc=$?
  trap - EXIT
  set +e
  [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt"
  for cell in A B1 B2 B3; do
    [ -s "$W/$cell.pjtw" ] && gzip -n -c "$W/$cell.pjtw" > "$ART/$cell.pjtw.gz"
  done
  if [ -d "$W" ]; then
    (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  fi
  rm -rf "$W/build" "$SRC" "$INPUTS" "$MINE" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

python3 -m py_compile jobs/tools/fetch_result_files.py jobs/tools/teacher_smoke_gate.py
python3 jobs/tests/test_teacher_smoke_gate.py > "$W/test_teacher_smoke_gate.log" 2>&1 || die "test verdict teacher rouge"
python3 jobs/tools/fetch_result_files.py --prefix "$SOURCE_RUN_PREFIX" \
  --file artefacts/candidate.pjtw.gz=candidate.pjtw.gz \
  --file artefacts/promotion.json=promotion.json \
  --out-dir "$SRC" --report "$ART/verified-source-result.json" > "$W/fetch-source.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$TEACHER_CORPUS_RUN_PREFIX" \
  --file artefacts/teacher-corpus.tar.gz=teacher-corpus.tar.gz \
  --file artefacts/teacher-summary.json=teacher-summary.json \
  --out-dir "$MINE" --report "$ART/verified-mining-result.json" > "$W/fetch-mining.log" 2>&1
python3 jobs/tools/fetch_t1bis_inputs.py --remote-prefix "$STRONG_INPUTS_PREFIX" \
  --out-dir "$INPUTS" --report "$ART/verified-strong-inputs.json" > "$W/fetch-inputs.log" 2>&1
gunzip -c "$SRC/candidate.pjtw.gz" > "$W/A.pjtw"
python3 - "$SRC/promotion.json" "$MINE/teacher-summary.json" "$MIN_TEACHER_PARENTS" "$W/A.pjtw" <<'PY'
import hashlib,json,sys
promotion=json.load(open(sys.argv[1])); summary=json.load(open(sys.argv[2])); minimum=int(sys.argv[3])
if promotion.get('promotion_decision')!='promote': raise SystemExit('source run was not promoted')
tour=summary.get('probe_tour')
if promotion.get('tour') != tour: raise SystemExit(f"teacher/source tour mismatch: {tour} != {promotion.get('tour')}")
expected='complete_probe' if tour == 'T3' else 'continue_probe'
if promotion.get('scientific_status') != expected:
    raise SystemExit(f"source status mismatch: {promotion.get('scientific_status')} != {expected}")
if int(summary.get('teacher_parents',0)) < minimum:
    raise SystemExit(f"not enough teacher parents: {summary.get('teacher_parents',0)} < {minimum}")
payload_sha=hashlib.sha256(open(sys.argv[4],'rb').read()).hexdigest()
if promotion.get('candidate_sha') != payload_sha:
    raise SystemExit(f"promotion/source weights mismatch: {promotion.get('candidate_sha')} != {payload_sha}")
if summary.get('weights_sha') != payload_sha:
    raise SystemExit(f"teacher/source weights mismatch: {summary.get('weights_sha')} != {payload_sha}")
PY
python3 - "$MINE/teacher-corpus.tar.gz" "$W" <<'PY'
import pathlib,sys,tarfile
archive=pathlib.Path(sys.argv[1]); root=pathlib.Path(sys.argv[2]).resolve()
with tarfile.open(archive,'r:gz') as tf:
    members=tf.getmembers()
    for member in members:
        target=(root/member.name).resolve()
        if member.name.startswith('/') or root not in target.parents:
            raise SystemExit(f'unsafe tar member: {member.name}')
    tf.extractall(root, members=members, filter='data')
PY
cp "$MINE/teacher-summary.json" "$ART/teacher-summary.json"
gunzip -c "$INPUTS/parent.pjtw.gz" > "$W/absolute.pjtw"
gunzip -c "$INPUTS/gen2.pjtw.gz" > "$W/gen2.pjtw"
cp "$INPUTS/gauge.fen" "$W/gauge.fen"
for split in train holdout; do
  P="$(jnnw_count "$W/teacher/$split/parents.jnnw")"
  [ "$(( $(jnnw_count "$W/teacher/$split/b2_pairs.jnnw") / 2 ))" -eq "$P" ] || die "$split B2 désaligné"
  [ "$(( $(jnnw_count "$W/teacher/$split/b3_pairs.jnnw") / 2 ))" -eq "$P" ] || die "$split B3 désaligné"
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

say "=== fits A/B1/B2/B3 ==="
# A is the promoted WDL-adjudicated source. B1 adds the same oracle siblings
# through ordinary WDL; B2/B3 start from the exact same A and share rank budget.
"$J" --dump-eval-features "$W/teacher/train/b1_siblings.jnnw" "$W/b1.feat" > "$W/b1-dump.log" 2>&1
env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
  python3 pattern_jass/tools/wdl_finetune.py --champion "$W/A.pjtw" \
  --data "$W/teacher/train/b1_siblings.jnnw" --feat "$W/b1.feat" --out "$W/B1.pjtw" \
  --tools pattern_jass/tools --anchor "$WDL_ANCHOR" --color-fold --tempo-stage \
  --max-iter "$MAXIT" --chunk "$CHUNK" --verify-jass "$J" --verify-n 80 > "$W/B1-fit.log" 2>&1
for cell in B2 B3; do
  lower="$(echo "$cell" | tr '[:upper:]' '[:lower:]')"
  pairs="$W/teacher/train/${lower}_pairs.jnnw"
  "$J" --dump-eval-features "$pairs" "$W/$cell.feat" > "$W/$cell-dump.log" 2>&1
  EXTRA=(); [ "$cell" = B3 ] && EXTRA+=(--leaf-pov)
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
    python3 pattern_jass/tools/rank_finetune.py --champion "$W/A.pjtw" \
    --pairs "$pairs" --feat "$W/$cell.feat" --out "$W/$cell.pjtw" \
    --tools pattern_jass/tools --lam "$RANK_LAM" --anchor "$RANK_ANCHOR" \
    --min-pairs "$MIN_PAIRS" --color-fold --tempo-stage --max-iter "$MAXIT" \
    --chunk "$CHUNK" --verify-jass "$J" --verify-n 80 "${EXTRA[@]}" > "$W/$cell-fit.log" 2>&1
done
for cell in A B1 B2 B3; do [ -s "$W/$cell.pjtw" ] || die "poids $cell absents"; done

awk -v limit="$NOPEN" '
  /^[[:space:]]*#/ { next }
  { sub(/#.*/, ""); if (NF) { print; count++; if (count >= limit) exit } }
' data/dilf_combinations.fen > "$W/open.fen"
[ "$(wc -l < "$W/open.fen")" -eq "$NOPEN" ] || die "openings insuffisantes"
mkdir -p "$ART/gates"
say "=== gates communs vs A + référence absolue ==="
for cell in B1 B2 B3; do
  python3 jobs/tools/run_jass_gate_bounded.py --jass "$J" \
    --pattern-a "$W/$cell.pjtw" --pattern-b "$W/A.pjtw" --openings-file "$W/open.fen" \
    --search-params "$QS" --depth "$DEPTH" --pairs "$PAIRS" --nshards "$NSH_GATE" \
    --max-parallel "$PAR_GATE" --timeout "$SHARD_TIMEOUT" --work-dir "$W/gate-$cell-A" \
    --out "$ART/gates/$cell-vs-A.json" > "$W/gate-$cell-A.log" 2>&1
  if cmp -s "$W/A.pjtw" "$W/absolute.pjtw"; then
    cp "$ART/gates/$cell-vs-A.json" "$ART/gates/$cell-vs-absolute.json"
  else
    python3 jobs/tools/run_jass_gate_bounded.py --jass "$J" \
      --pattern-a "$W/$cell.pjtw" --pattern-b "$W/absolute.pjtw" --openings-file "$W/open.fen" \
      --search-params "$QS" --depth "$DEPTH" --pairs "$PAIRS" --nshards "$NSH_GATE" \
      --max-parallel "$PAR_GATE" --timeout "$SHARD_TIMEOUT" --work-dir "$W/gate-$cell-absolute" \
      --out "$ART/gates/$cell-vs-absolute.json" > "$W/gate-$cell-absolute.log" 2>&1
  fi
done

say "=== jauge commune p1-p4 ==="
python3 jobs/tools/split_stratified_fen.py --input "$W/gauge.fen" --out-dir "$W/strata" \
  --manifest "$ART/gauge-strata.json"
for stratum in p1_net p2_moyen p3_mince p4_egal; do
  python3 jobs/tools/jnnw_doe.py fen-to-jnnw --input "$W/strata/$stratum.fen" \
    --output "$W/$stratum.raw.jnnw" >/dev/null
  "$J" --deep-relabel "$W/$stratum.raw.jnnw" "$W/$stratum.rel.jnnw" "$ARB_DEPTH" \
    --egdb "$EGDIR" --cache-mb "$CACHE_MB" > "$W/$stratum.rel.log" 2>&1
  python3 jobs/tools/jnnw_doe.py keep-decisive --input "$W/$stratum.rel.jnnw" \
    --output "$W/$stratum.dec.jnnw" >/dev/null
  [ "$(jnnw_count "$W/$stratum.dec.jnnw")" -gt 0 ] || die "$stratum sans position décisive"
done
mkdir -p "$ART/conversion"
for cell in A B1 B2 B3; do
  mkdir -p "$ART/conversion/$cell"
  for stratum in p1_net p2_moyen p3_mince p4_egal; do
    EXPECTED="$(jnnw_count "$W/$stratum.dec.jnnw")"
    pids=(); inputs=()
    for shard in $(seq 0 $((NSH_CONV-1))); do
      out="$W/$cell.$stratum.$shard.json"; inputs+=("$out")
      timeout "$SHARD_TIMEOUT" python3 jobs/tools/conv_fixed_wdl.py --jass "$J" \
        --pattern "$W/$cell.pjtw" --defender-pattern "$W/gen2.pjtw" \
        --pool-jnnw "$W/$stratum.dec.jnnw" --calibrate-tool jobs/tools/calibrate_vs_scan.py \
        --depth "$CONV_DEPTH" --max-plies 260 --shard "$shard" --nshards "$NSH_CONV" \
        --out "$out" > "$W/$cell.$stratum.$shard.log" 2>&1 &
      pids+=("$!")
      if [ "${#pids[@]}" -ge "$PAR_CONV" ]; then run_pids "$cell/$stratum batch" "${pids[@]}"; pids=(); fi
    done
    run_pids "$cell/$stratum" "${pids[@]}"
    python3 jobs/tools/aggregate_conv_shards.py --inputs "${inputs[@]}" \
      --expected-shards "$NSH_CONV" --expected-records "$EXPECTED" --max-error-rate 0.08 \
      --stratum "$stratum" --out "$ART/conversion/$cell/$stratum.json"
  done
  python3 - "$ART/conversion/$cell" "$ART/conversion/$cell.json" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]); reports={p.stem:json.loads(p.read_text()) for p in root.glob('*.json')}
n=sum(r['n_pos'] for r in reports.values()); w=sum(r['n_win'] for r in reports.values())
out={'global':None if not n else round(w/n,6),**{k:v['conversion'] for k,v in reports.items()},'reports':reports}
Path(sys.argv[2]).write_text(json.dumps(out,indent=2)+'\n')
PY
done

python3 - "$ART" "$W/teacher-smoke-input.json" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]); cells={}
for cell in ('A','B1','B2','B3'):
    data={'conversion':json.loads((root/'conversion'/f'{cell}.json').read_text())}
    if cell!='A':
        data['vs_a']=json.loads((root/'gates'/f'{cell}-vs-A.json').read_text())
        data['vs_absolute']=json.loads((root/'gates'/f'{cell}-vs-absolute.json').read_text())
    cells[cell]=data
Path(sys.argv[2]).write_text(json.dumps(cells,indent=2)+'\n')
PY
python3 jobs/tools/teacher_smoke_gate.py --input "$W/teacher-smoke-input.json" \
  --out "$ART/teacher-smoke-decision.json" --min-hard-delta "$MIN_HARD_DELTA" \
  --simplicity-tolerance "$SIMPLICITY_TOLERANCE" > "$W/teacher-smoke-gate.log" 2>&1
say "teacher smoke terminé; verdict dans teacher-smoke-decision.json"

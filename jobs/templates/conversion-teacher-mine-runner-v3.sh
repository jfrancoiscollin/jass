#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Mine a completed probe run and materialize matched B1/B2/B3 corpora.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?runner v3 must provide JASS_CODE_DIR}"
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
: "${JASS_ARTEFACT_DIR:?runner v3 must provide JASS_ARTEFACT_DIR}"
: "${JASS_JOB_ID:?runner v3 must provide JASS_JOB_ID}"
: "${SOURCE_RUN_PREFIX:?completed T1/T2/T3 runner-v3 result required}"
: "${PROBE_TOUR:?T1-bis, T2 or T3 required}"

case "$PROBE_TOUR" in T1-bis|T2|T3) ;; *) echo "invalid PROBE_TOUR=$PROBE_TOUR" >&2; exit 2;; esac
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
SRC="$JASS_RESULT_DIR/source"
CORPUS="$W/teacher"
mkdir -p "$W" "$ART" "$SRC" "$CORPUS"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: instance active" >&2; exit 3; }

ARB_DEPTH="${ARB_DEPTH:-14}"
LEAF_DEPTH="${LEAF_DEPTH:-9}"
CACHE_MB="${CACHE_MB_RELABEL:-384}"
HOLDOUT_MOD="${HOLDOUT_MOD:-5}"
MAX_SIBLINGS="${MAX_SIBLINGS_PER_PARENT:-4}"
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

finalize(){
  rc=$?
  trap - EXIT
  set +e
  [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt"
  if [ -d "$CORPUS" ]; then
    tar -C "$W" -czf "$ART/teacher-corpus.tar.gz" teacher
  fi
  if [ -d "$W" ]; then
    (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  fi
  rm -rf "$W/build" "$SRC" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

python3 -m py_compile jobs/tools/conversion_teacher.py jobs/tools/fetch_result_files.py
python3 jobs/tests/test_conversion_teacher.py > "$W/test_conversion_teacher.log" 2>&1 || die "test teacher rouge"
python3 jobs/tools/fetch_result_files.py --prefix "$SOURCE_RUN_PREFIX" \
  --file artefacts/gen.jnnw.gz=gen.jnnw.gz \
  --file artefacts/deep.jnnw.gz=deep.jnnw.gz \
  --file artefacts/candidate.pjtw.gz=candidate.pjtw.gz \
  --file artefacts/promotion.json=promotion.json \
  --out-dir "$SRC" --report "$ART/verified-source-result.json" > "$W/fetch-source.log" 2>&1
gunzip -c "$SRC/gen.jnnw.gz" > "$W/gen.jnnw"
gunzip -c "$SRC/deep.jnnw.gz" > "$W/deep.jnnw"
gunzip -c "$SRC/candidate.pjtw.gz" > "$W/source.pjtw"
python3 - "$SRC/promotion.json" "$W/source.pjtw" "$PROBE_TOUR" <<'PY'
import hashlib,json,sys
promotion=json.load(open(sys.argv[1])); payload=open(sys.argv[2],'rb').read(); tour=sys.argv[3]
if promotion.get('tour') != tour: raise SystemExit(f"source tour mismatch: {promotion.get('tour')} != {tour}")
if promotion.get('promotion_decision') != 'promote': raise SystemExit('source candidate was not promoted')
expected='complete_probe' if tour == 'T3' else 'continue_probe'
if promotion.get('scientific_status') != expected:
    raise SystemExit(f"source status mismatch: {promotion.get('scientific_status')} != {expected}")
digest=hashlib.sha256(payload).hexdigest()
if promotion.get('candidate_sha') != digest:
    raise SystemExit(f"source candidate hash mismatch: {promotion.get('candidate_sha')} != {digest}")
PY
cp "$SRC/promotion.json" "$ART/source-promotion.json"

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

ENGINE_SHA="$(git rev-parse HEAD)"
WEIGHTS_SHA="$(sha256sum "$W/source.pjtw" | awk '{print $1}')"
say "=== mining causal $PROBE_TOUR depuis $SOURCE_RUN_PREFIX ==="
set +e
python3 jobs/tools/conversion_teacher.py --gen "$W/gen.jnnw" --oracle "$W/deep.jnnw" \
  --jass "$J" --probe-tour "$PROBE_TOUR" --out-dir "$CORPUS" --work-dir "$W/mining" \
  --oracle-depth "$ARB_DEPTH" --egdb "$EGDIR" --cache-mb "$CACHE_MB" \
  --holdout-mod "$HOLDOUT_MOD" --max-siblings-per-parent "$MAX_SIBLINGS" \
  --engine-sha "$ENGINE_SHA" --weights-sha "$WEIGHTS_SHA" > "$W/mining.log" 2>&1
MINE_RC=$?
set -e
if [ "$MINE_RC" -eq 3 ]; then
  cp "$CORPUS/summary.json" "$ART/teacher-summary.json"
  say "teacher: aucun parent causal certifié ; smoke A/B1/B2/B3 ne doit pas être soumis"
  exit 0
elif [ "$MINE_RC" -ne 0 ]; then
  die "mining technique (rc=$MINE_RC)"
fi
cp "$CORPUS/summary.json" "$ART/teacher-summary.json"

say "=== B3 leaf-mode sur exactement les paires B2 ==="
for split in train holdout; do
  parents="$CORPUS/$split/parents.jnnw"
  b2="$CORPUS/$split/b2_pairs.jnnw"
  b3="$CORPUS/$split/b3_pairs.jnnw"
  PAIRS=$(( $(jnnw_count "$b2") / 2 ))
  [ "$(jnnw_count "$parents")" -eq "$PAIRS" ] || die "$split: parents/B2 désalignés"
  if [ "$PAIRS" -eq 0 ]; then
    python3 - "$b3" <<'PY'
import struct,sys
open(sys.argv[1],'wb').write(b'JNNW'+struct.pack('<I',0))
PY
    continue
  fi
  "$J" --gen-siblings "$parents" "$b3" "$LEAF_DEPTH" --nnue "$W/source.pjtw" \
    --played-moves "$CORPUS/$split/good_moves.bin" \
    --dominated-moves "$CORPUS/$split/bad_moves.bin" \
    --leaf-mode --keep-all-pairs > "$W/b3-$split.log" 2>&1
  [ "$(( $(jnnw_count "$b3") / 2 ))" -eq "$PAIRS" ] || die "$split: B3 n'a pas conservé les paires B2"
done
say "teacher corpus prêt: mêmes parents/paires/splits pour B2 et B3"

#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# L3-IMBALANCE2 V3: controlled A/B refit of V1 outcome weighting vs
# outcome x searched move-criticality weighting. No new self-play.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?runner v3 must provide JASS_CODE_DIR}"
: "${JASS_RESULT_DIR:?runner v3 must provide JASS_RESULT_DIR}"
: "${JASS_ARTEFACT_DIR:?runner v3 must provide JASS_ARTEFACT_DIR}"
: "${JASS_JOB_ID:?runner v3 must provide JASS_JOB_ID}"
: "${EXPECTED_CODE_SHA:?pin the reviewed/merged jass SHA}"
: "${SOURCE_DATA_URI:?immutable V1 gN-source.jnnw.gz URI/path required}"
: "${SOURCE_DATA_SHA256:?SHA-256 of compressed source data required}"
: "${SOURCE_META_URI:?immutable V1 gN-source.jsm.gz URI/path required}"
: "${SOURCE_META_SHA256:?SHA-256 of compressed source metadata required}"
: "${PARENT_MODEL_URI:?frozen parent .pjtw.gz URI/path required}"
: "${PARENT_MODEL_SHA256:?SHA-256 of compressed parent model required}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$ART" "$GEOM"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: another instance is active" >&2; exit 3; }

BASE_SEED="${BASE_SEED:-271828}"
HOLDOUT_MOD="${HOLDOUT_MOD:-10}"
MAX_PARENTS="${MAX_PARENTS:-25000}"
CRITICALITY_DEPTH="${CRITICALITY_DEPTH:-8}"
CRITICALITY_SHARDS="${CRITICALITY_SHARDS:-8}"
TB_LOCK_PIECES="${TB_LOCK_PIECES:-6}"
PRESERVE_MARGIN="${PRESERVE_MARGIN:-50}"
UNIQUE_GAP="${UNIQUE_GAP:-75}"
NARROW_GAP="${NARROW_GAP:-30}"
NARROW_RATIO="${NARROW_RATIO:-0.25}"
CONTESTED_RATIO="${CONTESTED_RATIO:-0.50}"
UNIQUE_MULTIPLIER="${UNIQUE_MULTIPLIER:-3.0}"
NARROW_MULTIPLIER="${NARROW_MULTIPLIER:-2.0}"
CONTESTED_MULTIPLIER="${CONTESTED_MULTIPLIER:-1.5}"
WEIGHT_CAP="${WEIGHT_CAP:-8.0}"
WIN_WEIGHT="${WIN_WEIGHT:-1}"
DRAW_WEIGHT="${DRAW_WEIGHT:-2}"
LOSS_WEIGHT="${LOSS_WEIGHT:-4}"
MAXIT="${MAXIT:-25}"
L2="${L2:-3e-5}"
CHUNK="${CHUNK:-500000}"
JASS_BUILD_JOBS="${JASS_BUILD_JOBS:-8}"

RES="$W/RESULTS.txt"
: > "$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
fetch_input(){
  local src="$1" dst="$2"
  if [ -f "$src" ]; then cp "$src" "$dst"
  elif [[ "$src" == r2:* ]]; then command -v rclone >/dev/null || die "rclone missing"; rclone copyto "$src" "$dst"
  else die "unsupported or missing input: $src"; fi
}
finalize(){
  rc=$?; trap - EXIT; set +e
  [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt"
  if [ -d "$W" ]; then
    (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  fi
  rm -rf "$W/build" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

say "=== $JASS_JOB_ID — L3-IMBALANCE2 V3 criticality A/B refit ==="
[ -z "$(git branch --show-current)" ] || die "runner code worktree must be detached"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] || die "FULL_RUN_APPROVED=1 missing"
[ "${SCIENTIFIC_GO:-0}" = 1 ] || die "SCIENTIFIC_GO=1 missing"
[ "$BASE_SEED" -eq 271828 ] || die "primary seed must remain 271828"
[ "$HOLDOUT_MOD" -eq 10 ] || die "holdout-mod must remain 10"
[ "$MAX_PARENTS" -eq 25000 ] || die "first V3 test freezes MAX_PARENTS=25000"
[ "$CRITICALITY_DEPTH" -eq 8 ] || die "first V3 test freezes child search depth=8"
[ "$CRITICALITY_SHARDS" -eq 8 ] || die "cpx62 contract freezes 8 scoring shards"
[ "$TB_LOCK_PIECES" -eq 6 ] || die "exact-TB positions <=6 pieces must not receive criticality bonus"
[ "$PRESERVE_MARGIN" -eq 50 ] && [ "$UNIQUE_GAP" -eq 75 ] && [ "$NARROW_GAP" -eq 30 ] \
  || die "criticality score margins differ from preregistration"
[ "$NARROW_RATIO" = 0.25 ] && [ "$CONTESTED_RATIO" = 0.50 ] \
  || die "criticality preserving ratios differ from preregistration"
[ "$UNIQUE_MULTIPLIER" = 3.0 ] && [ "$NARROW_MULTIPLIER" = 2.0 ] \
  && [ "$CONTESTED_MULTIPLIER" = 1.5 ] && [ "$WEIGHT_CAP" = 8.0 ] \
  || die "criticality multipliers/cap differ from preregistration"
[ "$WIN_WEIGHT" = 1 ] && [ "$DRAW_WEIGHT" = 2 ] && [ "$LOSS_WEIGHT" = 4 ] \
  || die "V1 base weights must remain 1/2/4"
[ "$MAXIT" -eq 25 ] && [ "$L2" = 3e-5 ] && [ "$CHUNK" -eq 500000 ] \
  || die "fit recipe differs from V1"
[ "$(nproc)" -ge "$CRITICALITY_SHARDS" ] || die "not enough CPUs"

python3 -m py_compile jobs/tools/prepare_imbalance2_training.py \
  jobs/tools/imbalance2_criticality.py tools/selfplay_frontier.py \
  pattern_jass/tools/train_stream.py
python3 jobs/tests/test_imbalance2_criticality.py > "$W/test-criticality.log" 2>&1 \
  || die "criticality tests failed"
python3 jobs/tests/test_imbalance2_tools.py > "$W/test-imbalance2.log" 2>&1 \
  || die "imbalance2 regression tests failed"

python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen-patterns.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
NPAT="$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')"
[ "$NPAT" -eq 4251528 ] || die "8cf geometry mismatch"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
  -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j "$JASS_BUILD_JOBS" > "$W/build.log" 2>&1
J="$W/build/jass"
[ -x "$J" ] || die "jass binary missing"

fetch_input "$SOURCE_DATA_URI" "$W/source.jnnw.gz"
echo "$SOURCE_DATA_SHA256  $W/source.jnnw.gz" | sha256sum -c -
fetch_input "$SOURCE_META_URI" "$W/source.jsm.gz"
echo "$SOURCE_META_SHA256  $W/source.jsm.gz" | sha256sum -c -
fetch_input "$PARENT_MODEL_URI" "$W/parent.pjtw.gz"
echo "$PARENT_MODEL_SHA256  $W/parent.pjtw.gz" | sha256sum -c -
gzip -dc "$W/source.jnnw.gz" > "$W/source.jnnw"
gzip -dc "$W/source.jsm.gz" > "$W/source.jsm"
gzip -dc "$W/parent.pjtw.gz" > "$W/parent.pjtw"
[ -s "$W/parent.pjtw" ] || die "parent model missing"

python3 tools/selfplay_frontier.py profile --data "$W/source.jnnw" --meta "$W/source.jsm" \
  --manifest "$ART/source-profile.json" > "$W/source-profile.log" 2>&1
python3 tools/selfplay_frontier.py split --data "$W/source.jnnw" --meta "$W/source.jsm" \
  --out-data "$W/fit.jnnw" --out-meta "$W/fit.jsm" --holdout-mod "$HOLDOUT_MOD" \
  --seed "$BASE_SEED" --manifest "$ART/split.json" > "$W/split.log" 2>&1
HOLDOUT_COUNT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["holdout_records"])' "$ART/split.json")"
[ "$HOLDOUT_COUNT" -gt 0 ] || die "empty holdout"

# Control arm: current V1 deterministic 1/2/4 resampling.
python3 jobs/tools/prepare_imbalance2_training.py reweight --input "$W/fit.jnnw" \
  --output "$W/control.jnnw" --holdout-count "$HOLDOUT_COUNT" \
  --win-weight "$WIN_WEIGHT" --draw-weight "$DRAW_WEIGHT" --loss-weight "$LOSS_WEIGHT" \
  --seed $((BASE_SEED + 1)) --report "$ART/control-reweight.json"

# Select a bounded, weighted subset of exact-current-+2 training parents.
python3 jobs/tools/imbalance2_criticality.py make-parents --input "$W/fit.jnnw" \
  --holdout-count "$HOLDOUT_COUNT" --max-parents "$MAX_PARENTS" \
  --tb-lock-pieces "$TB_LOCK_PIECES" --win-weight "$WIN_WEIGHT" \
  --draw-weight "$DRAW_WEIGHT" --loss-weight "$LOSS_WEIGHT" --seed $((BASE_SEED + 2)) \
  --out-fen "$W/criticality-parents.fen" --out-index "$W/criticality-parents.json"
"$J" --dump-children "$W/criticality-parents.fen" "$W/criticality-children.jsonl" \
  > "$W/dump-children.log" 2>&1
python3 jobs/tools/imbalance2_criticality.py flatten-children \
  --parent-index "$W/criticality-parents.json" \
  --children-jsonl "$W/criticality-children.jsonl" \
  --out-data "$W/criticality-children.jnnw" --out-index "$W/criticality-child-index.json"
CHILD_COUNT="$(python3 -c 'import struct,sys; f=open(sys.argv[1],"rb"); h=f.read(8); print(struct.unpack("<I",h[4:])[0])' "$W/criticality-children.jnnw")"
[ "$CHILD_COUNT" -gt 0 ] || die "criticality child corpus is empty"

# Search child positions in deterministic contiguous shards. Ordered merge restores
# exact parent/child alignment. The frozen parent, never either new student, is the teacher.
pids=(); scored_args=();
base=$((CHILD_COUNT / CRITICALITY_SHARDS)); rem=$((CHILD_COUNT % CRITICALITY_SHARDS)); start=0
for shard in $(seq 0 $((CRITICALITY_SHARDS - 1))); do
  count="$base"; [ "$shard" -lt "$rem" ] && count=$((count + 1))
  out="$W/criticality-scored-${shard}.jnnw"
  scored_args+=(--input "$out")
  "$J" --rewrite-scores-with-search "$W/criticality-children.jnnw" "$out" \
    --nnue "$W/parent.pjtw" --depth "$CRITICALITY_DEPTH" --start "$start" --count "$count" \
    > "$W/criticality-search-${shard}.log" 2>&1 &
  pids+=("$!")
  start=$((start + count))
done
fail=0
for pid in "${pids[@]}"; do wait "$pid" || fail=$((fail + 1)); done
[ "$fail" -eq 0 ] || die "$fail criticality search shard(s) failed"
[ "$start" -eq "$CHILD_COUNT" ] || die "criticality shard allocation mismatch"
python3 jobs/tools/imbalance2_criticality.py merge-jnnw "${scored_args[@]}" \
  --output "$W/criticality-scored.jnnw" --report "$ART/criticality-search-merge.json"

# Treatment arm: same base outcome weights, multiplied only for searched narrow decisions.
python3 jobs/tools/imbalance2_criticality.py reweight --input "$W/fit.jnnw" \
  --scored-children "$W/criticality-scored.jnnw" \
  --child-index "$W/criticality-child-index.json" --output "$W/treatment.jnnw" \
  --holdout-count "$HOLDOUT_COUNT" --win-weight "$WIN_WEIGHT" \
  --draw-weight "$DRAW_WEIGHT" --loss-weight "$LOSS_WEIGHT" \
  --preserve-margin "$PRESERVE_MARGIN" --unique-gap "$UNIQUE_GAP" \
  --narrow-gap "$NARROW_GAP" --narrow-ratio "$NARROW_RATIO" \
  --contested-ratio "$CONTESTED_RATIO" --unique-multiplier "$UNIQUE_MULTIPLIER" \
  --narrow-multiplier "$NARROW_MULTIPLIER" \
  --contested-multiplier "$CONTESTED_MULTIPLIER" --weight-cap "$WEIGHT_CAP" \
  --seed $((BASE_SEED + 1)) --report "$ART/treatment-reweight.json" \
  --profile-report "$W/criticality-profiles.json"

gzip -n -c "$W/criticality-parents.json" > "$ART/criticality-parents.json.gz"
gzip -n -c "$W/criticality-child-index.json" > "$ART/criticality-child-index.json.gz"
gzip -n -c "$W/criticality-profiles.json" > "$ART/criticality-profiles.json.gz"

for arm in control treatment; do
  "$J" --dump-eval-features "$W/${arm}.jnnw" "$W/${arm}.feat" > "$W/${arm}-features.log" 2>&1
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
    python3 pattern_jass/tools/train_stream.py --data "$W/${arm}.jnnw" \
      --feat "$W/${arm}.feat" --out "$W/${arm}.pjtw" --target wdl --loss logistic \
      --color-fold --tempo-stage --warm-start "$W/parent.pjtw" \
      --holdout-count "$HOLDOUT_COUNT" --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
      > "$W/${arm}-train.log" 2>&1
  [ -s "$W/${arm}.pjtw" ] || die "$arm student missing"
  gzip -n -c "$W/${arm}.pjtw" > "$ART/${arm}.pjtw.gz"
done

python3 - "$ART" "$EXPECTED_CODE_SHA" "$SOURCE_DATA_URI" "$SOURCE_DATA_SHA256" \
  "$SOURCE_META_URI" "$SOURCE_META_SHA256" "$PARENT_MODEL_URI" "$PARENT_MODEL_SHA256" \
  "$HOLDOUT_COUNT" "$CHILD_COUNT" <<'PY'
import hashlib, json, sys
from pathlib import Path
art=Path(sys.argv[1])
payload={
  'schema':1,
  'experiment':'L3-IMBALANCE2-V3-CRITICALITY-AB-REFIT',
  'code_sha':sys.argv[2],
  'source_data':{'uri':sys.argv[3],'sha256_gzip':sys.argv[4]},
  'source_meta':{'uri':sys.argv[5],'sha256_gzip':sys.argv[6]},
  'parent_model':{'uri':sys.argv[7],'sha256_gzip':sys.argv[8]},
  'holdout_records':int(sys.argv[9]),
  'searched_children':int(sys.argv[10]),
  'arms':{
    'control':'deterministic material-up W/D/L resampling 1/2/4',
    'treatment':'same 1/2/4 multiplied by searched move criticality, capped at 8',
  },
  'new_selfplay':False,
  'scan_used_for_training':False,
  'gen2_used_for_training':False,
  'promotion_authorized':False,
  'next_action':'run independent unweighted specialist, role-slice, boundary and general-anchor gates',
}
for name in ('control.pjtw.gz','treatment.pjtw.gz','control-reweight.json','treatment-reweight.json'):
  path=art/name
  payload.setdefault('artefact_sha256',{})[name]=hashlib.sha256(path.read_bytes()).hexdigest()
(art/'l3-imbalance2-v3-criticality-manifest.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY

say "control_sha=$(sha256sum "$ART/control.pjtw.gz" | awk '{print $1}')"
say "treatment_sha=$(sha256sum "$ART/treatment.pjtw.gz" | awk '{print $1}')"
say "=== V3 A/B refit complete; no promotion without independent unweighted gates ==="

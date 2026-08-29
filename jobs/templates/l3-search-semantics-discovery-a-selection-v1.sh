#!/usr/bin/env bash
# HOME-only target-blind Discovery A freeze for Search-Semantics Attribution V1.
# No Jass/Scan scientific score, fit, tuning, training, force, bake or promotion.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_HOST:?}"
: "${PREFLIGHT_PREFIX:?}"; : "${FULL_RUN_APPROVED:?}"; : "${SCIENTIFIC_GO:?}"
export SCAN_BENCHMARK_ONLY=true SEARCH_ATTRIBUTION_ONLY=true HOME_ONLY=true

source jobs/templates/t3-f6-runtime-exclusions-v1.sh
PREREG_REF="afe4b96fc3c31739c6d53fa758260a5274e99c52"
CONTROL_CUTOFF="2c581c640876269cf18d70906b5b6051394e89b1"
JASS_CODE_FLOOR="cb91bec5c64b60f1084adb7c0c5459846f4624b1"
SCAN1651_PREFIX="r2:jass-data/runs/home-1651-l3-scan-ceiling-selection-v1/20260829T133348Z-28e12fba"
SOURCE_SEED_BASE=2026091410
SELECTION_SEED=2026091401
SUBSET_HASH_SEED=2026091402
BOOTSTRAP_SEED=2026091403
NSHARDS=16
RECORDS_PER_SHARD=50000
MIN_PLY=8
MAX_PLY=160
MAX_WORKERS=15

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
SRC="$W/source"; EXP="$W/export"; B="$W/build"
mkdir -p "$W" "$IN" "$ART" "$SRC" "$EXP" "$B"
RES="$W/RESULTS.txt"; PROG="$ART/PROGRESS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "TECHNICAL_ABORT: $*"; exit 1; }
stage(){ printf 'phase=%s\nscientific_data=0\nstrength_games=0\n' "$1" >"$PROG"; say "phase=$1"; }
trap 'rc=$?; set +e; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true; exit "$rc"' EXIT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^home-[0-9]+-l3-search-semantics-discovery-a-selection-v1$ ]] || die "job nomenclature drift"
[ "$(hostname)" = "$EXPECTED_HOST" ] || die "HOME host mismatch"
[ "$(nproc)" -eq 16 ] || die "HOME CPU contract mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "worktree not detached/clean"
[ "$FULL_RUN_APPROVED" = 1 ] && [ "$SCIENTIFIC_GO" = 1 ] || die "GO missing"
[ "$SCAN_BENCHMARK_ONLY" = true ] && [ "$SEARCH_ATTRIBUTION_ONLY" = true ] && [ "$HOME_ONLY" = true ] || die "benchmark/HOME guards missing"
unset JASS_TB_MOVE_ORDER_POLICY JASS_DSSD_MOVE_ORDER_POLICY JASS_T3_F6_MODEL || true
for f in SCIENTIFIC_DATA__0 STRENGTH_GAMES__0 TRAINING__FALSE TUNING__FALSE BAKE__FALSE PROMOTION__FALSE FORCE__FALSE; do : >"$ART/$f"; done

stage immutable-contracts
[ "$(git rev-parse "$PREREG_REF:docs/experiments/L3_JASS_SCAN_SEARCH_SEMANTICS_ATTRIBUTION_V1_20260829.md")" = "$(git rev-parse HEAD:docs/experiments/L3_JASS_SCAN_SEARCH_SEMANTICS_ATTRIBUTION_V1_20260829.md)" ] || die "prereg modified"
for f in src/search.cpp src/hub.cpp tests/test_search.cpp; do
  [ "$(git rev-parse "$PREREG_REF:$f")" = "$(git rev-parse HEAD:$f)" ] || die "production science drift: $f"
done
[ "$SOURCE_SEED_BASE" -eq 2026091410 ] && [ "$SELECTION_SEED" -eq 2026091401 ] && [ "$SUBSET_HASH_SEED" -eq 2026091402 ] && [ "$BOOTSTRAP_SEED" -eq 2026091403 ] || die "frozen seed drift"
: >"$ART/PREREG_UNCHANGED"; : >"$ART/PRODUCTION_SEARCH_UNCHANGED"

stage authenticate-current-preflight
python3 jobs/tools/fetch_result_files.py --prefix "$PREFLIGHT_PREFIX" \
  --file artefacts/RESULTS.txt=preflight-results.txt \
  --file artefacts/arm-manifest.json=arm-manifest.json \
  --out-dir "$IN/preflight" --report "$ART/verified-preflight.json" >"$W/fetch-preflight.log" 2>&1 || die "current-code preflight unavailable"
python3 - "$ART/verified-preflight.json" "$IN/preflight/preflight-results.txt" "$IN/preflight/arm-manifest.json" "$EXPECTED_CODE_SHA" <<'PY'
import json,sys
receipt=json.load(open(sys.argv[1])); text=open(sys.argv[2]).read(); arms=json.load(open(sys.argv[3])); code=sys.argv[4]
assert receipt['result_state']=='completed' and receipt['exit_code']==0 and receipt['code_sha']==code
assert 'PREFLIGHT_PASS' in text and arms['code_sha']==code
assert arms['arm_order']==['J0','J1_SCAN_VERIFY','J2_SCAN_THREAT_REENTRY','J3_SCAN_SINGLE_REPLY','J4_SCAN_LMR','J5_SCAN_ORDERING','J6_NO_NULL_MOVE']
assert arms['training_allowed'] is False and arms['tuning_allowed'] is False and arms['promotion_authorized'] is False
PY

stage freeze-exclusion-cutoff
CONTROL="${JASS_CONTROL_REPO_DIR:-/srv/jass/control}"
[ -e "$CONTROL/.git" ] || die "control checkout unavailable"
git -C "$CONTROL" cat-file -e "$CONTROL_CUTOFF^{commit}" || die "frozen control cutoff unavailable"
python3 jobs/tools/scan_ceiling_runtime_snapshot.py --control-dir "$CONTROL" --ref "$CONTROL_CUTOFF" \
  --output "$ART/runtime-exclusion-snapshot.json" --specs "$W/runtime-exclusions.tsv" >"$W/runtime-snapshot.log" 2>&1 || die "runtime cutoff snapshot failed"
DYNAMIC_ARGS=(); SOURCE_SPECS="$W/exclusion-source-specs.tsv"
printf 'label\tkind\tlocal_path\tprefix\tremote_path\treceipt\tcovers\n' >"$SOURCE_SPECS"
DYNAMIC_COUNT=0
while IFS=$'\t' read -r label prefix remote_path; do
  [ "$label" = label ] && continue; [ -n "${label:-}" ] || continue
  local="$IN/$label.fen"; rclone copyto "$prefix/$remote_path" "$local" >"$W/fetch-$label.log" 2>&1 || die "runtime exclusion fetch failed: $label"
  [ -s "$local" ] || die "empty runtime exclusion: $label"
  DYNAMIC_ARGS+=(--exclude-fen "$local"); DYNAMIC_COUNT=$((DYNAMIC_COUNT+1))
  printf '%s\tfen\t%s\t%s\t%s\t-\tR0_T3A_RUNTIME_PRE_CUTOFF\n' "$label" "$local" "$prefix" "$remote_path" >>"$SOURCE_SPECS"
done <"$W/runtime-exclusions.tsv"

stage authenticate-static-and-force-exclusions
IDENTITY_ARGS=(); FORCE_ARGS=(); IDENTITY_COUNT=0; FORCE_COUNT=0
while IFS='|' read -r label prefix remote_path; do
  [ -n "${label:-}" ] || continue
  local="$IN/$label.tsv.gz"; receipt="$ART/verified-identity-$label.json"
  python3 jobs/tools/fetch_result_files.py --prefix "$prefix" --file "$remote_path=$label.tsv.gz" --out-dir "$IN" --report "$receipt" >"$W/fetch-id-$label.log" 2>&1 || die "identity exclusion unavailable: $label"
  IDENTITY_ARGS+=(--exclude-tsv "$local"); IDENTITY_COUNT=$((IDENTITY_COUNT+1))
  covers="STATIC_SCIENTIFIC_COHORT"
  [ "$label" = train-a ] && covers="HISTORICAL_T3_ABC"
  [ "$label" = train-b ] && covers="DSSD_CONFIRMATION"
  [ "$label" = train-c ] && covers="M1,RICH_D_FRESH"
  [ "$label" = m2 ] && covers="M2"
  [ "$label" = m3 ] && covers="M3,M4"
  [ "$label" = m5 ] && covers="M5"
  [ "$label" = q1 ] && covers="Q1"
  [ "$label" = t2 ] && covers="T2_FRESH"
  [ "$label" = rf1 ] && covers="RF1_FRESH_1633"
  [ "$label" = t3 ] && covers="T3_FRESH_1638"
  printf '%s\ttsv\t%s\t%s\t%s\t%s\t%s\n' "$label" "$local" "$prefix" "$remote_path" "$receipt" "$covers" >>"$SOURCE_SPECS"
done <<<"$T3_F6_IDENTITY_EXCLUDE_SPECS"
while IFS='|' read -r label prefix remote_path; do
  [ -n "${label:-}" ] || continue
  local="$IN/force-$label.fen"; receipt="$ART/verified-force-$label.json"
  python3 jobs/tools/fetch_result_files.py --prefix "$prefix" --file "$remote_path=force-$label.fen" --out-dir "$IN" --report "$receipt" >"$W/fetch-force-$label.log" 2>&1 || die "force/opening exclusion unavailable: $label"
  FORCE_ARGS+=(--exclude-fen "$local"); FORCE_COUNT=$((FORCE_COUNT+1))
  printf 'force-%s\tfen\t%s\t%s\t%s\t%s\tFORCE_OPENING_POOL\n' "$label" "$local" "$prefix" "$remote_path" "$receipt" >>"$SOURCE_SPECS"
done <<<"$T3_F6_FORCE_EXCLUDE_SPECS"
[ "$IDENTITY_COUNT" -eq 10 ] && [ "$FORCE_COUNT" -eq 24 ] || die "static exclusion cardinality drift"

stage authenticate-consumed-scan1651
SCAN1651_LOCAL="$IN/scan-ceiling-consumed-1651.tsv"; SCAN1651_RECEIPT="$ART/verified-scan-ceiling-1651.json"
python3 jobs/tools/fetch_result_files.py --prefix "$SCAN1651_PREFIX" \
  --file artefacts/parents.tsv=scan-ceiling-consumed-1651.tsv \
  --file artefacts/selection-report.json=scan-ceiling-selection-report.json \
  --out-dir "$IN" --report "$SCAN1651_RECEIPT" >"$W/fetch-scan1651.log" 2>&1 || die "consumed Scan ceiling cohort unavailable"
python3 - "$SCAN1651_RECEIPT" "$IN/scan-ceiling-selection-report.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1])); s=json.load(open(sys.argv[2]));
assert r['job_id']=='home-1651-l3-scan-ceiling-selection-v1' and r['attempt_id']=='20260829T133348Z-28e12fba'
assert r['result_state']=='completed' and r['exit_code']==0
assert s['selected']==2000 and s['forbidden_overlap']==0
PY
SCAN_ARGS=(--exclude-tsv "$SCAN1651_LOCAL")
printf 'scan-ceiling-consumed-1651\ttsv\t%s\t%s\tartefacts/parents.tsv\t%s\tSCAN_CEILING_1651_1660\n' "$SCAN1651_LOCAL" "$SCAN1651_PREFIX" "$SCAN1651_RECEIPT" >>"$SOURCE_SPECS"

stage authenticate-exclusion-inventory
python3 - "$SOURCE_SPECS" "$ART/runtime-exclusion-snapshot.json" "$ART/exclusion-sources.json" "$CONTROL_CUTOFF" "$JASS_CODE_FLOOR" "$DYNAMIC_COUNT" <<'PY'
import csv,json,sys
from pathlib import Path
spec,snapshot,out=map(Path,sys.argv[1:4]); cutoff,floor=sys.argv[4:6]; expected=int(sys.argv[6]); snap=json.load(open(snapshot))
by_prefix={str(x.get('result_uri')):x for x in snap.get('runtime_jobs',[]) if x.get('result_uri')}
sources=[]; coverage={'M1','M2','M3','M4','M5','RICH_D_FRESH','DSSD_CONFIRMATION','SCAN_CEILING_1651_1660','HISTORICAL_T3_ABC','Q1','T2_FRESH','RF1_FRESH_1633','T3_FRESH_1638','R0_T3A_RUNTIME_PRE_CUTOFF','FORCE_OPENING_POOL'}
with spec.open(newline='',encoding='utf-8') as f:
 rd=csv.DictReader(f,delimiter='\t')
 for row in rd:
  receipt=None if row['receipt']=='-' else json.load(open(row['receipt']))
  runtime=by_prefix.get(row['prefix'])
  meta=receipt or runtime or {}
  covers=[x for x in row['covers'].split(',') if x]
  coverage.update(covers)
  sources.append({'label':row['label'],'kind':row['kind'],'local_path':row['local_path'],'source_uri':row['prefix'],
    'remote_path':row['remote_path'],'job_id':meta.get('job_id'),'attempt_id':meta.get('attempt_id'),'code_sha':meta.get('code_sha'),
    'cohort_sha256':None,'covers':covers})
p={'schema':'jass.search_semantics_exclusion_sources.v1','control_cutoff_ref':cutoff,'jass_code_floor':floor,
   'expected_dynamic_runtime_sources':expected,'coverage_claims':sorted(coverage),'sources':sources}
out.write_text(json.dumps(p,indent=2,sort_keys=True)+'\n')
PY
python3 jobs/tools/search_semantics_exclusion_inventory.py --manifest "$ART/exclusion-sources.json" --output "$ART/exclusion-inventory.json" >"$W/exclusion-inventory.log" 2>&1 || die "mandatory exclusion inventory failed"
ALL_FEN_ARGS=("${DYNAMIC_ARGS[@]}" "${FORCE_ARGS[@]}"); ALL_TSV_ARGS=("${IDENTITY_ARGS[@]}" "${SCAN_ARGS[@]}")

stage build-score-free-discovery-tools
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
[ -f "$VENV/.jass-runtime-ready-v1" ] || die "numeric venv unavailable"
"$VENV/bin/python" - <<'PY'
import numpy as np
assert np.random.Generator(np.random.PCG64(2026091410)).bit_generator.random_raw(1).shape==(1,)
PY
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen-patterns.log" 2>&1
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] && [ -d /root/egdb_intl ] || die "EGDB unavailable"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$B" -j8 --target jass_lib egdb_intl jass_scan_ceiling_parent_filter >"$W/build.log" 2>&1
CXX="${CXX:-c++}"
"$CXX" -std=c++20 -O2 -Isrc -Ipattern_jass/src -I/root/egdb_intl src/search_semantics_source_generator.cpp \
  -Wl,--start-group "$B/libjass_lib.a" "$B/libegdb_intl.a" -Wl,--end-group -pthread -o "$B/discovery-source" >"$W/source-link.log" 2>&1 || die "source generator link failed"
"$CXX" -std=c++20 -O2 -Isrc -Ipattern_jass/src -I/root/egdb_intl src/search_semantics_sibling_export.cpp \
  -Wl,--start-group "$B/libjass_lib.a" "$B/libegdb_intl.a" -Wl,--end-group -pthread -o "$B/discovery-siblings" >"$W/sibling-link.log" 2>&1 || die "sibling exporter link failed"

stage generate-fixed-pcg64-source
pids=(); for shard in $(seq 0 $((NSHARDS-1))); do
  (
    printf -v tag '%02d' "$shard"; seed=$((SOURCE_SEED_BASE+shard))
    "$VENV/bin/python" jobs/tools/pcg64_raw_stream.py --seed "$seed" | "$B/discovery-source" "$RECORDS_PER_SHARD" "$SRC/source-$tag.jnnw" "$SRC/source-$tag-report.json" "$seed" "$MIN_PLY" "$MAX_PLY" 9 >"$SRC/source-$tag.log" 2>&1
    "$B/jass_scan_ceiling_parent_filter" "$SRC/source-$tag.jnnw" "$SRC/filtered-$tag.jnnw" "$SRC/filtered-$tag.tsv" "$SRC/filter-$tag-report.json" 9 40 2 16 >"$SRC/filter-$tag.log" 2>&1
    python3 - "$SRC" "$tag" "$seed" "$EXPECTED_CODE_SHA" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); tag=sys.argv[2]; seed=int(sys.argv[3]); code=sys.argv[4]; sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
s=json.load(open(root/f'source-{tag}-report.json')); f=json.load(open(root/f'filter-{tag}-report.json'))
assert s['schema']=='jass.search_semantics_score_free_source.v1' and s['seed']==seed and s['records']==50000 and s['scores_generated']==0 and s['searches']==0
assert s['rng'].startswith('numpy.random.Generator(numpy.random.PCG64(seed))') and f['source_score_bytes_read'] is False and f['source_wdl_bytes_read'] is False
files=[f'source-{tag}.jnnw',f'source-{tag}-report.json',f'filtered-{tag}.jnnw',f'filtered-{tag}.tsv',f'filter-{tag}-report.json']
p={'schema':'jass.search_semantics_source_shard.v1','immutable':True,'benchmark_only':True,'target_blind':True,'code_sha':code,'shard':int(tag),'seed':seed,
   'source_records':50000,'rng':'numpy.random.Generator(numpy.random.PCG64(seed))','files_sha256':{x:sha(root/x) for x in files},
   'evaluations':0,'searches':0,'scores_generated':0,'fits':0,'strength_games':0,'training_allowed':False,'tuning_allowed':False,'promotion_authorized':False}
(root/f'shard-{tag}-manifest.json').write_text(json.dumps(p,indent=2,sort_keys=True)+'\n')
PY
  ) & pids+=("$!")
  if [ "${#pids[@]}" -ge "$MAX_WORKERS" ]; then rc=0; for p in "${pids[@]}"; do wait "$p" || rc=1; done; [ "$rc" -eq 0 ] || die "source shard failed"; pids=(); fi
done
rc=0; for p in "${pids[@]}"; do wait "$p" || rc=1; done; [ "$rc" -eq 0 ] || die "source shard failed"

stage select-and-freeze-discovery-a
SELECT_ARGS=(); for shard in $(seq 0 $((NSHARDS-1))); do printf -v tag '%02d' "$shard"; SELECT_ARGS+=(--filtered-jnnw "$SRC/filtered-$tag.jnnw" --filtered-meta "$SRC/filtered-$tag.tsv"); done
python3 jobs/tools/search_semantics_discovery_select.py "${SELECT_ARGS[@]}" "${ALL_FEN_ARGS[@]}" "${ALL_TSV_ARGS[@]}" \
  --exclusion-inventory "$ART/exclusion-inventory.json" --source-seed-base "$SOURCE_SEED_BASE" --selection-seed "$SELECTION_SEED" \
  --subset-hash-seed "$SUBSET_HASH_SEED" --bootstrap-seed "$BOOTSTRAP_SEED" --expected-shards "$NSHARDS" \
  --out-jnnw "$W/parents.jnnw" --out-tsv "$W/parents.tsv" --deep-tsv "$W/deep128.tsv" --report "$ART/selection-report.json" >"$W/select.log" 2>&1 || die "Discovery A selection failed"
python3 - "$ART/selection-report.json" "$ART/exclusion-inventory.json" "$ART/cohort-freeze-before-score.json" "$W/parents.tsv" "$W/deep128.tsv" <<'PY'
import hashlib,json,sys
from pathlib import Path
selp,exp,out,parents,deep=map(Path,sys.argv[1:]); sel=json.load(open(selp)); ex=json.load(open(exp)); sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sel['selected']==512 and sel['selected_by_phase']=={'P0':128,'P1':128,'P2':128,'P3':128} and sel['deep128']==128 and sel['deep128_by_phase']=={'P0':32,'P1':32,'P2':32,'P3':32}
assert sel['forbidden_overlap']==0 and sel['scores_read']==0 and sel['labels_read']==0 and sel['sorted_exclusion_set_sha256']==ex['sorted_exclusion_set_sha256']
p={'schema':'jass.search_semantics_discovery_a_freeze.v1','frozen_before_any_scientific_score':True,'cohort_consumed_after_first_score_only':True,
   'cohort_identity_sha256':sel['cohort_identity_sha256'],'selection_report_sha256':sha(selp),'exclusion_inventory_sha256':sha(exp),
   'parents_tsv_sha256':sha(parents),'deep128_tsv_sha256':sha(deep),'selected':512,'deep128':128,'source_shards':16,'source_records_per_shard':50000,
   'source_seed_base':2026091410,'selection_seed':2026091401,'subset_hash_seed':2026091402,'bootstrap_seed':2026091403,
   'rng':'numpy.random.Generator(numpy.random.PCG64(seed))','scientific_scores_generated':0,'evaluations':0,'searches':0,'fits':0,'strength_games':0,
   'training_allowed':False,'tuning_allowed':False,'promotion_authorized':False}
out.write_text(json.dumps(p,indent=2,sort_keys=True)+'\n')
PY
cp "$W/parents.tsv" "$ART/parents.tsv"; cp "$W/deep128.tsv" "$ART/deep128.tsv"; gzip -c "$W/parents.jnnw" >"$ART/parents.jnnw.gz"
: >"$ART/DISCOVERY_A_COHORT_FROZEN_BEFORE_SCORE"

stage enumerate-score-free-siblings
pids=(); for shard in $(seq 0 $((NSHARDS-1))); do
  ( printf -v tag '%02d' "$shard"; "$B/discovery-siblings" "$W/parents.jnnw" "$EXP/children-$tag.jnnw" "$EXP/groups-$tag.tsv" "$EXP/report-$tag.json" "$EGDIR" "$shard" "$NSHARDS" 64 >"$EXP/export-$tag.log" 2>&1 ) & pids+=("$!")
done
rc=0; for p in "${pids[@]}"; do wait "$p" || rc=1; done; [ "$rc" -eq 0 ] || die "score-free sibling export failed"
MERGE_ARGS=(); for shard in $(seq 0 $((NSHARDS-1))); do printf -v tag '%02d' "$shard"; MERGE_ARGS+=(--children-shard "$EXP/children-$tag.jnnw" --groups-shard "$EXP/groups-$tag.tsv" --report-shard "$EXP/report-$tag.json"); done
python3 jobs/tools/search_semantics_sibling_merge.py --parents "$W/parents.tsv" --deep "$W/deep128.tsv" "${MERGE_ARGS[@]}" \
  --out-children "$W/children.jnnw" --out-groups "$W/groups.tsv" --deep-row-ids "$W/deep128-row-ids.txt" --manifest "$ART/sibling-manifest.json" >"$W/sibling-merge.log" 2>&1 || die "sibling merge failed"
python3 - "$ART/sibling-manifest.json" "$ART/cohort-freeze-before-score.json" <<'PY'
import json,sys
s=json.load(open(sys.argv[1])); f=json.load(open(sys.argv[2]));
assert s['parents']==512 and s['deep128_parents']==128 and s['score_free'] is True and s['evaluations']==0 and s['searches']==0 and s['scores_generated']==0
assert f['frozen_before_any_scientific_score'] is True
PY
gzip -c "$W/children.jnnw" >"$ART/children.jnnw.gz"; gzip -c "$W/groups.tsv" >"$ART/groups.tsv.gz"; cp "$W/deep128-row-ids.txt" "$ART/deep128-row-ids.txt"
python3 - "$SRC" "$ART/source-stage-manifest.json" "$EXPECTED_CODE_SHA" <<'PY'
import hashlib,json,sys
from pathlib import Path
root,out=map(Path,sys.argv[1:3]); code=sys.argv[3]; sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest(); items=[]
for p in sorted(root.glob('shard-*-manifest.json')): items.append({'name':p.name,'sha256':sha(p)})
assert len(items)==16
out.write_text(json.dumps({'schema':'jass.search_semantics_source_stage.v1','immutable':True,'benchmark_only':True,'target_blind':True,'code_sha':code,
 'source_seed_base':2026091410,'source_shards':16,'source_records_per_shard':50000,'rng':'numpy.random.Generator(numpy.random.PCG64(seed))',
 'manifests':items,'evaluations':0,'searches':0,'scores_generated':0,'fits':0,'strength_games':0,'training_allowed':False,'tuning_allowed':False,'promotion_authorized':False},indent=2,sort_keys=True)+'\n')
PY
: >"$ART/DISCOVERY_A_SELECTION_READY__PASS"; : >"$ART/SCIENTIFIC_DATA__0"; : >"$ART/STRENGTH_GAMES__0"
say "DISCOVERY_A_SELECTION_READY code=$EXPECTED_CODE_SHA parents=512 deep128=128 source_shards=16 records_per_shard=$RECORDS_PER_SHARD scientific_data=0 strength_games=0"

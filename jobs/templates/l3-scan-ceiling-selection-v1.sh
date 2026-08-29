#!/usr/bin/env bash
# HOME-only target-blind cohort/subset freeze and sibling enumeration.
# No Scan score, fit, calibration, model/feature selection, game or promotion.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_ATTEMPT_ID:?}"
: "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_HOST:?}"
: "${PREFLIGHT_PREFIX:?}"; : "${FULL_RUN_APPROVED:?}"; : "${SCIENTIFIC_GO:?}"
export SCAN_BENCHMARK_ONLY=true

source jobs/templates/t3-f6-runtime-exclusions-v1.sh
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
SOURCE_SEED_BASE=2026091310
SELECTION_SEED=2026091301
SUBSET_SEED=2026091302
NSHARDS=16
MAX_WORKERS=15
RECORDS_PER_SHARD=50000
MAX_PLIES=160

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
SRC="$W/source"; OUTSRC="$ART/source"; EXP="$W/export"; EXPART="$ART/sibling-shards"
mkdir -p "$W" "$IN" "$ART" "$SRC" "$OUTSRC" "$EXP" "$EXPART"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + \
  2>/dev/null || true
DFA=$(df -Pm /root | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 3000 ] || { say "ABORT disque HOME <3Go"; exit 3; }
say "disk_free_mb=$DFA"

arch_assert(){
  local ref="$1" scratch="$W/arch-ref"
  mkdir -p "$scratch/src"
  for file in src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/movegen.cpp src/movegen.hpp; do
    git show "$ref:$file" >"$scratch/$file" || die "cannot materialize arch ref $ref:$file"
    cmp -s "$scratch/$file" "$file" || die "arch source is not byte-exact: $file"
  done
  grep -q 'g_emasks' src/scan_eval.cpp || die "arch guard: scan_eval missing g_emasks"
  grep -q 'has_any_capture' src/search.cpp || die "arch guard: search missing has_any_capture"
  grep -q 'has_any_capture' src/movegen.cpp || die "arch guard: movegen missing has_any_capture"
  say "arch_guard=PASS ref=$ref byte_exact=5 g_emasks=1 has_any_capture=2"
}

MON=""
monitor(){
  (t0=$(date +%s); while true; do
    {
      printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
      printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
      printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
      printf 'immutable_source_shards=%s/16\n' "$(find "$OUTSRC" -name 'shard-*-manifest.json' -type f 2>/dev/null | wc -l)"
      printf 'immutable_sibling_shards=%s/16\n' "$(find "$EXPART" -name 'shard-*-manifest.json' -type f 2>/dev/null | wc -l)"
      printf 'scan_benchmark_only=true\n'
    } >"$PROG.tmp"; mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 120
  done) & MON="$!"
}
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^home-[0-9]+-l3-scan-ceiling-selection-v1$ ]] || die "HOME job nomenclature drift"
[ "$(hostname)" = "$EXPECTED_HOST" ] || die "HOME host mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "dirty/non-detached worktree"
[ "$(nproc)" -eq 16 ] || die "HOME 16-CPU contract mismatch"
[ "$FULL_RUN_APPROVED" = 1 ] && [ "$SCIENTIFIC_GO" = 1 ] || die "execution GO missing"
[ "$SCAN_BENCHMARK_ONLY" = true ] || die "benchmark-only guard missing"
for command in cmp timeout df; do command -v "$command" >/dev/null || die "$command missing"; done
unset JASS_TB_MOVE_ORDER_POLICY JASS_DSSD_MOVE_ORDER_POLICY JASS_T3_F6_MODEL
monitor

stage authenticate-passed-scan-preflight
python3 jobs/tools/fetch_result_files.py --prefix "$PREFLIGHT_PREFIX" \
  --file artefacts/scan-technical-preflight.json=scan-technical-preflight.json \
  --file artefacts/runtime-payload-manifest.json=runtime-payload-manifest.json \
  --file artefacts/jass-sibling-export.gz=jass-sibling-export.gz \
  --file artefacts/curriculum.pjtw=curriculum.pjtw \
  --out-dir "$IN" --report "$ART/verified-preflight.json" >"$W/fetch-preflight.log" 2>&1 \
  || die "preflight fetch failed"
python3 - "$IN" "$ART/verified-preflight.json" "$EXPECTED_CODE_SHA" "$CURRICULUM_SHA" <<'PY_PREFLIGHT'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); receipt=json.load(open(sys.argv[2])); code,curr=sys.argv[3:]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=json.loads((root/'scan-technical-preflight.json').read_text())
runtime=json.loads((root/'runtime-payload-manifest.json').read_text())
if receipt.get('code_sha')!=code or receipt.get('result_state')!='completed' or receipt.get('exit_code')!=0: raise SystemExit('preflight result drift')
if p.get('verdict')!='SCAN_MAPPING_TECHNICAL_PASS' or p.get('passed') is not True: raise SystemExit('preflight did not pass')
if sha(root/'curriculum.pjtw')!=curr: raise SystemExit('CURRICULUM SHA drift')
if runtime.get('schema')!='jass.scan_ceiling_runtime_payload.v1' or sha(root/'jass-sibling-export.gz')!=runtime.get('files',{}).get('jass-sibling-export.gz',{}).get('sha256'): raise SystemExit('sibling-export runtime payload drift')
PY_PREFLIGHT
read -r SOURCE_SHARD_TIMEOUT EXPORT_SHARD_TIMEOUT < <(python3 - "$IN/scan-technical-preflight.json" <<'PY_TIMEOUTS'
import json,sys
p=json.load(open(sys.argv[1]))['throughput_and_eta']['selection_runtime']
if p.get('planning_only_not_scientific_metric') is not True or p.get('safety_factor')!=1.3:
 raise SystemExit('selection operational timeout plan drift')
source=int(p['source_timeout_seconds_per_shard']); export=int(p['export_timeout_seconds_per_shard'])
if source<300 or export<300: raise SystemExit('selection shard timeout below floor')
print(source,export)
PY_TIMEOUTS
)
python3 - "$IN/scan-technical-preflight.json" "$ART/selection-timeout-plan.json" <<'PY_TIMEOUT_PLAN'
import hashlib,json,sys
from pathlib import Path
source,out=map(Path,sys.argv[1:3]); pre=json.loads(source.read_text()); plan=pre['throughput_and_eta']['selection_runtime']
payload={'schema':'jass.scan_ceiling_selection_timeout_plan.v1',**plan,
 'preflight_report_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
 'scientific_budgets_changed':False}
out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY_TIMEOUT_PLAN
say "selection_rate_plan source_timeout_s=$SOURCE_SHARD_TIMEOUT export_timeout_s=$EXPORT_SHARD_TIMEOUT workers=$MAX_WORKERS"
gunzip -t "$IN/jass-sibling-export.gz"
gunzip -c "$IN/jass-sibling-export.gz" >"$W/jass-sibling-export"; chmod 0555 "$W/jass-sibling-export"

try_reuse_frozen_cohort(){
  [ -n "${SELECTION_RESUME_PREFIX:-}" ] || return 1
  local root="$W/resume-cohort" shard tag name
  local args=(
    --file artefacts/selection-report.json=selection-report.json
    --file artefacts/cohort-freeze-before-score.json=cohort-freeze-before-score.json
    --file artefacts/runtime-exclusion-snapshot.json=runtime-exclusion-snapshot.json
    --file artefacts/parents.tsv=parents.tsv
    --file artefacts/deep512.tsv=deep512.tsv
    --file artefacts/ultra256.tsv=ultra256.tsv
    --file artefacts/parents.jnnw.gz=parents.jnnw.gz
    --file artefacts/source-stage-manifest.json=source-stage-manifest.json
  )
  for shard in $(seq 0 $((NSHARDS-1))); do
    printf -v tag '%02d' "$shard"
    for name in manifest.json source.jnnw.gz filtered.jnnw.gz filtered.tsv.gz source-report.json filter-report.json; do
      args+=(--file "artefacts/source/shard-$tag-$name=source/shard-$tag-$name")
    done
  done
  mkdir -p "$root"
  python3 jobs/tools/fetch_result_files.py --prefix "$SELECTION_RESUME_PREFIX" \
    --expected-state failed --inventory-only --out-dir "$W" \
    --report "$W/resume-inventory.json" >"$W/fetch-resume-inventory.log" 2>&1 \
    || die "cannot authenticate failed selection inventory"
  python3 - "$W/resume-inventory.json" "$EXPECTED_CODE_SHA" "$EXPECTED_HOST" <<'PY_RESUME_IDENTITY'
import json,re,sys
p=json.load(open(sys.argv[1])); code,host=sys.argv[2:]
if p.get('state')!='verified' or p.get('result_state')!='failed' or int(p.get('exit_code',0))==0 or p.get('code_sha')!=code or p.get('host')!=host or not re.fullmatch(r'home-[0-9]+-l3-scan-ceiling-selection-v1',str(p.get('job_id',''))):
 raise SystemExit('failed selection resume identity/code/host drift')
PY_RESUME_IDENTITY
  [ "$?" -eq 0 ] || die "failed selection resume identity validation failed"
  if ! python3 - "$W/resume-inventory.json" <<'PY_HAS_FREEZE'
import json,sys
paths={str(x.get('path','')) for x in json.load(open(sys.argv[1])).get('files',[]) if isinstance(x,dict)}
raise SystemExit(0 if 'artefacts/cohort-freeze-before-score.json' in paths else 1)
PY_HAS_FREEZE
  then
    return 1
  fi
  python3 jobs/tools/fetch_result_files.py --prefix "$SELECTION_RESUME_PREFIX" \
    --expected-state failed "${args[@]}" --out-dir "$root" \
    --report "$W/verified-resume-cohort.json" >"$W/fetch-resume-cohort.log" 2>&1 \
    || die "failed attempt contains a cohort freeze but its immutable payload is incomplete"
  python3 - "$root" "$W/verified-resume-cohort.json" "$EXPECTED_CODE_SHA" \
    "$ART/selection-timeout-plan.json" <<'PY_REUSE_COHORT'
import gzip,hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); receipt=json.load(open(sys.argv[2])); code=sys.argv[3]; current_plan=Path(sys.argv[4])
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
if receipt.get('code_sha')!=code or receipt.get('result_state')!='failed' or int(receipt.get('exit_code',0))==0:
 raise SystemExit('resume attempt state/code drift')
selection=json.loads((root/'selection-report.json').read_text()); freeze=json.loads((root/'cohort-freeze-before-score.json').read_text()); source=json.loads((root/'source-stage-manifest.json').read_text())
policy=('training_allowed','tuning_allowed','calibration_allowed','model_selection_allowed','runtime_scale_selection_allowed')
policy_ok=lambda payload: all(payload.get(name) is False for name in policy)
if selection.get('selected')!=2000 or selection.get('selected_by_phase')!={'P0':500,'P1':500,'P2':500,'P3':500} or selection.get('deep512')!=512 or selection.get('ultra256')!=256 or selection.get('forbidden_overlap')!=0:
 raise SystemExit('frozen cohort cardinality/overlap drift')
if not policy_ok(selection) or not policy_ok(freeze):
 raise SystemExit('frozen cohort quarantine policy drift')
if freeze.get('frozen_before_any_sibling_score') is not True or freeze.get('cohort_identity_sha256')!=selection.get('cohort_identity_sha256') or freeze.get('selection_report_sha256')!=sha(root/'selection-report.json') or freeze.get('runtime_snapshot_sha256')!=sha(root/'runtime-exclusion-snapshot.json'):
 raise SystemExit('frozen cohort receipt drift')
if sha(root/'parents.tsv')!=selection['parents_tsv_sha256'] or sha(root/'deep512.tsv')!=selection['deep512_tsv_sha256'] or sha(root/'ultra256.tsv')!=selection['ultra256_tsv_sha256']:
 raise SystemExit('frozen cohort metadata SHA drift')
if hashlib.sha256(gzip.open(root/'parents.jnnw.gz','rb').read()).hexdigest()!=selection['parents_jnnw_sha256']:
 raise SystemExit('frozen parent JNNW SHA drift')
if source.get('schema')!='jass.scan_ceiling_source_stage.v1' or source.get('immutable') is not True or source.get('benchmark_only') is not True or not policy_ok(source) or source.get('source_seed_base')!=2026091310 or source.get('source_shards')!=16 or source.get('timeout_plan_sha256')!=sha(current_plan) or len(source.get('manifests',[]))!=16:
 raise SystemExit('frozen source-stage manifest drift')
for item in source['manifests']:
 manifest=root/'source'/item['name']
 if sha(manifest)!=item['sha256']: raise SystemExit(f"source manifest SHA drift: {manifest.name}")
 payload=json.loads(manifest.read_text())
 if payload.get('schema')!='jass.scan_ceiling_source_shard.v1' or payload.get('immutable') is not True or payload.get('benchmark_only') is not True or not policy_ok(payload):
  raise SystemExit(f'source shard quarantine drift: {manifest.name}')
 for name,want in payload['files_sha256'].items():
  if sha(root/'source'/name)!=want: raise SystemExit(f'source shard payload SHA drift: {name}')
PY_REUSE_COHORT
  [ "$?" -eq 0 ] || die "frozen cohort resume validation failed"
  cp "$root/selection-report.json" "$ART/selection-report.json" || die "cannot restore selection report"
  cp "$root/cohort-freeze-before-score.json" "$ART/cohort-freeze-before-score.json" || die "cannot restore freeze receipt"
  cp "$root/runtime-exclusion-snapshot.json" "$ART/runtime-exclusion-snapshot.json" || die "cannot restore runtime cutoff"
  cp "$root/source-stage-manifest.json" "$ART/source-stage-manifest.json" || die "cannot restore source manifest"
  cp "$root/parents.tsv" "$W/parents.tsv" && cp "$root/parents.tsv" "$ART/parents.tsv" || die "cannot restore parent metadata"
  cp "$root/deep512.tsv" "$W/deep512.tsv" && cp "$root/deep512.tsv" "$ART/deep512.tsv" || die "cannot restore DEEP512"
  cp "$root/ultra256.tsv" "$W/ultra256.tsv" && cp "$root/ultra256.tsv" "$ART/ultra256.tsv" || die "cannot restore ULTRA256"
  cp "$root/parents.jnnw.gz" "$ART/parents.jnnw.gz" || die "cannot restore parent JNNW"
  gunzip -c "$root/parents.jnnw.gz" >"$W/parents.jnnw" || die "cannot decompress frozen parent JNNW"
  cp "$root/source/"* "$OUTSRC/" || die "cannot restore immutable source shards"
}

COHORT_REUSED=0
if try_reuse_frozen_cohort; then
  COHORT_REUSED=1
  DYNAMIC_COUNT=$(python3 -c 'import json,sys; print(int(json.load(open(sys.argv[1]))["observable_pool_artifacts"]))' "$ART/runtime-exclusion-snapshot.json")
  stage reuse-byte-identical-frozen-cohort-after-failed-attempt
  say "cohort_resume=byte_exact prefix=$SELECTION_RESUME_PREFIX cutoff_preserved=true"
fi

if [ "$COHORT_REUSED" -eq 0 ]; then
stage cutoff-control-plane-and-runtime-pools
CONTROL="${JASS_CONTROL_REPO_DIR:-/srv/jass/control}"
[ -e "$CONTROL/.git" ] || die "runner control-plane checkout unavailable"
git -C "$CONTROL" fetch origin main >"$W/control-fetch.log" 2>&1 \
  || die "cannot freeze current origin/main control-plane view"
python3 jobs/tools/scan_ceiling_runtime_snapshot.py --control-dir "$CONTROL" \
  --ref origin/main --output "$ART/runtime-exclusion-snapshot.json" --specs "$W/runtime-exclusions.tsv" \
  >"$W/runtime-snapshot.log" 2>&1
DYNAMIC_ARGS=(); DYNAMIC_COUNT=0
while IFS=$'\t' read -r label prefix remote_path; do
  [ "$label" = label ] && continue
  [ -n "${label:-}" ] || continue
  local_path="$IN/$label.fen"
  rclone copyto "$prefix/$remote_path" "$local_path" >"$W/fetch-$label.log" 2>&1 \
    || die "pre-cutoff runtime pool was observable but cannot be fetched: $label"
  [ -s "$local_path" ] || die "empty pre-cutoff runtime pool: $label"
  DYNAMIC_ARGS+=(--exclude-fen "$local_path"); DYNAMIC_COUNT=$((DYNAMIC_COUNT+1))
done <"$W/runtime-exclusions.tsv"
python3 - "$ART/runtime-exclusion-snapshot.json" "$ART/runtime-dynamic-files.json" "$IN" "$DYNAMIC_COUNT" <<'PY_DYNAMIC'
import hashlib,json,sys
from pathlib import Path
snap,out,root=map(Path,sys.argv[1:4]); count=int(sys.argv[4]); files=sorted(root.glob('runtime-precutoff-*.fen'))
if len(files)!=count: raise SystemExit('dynamic runtime exclusion count drift')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
out.write_text(json.dumps({'schema':'jass.scan_ceiling_dynamic_runtime_files.v1','snapshot_sha256':sha(snap),
 'files':[{'name':p.name,'sha256':sha(p),'size_bytes':p.stat().st_size} for p in files]},indent=2,sort_keys=True)+'\n')
PY_DYNAMIC

stage fetch-all-preregistered-identity-only-exclusions
IDENTITY_ARGS=(); FORCE_ARGS=(); IDENTITY_COUNT=0; FORCE_COUNT=0
while IFS='|' read -r label prefix remote_path; do
  [ -n "${label:-}" ] || continue
  python3 jobs/tools/fetch_result_files.py --prefix "$prefix" --file "$remote_path=$label.tsv.gz" \
    --out-dir "$IN" --report "$ART/verified-identity-$label.json" >"$W/fetch-identity-$label.log" 2>&1 \
    || die "identity exclusion fetch failed: $label"
  IDENTITY_ARGS+=(--exclude-tsv "$IN/$label.tsv.gz"); IDENTITY_COUNT=$((IDENTITY_COUNT+1))
done <<<"$T3_F6_IDENTITY_EXCLUDE_SPECS"
while IFS='|' read -r label prefix remote_path; do
  [ -n "${label:-}" ] || continue
  python3 jobs/tools/fetch_result_files.py --prefix "$prefix" --file "$remote_path=$label.fen" \
    --out-dir "$IN" --report "$ART/verified-force-$label.json" >"$W/fetch-force-$label.log" 2>&1 \
    || die "force exclusion fetch failed: $label"
  FORCE_ARGS+=(--exclude-fen "$IN/$label.fen"); FORCE_COUNT=$((FORCE_COUNT+1))
done <<<"$T3_F6_FORCE_EXCLUDE_SPECS"
[ "$IDENTITY_COUNT" -eq 10 ] && [ "$FORCE_COUNT" -eq 24 ] || die "static exclusion count drift"

stage build-score-free-source-generator-and-zero-target-filter
arch_assert "$EXPECTED_CODE_SHA"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen-patterns.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=OFF \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON \
  -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass_scan_ceiling_source_generator jass_scan_ceiling_parent_filter \
  >"$W/build.log" 2>&1
GENERATOR="$W/build/jass_scan_ceiling_source_generator"; FILTER="$W/build/jass_scan_ceiling_parent_filter"

reuse_shard(){
  local shard="$1" tag; printf -v tag '%02d' "$shard"
  [ -n "${SELECTION_RESUME_PREFIX:-}" ] || return 1
  [ -f "$W/resume-inventory.json" ] || die "resume inventory absent"
  if ! python3 - "$W/resume-inventory.json" "$tag" <<'PY_HAS_SOURCE'
import json,sys
tag=sys.argv[2]; paths={str(x.get('path','')) for x in json.load(open(sys.argv[1])).get('files',[]) if isinstance(x,dict)}
raise SystemExit(0 if f'artefacts/source/shard-{tag}-manifest.json' in paths else 1)
PY_HAS_SOURCE
  then
    return 1
  fi
  rclone copyto "$SELECTION_RESUME_PREFIX/artefacts/source/shard-$tag-manifest.json" \
    "$OUTSRC/shard-$tag-manifest.json" >"$W/resume-$tag.log" 2>&1 \
    || die "cannot restore immutable source shard manifest $tag"
  for name in source.jnnw.gz filtered.jnnw.gz filtered.tsv.gz source-report.json filter-report.json; do
    rclone copyto "$SELECTION_RESUME_PREFIX/artefacts/source/shard-$tag-$name" \
      "$OUTSRC/shard-$tag-$name" >>"$W/resume-$tag.log" 2>&1 \
      || die "resume shard $tag is partially published"
  done
  python3 - "$OUTSRC" "$tag" "$ART/selection-timeout-plan.json" \
    "$W/resume-inventory.json" <<'PY_REUSE'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); tag=sys.argv[2]; plan,inventory=map(Path,sys.argv[3:5]); m=json.loads((root/f'shard-{tag}-manifest.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
remote={x['path']:x for x in json.loads(inventory.read_text())['files']}
for suffix in ('manifest.json','source.jnnw.gz','filtered.jnnw.gz','filtered.tsv.gz','source-report.json','filter-report.json'):
 name=f'shard-{tag}-{suffix}'; item=remote.get(f'artefacts/source/{name}'); local=root/name
 if item is None or sha(local)!=item['sha256'] or local.stat().st_size!=item['size_bytes']:
  raise SystemExit(f'resume inventory authentication drift: {name}')
if m.get('timeout_plan_sha256')!=sha(plan): raise SystemExit('resume timeout plan drift')
for name,want in m['files_sha256'].items():
 p=root/name
 if not p.is_file() or sha(p)!=want: raise SystemExit(f'resume hash drift: {name}')
PY_REUSE
  [ "$?" -eq 0 ] || die "resumed source shard validation failed: $tag"
  return 0
}

generate_shard(){
  local shard="$1" tag seed raw filt meta source_report filter_report
  printf -v tag '%02d' "$shard"; seed=$((SOURCE_SEED_BASE+shard))
  raw="$SRC/shard-$tag-source.jnnw"; filt="$SRC/shard-$tag-filtered.jnnw"
  meta="$SRC/shard-$tag-filtered.tsv"
  source_report="$OUTSRC/shard-$tag-source-report.json"
  filter_report="$OUTSRC/shard-$tag-filter-report.json"
  timeout -k 120s "${SOURCE_SHARD_TIMEOUT}s" \
    "$GENERATOR" "$RECORDS_PER_SHARD" "$raw" "$source_report" "$seed" 8 "$MAX_PLIES" 9 \
    >"$W/source-$tag.log" 2>&1
  timeout -k 120s "${SOURCE_SHARD_TIMEOUT}s" \
    "$FILTER" "$raw" "$filt" "$meta" "$filter_report" 9 40 2 16 \
    >"$W/filter-$tag.log" 2>&1
  gzip -n -c "$raw" >"$OUTSRC/.shard-$tag-source.jnnw.gz.tmp"
  gzip -n -c "$filt" >"$OUTSRC/.shard-$tag-filtered.jnnw.gz.tmp"
  gzip -n -c "$meta" >"$OUTSRC/.shard-$tag-filtered.tsv.gz.tmp"
  mv "$OUTSRC/.shard-$tag-source.jnnw.gz.tmp" "$OUTSRC/shard-$tag-source.jnnw.gz"
  mv "$OUTSRC/.shard-$tag-filtered.jnnw.gz.tmp" "$OUTSRC/shard-$tag-filtered.jnnw.gz"
  mv "$OUTSRC/.shard-$tag-filtered.tsv.gz.tmp" "$OUTSRC/shard-$tag-filtered.tsv.gz"
  python3 - "$OUTSRC" "$tag" "$seed" "$raw" "$filt" "$meta" \
    "$ART/selection-timeout-plan.json" <<'PY_SHARD'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); tag=sys.argv[2]; seed=int(sys.argv[3]); raw,filt,meta=map(Path,sys.argv[4:7]); plan=Path(sys.argv[7])
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
names=[f'shard-{tag}-source.jnnw.gz',f'shard-{tag}-filtered.jnnw.gz',f'shard-{tag}-filtered.tsv.gz',f'shard-{tag}-source-report.json',f'shard-{tag}-filter-report.json']
source=json.loads((root/f'shard-{tag}-source-report.json').read_text()); filt_report=json.loads((root/f'shard-{tag}-filter-report.json').read_text())
if source.get('records')!=50000 or source.get('seed')!=seed or source.get('evaluations')!=0 or source.get('scores_generated')!=0 or source.get('wdl_generated')!=0: raise SystemExit('score-free source report drift')
if filt_report.get('source_score_bytes_read') is not False or filt_report.get('source_wdl_bytes_read') is not False: raise SystemExit('target-blind filter drift')
payload={'schema':'jass.scan_ceiling_source_shard.v1','immutable':True,'benchmark_only':True,
 'training_allowed':False,'tuning_allowed':False,'calibration_allowed':False,
 'model_selection_allowed':False,'runtime_scale_selection_allowed':False,
 'shard':int(tag),'seed':seed,'records_requested':50000,
 'timeout_plan_sha256':sha(plan),'timeout_seconds':json.loads(plan.read_text())['source_timeout_seconds_per_shard'],
 'uncompressed_sha256':{'source_jnnw':sha(raw),'filtered_jnnw':sha(filt),'filtered_tsv':sha(meta)},
 'files_sha256':{n:sha(root/n) for n in names}}
tmp=root/f'.shard-{tag}-manifest.json.tmp'; tmp.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n'); tmp.replace(root/f'shard-{tag}-manifest.json')
PY_SHARD
}

stage generate-or-resume-sixteen-immutable-source-shards
failed=0
for wave_start in 0 15; do
  wave_end=$((wave_start+MAX_WORKERS-1)); [ "$wave_end" -lt "$NSHARDS" ] || wave_end=$((NSHARDS-1))
  pids=(); shards=()
  for shard in $(seq "$wave_start" "$wave_end"); do
    if reuse_shard "$shard"; then say "  reused immutable source shard $shard"; continue; fi
    (generate_shard "$shard") & pids+=("$!"); shards+=("$shard")
  done
  for index in "${!pids[@]}"; do
    if wait "${pids[$index]}"; then rc=0; else rc=$?; fi
    say "  generated shard=${shards[$index]} rc=$rc"
    [ "$rc" -eq 0 ] || failed=$((failed+1))
  done
done
[ "$failed" -eq 0 ] || die "$failed source shard(s) failed; retry with SELECTION_RESUME_PREFIX"
[ "$(find "$OUTSRC" -name 'shard-*-manifest.json' -type f | wc -l)" -eq 16 ] || die "source manifest count drift"
FILTERED_ARGS=(); META_ARGS=()
for shard in $(seq 0 $((NSHARDS-1))); do
  printf -v tag '%02d' "$shard"
  gunzip -c "$OUTSRC/shard-$tag-filtered.jnnw.gz" >"$SRC/shard-$tag-filtered.jnnw"
  gunzip -c "$OUTSRC/shard-$tag-filtered.tsv.gz" >"$SRC/shard-$tag-filtered.tsv"
  FILTERED_ARGS+=(--filtered-jnnw "$SRC/shard-$tag-filtered.jnnw")
  META_ARGS+=(--filtered-meta "$SRC/shard-$tag-filtered.tsv")
done
python3 - "$OUTSRC" "$ART/source-stage-manifest.json" "$ART/selection-timeout-plan.json" <<'PY_SOURCE'
import hashlib,json,sys
from pathlib import Path
root,out,plan=map(Path,sys.argv[1:4]); files=sorted(root.glob('shard-*-manifest.json'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
payload={'schema':'jass.scan_ceiling_source_stage.v1','immutable':True,'benchmark_only':True,
 'training_allowed':False,'tuning_allowed':False,'calibration_allowed':False,
 'model_selection_allowed':False,'runtime_scale_selection_allowed':False,
 'source_seed_base':2026091310,'source_shards':16,'records_per_shard':50000,
 'timeout_plan_sha256':sha(plan),'timeout_plan':json.loads(plan.read_text()),
 'manifests':[{'name':p.name,'sha256':sha(p),'payload':json.loads(p.read_text())} for p in files]}
out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY_SOURCE

stage freeze-cohort-and-nested-subsets-before-any-score
python3 jobs/tools/scan_ceiling_select.py "${FILTERED_ARGS[@]}" "${META_ARGS[@]}" \
  "${IDENTITY_ARGS[@]}" "${FORCE_ARGS[@]}" "${DYNAMIC_ARGS[@]}" \
  --selection-seed "$SELECTION_SEED" --subset-seed "$SUBSET_SEED" --expected-shards 16 \
  --out-jnnw "$W/parents.jnnw" --out-tsv "$W/parents.tsv" \
  --deep-tsv "$W/deep512.tsv" --ultra-tsv "$W/ultra256.tsv" \
  --report "$ART/selection-report.json" >"$W/select.log" 2>&1
cp "$W/parents.tsv" "$ART/parents.tsv"
cp "$W/deep512.tsv" "$ART/deep512.tsv"
cp "$W/ultra256.tsv" "$ART/ultra256.tsv"
gzip -n -c "$W/parents.jnnw" >"$ART/parents.jnnw.gz"
python3 - "$ART/selection-report.json" "$ART/cohort-freeze-before-score.json" "$ART/runtime-exclusion-snapshot.json" <<'PY_FREEZE'
import hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
sel,out,snap=map(Path,sys.argv[1:4]); s=json.loads(sel.read_text())
assert s['selected']==2000 and s['deep512']==512 and s['ultra256']==256 and s['forbidden_overlap']==0
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
out.write_text(json.dumps({'schema':'jass.scan_ceiling_cohort_freeze.v1','frozen_before_any_sibling_score':True,
 'frozen_at_utc':datetime.now(timezone.utc).isoformat(),'selection_report_sha256':sha(sel),
 'runtime_snapshot_sha256':sha(snap),'cohort_identity_sha256':s['cohort_identity_sha256'],
 'deep512_tsv_sha256':s['deep512_tsv_sha256'],'ultra256_tsv_sha256':s['ultra256_tsv_sha256'],
 'benchmark_only':True,'training_allowed':False,'tuning_allowed':False,
 'calibration_allowed':False,'model_selection_allowed':False,
 'runtime_scale_selection_allowed':False,
 'future_training_tuning_selection_calibration_forbidden':True},indent=2,sort_keys=True)+'\n')
PY_FREEZE
fi

stage enumerate-all-siblings-after-freeze
EGDIR=""
for directory in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$directory"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$directory"; break; }
done
[ -n "$EGDIR" ] || die "real HOME EGDB unavailable"

reuse_export_shard(){
  local shard="$1" tag name; printf -v tag '%02d' "$shard"
  [ -n "${SELECTION_RESUME_PREFIX:-}" ] || return 1
  [ -f "$W/resume-inventory.json" ] || die "resume inventory absent"
  if ! python3 - "$W/resume-inventory.json" "$tag" <<'PY_HAS_EXPORT'
import json,sys
tag=sys.argv[2]; paths={str(x.get('path','')) for x in json.load(open(sys.argv[1])).get('files',[]) if isinstance(x,dict)}
raise SystemExit(0 if f'artefacts/sibling-shards/shard-{tag}-manifest.json' in paths else 1)
PY_HAS_EXPORT
  then
    return 1
  fi
  for name in manifest.json children.jnnw.gz groups.tsv.gz report.json; do
    rclone copyto "$SELECTION_RESUME_PREFIX/artefacts/sibling-shards/shard-$tag-$name" \
      "$EXPART/shard-$tag-$name" >"$W/resume-export-$tag-$name.log" 2>&1 \
      || die "immutable sibling shard $tag is partially published"
  done
  python3 - "$EXPART" "$tag" "$ART/selection-report.json" \
    "$ART/selection-timeout-plan.json" "$W/resume-inventory.json" <<'PY_REUSE_EXPORT'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); tag=sys.argv[2]; selection,plan,inventory=map(Path,sys.argv[3:6]); sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((root/f'shard-{tag}-manifest.json').read_text()); s=json.loads(selection.read_text())
remote={x['path']:x for x in json.loads(inventory.read_text())['files']}
for suffix in ('manifest.json','children.jnnw.gz','groups.tsv.gz','report.json'):
 name=f'shard-{tag}-{suffix}'; item=remote.get(f'artefacts/sibling-shards/{name}'); local=root/name
 if item is None or sha(local)!=item['sha256'] or local.stat().st_size!=item['size_bytes']:
  raise SystemExit(f'resumed sibling inventory authentication drift: {name}')
if m.get('cohort_identity_sha256')!=s['cohort_identity_sha256'] or m.get('timeout_plan_sha256')!=sha(plan) or m.get('shard')!=int(tag):
 raise SystemExit('resumed sibling shard cohort/timeout drift')
for name,want in m['files_sha256'].items():
 if sha(root/name)!=want: raise SystemExit(f'resumed sibling shard SHA drift: {name}')
PY_REUSE_EXPORT
  [ "$?" -eq 0 ] || die "resumed sibling shard validation failed: $tag"
}

export_shard(){
  local shard="$1" tag; printf -v tag '%02d' "$shard"
  timeout -k 120s "${EXPORT_SHARD_TIMEOUT}s" \
    "$W/jass-sibling-export" "$W/parents.jnnw" "$EXP/children-$tag.jnnw" \
    "$EXP/groups-$tag.tsv" "$EXP/report-$tag.json" "$IN/curriculum.pjtw" \
    "$EGDIR" "$shard" "$NSHARDS" 256 >"$W/export-$tag.log" 2>&1
  gzip -n -c "$EXP/children-$tag.jnnw" >"$EXPART/.shard-$tag-children.jnnw.gz.tmp"
  gzip -n -c "$EXP/groups-$tag.tsv" >"$EXPART/.shard-$tag-groups.tsv.gz.tmp"
  cp "$EXP/report-$tag.json" "$EXPART/.shard-$tag-report.json.tmp"
  mv "$EXPART/.shard-$tag-children.jnnw.gz.tmp" "$EXPART/shard-$tag-children.jnnw.gz"
  mv "$EXPART/.shard-$tag-groups.tsv.gz.tmp" "$EXPART/shard-$tag-groups.tsv.gz"
  mv "$EXPART/.shard-$tag-report.json.tmp" "$EXPART/shard-$tag-report.json"
  python3 - "$EXPART" "$tag" "$ART/selection-report.json" \
    "$ART/selection-timeout-plan.json" <<'PY_EXPORT_SHARD'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); tag=sys.argv[2]; selection,plan=map(Path,sys.argv[3:5]); sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest(); s=json.loads(selection.read_text()); r=json.loads((root/f'shard-{tag}-report.json').read_text())
if r.get('schema')!='jass.scan_ceiling_sibling_export.v1' or r.get('shard')!=int(tag) or r.get('nshards')!=16 or r.get('input_parents')!=2000 or r.get('searches')!=0 or r.get('fits')!=0:
 raise SystemExit('sibling export report drift')
names=[f'shard-{tag}-children.jnnw.gz',f'shard-{tag}-groups.tsv.gz',f'shard-{tag}-report.json']
payload={'schema':'jass.scan_ceiling_sibling_export_shard.v1','immutable':True,'benchmark_only':True,
 'training_allowed':False,'tuning_allowed':False,'calibration_allowed':False,
 'model_selection_allowed':False,'runtime_scale_selection_allowed':False,
 'shard':int(tag),'nshards':16,'cohort_identity_sha256':s['cohort_identity_sha256'],
 'parents_jnnw_sha256':s['parents_jnnw_sha256'],'timeout_seconds':json.loads(plan.read_text())['export_timeout_seconds_per_shard'],
 'timeout_plan_sha256':sha(plan),'emitted_siblings':r['emitted_siblings'],
 'files_sha256':{name:sha(root/name) for name in names}}
tmp=root/f'.shard-{tag}-manifest.json.tmp'; tmp.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n'); tmp.replace(root/f'shard-{tag}-manifest.json')
PY_EXPORT_SHARD
}

failed=0
for wave_start in 0 15; do
  wave_end=$((wave_start+MAX_WORKERS-1)); [ "$wave_end" -lt "$NSHARDS" ] || wave_end=$((NSHARDS-1))
  pids=(); shards=()
  for shard in $(seq "$wave_start" "$wave_end"); do
    if reuse_export_shard "$shard"; then say "  reused immutable sibling shard $shard"; continue; fi
    (export_shard "$shard") & pids+=("$!"); shards+=("$shard")
  done
  for index in "${!pids[@]}"; do
    if wait "${pids[$index]}"; then rc=0; else rc=$?; fi
    say "  exported sibling shard=${shards[$index]} rc=$rc"
    [ "$rc" -eq 0 ] || failed=$((failed+1))
  done
done
[ "$failed" -eq 0 ] || die "$failed sibling export shard(s) failed; retry with SELECTION_RESUME_PREFIX"
[ "$(find "$EXPART" -name 'shard-*-manifest.json' -type f | wc -l)" -eq 16 ] || die "sibling export manifest count drift"
MERGE_ARGS=()
for shard in $(seq 0 $((NSHARDS-1))); do
  printf -v tag '%02d' "$shard"
  gunzip -t "$EXPART/shard-$tag-children.jnnw.gz"; gunzip -c "$EXPART/shard-$tag-children.jnnw.gz" >"$EXP/children-$tag.jnnw"
  gunzip -t "$EXPART/shard-$tag-groups.tsv.gz"; gunzip -c "$EXPART/shard-$tag-groups.tsv.gz" >"$EXP/groups-$tag.tsv"
  cp "$EXPART/shard-$tag-report.json" "$EXP/report-$tag.json"
  MERGE_ARGS+=(--children-shard "$EXP/children-$tag.jnnw" \
    --groups-shard "$EXP/groups-$tag.tsv" --report-shard "$EXP/report-$tag.json")
done
python3 - "$EXPART" "$ART/sibling-export-stage-manifest.json" "$ART/selection-report.json" \
  "$ART/selection-timeout-plan.json" <<'PY_EXPORT_STAGE'
import hashlib,json,sys
from pathlib import Path
root,out,selection,plan=map(Path,sys.argv[1:5]); sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest(); s=json.loads(selection.read_text()); files=sorted(root.glob('shard-*-manifest.json'))
if len(files)!=16: raise SystemExit('sibling export stage coverage drift')
payload={'schema':'jass.scan_ceiling_sibling_export_stage.v1','immutable':True,'benchmark_only':True,
 'training_allowed':False,'tuning_allowed':False,'calibration_allowed':False,
 'model_selection_allowed':False,'runtime_scale_selection_allowed':False,
 'cohort_identity_sha256':s['cohort_identity_sha256'],'shards':16,
 'timeout_plan_sha256':sha(plan),
 'manifests':[{'name':p.name,'sha256':sha(p),'payload':json.loads(p.read_text())} for p in files]}
out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY_EXPORT_STAGE
python3 jobs/tools/scan_ceiling_merge.py --parents "$W/parents.tsv" \
  --deep "$W/deep512.tsv" --ultra "$W/ultra256.tsv" "${MERGE_ARGS[@]}" \
  --expected-shards 16 --out-children "$W/children.jnnw" --out-groups "$ART/siblings.tsv" \
  --deep-row-ids "$ART/deep512-row-ids.txt" --ultra-row-ids "$ART/ultra256-row-ids.txt" \
  --manifest "$ART/sibling-manifest.json" >"$W/merge.log" 2>&1
gzip -n -c "$W/children.jnnw" >"$ART/children.jnnw.gz"

stage quarantine-and-selection-terminal-summary
python3 - "$ART/JASS_CONTROL_SUMMARY.json" "$ART/selection-report.json" \
  "$ART/sibling-manifest.json" "$ART/cohort-freeze-before-score.json" \
  "$ART/source-stage-manifest.json" "$ART/sibling-export-stage-manifest.json" \
  "$ART/selection-timeout-plan.json" \
  "$EXPECTED_CODE_SHA" <<'PY_SUMMARY'
import hashlib,json,sys
from pathlib import Path
out,sel,sib,freeze,source_stage,export_stage,timeout_plan=map(Path,sys.argv[1:8]); code=sys.argv[8]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest(); s=json.loads(sel.read_text()); m=json.loads(sib.read_text())
payload={'schema':'jass.scan_ceiling_selection_summary.v1','verdict':'SCAN_COHORT_FROZEN_BENCHMARK_ONLY',
 'passed':True,'code_sha':code,'benchmark_only':True,'scan_benchmark_only':True,
 'cohort_identity_sha256':s['cohort_identity_sha256'],'parents':s['selected'],
 'deep512':s['deep512'],'ultra256':s['ultra256'],'siblings':m['siblings'],
 'selection_report_sha256':sha(sel),'sibling_manifest_sha256':sha(sib),'freeze_receipt_sha256':sha(freeze),
 'source_stage_manifest_sha256':sha(source_stage),'sibling_export_stage_manifest_sha256':sha(export_stage),
 'timeout_plan_sha256':sha(timeout_plan),
 'consumption_state':'quarantined_before_first_score',
 'training_allowed':False,'tuning_allowed':False,'calibration_allowed':False,
 'model_selection_allowed':False,'runtime_scale_selection_allowed':False,
 'future_training_tuning_selection_calibration_forbidden':True,
 'guards':{'fits':0,'refits':0,'calibrations':0,'feature_selections':0,'model_selections':0,
           'strength_games':0,'bakes':0,'promotions':0,'promotion_authorized':False}}
out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY_SUMMARY
: >"$ART/VERDICT__SCAN_COHORT_FROZEN_BENCHMARK_ONLY"
: >"$ART/SCAN_BENCHMARK_ONLY__TRUE"
: >"$ART/COHORT_QUARANTINED__TRUE"
: >"$ART/STRENGTH_GAMES__0"
printf 'PROMOTION_AUTHORIZED__FALSE\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"
printf 'AUTOMATIC_NEXT_JOB__NULL\n' >"$ART/AUTOMATIC_NEXT_JOB__NULL"
say "SCAN_COHORT_FROZEN_BENCHMARK_ONLY cohort=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["cohort_identity_sha256"])' "$ART/selection-report.json")"
say "parents=2000 deep=512 ultra=256 dynamic_runtime_exclusions=$DYNAMIC_COUNT fits=0 games=0"

#!/usr/bin/env bash
# HOME-only resumable official Scan exact-request node ladder.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_HOST:?}"; : "${FROZEN_COHORT_CODE_SHA:?}"
: "${SELECTION_PREFIX:?}"; : "${PREFLIGHT_PREFIX:?}"
: "${SCORE_SCOPE:?base, deep or ultra}"; : "${FULL_RUN_APPROVED:?}"; : "${SCIENTIFIC_GO:?}"
export SCAN_BENCHMARK_ONLY=true
SCAN_COMMIT="7aae17e7b7bfc47744601afb1ee7655e18983ce5"
NSHARDS=16
MAX_WORKERS=15
case "$SCORE_SCOPE" in
  base) BUDGETS="1000,5000,50000,200000"; LABEL="scan-base"; ROW_FILE="-";;
  deep) BUDGETS="1000000,2000000"; LABEL="scan-deep"; ROW_FILE="deep512-row-ids.txt";;
  ultra) BUDGETS="5000000"; LABEL="scan-ultra"; ROW_FILE="ultra256-row-ids.txt";;
  *) echo "invalid SCORE_SCOPE=$SCORE_SCOPE" >&2; exit 2;;
esac

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"; SCORES="$ART/scores"
mkdir -p "$W" "$IN" "$ART" "$SCORES" "$W/scan-runtime/data"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }; die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

DFA=$(df -Pm /root | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 3000 ] || { say "ABORT disque HOME <3Go"; exit 3; }
say "disk_free_mb=$DFA"

MON=""
monitor(){ (t0=$(date +%s); while true; do { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%FT%T%z')"; printf 'phase=%s\n' "$(cat "$STAGE")"; printf 'elapsed_min=%d\n' "$((($(date +%s)-t0)/60))"; printf 'immutable_score_shards=%s/16\n' "$(find "$SCORES" -name "$LABEL-shard-*-manifest.json" -type f 2>/dev/null | wc -l)"; [ ! -f "$W/rate-plan-progress.txt" ] || cat "$W/rate-plan-progress.txt"; } >"$PROG.tmp"; mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 120; done) & MON="$!"; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e; [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true; [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"; (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^home-[0-9]+-l3-scan-ceiling-scan-(base|deep|ultra)-v1$ ]] || die "HOME job nomenclature drift"
[[ "$JASS_JOB_ID" == *"-scan-$SCORE_SCOPE-v1" ]] || die "job/scope mismatch"
[ "$(hostname)" = "$EXPECTED_HOST" ] || die "HOME host mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "dirty/non-detached worktree"
[ "$(nproc)" -eq 16 ] || die "HOME 16-CPU contract mismatch"
[ "$FULL_RUN_APPROVED" = 1 ] && [ "$SCIENTIFIC_GO" = 1 ] || die "execution GO missing"
for command in timeout df; do command -v "$command" >/dev/null || die "$command missing"; done
unset JASS_TB_MOVE_ORDER_POLICY JASS_DSSD_MOVE_ORDER_POLICY JASS_T3_F6_MODEL
monitor

stage fetch-authenticate-frozen-cohort-and-home-compiled-scan
python3 jobs/tools/fetch_result_files.py --prefix "$SELECTION_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=selection-summary.json \
  --file artefacts/selection-report.json=selection-report.json \
  --file artefacts/sibling-manifest.json=sibling-manifest.json \
  --file artefacts/children.jnnw.gz=children.jnnw.gz \
  --file artefacts/siblings.tsv=siblings.tsv \
  --file artefacts/deep512-row-ids.txt=deep512-row-ids.txt \
  --file artefacts/ultra256-row-ids.txt=ultra256-row-ids.txt \
  --out-dir "$IN" --report "$ART/verified-selection.json" >"$W/fetch-selection.log" 2>&1 \
  || die "selection fetch failed"
python3 jobs/tools/fetch_result_files.py --prefix "$PREFLIGHT_PREFIX" \
  --file artefacts/scan-technical-preflight.json=scan-technical-preflight.json \
  --file artefacts/scan-build-manifest.json=scan-build-manifest.json \
  --file artefacts/runtime-payload-manifest.json=runtime-payload-manifest.json \
  --file artefacts/scan-home-compiled.gz=scan-home-compiled.gz \
  --file artefacts/scan-data-eval=scan-data-eval \
  --file artefacts/scan.ini=scan.ini \
  --out-dir "$IN" --report "$ART/verified-preflight.json" >"$W/fetch-preflight.log" 2>&1 \
  || die "Scan runtime fetch failed"
gunzip -t "$IN/children.jnnw.gz"; gunzip -c "$IN/children.jnnw.gz" >"$W/children.jnnw"
gunzip -t "$IN/scan-home-compiled.gz"; gunzip -c "$IN/scan-home-compiled.gz" >"$W/scan-runtime/scan_home"
chmod 0555 "$W/scan-runtime/scan_home"; cp "$IN/scan-data-eval" "$W/scan-runtime/data/eval"; cp "$IN/scan.ini" "$W/scan-runtime/scan.ini"
python3 - "$IN" "$W/children.jnnw" "$W/scan-runtime/scan_home" "$ART/verified-selection.json" "$ART/verified-preflight.json" "$FROZEN_COHORT_CODE_SHA" "$SCAN_COMMIT" <<'PY_AUTH'
import hashlib,json,sys
from pathlib import Path
root,children,scan=map(Path,sys.argv[1:4]); sr,pr=map(lambda p:json.load(open(p)),sys.argv[4:6]); code,commit=sys.argv[6:]
sel=json.loads((root/'selection-summary.json').read_text()); selection=json.loads((root/'selection-report.json').read_text()); siblings=json.loads((root/'sibling-manifest.json').read_text()); pre=json.loads((root/'scan-technical-preflight.json').read_text()); build=json.loads((root/'scan-build-manifest.json').read_text()); payload=json.loads((root/'runtime-payload-manifest.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
if any(r.get('code_sha')!=code or r.get('result_state')!='completed' or r.get('exit_code')!=0 for r in (sr,pr)): raise SystemExit('upstream result/code drift')
if sel.get('verdict')!='SCAN_COHORT_FROZEN_BENCHMARK_ONLY' or not sel.get('passed'): raise SystemExit('selection not frozen')
if any(sel.get(name) is not False for name in ('training_allowed','tuning_allowed','calibration_allowed','model_selection_allowed','runtime_scale_selection_allowed')): raise SystemExit('selection quarantine drift')
if selection.get('cohort_identity_sha256')!=sel.get('cohort_identity_sha256') or sel.get('selection_report_sha256')!=sha(root/'selection-report.json') or sel.get('sibling_manifest_sha256')!=sha(root/'sibling-manifest.json') or len(str(sel.get('sibling_export_stage_manifest_sha256','')))!=64: raise SystemExit('selection manifest chain drift')
if siblings.get('children_sha256')!=sha(children) or siblings.get('groups_sha256')!=sha(root/'siblings.tsv') or siblings.get('deep_row_ids_sha256')!=sha(root/'deep512-row-ids.txt') or siblings.get('ultra_row_ids_sha256')!=sha(root/'ultra256-row-ids.txt'): raise SystemExit('sibling payload hash drift')
if pre.get('verdict')!='SCAN_MAPPING_TECHNICAL_PASS' or not pre.get('passed'): raise SystemExit('preflight not passed')
if build.get('source_commit')!=commit or build.get('scan_binary_sha256')!=sha(scan) or pre.get('scan_binary_sha256')!=sha(scan): raise SystemExit('compiled Scan provenance drift')
for name in ('scan-home-compiled.gz','scan-data-eval','scan.ini'):
 if sha(root/name)!=payload['files'][name]['sha256']: raise SystemExit(f'payload SHA drift: {name}')
PY_AUTH
ROW_ARG="$ROW_FILE"; [ "$ROW_ARG" = - ] || ROW_ARG="$IN/$ROW_ARG"

stage derive-publish-per-shard-timeouts-from-home-preflight-rate
PLAN_JSON="$ART/$LABEL-shard-timeout-plan.json"
PLAN_TSV="$W/$LABEL-shard-timeout-plan.tsv"
python3 jobs/tools/scan_ceiling_shard_timeouts.py \
  --preflight "$IN/scan-technical-preflight.json" --groups "$IN/siblings.tsv" \
  --row-ids "$ROW_ARG" --engine Scan --budgets "$BUDGETS" --nshards "$NSHARDS" \
  --output-json "$PLAN_JSON" --output-tsv "$PLAN_TSV"
PER_SEARCH_TIMEOUT=$(python3 -c 'import json,sys; print(int(json.load(open(sys.argv[1]))["per_search_timeout_seconds"]))' "$PLAN_JSON")
[[ "$PER_SEARCH_TIMEOUT" =~ ^[0-9]+$ ]] || die "invalid Scan per-search timeout"
python3 - "$PLAN_JSON" <<'PY_PLAN' | tee -a "$RES" "$W/rate-plan-progress.txt"
import json,sys
p=json.load(open(sys.argv[1]))
print(f"rate_engine=Scan")
print(f"rate_requested_nodes_per_second={p['smoke_requested_nodes_per_second']:.3f}")
print(f"planned_requested_nodes={p['requested_nodes']}")
print(f"planned_healthy_eta_seconds={p['stage_healthy_eta_seconds']:.1f}")
print(f"planned_timeout_ceiling_seconds={p['stage_timeout_ceiling_seconds']:.1f}")
print(f"per_search_timeout_seconds={p['per_search_timeout_seconds']}")
print(f"timeout_safety_factor={p['safety_factor']}")
PY_PLAN
if [ -n "${SCORE_RESUME_PREFIX:-}" ]; then
  python3 jobs/tools/fetch_result_files.py --prefix "$SCORE_RESUME_PREFIX" \
    --expected-state failed --inventory-only --out-dir "$W" \
    --report "$W/resume-inventory.json" >"$W/fetch-resume-inventory.log" 2>&1 \
    || die "cannot authenticate failed $LABEL inventory"
  python3 - "$W/resume-inventory.json" "$EXPECTED_CODE_SHA" "$EXPECTED_HOST" "$SCORE_SCOPE" <<'PY_RESUME_IDENTITY'
import json,re,sys
p=json.load(open(sys.argv[1])); code,host,scope=sys.argv[2:]
pattern=rf'home-[0-9]+-l3-scan-ceiling-scan-{re.escape(scope)}-v1'
if p.get('state')!='verified' or p.get('result_state')!='failed' or int(p.get('exit_code',0))==0 or p.get('code_sha')!=code or p.get('host')!=host or not re.fullmatch(pattern,str(p.get('job_id',''))):
 raise SystemExit('failed Scan resume identity/code/host/scope drift')
PY_RESUME_IDENTITY
  [ "$?" -eq 0 ] || die "failed $LABEL resume identity validation failed"
fi

reuse_shard(){
  local shard="$1" tag; printf -v tag '%02d' "$shard"
  [ -n "${SCORE_RESUME_PREFIX:-}" ] || return 1
  [ -f "$W/resume-inventory.json" ] || die "resume inventory absent"
  if ! python3 - "$W/resume-inventory.json" "$LABEL" "$tag" <<'PY_HAS_SHARD'
import json,sys
label,tag=sys.argv[2:4]; paths={str(x.get('path','')) for x in json.load(open(sys.argv[1])).get('files',[]) if isinstance(x,dict)}
raise SystemExit(0 if f'artefacts/scores/{label}-shard-{tag}-manifest.json' in paths else 1)
PY_HAS_SHARD
  then
    return 1
  fi
  rclone copyto "$SCORE_RESUME_PREFIX/artefacts/scores/$LABEL-shard-$tag-manifest.json" \
    "$SCORES/$LABEL-shard-$tag-manifest.json" >"$W/resume-$tag.log" 2>&1 \
    || die "cannot restore immutable $LABEL shard manifest $tag"
  for name in scores.tsv.gz report.json; do
    rclone copyto "$SCORE_RESUME_PREFIX/artefacts/scores/$LABEL-shard-$tag-$name" \
      "$SCORES/$LABEL-shard-$tag-$name" >>"$W/resume-$tag.log" 2>&1 || die "partial resumed shard $tag"
  done
  python3 - "$SCORES" "$LABEL" "$tag" "$PLAN_JSON" "$W/resume-inventory.json" \
    "$IN/selection-report.json" "$W/scan-runtime/scan_home" <<'PY_REUSE'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); label,tag=sys.argv[2:4]; plan,inventory,selection,scan=map(Path,sys.argv[4:8]); m=json.loads((root/f'{label}-shard-{tag}-manifest.json').read_text()); p=json.loads(plan.read_text()); r=json.loads((root/f'{label}-shard-{tag}-report.json').read_text()); sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
remote={x['path']:x for x in json.loads(inventory.read_text())['files']}
for suffix in ('manifest.json','scores.tsv.gz','report.json'):
 name=f'{label}-shard-{tag}-{suffix}'; item=remote.get(f'artefacts/scores/{name}'); local=root/name
 if item is None or sha(local)!=item['sha256'] or local.stat().st_size!=item['size_bytes']:
  raise SystemExit(f'resume inventory authentication drift: {name}')
cohort=json.loads(selection.read_text())['cohort_identity_sha256']
want=p['budgets_nodes']; planned=p['shards'][int(tag)]
if m.get('schema')!='jass.scan_ceiling_scan_score_shard.v1' or m.get('scope')!=label or m.get('shard')!=int(tag) or m.get('nshards')!=16 or m.get('budgets_nodes')!=want or m.get('processed_rows')!=planned['selected_rows']: raise SystemExit('resume shard scope/coverage drift')
if m.get('groups_sha256')!=p['groups_sha256'] or m.get('row_ids_sha256')!=p['row_ids_sha256'] or m.get('timeout_plan_sha256')!=sha(plan) or m.get('cohort_identity_sha256')!=cohort or m.get('scan_binary_sha256')!=sha(scan): raise SystemExit('resume input/timeout/cohort/Scan drift')
if r.get('schema')!='jass.scan_ceiling_scan_ladder.v1' or r.get('shard')!=int(tag) or r.get('nshards')!=16 or r.get('budgets_nodes')!=want or r.get('processed_rows')!=planned['selected_rows'] or r.get('scan_binary_sha256')!=sha(scan): raise SystemExit('resume report scope/coverage/binary drift')
for name,want in m['files_sha256'].items():
 if sha(root/name)!=want: raise SystemExit(f'resume SHA drift: {name}')
PY_REUSE
  [ "$?" -eq 0 ] || die "resumed $LABEL shard validation failed: $tag"
}

score_shard(){
  local shard="$1" tag out report shard_timeout; printf -v tag '%02d' "$shard"
  out="$W/$LABEL-shard-$tag.tsv"; report="$SCORES/$LABEL-shard-$tag-report.json"
  shard_timeout=$(awk -F '\t' -v target="$shard" 'NR>1 && $1==target {print $6}' "$PLAN_TSV")
  [[ "$shard_timeout" =~ ^[0-9]+$ ]] || die "missing timeout for $LABEL shard $shard"
  timeout -k 120s "${shard_timeout}s" \
    python3 jobs/tools/scan_ceiling_scan_score.py --scan "$W/scan-runtime/scan_home" \
      --children "$W/children.jnnw" --groups "$IN/siblings.tsv" --budgets "$BUDGETS" \
      --row-ids "$ROW_ARG" --shard "$shard" --nshards "$NSHARDS" \
      --timeout-seconds "$PER_SEARCH_TIMEOUT" --output "$out" --report "$report" \
      --source-commit "$SCAN_COMMIT" >"$W/$LABEL-shard-$tag.log" 2>&1
  gzip -n -c "$out" >"$SCORES/.$LABEL-shard-$tag-scores.tsv.gz.tmp"
  mv "$SCORES/.$LABEL-shard-$tag-scores.tsv.gz.tmp" "$SCORES/$LABEL-shard-$tag-scores.tsv.gz"
  python3 - "$SCORES" "$LABEL" "$tag" "$BUDGETS" "$report" "$PLAN_JSON" \
    "$IN/selection-report.json" <<'PY_SHARD'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); label,tag,budgets=sys.argv[2:5]; report,plan_path,selection=map(Path,sys.argv[5:8]); r=json.loads(report.read_text()); plan=json.loads(plan_path.read_text()); planned=plan['shards'][int(tag)]; want=[int(x) for x in budgets.split(',')]; cohort=json.loads(selection.read_text())['cohort_identity_sha256']
if r.get('schema')!='jass.scan_ceiling_scan_ladder.v1' or r.get('budgets_nodes')!=want: raise SystemExit('Scan report ladder drift')
if r.get('source_commit')!='7aae17e7b7bfc47744601afb1ee7655e18983ce5' or r.get('mode')!='go analyze': raise SystemExit('Scan provenance/mode drift')
expected_bounds={str(n):((n+15)//16)*16 for n in want}
if r.get('requested_nodes_exactly_configured') is not True or r.get('scan_source_algorithms_modified') is not False or r.get('node_poll_quantum')!=16 or r.get('last_info_snapshot_upper_bound_by_budget')!=expected_bounds: raise SystemExit('Scan requested-node/poll contract drift')
if r.get('book_enabled') is not False or r.get('threads_per_search')!=1 or r.get('bb_size')!=0 or r.get('fresh_state')!='new-game before every sibling/budget': raise SystemExit('Scan runtime drift')
if r.get('shard')!=int(tag) or r.get('nshards')!=16 or r.get('processed_rows')!=planned['selected_rows'] or r.get('output_rows')!=planned['selected_rows']*len(want) or r.get('searches')!=planned['searched_rows']*len(want) or r.get('terminal_exact_output_rows')!=(planned['selected_rows']-planned['searched_rows'])*len(want): raise SystemExit('Scan shard coverage drift')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest(); names=[f'{label}-shard-{tag}-scores.tsv.gz',f'{label}-shard-{tag}-report.json']
payload={'schema':'jass.scan_ceiling_scan_score_shard.v1','immutable':True,'benchmark_only':True,
 'training_allowed':False,'tuning_allowed':False,'calibration_allowed':False,
 'model_selection_allowed':False,'runtime_scale_selection_allowed':False,
 'scope':label,'shard':int(tag),'nshards':16,'budgets_nodes':want,'processed_rows':r['processed_rows'],
 'cohort_identity_sha256':cohort,
 'groups_sha256':plan['groups_sha256'],'row_ids_sha256':plan['row_ids_sha256'],
 'planned_requested_nodes':planned['requested_nodes'],'timeout_seconds':planned['timeout_seconds'],
 'timeout_plan_sha256':sha(plan_path),
 'scan_binary_sha256':r['scan_binary_sha256'],'files_sha256':{n:sha(root/n) for n in names}}
tmp=root/f'.{label}-shard-{tag}-manifest.json.tmp'; tmp.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n'); tmp.replace(root/f'{label}-shard-{tag}-manifest.json')
PY_SHARD
}

stage official-scan-score-or-resume-sixteen-shards
failed=0
for wave_start in 0 15; do
  wave_end=$((wave_start+MAX_WORKERS-1)); [ "$wave_end" -lt "$NSHARDS" ] || wave_end=$((NSHARDS-1))
  pids=(); shards=()
  for shard in $(seq "$wave_start" "$wave_end"); do
    if reuse_shard "$shard"; then say "  reused $LABEL shard $shard"; continue; fi
    (score_shard "$shard") & pids+=("$!"); shards+=("$shard")
  done
  for index in "${!pids[@]}"; do
    if wait "${pids[$index]}"; then rc=0; else rc=$?; fi
    say "  scored scope=$LABEL shard=${shards[$index]} rc=$rc"
    [ "$rc" -eq 0 ] || failed=$((failed+1))
  done
done
[ "$failed" -eq 0 ] || die "$failed $LABEL shard(s) failed; retry with SCORE_RESUME_PREFIX"
[ "$(find "$SCORES" -name "$LABEL-shard-*-manifest.json" -type f | wc -l)" -eq 16 ] || die "score shard manifest count drift"

stage immutable-stage-manifest-and-summary
python3 - "$SCORES" "$ART/$LABEL-stage-manifest.json" "$LABEL" "$BUDGETS" "$IN/selection-report.json" "$W/scan-runtime/scan_home" "$PLAN_JSON" "$EXPECTED_CODE_SHA" "$FROZEN_COHORT_CODE_SHA" <<'PY_STAGE'
import hashlib,json,sys
from pathlib import Path
root,out=map(Path,sys.argv[1:3]); label,budgets=sys.argv[3:5]; selection,scan,plan=map(Path,sys.argv[5:8]); code,frozen_code=sys.argv[8:]; sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest(); files=sorted(root.glob(f'{label}-shard-*-manifest.json')); s=json.loads(selection.read_text()); plan_payload=json.loads(plan.read_text()); want=[int(x) for x in budgets.split(',')]
if len(files)!=16: raise SystemExit('Scan stage shard count drift')
for index,path in enumerate(files):
 item=json.loads(path.read_text())
 if item.get('scope')!=label or item.get('shard')!=index or item.get('nshards')!=16 or item.get('budgets_nodes')!=want or item.get('cohort_identity_sha256')!=s['cohort_identity_sha256'] or item.get('scan_binary_sha256')!=sha(scan) or item.get('groups_sha256')!=plan_payload['groups_sha256'] or item.get('row_ids_sha256')!=plan_payload['row_ids_sha256'] or item.get('timeout_plan_sha256')!=sha(plan):
  raise SystemExit(f'Scan stage shard semantic drift: {path.name}')
payload={'schema':'jass.scan_ceiling_scan_score_stage.v1','immutable':True,'benchmark_only':True,
 'code_sha':code,'frozen_cohort_code_sha':frozen_code,
 'training_allowed':False,'tuning_allowed':False,'calibration_allowed':False,
 'model_selection_allowed':False,'runtime_scale_selection_allowed':False,
 'scope':label,'budgets_nodes':want,'shards':16,
 'cohort_identity_sha256':s['cohort_identity_sha256'],'scan_binary_sha256':sha(scan),
 'timeout_plan_sha256':sha(plan),'timeout_plan':json.loads(plan.read_text()),
 'manifests':[{'name':p.name,'sha256':sha(p),'payload':json.loads(p.read_text())} for p in files],
 'guards':{'fits':0,'calibrations':0,'strength_games':0,'promotions':0,'promotion_authorized':False}}
out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY_STAGE
python3 - "$ART/JASS_CONTROL_SUMMARY.json" "$ART/$LABEL-stage-manifest.json" "$EXPECTED_CODE_SHA" "$FROZEN_COHORT_CODE_SHA" <<'PY_SUMMARY'
import hashlib,json,sys
from pathlib import Path
out,stage=map(Path,sys.argv[1:3]); code,frozen_code=sys.argv[3:]; p=json.loads(stage.read_text()); sha=lambda x:hashlib.sha256(x.read_bytes()).hexdigest()
if p.get('code_sha')!=code or p.get('frozen_cohort_code_sha')!=frozen_code: raise SystemExit('Scan stage code provenance drift')
summary={'schema':'jass.scan_ceiling_scan_stage_summary.v1','verdict':'SCAN_'+p['scope'].upper().replace('-','_')+'_COMPLETE',
 'passed':True,'benchmark_only':True,'code_sha':code,'frozen_cohort_code_sha':frozen_code,
 'scope':p['scope'],'budgets_nodes':p['budgets_nodes'],
 'cohort_identity_sha256':p['cohort_identity_sha256'],'scan_binary_sha256':p['scan_binary_sha256'],
 'stage_manifest_sha256':sha(stage),'guards':p['guards']}
summary.update({'cohort_and_scores_consumed':True,'training_allowed':False,'tuning_allowed':False,
 'calibration_allowed':False,'model_selection_allowed':False,'runtime_scale_selection_allowed':False})
out.write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
PY_SUMMARY
VERDICT="SCAN_${LABEL^^}_COMPLETE"; VERDICT="${VERDICT//-/_}"
: >"$ART/VERDICT__$VERDICT"; : >"$ART/SCAN_BENCHMARK_ONLY__TRUE"; : >"$ART/STRENGTH_GAMES__0"
: >"$ART/COHORT_CONSUMED__TRUE"
printf 'PROMOTION_AUTHORIZED__FALSE\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"; printf 'AUTOMATIC_NEXT_JOB__NULL\n' >"$ART/AUTOMATIC_NEXT_JOB__NULL"
say "$VERDICT budgets=$BUDGETS shards=16 source=$SCAN_COMMIT"

#!/usr/bin/env bash
# HOME-only resumable Jass exact-node ladder for BASE2000 or DEEP512.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_HOST:?}"; : "${SELECTION_PREFIX:?}"; : "${PREFLIGHT_PREFIX:?}"
: "${SCORE_SCOPE:?base or deep}"; : "${FULL_RUN_APPROVED:?}"; : "${SCIENTIFIC_GO:?}"
export SCAN_BENCHMARK_ONLY=true
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
NSHARDS=16
MAX_WORKERS=15

case "$SCORE_SCOPE" in
  base) BUDGETS="1000,5000,50000,200000"; LABEL="jass-base"; ROW_FILE="-";;
  deep) BUDGETS="1000000"; LABEL="jass-deep"; ROW_FILE="deep512-row-ids.txt";;
  *) echo "invalid SCORE_SCOPE=$SCORE_SCOPE" >&2; exit 2;;
esac

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"; SCORES="$ART/scores"
mkdir -p "$W" "$IN" "$ART" "$SCORES"
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
[[ "$JASS_JOB_ID" =~ ^home-[0-9]+-l3-scan-ceiling-jass-(base|deep)-v1$ ]] || die "HOME job nomenclature drift"
[[ "$JASS_JOB_ID" == *"-jass-$SCORE_SCOPE-v1" ]] || die "job/scope mismatch"
[ "$(hostname)" = "$EXPECTED_HOST" ] || die "HOME host mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "dirty/non-detached worktree"
[ "$(nproc)" -eq 16 ] || die "HOME 16-CPU contract mismatch"
[ "$FULL_RUN_APPROVED" = 1 ] && [ "$SCIENTIFIC_GO" = 1 ] || die "execution GO missing"
for command in timeout df; do command -v "$command" >/dev/null || die "$command missing"; done
unset JASS_TB_MOVE_ORDER_POLICY JASS_DSSD_MOVE_ORDER_POLICY JASS_T3_F6_MODEL
monitor

stage fetch-authenticate-frozen-cohort-and-jass-runtime
python3 jobs/tools/fetch_result_files.py --prefix "$SELECTION_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=selection-summary.json \
  --file artefacts/selection-report.json=selection-report.json \
  --file artefacts/sibling-manifest.json=sibling-manifest.json \
  --file artefacts/children.jnnw.gz=children.jnnw.gz \
  --file artefacts/siblings.tsv=siblings.tsv \
  --file artefacts/deep512-row-ids.txt=deep512-row-ids.txt \
  --out-dir "$IN" --report "$ART/verified-selection.json" >"$W/fetch-selection.log" 2>&1 \
  || die "selection fetch failed"
python3 jobs/tools/fetch_result_files.py --prefix "$PREFLIGHT_PREFIX" \
  --file artefacts/scan-technical-preflight.json=scan-technical-preflight.json \
  --file artefacts/runtime-payload-manifest.json=runtime-payload-manifest.json \
  --file artefacts/jass-search-ladder.gz=jass-search-ladder.gz \
  --file artefacts/curriculum.pjtw=curriculum.pjtw \
  --out-dir "$IN" --report "$ART/verified-preflight.json" >"$W/fetch-preflight.log" 2>&1 \
  || die "preflight runtime fetch failed"
gunzip -t "$IN/children.jnnw.gz"; gunzip -c "$IN/children.jnnw.gz" >"$W/children.jnnw"
gunzip -t "$IN/jass-search-ladder.gz"; gunzip -c "$IN/jass-search-ladder.gz" >"$W/jass-search-ladder"; chmod 0555 "$W/jass-search-ladder"
python3 - "$IN" "$W/children.jnnw" "$ART/verified-selection.json" "$ART/verified-preflight.json" "$EXPECTED_CODE_SHA" "$CURRICULUM_SHA" <<'PY_AUTH'
import hashlib,json,sys
from pathlib import Path
root,children=map(Path,sys.argv[1:3]); sr,pr=map(lambda p:json.load(open(p)),sys.argv[3:5]); code,curr=sys.argv[5:]
sel=json.loads((root/'selection-summary.json').read_text()); selection=json.loads((root/'selection-report.json').read_text()); siblings=json.loads((root/'sibling-manifest.json').read_text()); pre=json.loads((root/'scan-technical-preflight.json').read_text()); sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
if any(r.get('code_sha')!=code or r.get('result_state')!='completed' or r.get('exit_code')!=0 for r in (sr,pr)): raise SystemExit('upstream result/code drift')
if sel.get('verdict')!='SCAN_COHORT_FROZEN_BENCHMARK_ONLY' or not sel.get('passed'): raise SystemExit('selection not frozen')
if any(sel.get(name) is not False for name in ('training_allowed','tuning_allowed','calibration_allowed','model_selection_allowed','runtime_scale_selection_allowed')): raise SystemExit('selection quarantine drift')
if selection.get('cohort_identity_sha256')!=sel.get('cohort_identity_sha256') or sel.get('selection_report_sha256')!=sha(root/'selection-report.json') or sel.get('sibling_manifest_sha256')!=sha(root/'sibling-manifest.json') or len(str(sel.get('sibling_export_stage_manifest_sha256','')))!=64: raise SystemExit('selection manifest chain drift')
if siblings.get('children_sha256')!=sha(children) or siblings.get('groups_sha256')!=sha(root/'siblings.tsv') or siblings.get('deep_row_ids_sha256')!=sha(root/'deep512-row-ids.txt'): raise SystemExit('sibling payload hash drift')
if pre.get('verdict')!='SCAN_MAPPING_TECHNICAL_PASS' or not pre.get('passed'): raise SystemExit('preflight not passed')
if sha(root/'curriculum.pjtw')!=curr: raise SystemExit('CURRICULUM SHA drift')
payload=json.loads((root/'runtime-payload-manifest.json').read_text())['files']['jass-search-ladder.gz']['sha256']
if sha(root/'jass-search-ladder.gz')!=payload: raise SystemExit('Jass ladder payload drift')
PY_AUTH

stage locate-real-home-egdb
EGDIR=""
for directory in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$directory"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$directory"; break; }
done
[ -n "$EGDIR" ] || die "real HOME EGDB unavailable"
ROW_ARG="$ROW_FILE"; [ "$ROW_ARG" = - ] || ROW_ARG="$IN/$ROW_ARG"

stage derive-publish-per-shard-timeouts-from-home-preflight-rate
PLAN_JSON="$ART/$LABEL-shard-timeout-plan.json"
PLAN_TSV="$W/$LABEL-shard-timeout-plan.tsv"
python3 jobs/tools/scan_ceiling_shard_timeouts.py \
  --preflight "$IN/scan-technical-preflight.json" --groups "$IN/siblings.tsv" \
  --row-ids "$ROW_ARG" --engine Jass --budgets "$BUDGETS" --nshards "$NSHARDS" \
  --output-json "$PLAN_JSON" --output-tsv "$PLAN_TSV"
python3 - "$PLAN_JSON" <<'PY_PLAN' | tee -a "$RES" "$W/rate-plan-progress.txt"
import json,sys
p=json.load(open(sys.argv[1]))
print(f"rate_engine=Jass")
print(f"rate_requested_nodes_per_second={p['smoke_requested_nodes_per_second']:.3f}")
print(f"planned_requested_nodes={p['requested_nodes']}")
print(f"planned_healthy_eta_seconds={p['stage_healthy_eta_seconds']:.1f}")
print(f"planned_timeout_ceiling_seconds={p['stage_timeout_ceiling_seconds']:.1f}")
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
pattern=rf'home-[0-9]+-l3-scan-ceiling-jass-{re.escape(scope)}-v1'
if p.get('state')!='verified' or p.get('result_state')!='failed' or int(p.get('exit_code',0))==0 or p.get('code_sha')!=code or p.get('host')!=host or not re.fullmatch(pattern,str(p.get('job_id',''))):
 raise SystemExit('failed Jass resume identity/code/host/scope drift')
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
    "$IN/selection-report.json" "$IN/curriculum.pjtw" <<'PY_REUSE'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); label,tag=sys.argv[2:4]; plan,inventory,selection,curriculum=map(Path,sys.argv[4:8]); m=json.loads((root/f'{label}-shard-{tag}-manifest.json').read_text()); p=json.loads(plan.read_text()); r=json.loads((root/f'{label}-shard-{tag}-report.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
remote={x['path']:x for x in json.loads(inventory.read_text())['files']}
for suffix in ('manifest.json','scores.tsv.gz','report.json'):
 name=f'{label}-shard-{tag}-{suffix}'; item=remote.get(f'artefacts/scores/{name}'); local=root/name
 if item is None or sha(local)!=item['sha256'] or local.stat().st_size!=item['size_bytes']:
  raise SystemExit(f'resume inventory authentication drift: {name}')
cohort=json.loads(selection.read_text())['cohort_identity_sha256']
want=p['budgets_nodes']; planned=p['shards'][int(tag)]
if m.get('schema')!='jass.scan_ceiling_jass_score_shard.v1' or m.get('scope')!=label or m.get('shard')!=int(tag) or m.get('nshards')!=16 or m.get('budgets_nodes')!=want or m.get('processed_rows')!=planned['selected_rows']: raise SystemExit('resume shard scope/coverage drift')
if m.get('groups_sha256')!=p['groups_sha256'] or m.get('row_ids_sha256')!=p['row_ids_sha256'] or m.get('timeout_plan_sha256')!=sha(plan) or m.get('cohort_identity_sha256')!=cohort or m.get('curriculum_sha256')!=sha(curriculum): raise SystemExit('resume input/timeout/cohort/evaluator drift')
if r.get('schema')!='jass.scan_ceiling_jass_ladder.v1' or r.get('shard')!=int(tag) or r.get('nshards')!=16 or r.get('budgets_nodes')!=want or r.get('processed_rows')!=planned['selected_rows'] or r.get('invalid_rows')!=0: raise SystemExit('resume report scope/coverage drift')
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
    "$W/jass-search-ladder" "$W/children.jnnw" "$IN/siblings.tsv" "$out" "$report" \
    "$IN/curriculum.pjtw" "$EGDIR" "$BUDGETS" "$ROW_ARG" "$shard" "$NSHARDS" 16 256 \
    >"$W/$LABEL-shard-$tag.log" 2>&1
  gzip -n -c "$out" >"$SCORES/.$LABEL-shard-$tag-scores.tsv.gz.tmp"
  mv "$SCORES/.$LABEL-shard-$tag-scores.tsv.gz.tmp" "$SCORES/$LABEL-shard-$tag-scores.tsv.gz"
  python3 - "$SCORES" "$LABEL" "$tag" "$BUDGETS" "$report" "$PLAN_JSON" \
    "$IN/selection-report.json" "$IN/curriculum.pjtw" <<'PY_SHARD'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); label,tag,budgets=sys.argv[2:5]; report,plan_path,selection,curriculum=map(Path,sys.argv[5:9]); r=json.loads(report.read_text()); plan=json.loads(plan_path.read_text()); planned=plan['shards'][int(tag)]; cohort=json.loads(selection.read_text())['cohort_identity_sha256']
want=[int(x) for x in budgets.split(',')];
if r.get('schema')!='jass.scan_ceiling_jass_ladder.v1' or r.get('budgets_nodes')!=want: raise SystemExit('Jass report ladder drift')
if r.get('node_limit_mode')!='exact' or r.get('requested_node_caps_exactly_configured') is not True or r.get('node_stopped_rows_equal_requested') is not True or r.get('max_depth_exhaustion_allowed') is not True or r.get('max_ply')!=64: raise SystemExit('Jass node-cap contract drift')
if r.get('score_pov')!='parent' or r.get('child_to_parent_sign_validated') is not True: raise SystemExit('Jass POV contract drift')
if r.get('book_enabled') is not False or r.get('threads_per_search')!=1 or r.get('fresh_engine_tt_search_state_each_sibling_budget') is not True or r.get('tt_mb')!=16: raise SystemExit('Jass runtime drift')
if r.get('shard')!=int(tag) or r.get('nshards')!=16 or r.get('processed_rows')!=planned['selected_rows'] or r.get('invalid_rows')!=0: raise SystemExit('Jass shard coverage drift')
for budget in want:
 item=r['by_budget'][str(budget)]
 if item['searches']!=planned['searched_rows'] or item['searches']+item['terminal_exact_rows']+item['tb_exact_rows']!=planned['selected_rows'] or item['exact_budget_rows']+item['max_depth_exhausted_rows']!=item['searches'] or item['nodes']>item['searches']*budget or (item['searches'] and item['nodes']<=0):
  raise SystemExit(f'Jass budget receipt drift: {budget}')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest(); names=[f'{label}-shard-{tag}-scores.tsv.gz',f'{label}-shard-{tag}-report.json']
payload={'schema':'jass.scan_ceiling_jass_score_shard.v1','immutable':True,'benchmark_only':True,
 'training_allowed':False,'tuning_allowed':False,'calibration_allowed':False,
 'model_selection_allowed':False,'runtime_scale_selection_allowed':False,
 'scope':label,'shard':int(tag),'nshards':16,'budgets_nodes':want,'processed_rows':r['processed_rows'],
 'cohort_identity_sha256':cohort,'curriculum_sha256':sha(curriculum),
 'groups_sha256':plan['groups_sha256'],'row_ids_sha256':plan['row_ids_sha256'],
 'planned_requested_nodes':planned['requested_nodes'],'timeout_seconds':planned['timeout_seconds'],
 'timeout_plan_sha256':sha(plan_path),
 'files_sha256':{n:sha(root/n) for n in names}}
tmp=root/f'.{label}-shard-{tag}-manifest.json.tmp'; tmp.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n'); tmp.replace(root/f'{label}-shard-{tag}-manifest.json')
PY_SHARD
}

stage exact-node-score-or-resume-sixteen-shards
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
python3 - "$SCORES" "$ART/$LABEL-stage-manifest.json" "$LABEL" "$BUDGETS" "$IN/selection-report.json" "$IN/curriculum.pjtw" "$PLAN_JSON" <<'PY_STAGE'
import hashlib,json,sys
from pathlib import Path
root,out=map(Path,sys.argv[1:3]); label,budgets=sys.argv[3:5]; selection,curr,plan=map(Path,sys.argv[5:8])
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest(); files=sorted(root.glob(f'{label}-shard-*-manifest.json')); s=json.loads(selection.read_text()); plan_payload=json.loads(plan.read_text()); want=[int(x) for x in budgets.split(',')]
if len(files)!=16: raise SystemExit('Jass stage shard count drift')
for index,path in enumerate(files):
 item=json.loads(path.read_text())
 if item.get('scope')!=label or item.get('shard')!=index or item.get('nshards')!=16 or item.get('budgets_nodes')!=want or item.get('cohort_identity_sha256')!=s['cohort_identity_sha256'] or item.get('curriculum_sha256')!=sha(curr) or item.get('groups_sha256')!=plan_payload['groups_sha256'] or item.get('row_ids_sha256')!=plan_payload['row_ids_sha256'] or item.get('timeout_plan_sha256')!=sha(plan):
  raise SystemExit(f'Jass stage shard semantic drift: {path.name}')
payload={'schema':'jass.scan_ceiling_jass_score_stage.v1','immutable':True,'benchmark_only':True,
 'training_allowed':False,'tuning_allowed':False,'calibration_allowed':False,
 'model_selection_allowed':False,'runtime_scale_selection_allowed':False,
 'scope':label,'budgets_nodes':want,'shards':16,
 'cohort_identity_sha256':s['cohort_identity_sha256'],'curriculum_sha256':sha(curr),
 'timeout_plan_sha256':sha(plan),'timeout_plan':json.loads(plan.read_text()),
 'manifests':[{'name':p.name,'sha256':sha(p),'payload':json.loads(p.read_text())} for p in files],
 'guards':{'fits':0,'calibrations':0,'strength_games':0,'promotions':0,'promotion_authorized':False}}
out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY_STAGE
python3 - "$ART/JASS_CONTROL_SUMMARY.json" "$ART/$LABEL-stage-manifest.json" "$EXPECTED_CODE_SHA" <<'PY_SUMMARY'
import hashlib,json,sys
from pathlib import Path
out,stage=map(Path,sys.argv[1:3]); code=sys.argv[3]; p=json.loads(stage.read_text()); sha=lambda x:hashlib.sha256(x.read_bytes()).hexdigest()
summary={'schema':'jass.scan_ceiling_jass_stage_summary.v1','verdict':'SCAN_'+p['scope'].upper().replace('-','_')+'_COMPLETE',
 'passed':True,'benchmark_only':True,'code_sha':code,'scope':p['scope'],'budgets_nodes':p['budgets_nodes'],
 'cohort_identity_sha256':p['cohort_identity_sha256'],'stage_manifest_sha256':sha(stage),'guards':p['guards']}
summary.update({'cohort_and_scores_consumed':True,'training_allowed':False,'tuning_allowed':False,
 'calibration_allowed':False,'model_selection_allowed':False,'runtime_scale_selection_allowed':False})
out.write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
PY_SUMMARY
VERDICT="SCAN_${LABEL^^}_COMPLETE"; VERDICT="${VERDICT//-/_}"
: >"$ART/VERDICT__$VERDICT"; : >"$ART/SCAN_BENCHMARK_ONLY__TRUE"; : >"$ART/STRENGTH_GAMES__0"
: >"$ART/COHORT_CONSUMED__TRUE"
printf 'PROMOTION_AUTHORIZED__FALSE\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"; printf 'AUTOMATIC_NEXT_JOB__NULL\n' >"$ART/AUTOMATIC_NEXT_JOB__NULL"
say "$VERDICT budgets=$BUDGETS shards=16 fits=0 games=0"

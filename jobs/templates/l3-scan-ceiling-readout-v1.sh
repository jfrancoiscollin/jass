#!/usr/bin/env bash
# HOME-only terminal scientific readout of immutable benchmark-only score shards.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_HOST:?}"
: "${SELECTION_PREFIX:?}"; : "${PREFLIGHT_PREFIX:?}"; : "${STATIC_PREFIX:?}"
: "${JASS_BASE_PREFIX:?}"; : "${JASS_DEEP_PREFIX:?}"
: "${SCAN_BASE_PREFIX:?}"; : "${SCAN_DEEP_PREFIX:?}"; : "${SCAN_ULTRA_PREFIX:?}"
: "${FULL_RUN_APPROVED:?}"; : "${SCIENTIFIC_GO:?}"
export SCAN_BENCHMARK_ONLY=true
BOOTSTRAP=200000
BOOTSTRAP_SEED=2026091303

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }; die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }

DFA=$(df -Pm /root | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 3000 ] || { say "ABORT disque HOME <3Go"; exit 3; }
say "disk_free_mb=$DFA"

MON=""
monitor(){ (t0=$(date +%s); while true; do { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%FT%T%z')"; printf 'phase=%s\n' "$(cat "$STAGE")"; printf 'elapsed_min=%d\n' "$((($(date +%s)-t0)/60))"; printf 'bootstrap_samples=%d\n' "$BOOTSTRAP"; } >"$PROG.tmp"; mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 120; done) & MON="$!"; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e; [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true; [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"; (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^home-[0-9]+-l3-scan-ceiling-readout-v1$ ]] || die "HOME job nomenclature drift"
[ "$(hostname)" = "$EXPECTED_HOST" ] || die "HOME host mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "dirty/non-detached worktree"
[ "$(nproc)" -eq 16 ] || die "HOME 16-CPU contract mismatch"
[ "$FULL_RUN_APPROVED" = 1 ] && [ "$SCIENTIFIC_GO" = 1 ] || die "execution GO missing"
command -v df >/dev/null || die "df missing"
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
[ -f "$VENV/.jass-runtime-ready-v1" ] || die "numeric runtime absent"
PY="$VENV/bin/python"; "$PY" -c 'import numpy; assert numpy.__version__'
unset JASS_TB_MOVE_ORDER_POLICY JASS_DSSD_MOVE_ORDER_POLICY JASS_T3_F6_MODEL
monitor

stage fetch-authenticate-core-freezes
python3 jobs/tools/fetch_result_files.py --prefix "$SELECTION_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=selection-summary.json \
  --file artefacts/selection-report.json=selection-report.json \
  --file artefacts/sibling-manifest.json=sibling-manifest.json \
  --file artefacts/cohort-freeze-before-score.json=cohort-freeze-before-score.json \
  --file artefacts/runtime-exclusion-snapshot.json=runtime-exclusion-snapshot.json \
  --file artefacts/source-stage-manifest.json=source-stage-manifest.json \
  --file artefacts/sibling-export-stage-manifest.json=sibling-export-stage-manifest.json \
  --file artefacts/selection-timeout-plan.json=selection-timeout-plan.json \
  --file artefacts/siblings.tsv=siblings.tsv \
  --file artefacts/deep512-row-ids.txt=deep512-row-ids.txt \
  --file artefacts/ultra256-row-ids.txt=ultra256-row-ids.txt \
  --out-dir "$IN" --report "$ART/verified-selection.json" >"$W/fetch-selection.log" 2>&1 || die "selection fetch failed"
python3 jobs/tools/fetch_result_files.py --prefix "$PREFLIGHT_PREFIX" \
  --file artefacts/scan-technical-preflight.json=scan-technical-preflight.json \
  --out-dir "$IN" --report "$ART/verified-preflight.json" >"$W/fetch-preflight.log" 2>&1 || die "preflight fetch failed"
python3 jobs/tools/fetch_result_files.py --prefix "$STATIC_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=static-summary.json \
  --file artefacts/static-score-report.json=static-score-report.json \
  --file artefacts/static-scores.tsv=static-scores.tsv \
  --out-dir "$IN" --report "$ART/verified-static.json" >"$W/fetch-static.log" 2>&1 || die "static fetch failed"

fetch_stage(){
  local prefix="$1" label="$2" manifest="$3" log="$4"; local args=()
  args+=(--file "artefacts/JASS_CONTROL_SUMMARY.json=$label-summary.json")
  args+=(--file "artefacts/$manifest=$manifest")
  args+=(--file "artefacts/$label-shard-timeout-plan.json=$label-shard-timeout-plan.json")
  for shard in $(seq 0 15); do
    printf -v tag '%02d' "$shard"
    args+=(--file "artefacts/scores/$label-shard-$tag-scores.tsv.gz=$label-$tag.tsv.gz")
  done
  python3 jobs/tools/fetch_result_files.py --prefix "$prefix" "${args[@]}" \
    --out-dir "$IN" --report "$ART/verified-$label.json" >"$W/$log" 2>&1 \
    || die "$label stage fetch failed"
}
stage fetch-all-immutable-score-shards
fetch_stage "$JASS_BASE_PREFIX" jass-base jass-base-stage-manifest.json fetch-jass-base.log
fetch_stage "$JASS_DEEP_PREFIX" jass-deep jass-deep-stage-manifest.json fetch-jass-deep.log
fetch_stage "$SCAN_BASE_PREFIX" scan-base scan-base-stage-manifest.json fetch-scan-base.log
fetch_stage "$SCAN_DEEP_PREFIX" scan-deep scan-deep-stage-manifest.json fetch-scan-deep.log
fetch_stage "$SCAN_ULTRA_PREFIX" scan-ultra scan-ultra-stage-manifest.json fetch-scan-ultra.log

stage validate-shard-hashes-cardinalities-and-guards
"$PY" - "$IN" "$ART" "$EXPECTED_CODE_SHA" <<'PY_AUTH'
import hashlib,json,sys
from pathlib import Path
root,art=map(Path,sys.argv[1:3]); code=sys.argv[3]; sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
policy=('training_allowed','tuning_allowed','calibration_allowed','model_selection_allowed','runtime_scale_selection_allowed')
def policy_ok(payload): return all(payload.get(name) is False for name in policy)
sel=json.loads((root/'selection-summary.json').read_text()); cohort=sel['cohort_identity_sha256']
if sel.get('verdict')!='SCAN_COHORT_FROZEN_BENCHMARK_ONLY' or not sel.get('passed') or not policy_ok(sel): raise SystemExit('selection not frozen/quarantined')
selection=root/'selection-report.json'; sibling=root/'sibling-manifest.json'; freeze=root/'cohort-freeze-before-score.json'; runtime_snapshot=root/'runtime-exclusion-snapshot.json'; source_stage=root/'source-stage-manifest.json'; export_stage=root/'sibling-export-stage-manifest.json'; selection_plan=root/'selection-timeout-plan.json'
if sel.get('selection_report_sha256')!=sha(selection) or sel.get('sibling_manifest_sha256')!=sha(sibling) or sel.get('freeze_receipt_sha256')!=sha(freeze) or sel.get('source_stage_manifest_sha256')!=sha(source_stage) or sel.get('sibling_export_stage_manifest_sha256')!=sha(export_stage) or sel.get('timeout_plan_sha256')!=sha(selection_plan): raise SystemExit('selection operational manifest drift')
selection_payload=json.loads(selection.read_text()); sibling_payload=json.loads(sibling.read_text()); freeze_payload=json.loads(freeze.read_text()); runtime_payload=json.loads(runtime_snapshot.read_text()); source_payload=json.loads(source_stage.read_text()); export_payload=json.loads(export_stage.read_text())
if selection_payload.get('cohort_identity_sha256')!=cohort or selection_payload.get('selected')!=2000 or selection_payload.get('deep512')!=512 or selection_payload.get('ultra256')!=256 or selection_payload.get('forbidden_overlap')!=0: raise SystemExit('selection cohort drift')
if freeze_payload.get('frozen_before_any_sibling_score') is not True or freeze_payload.get('cohort_identity_sha256')!=cohort or freeze_payload.get('selection_report_sha256')!=sha(selection) or freeze_payload.get('runtime_snapshot_sha256')!=sha(runtime_snapshot) or not policy_ok(freeze_payload): raise SystemExit('cohort freeze drift')
if runtime_payload.get('schema')!='jass.scan_ceiling_runtime_exclusion_snapshot.v1' or not isinstance(runtime_payload.get('control_plane_head'),str) or len(runtime_payload['control_plane_head'])!=40 or runtime_payload.get('observable_pool_artifacts')!=sum(len(x.get('observable_pool_artifacts_at_cutoff',[])) for x in runtime_payload.get('runtime_jobs',[])): raise SystemExit('runtime exclusion snapshot drift')
if sibling_payload.get('parents')!=2000 or sibling_payload.get('deep512_parents')!=512 or sibling_payload.get('ultra256_parents')!=256 or sibling_payload.get('ultra_strict_subset_of_deep') is not True or sibling_payload.get('groups_sha256')!=sha(root/'siblings.tsv') or sibling_payload.get('deep_row_ids_sha256')!=sha(root/'deep512-row-ids.txt') or sibling_payload.get('ultra_row_ids_sha256')!=sha(root/'ultra256-row-ids.txt') or not policy_ok(sibling_payload): raise SystemExit('sibling manifest/payload drift')
if source_payload.get('source_seed_base')!=2026091310 or source_payload.get('source_shards')!=16 or len(source_payload.get('manifests',[]))!=16 or source_payload.get('timeout_plan_sha256')!=sha(selection_plan) or not policy_ok(source_payload): raise SystemExit('source stage drift')
if export_payload.get('cohort_identity_sha256')!=cohort or export_payload.get('shards')!=16 or len(export_payload.get('manifests',[]))!=16 or export_payload.get('timeout_plan_sha256')!=sha(selection_plan) or not policy_ok(export_payload): raise SystemExit('sibling export stage drift')
for item in export_payload['manifests']:
 payload=item.get('payload',{})
 if payload.get('cohort_identity_sha256')!=cohort or payload.get('nshards')!=16 or not policy_ok(payload): raise SystemExit('sibling export shard policy/cohort drift')
selection_plan_payload=json.loads(selection_plan.read_text())
if selection_plan_payload.get('scientific_budgets_changed') is not False: raise SystemExit('selection timeout changed science')
pre=json.loads((root/'scan-technical-preflight.json').read_text())
if selection_plan_payload.get('preflight_report_sha256')!=sha(root/'scan-technical-preflight.json'): raise SystemExit('selection/preflight timeout chain drift')
if pre.get('verdict')!='SCAN_MAPPING_TECHNICAL_PASS' or not pre.get('passed') or pre.get('source_commit')!='7aae17e7b7bfc47744601afb1ee7655e18983ce5' or len(str(pre.get('scan_binary_sha256','')))!=64: raise SystemExit('preflight not passed/provenance drift')
static=json.loads((root/'static-summary.json').read_text()); static_report=json.loads((root/'static-score-report.json').read_text())
if static.get('verdict')!='SCAN_STATIC_SIGNALS_FROZEN' or not static.get('passed') or static.get('cohort_identity_sha256')!=cohort or static.get('cohort_and_scores_consumed') is not True or not policy_ok(static): raise SystemExit('static stage drift')
expected_artifacts={'curriculum':'319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1','d1':'e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49','rf1':'0d26ba50b668160b3da3e247cd4e1bd709c2cb7989b3b5877b9ea7deb34db58b','t3_a':'16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2'}
if static.get('report_sha256')!=sha(root/'static-score-report.json') or sha(root/'static-scores.tsv')!=static_report['output_sha256'] or static_report.get('groups_sha256')!=sha(root/'siblings.tsv') or static_report.get('artifacts')!=expected_artifacts or static_report.get('fits')!=0 or not policy_ok(static_report): raise SystemExit('static score hash/artifact/guard drift')
expected={
 'jass-base':('Jass',[1000,5000,50000,200000],None),
 'jass-deep':('Jass',[1000000],sha(root/'deep512-row-ids.txt')),
 'scan-base':('Scan',[1000,5000,50000,200000],None),
 'scan-deep':('Scan',[1000000,2000000],sha(root/'deep512-row-ids.txt')),
 'scan-ultra':('Scan',[5000000],sha(root/'ultra256-row-ids.txt')),
}
for label,(engine,budgets,row_ids_sha) in expected.items():
 receipt=json.loads((art/f'verified-{label}.json').read_text()); summary=json.loads((root/f'{label}-summary.json').read_text()); stage=json.loads((root/f'{label}-stage-manifest.json').read_text())
 if receipt.get('code_sha')!=code or receipt.get('result_state')!='completed' or receipt.get('exit_code')!=0: raise SystemExit(f'{label} result/code drift')
 if not summary.get('passed') or summary.get('cohort_identity_sha256')!=cohort or stage.get('cohort_identity_sha256')!=cohort or summary.get('stage_manifest_sha256')!=sha(root/f'{label}-stage-manifest.json') or summary.get('cohort_and_scores_consumed') is not True or not policy_ok(summary) or not policy_ok(stage): raise SystemExit(f'{label} cohort/manifest/quarantine drift')
 plan_path=root/f'{label}-shard-timeout-plan.json'; plan=json.loads(plan_path.read_text())
 if stage.get('scope')!=label or stage.get('budgets_nodes')!=budgets or plan.get('engine')!=engine or plan.get('budgets_nodes')!=budgets or plan.get('groups_sha256')!=sha(root/'siblings.tsv') or plan.get('row_ids_sha256')!=row_ids_sha: raise SystemExit(f'{label} scope/budget/input drift')
 if stage.get('timeout_plan_sha256')!=sha(plan_path) or stage.get('timeout_plan')!=plan or plan.get('planning_only_not_scientific_metric') is not True or plan.get('scientific_budgets_changed') is not False or plan.get('nshards')!=16 or plan.get('worker_cap')!=15: raise SystemExit(f'{label} timeout plan drift')
 if engine=='Jass' and stage.get('curriculum_sha256')!=expected_artifacts['curriculum']: raise SystemExit(f'{label} Jass evaluator drift')
 if engine=='Scan' and stage.get('scan_binary_sha256')!=pre['scan_binary_sha256']: raise SystemExit(f'{label} Scan binary drift')
 manifests=stage.get('manifests',[])
 if len(manifests)!=16 or sorted(int(x['payload']['shard']) for x in manifests)!=list(range(16)): raise SystemExit(f'{label} manifest coverage drift')
 for item in manifests:
  payload=item['payload']; tag=f"{int(payload['shard']):02d}"; name=f'{label}-{tag}.tsv.gz'; remote_name=f'{label}-shard-{tag}-scores.tsv.gz'
  if sha(root/name)!=payload['files_sha256'][remote_name] or payload.get('scope')!=label or payload.get('shard')!=int(tag) or payload.get('nshards')!=16 or payload.get('budgets_nodes')!=budgets or payload.get('groups_sha256')!=plan['groups_sha256'] or payload.get('row_ids_sha256')!=plan['row_ids_sha256'] or payload.get('timeout_plan_sha256')!=sha(plan_path) or payload.get('cohort_identity_sha256')!=cohort or not policy_ok(payload): raise SystemExit(f'{label} shard {tag} hash/scope/input/timeout/cohort/quarantine drift')
  if engine=='Jass' and payload.get('curriculum_sha256')!=expected_artifacts['curriculum']: raise SystemExit(f'{label} shard {tag} evaluator drift')
  if engine=='Scan' and payload.get('scan_binary_sha256')!=pre['scan_binary_sha256']: raise SystemExit(f'{label} shard {tag} Scan binary drift')
 guards=stage.get('guards',{})
 if any(guards.get(k)!=0 for k in ('fits','calibrations','strength_games','promotions')) or guards.get('promotion_authorized') is not False: raise SystemExit(f'{label} guard drift')
for name in ('verified-selection.json','verified-preflight.json','verified-static.json'):
 r=json.loads((art/name).read_text())
 if r.get('code_sha')!=code or r.get('result_state')!='completed' or r.get('exit_code')!=0: raise SystemExit(f'{name} upstream state/code drift')
PY_AUTH

stage decompress-score-shards
JASS_BASE_ARGS=(); JASS_DEEP_ARGS=(); SCAN_BASE_ARGS=(); SCAN_DEEP_ARGS=(); SCAN_ULTRA_ARGS=()
for shard in $(seq 0 15); do
  printf -v tag '%02d' "$shard"
  for label in jass-base jass-deep scan-base scan-deep scan-ultra; do
    gunzip -t "$IN/$label-$tag.tsv.gz"
    gunzip -c "$IN/$label-$tag.tsv.gz" >"$W/$label-$tag.tsv"
  done
  JASS_BASE_ARGS+=(--jass-base "$W/jass-base-$tag.tsv")
  JASS_DEEP_ARGS+=(--jass-deep "$W/jass-deep-$tag.tsv")
  SCAN_BASE_ARGS+=(--scan-base "$W/scan-base-$tag.tsv")
  SCAN_DEEP_ARGS+=(--scan-deep "$W/scan-deep-$tag.tsv")
  SCAN_ULTRA_ARGS+=(--scan-ultra "$W/scan-ultra-$tag.tsv")
done

stage parent-cluster-bootstrap-and-terminal-readout
"$PY" jobs/tools/scan_ceiling_readout.py --groups "$IN/siblings.tsv" \
  --deep-row-ids "$IN/deep512-row-ids.txt" --ultra-row-ids "$IN/ultra256-row-ids.txt" \
  --static "$IN/static-scores.tsv" "${JASS_BASE_ARGS[@]}" "${JASS_DEEP_ARGS[@]}" \
  "${SCAN_BASE_ARGS[@]}" "${SCAN_DEEP_ARGS[@]}" "${SCAN_ULTRA_ARGS[@]}" \
  --preflight-report "$IN/scan-technical-preflight.json" \
  --selection-report "$IN/selection-report.json" --sibling-manifest "$IN/sibling-manifest.json" \
  --cohort-freeze "$IN/cohort-freeze-before-score.json" \
  --runtime-exclusion-snapshot "$IN/runtime-exclusion-snapshot.json" \
  --source-stage-manifest "$IN/source-stage-manifest.json" \
  --sibling-export-stage-manifest "$IN/sibling-export-stage-manifest.json" \
  --stage-manifest "$IN/jass-base-stage-manifest.json" \
  --stage-manifest "$IN/jass-deep-stage-manifest.json" \
  --stage-manifest "$IN/scan-base-stage-manifest.json" \
  --stage-manifest "$IN/scan-deep-stage-manifest.json" \
  --stage-manifest "$IN/scan-ultra-stage-manifest.json" \
  --bootstrap-samples "$BOOTSTRAP" --bootstrap-seed "$BOOTSTRAP_SEED" \
  --output-json "$ART/scan-ceiling-terminal-readout.json" \
  --output-markdown "$ART/L3_SCAN_CEILING_BENCHMARK_V1_RESULTS_20260829.md" \
  >"$W/readout.log" 2>&1

stage terminal-guard-and-verdict-publication
cp "$ART/scan-ceiling-terminal-readout.json" "$ART/JASS_CONTROL_SUMMARY.json"
VERDICT=$("$PY" - "$ART/scan-ceiling-terminal-readout.json" <<'PY_VERDICT'
import json,sys
p=json.load(open(sys.argv[1])); allowed={'JASS_Q200_NEAR_SCAN_PRACTICAL_CEILING','JASS_SEARCH_HEADROOM_TO_SCAN_ESTABLISHED','JASS_SEARCH_LARGE_HEADROOM_TO_SCAN_ESTABLISHED','JASS_Q200_SCAN_DISTANCE_INCONCLUSIVE'}
v=p['decision']['terminal_verdict']
if v not in allowed: raise SystemExit('unregistered terminal verdict')
g=p['guards']; zero=('fits','refits','calibrations','feature_selections','model_selections','strength_games','bakes','promotions')
forbidden=('training_allowed','tuning_allowed','calibration_allowed','model_selection_allowed','runtime_scale_selection_allowed')
if any(g[k]!=0 for k in zero) or g['promotion_authorized'] is not False or not g['cohort_and_scores_consumed'] or any(g[k] is not False for k in forbidden): raise SystemExit('terminal guard drift')
print(v)
PY_VERDICT
)
: >"$ART/VERDICT__$VERDICT"; : >"$ART/SCAN_BENCHMARK_ONLY__TRUE"; : >"$ART/COHORT_CONSUMED__TRUE"; : >"$ART/STRENGTH_GAMES__0"
printf 'PROMOTION_AUTHORIZED__FALSE\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"; printf 'AUTOMATIC_NEXT_JOB__NULL\n' >"$ART/AUTOMATIC_NEXT_JOB__NULL"
say "$VERDICT bootstrap=$BOOTSTRAP seed=$BOOTSTRAP_SEED"
"$PY" - "$ART/scan-ceiling-terminal-readout.json" <<'PY_PRINT' | tee -a "$RES"
import json,sys
p=json.load(open(sys.argv[1])); d=p['decision']; b=p['bottleneck']; c=p['scan_convergence']
print('roadmap_reading='+d['roadmap_reading'])
for name in ('jass200k_accuracy','jass200k_minus_t3_a','jass1m_minus_jass200k','jass1m_accuracy'):
 print(name+'='+json.dumps(d[name],sort_keys=True))
for name,value in c.items(): print(name+'='+json.dumps(value,sort_keys=True))
print('promotion=false automatic_next_job=null')
PY_PRINT

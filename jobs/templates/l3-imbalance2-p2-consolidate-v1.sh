#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Consolidate existing P1-G4 and P2-G5..G8 candidate reports on common A64/B64.
# No games are replayed: the job symmetrically excludes rare allowed error rows,
# computes paired/material-stratified progress, and joins the TB/Scan reference.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"
: "${JASS_RESULT_DIR:?}"
: "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"
: "${EXPECTED_CODE_SHA:?pin reviewed merged SHA}"
: "${P1_RAW_PREFIX:?failed 0853-style raw P1 comparison prefix}"
: "${P2_RAW_PREFIX:?failed 0864-style raw P2 plateau prefix}"
: "${REFERENCE_PREFIX:?completed 0862-style difficulty reference prefix}"
: "${EXPECTED_P1_JOB_ID:?expected raw P1 job id}"
: "${EXPECTED_P2_JOB_ID:?expected raw P2 job id}"
: "${EXPECTED_REFERENCE_JOB_ID:?expected reference job id}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"
ART="$JASS_ARTEFACT_DIR"
INPUTS="$JASS_RESULT_DIR/inputs"
mkdir -p "$W" "$ART" "$INPUTS/p1" "$INPUTS/p2" "$W/raw" "$W/clean"
exec 9>"$JASS_RESULT_DIR/job.lock"
flock -n 9 || { echo "ABORT: another instance is active" >&2; exit 3; }

BOOTSTRAP="${BOOTSTRAP:-10000}"
SEED="${SEED:-161806}"
EXPECTED_PER_STRATUM="${EXPECTED_PER_STRATUM:-64}"
MAX_EXCLUDED_POSITIONS="${MAX_EXCLUDED_POSITIONS:-2}"
MAX_EXCLUDED_FRACTION="${MAX_EXCLUDED_FRACTION:-0.001}"
MIN_EFFECT="${MIN_EFFECT:-0.02}"
MIN_NONWORSE_STRATA="${MIN_NONWORSE_STRATA:-12}"
MAX_STRATUM_REGRESSION="${MAX_STRATUM_REGRESSION:-0.10}"

RES="$W/RESULTS.txt"
PROG="$W/PROGRESS.txt"
: > "$RES"; : > "$PROG"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
finalize(){
  rc=$?; trap - EXIT; set +e
  [ -f "$RES" ] && cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  [ -d "$W" ] && (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$INPUTS" "$W/raw" "$W/raw-p2" "$W/clean" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR

say "=== $JASS_JOB_ID — L3-IMBALANCE2 P2 G4→G8 consolidation ==="
[ -z "$(git branch --show-current)" ] || die "runner worktree must be detached"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] || die "FULL_RUN_APPROVED=1 missing"
[ "${SCIENTIFIC_GO:-0}" = 1 ] || die "SCIENTIFIC_GO=1 missing"
[ "${CONSOLIDATION_GO:-0}" = 1 ] || die "CONSOLIDATION_GO=1 missing"
[ "$BOOTSTRAP" -ge 10000 ] || die "requires at least 10000 bootstrap replicates"
[ "$EXPECTED_PER_STRATUM" -eq 64 ] || die "requires A64/B64"
[ "$MAX_EXCLUDED_POSITIONS" -le 2 ] || die "exclusion cap may not exceed two positions"
[ "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2 {print $4}')" -ge 2000 ] || die "less than 2 GiB free"

python3 -m py_compile \
  jobs/tools/fetch_result_files.py \
  jobs/tools/imbalance2_symmetric_exclusion.py \
  jobs/tools/imbalance2_phase_progress.py
python3 jobs/tests/test_imbalance2_p2_consolidation.py > "$W/test-consolidation.log" 2>&1 \
  || die "P2 consolidation tests failed"

echo "stage=fetch_sources" > "$PROG"
python3 jobs/tools/fetch_result_files.py --prefix "$P1_RAW_PREFIX" \
  --file artefacts/candidate-only-a64-b64-reports.tar.gz=p1-reports.tar.gz \
  --expected-state failed --out-dir "$INPUTS/p1" --report "$ART/verified-p1-source.json" \
  > "$W/fetch-p1.log" 2>&1 || die "P1 raw report fetch failed"
python3 jobs/tools/fetch_result_files.py --prefix "$P2_RAW_PREFIX" \
  --file artefacts/candidate-p2-reports.tar.gz=p2-reports.tar.gz \
  --expected-state failed --out-dir "$INPUTS/p2" --report "$ART/verified-p2-source.json" \
  > "$W/fetch-p2.log" 2>&1 || die "P2 raw report fetch failed"
python3 jobs/tools/fetch_result_files.py --prefix "$REFERENCE_PREFIX" \
  --file artefacts/imbalance2-a64-b64-difficulty-reference.json=difficulty-reference.json \
  --expected-state completed --out-dir "$INPUTS" --report "$ART/verified-reference-source.json" \
  > "$W/fetch-reference.log" 2>&1 || die "difficulty reference fetch failed"

python3 - "$ART/verified-p1-source.json" "$EXPECTED_P1_JOB_ID" \
  "$ART/verified-p2-source.json" "$EXPECTED_P2_JOB_ID" \
  "$ART/verified-reference-source.json" "$EXPECTED_REFERENCE_JOB_ID" \
  "$ART/source-contract.json" <<'PY'
import json,sys
p1,p1id,p2,p2id,ref,refid,out=sys.argv[1:]
checks=[]
for path,expected,state in ((p1,p1id,'failed'),(p2,p2id,'failed'),(ref,refid,'completed')):
    payload=json.load(open(path))
    if payload.get('job_id') != expected:
        raise SystemExit(f"source job mismatch {payload.get('job_id')} != {expected}")
    if payload.get('result_state') != state:
        raise SystemExit(f"source state mismatch {payload.get('result_state')} != {state}")
    checks.append({'job_id':expected,'state':state,'prefix':payload.get('prefix'),'code_sha':payload.get('code_sha')})
json.dump({'schema':1,'sources':checks,'replayed_games':0},open(out,'w'),indent=2,sort_keys=True)
PY

tar -xzf "$INPUTS/p1/p1-reports.tar.gz" -C "$W/raw"
mkdir -p "$W/raw-p2"
tar -xzf "$INPUTS/p2/p2-reports.tar.gz" -C "$W/raw-p2"

python3 - "$W/raw" "$W/raw-p2" "$W/raw-manifest.json" <<'PY'
import glob,json,os,sys
p1,p2,out=sys.argv[1:]
def paths(pattern):
    values=sorted(glob.glob(pattern))
    if not values:
        raise SystemExit(f'no reports for {pattern}')
    return values
sets={
  'G4':paths(os.path.join(p1,'v2','G4','plateau-*.s*.json')),
  'G5':paths(os.path.join(p2,'G5','plateau-*.s*.json')),
  'G6':paths(os.path.join(p2,'G6','plateau-*.s*.json')),
  'G7':paths(os.path.join(p2,'G7','plateau-*.s*.json')),
  'G8':paths(os.path.join(p2,'G8','plateau-*.s*.json')),
}
json.dump({'schema':1,'same_pools':True,'same_search_budget':True,'report_sets':sets},open(out,'w'),indent=2,sort_keys=True)
PY

echo "stage=symmetric_exclusion" > "$PROG"
python3 jobs/tools/imbalance2_symmetric_exclusion.py \
  --manifest "$W/raw-manifest.json" \
  --out-dir "$W/clean" \
  --out-manifest "$W/clean-manifest.json" \
  --report "$ART/symmetric-exclusions.json" \
  --max-excluded-positions "$MAX_EXCLUDED_POSITIONS" \
  --max-excluded-fraction "$MAX_EXCLUDED_FRACTION" \
  --expected-per-stratum "$EXPECTED_PER_STRATUM" \
  --allow-error-substring "no match in 60.0s" \
  > "$W/clean.log" 2>&1 || die "symmetric exclusion failed"

echo "stage=stratified_progress" > "$PROG"
python3 jobs/tools/imbalance2_phase_progress.py \
  --manifest "$W/clean-manifest.json" \
  --reference "$INPUTS/difficulty-reference.json" \
  --exclusions "$ART/symmetric-exclusions.json" \
  --out "$ART/v2-g4-g8-stratified-progress.json" \
  --bootstrap "$BOOTSTRAP" --seed "$SEED" \
  --min-effect "$MIN_EFFECT" \
  --min-nonworse-strata "$MIN_NONWORSE_STRATA" \
  --max-stratum-regression "$MAX_STRATUM_REGRESSION" \
  > "$W/progress-eval.log" 2>&1 || die "phase progress aggregation failed"

python3 - "$ART/v2-g4-g8-stratified-progress.json" "$ART/c0-decision.json" <<'PY'
import json,sys
src,out=sys.argv[1:]
p=json.load(open(src)); final=p['comparisons']['G4_to_G8']; macro=final['macro_equal_stratum']
summary={
 'schema':1,
 'protocol':p['protocol'],
 'decision':p['decision'],
 'recommendation_for_review':p['recommendation_for_review'],
 'baseline_generation':p['baseline_generation'],
 'phase_generations':p['phase_generations'],
 'g4_to_g8_macro_delta':macro['last_minus_first_failure_cost'],
 'g4_to_g8_stratified_ci95':macro['stratified_bootstrap_95'],
 'g4_to_g8_nonworse_strata':macro['nonworse_strata'],
 'g4_to_g8_pool_deltas':{k:v['last_minus_first_failure_cost'] for k,v in final['pools'].items()},
 'p2_plateau_confirmed':p['p2_plateau']['confirmed'],
 'excluded_positions':(p.get('symmetric_exclusion') or {}).get('excluded_positions',[]),
 'difficulty_reference_used_for_reporting':p['difficulty_reference_used_for_reporting'],
 'difficulty_reference_used_in_decision_rule':False,
 'promotion_authorized':False,
 'p3_authorized':False,
 'automatic_next_job':None,
}
json.dump(summary,open(out,'w'),indent=2,sort_keys=True); print(json.dumps(summary,indent=2))
PY
cp "$INPUTS/difficulty-reference.json" "$ART/difficulty-reference.json"
say "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["decision"])' "$ART/c0-decision.json")"
echo "stage=completed" > "$PROG"

#!/usr/bin/env bash
# HOME-only inference of frozen T0/D1/RF1/T3-A signals on the frozen cohort.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${EXPECTED_HOST:?}"; : "${SELECTION_PREFIX:?}"; : "${PREFLIGHT_PREFIX:?}"
: "${FULL_RUN_APPROVED:?}"; : "${SCIENTIFIC_GO:?}"
export SCAN_BENCHMARK_ONLY=true

T0_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
D1_SHA="e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49"
RF1_SHA="0d26ba50b668160b3da3e247cd4e1bd709c2cb7989b3b5877b9ea7deb34db58b"
T3_SHA="16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2"
RF1_EXTRACTOR_CODE="e5c4a0d6e88e99c06819100c4b5dbc697bbe3a53"
D1_PREFIX="r2:jass-data/runs/cpx62-1575-l3-deep-sibling-phase-a-v1/20260826T191127Z-f1dee26a"
RF1_PREFIX="r2:jass-data/runs/cpx62-1632g-l3-residual-feature-freeze-v1/20260829T022015Z-e5c4a0d6"
T3_PREFIX="r2:jass-data/runs/cpx62-1637-l3-t3-rf1-joint-ab-train-freeze-v1/20260829T082456Z-bbb2bfe4"

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

arch_assert_rf1(){
  local ref="$1" root="$W/rf1-src" scratch="$W/arch-rf1-ref"
  mkdir -p "$scratch/src"
  for file in src/scan_eval.cpp src/scan_eval.hpp src/search.cpp src/movegen.cpp src/movegen.hpp; do
    git -C "$root" show "$ref:$file" >"$scratch/$file" \
      || die "cannot materialize RF1 arch ref $ref:$file"
    cmp -s "$scratch/$file" "$root/$file" || die "RF1 arch source is not byte-exact: $file"
  done
  grep -q 'g_emasks' "$root/src/scan_eval.cpp" || die "RF1 arch guard: scan_eval missing g_emasks"
  grep -q 'has_any_capture' "$root/src/search.cpp" || die "RF1 arch guard: search missing has_any_capture"
  grep -q 'has_any_capture' "$root/src/movegen.cpp" || die "RF1 arch guard: movegen missing has_any_capture"
  say "arch_guard=PASS ref=$ref byte_exact=5 g_emasks=1 has_any_capture=2"
}

MON=""
monitor(){ (t0=$(date +%s); while true; do { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%FT%T%z')"; printf 'phase=%s\n' "$(cat "$STAGE")"; printf 'elapsed_min=%d\n' "$((($(date +%s)-t0)/60))"; } >"$PROG.tmp"; mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 120; done) & MON="$!"; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e; [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true; [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"; (cd "$W" && find . -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true; git worktree remove --force "$W/rf1-src" 2>/dev/null || true; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^home-[0-9]+-l3-scan-ceiling-static-v1$ ]] || die "HOME job nomenclature drift"
[ "$(hostname)" = "$EXPECTED_HOST" ] || die "HOME host mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "dirty/non-detached worktree"
[ "$(nproc)" -eq 16 ] || die "HOME 16-CPU contract mismatch"
[ "$FULL_RUN_APPROVED" = 1 ] && [ "$SCIENTIFIC_GO" = 1 ] || die "execution GO missing"
for command in cmp df; do command -v "$command" >/dev/null || die "$command missing"; done
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
[ -f "$VENV/.jass-runtime-ready-v1" ] || die "numeric runtime absent"
PY="$VENV/bin/python"; "$PY" -c 'import numpy; assert numpy.__version__'
unset JASS_TB_MOVE_ORDER_POLICY JASS_DSSD_MOVE_ORDER_POLICY JASS_T3_F6_MODEL
monitor

stage fetch-authenticate-frozen-cohort
python3 jobs/tools/fetch_result_files.py --prefix "$SELECTION_PREFIX" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=selection-summary.json \
  --file artefacts/children.jnnw.gz=children.jnnw.gz \
  --file artefacts/siblings.tsv=siblings.tsv \
  --file artefacts/sibling-manifest.json=sibling-manifest.json \
  --file artefacts/selection-report.json=selection-report.json \
  --out-dir "$IN" --report "$ART/verified-selection.json" >"$W/fetch-selection.log" 2>&1 \
  || die "selection fetch failed"
gunzip -t "$IN/children.jnnw.gz"; gunzip -c "$IN/children.jnnw.gz" >"$W/children.jnnw"
python3 - "$IN" "$W/children.jnnw" "$ART/verified-selection.json" "$EXPECTED_CODE_SHA" <<'PY_SELECTION'
import hashlib,json,sys
from pathlib import Path
root,children=map(Path,sys.argv[1:3]); r=json.load(open(sys.argv[3])); code=sys.argv[4]; sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
s=json.loads((root/'selection-summary.json').read_text()); c=json.loads((root/'selection-report.json').read_text()); m=json.loads((root/'sibling-manifest.json').read_text())
if r.get('code_sha')!=code or r.get('result_state')!='completed' or r.get('exit_code')!=0: raise SystemExit('selection result drift')
if s.get('verdict')!='SCAN_COHORT_FROZEN_BENCHMARK_ONLY' or not s.get('passed'): raise SystemExit('cohort not frozen')
if any(s.get(name) is not False for name in ('training_allowed','tuning_allowed','calibration_allowed','model_selection_allowed','runtime_scale_selection_allowed')): raise SystemExit('selection quarantine drift')
if c.get('selected')!=2000 or c.get('cohort_identity_sha256')!=s.get('cohort_identity_sha256'): raise SystemExit('cohort identity drift')
if s.get('selection_report_sha256')!=sha(root/'selection-report.json') or s.get('sibling_manifest_sha256')!=sha(root/'sibling-manifest.json') or len(str(s.get('sibling_export_stage_manifest_sha256','')))!=64: raise SystemExit('selection manifest chain drift')
if m.get('children_sha256')!=sha(children) or m.get('groups_sha256')!=sha(root/'siblings.tsv'): raise SystemExit('sibling payload hash drift')
PY_SELECTION

stage fetch-authenticate-four-frozen-evaluators
python3 jobs/tools/fetch_result_files.py --prefix "$PREFLIGHT_PREFIX" \
  --file artefacts/curriculum.pjtw=curriculum.pjtw --out-dir "$IN" \
  --report "$ART/verified-curriculum.json" >"$W/fetch-curriculum.log" 2>&1 || die "T0 fetch failed"
python3 jobs/tools/fetch_result_files.py --prefix "$D1_PREFIX" --file artefacts/dssd-policy.json=d1.json \
  --out-dir "$IN" --report "$ART/verified-d1.json" >"$W/fetch-d1.log" 2>&1 || die "D1 fetch failed"
python3 jobs/tools/fetch_result_files.py --prefix "$RF1_PREFIX" --file artefacts/RF1.json=rf1.json \
  --out-dir "$IN" --report "$ART/verified-rf1.json" >"$W/fetch-rf1.log" 2>&1 || die "RF1 fetch failed"
python3 jobs/tools/fetch_result_files.py --prefix "$T3_PREFIX" --file artefacts/t3-a-f6-only.json=t3-a.json \
  --out-dir "$IN" --report "$ART/verified-t3-a.json" >"$W/fetch-t3.log" 2>&1 || die "T3-A fetch failed"
python3 - "$IN" "$T0_SHA" "$D1_SHA" "$RF1_SHA" "$T3_SHA" <<'PY_ARTIFACTS'
import hashlib,sys
from pathlib import Path
root=Path(sys.argv[1]); expected=dict(zip(['curriculum.pjtw','d1.json','rf1.json','t3-a.json'],sys.argv[2:]))
for name,want in expected.items():
 got=hashlib.sha256((root/name).read_bytes()).hexdigest()
 if got!=want: raise SystemExit(f'{name} SHA drift: {got}')
PY_ARTIFACTS

stage build-byte-frozen-rf1-extractor
git worktree add --detach "$W/rf1-src" "$RF1_EXTRACTOR_CODE" >"$W/rf1-worktree.log" 2>&1
arch_assert_rf1 "$RF1_EXTRACTOR_CODE"
(cd "$W/rf1-src" && python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf) >"$W/rf1-patterns.log" 2>&1
cmake -S "$W/rf1-src" -B "$W/rf1-build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=OFF \
  -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON \
  -DJASS_TEMPO_STAGE=ON >"$W/rf1-cmake.log" 2>&1
cmake --build "$W/rf1-build" -j8 --target jass jass_lib >"$W/rf1-build.log" 2>&1
c++ -std=c++20 -O3 -DNDEBUG -DJASS_ENDGAME_FEATURES=1 -DJASS_KING_MOBILITY=1 \
  -DJASS_SCAN_PARITY=1 -DJASS_TEMPO_STAGE=1 -I"$W/rf1-src/src" \
  -I"$W/rf1-src/pattern_jass/src" "$W/rf1-src/jobs/tools/residual_feature_dump.cpp" \
  "$W/rf1-src/src/residual_features.cpp" "$W/rf1-build/libjass_lib.a" -pthread \
  -o "$W/residual_feature_dump" >"$W/rf1-link.log" 2>&1

stage inference-only-feature-extraction
"$W/rf1-build/jass" --dump-eval-features "$W/children.jnnw" "$W/children.feat" \
  >"$W/eval-feature-dump.log" 2>&1
"$W/residual_feature_dump" "$W/children.jnnw" "$W/children.rffd" \
  >"$W/residual-feature-dump.log" 2>&1

stage deterministic-static-inference-no-fit
"$PY" jobs/tools/scan_ceiling_static_score.py --groups "$IN/siblings.tsv" \
  --features "$W/children.feat" --rffd "$W/children.rffd" \
  --curriculum "$IN/curriculum.pjtw" --d1 "$IN/d1.json" --rf1 "$IN/rf1.json" \
  --t3-a "$IN/t3-a.json" --output "$ART/static-scores.tsv" \
  --report "$ART/static-score-report.json" >"$W/static-score.log" 2>&1
gzip -n -c "$W/children.feat" >"$ART/children.feat.gz"
gzip -n -c "$W/children.rffd" >"$ART/children.rffd.gz"
python3 - "$ART/JASS_CONTROL_SUMMARY.json" "$ART/static-score-report.json" "$IN/selection-report.json" "$EXPECTED_CODE_SHA" "$RF1_EXTRACTOR_CODE" <<'PY_SUMMARY'
import hashlib,json,sys
from pathlib import Path
out,report,selection=map(Path,sys.argv[1:4]); code,extractor=sys.argv[4:]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest(); r=json.loads(report.read_text()); s=json.loads(selection.read_text())
assert r['rows']>0 and r['deterministic_replay_exact'] and r['fits']==0
payload={'schema':'jass.scan_ceiling_static_summary.v1','verdict':'SCAN_STATIC_SIGNALS_FROZEN',
 'passed':True,'benchmark_only':True,'code_sha':code,'rf1_extractor_code':extractor,
 'cohort_identity_sha256':s['cohort_identity_sha256'],'rows':r['rows'],
 'static_scores_sha256':r['output_sha256'],'report_sha256':sha(report),'artifacts':r['artifacts'],
 'cohort_and_scores_consumed':True,'training_allowed':False,'tuning_allowed':False,
 'calibration_allowed':False,'model_selection_allowed':False,
 'runtime_scale_selection_allowed':False,
 'guards':{'fits':0,'refits':0,'calibrations':0,'feature_selections':0,'model_selections':0,
           'strength_games':0,'bakes':0,'promotions':0,'promotion_authorized':False}}
out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY_SUMMARY
: >"$ART/VERDICT__SCAN_STATIC_SIGNALS_FROZEN"; : >"$ART/SCAN_BENCHMARK_ONLY__TRUE"; : >"$ART/STRENGTH_GAMES__0"
: >"$ART/COHORT_CONSUMED__TRUE"
printf 'PROMOTION_AUTHORIZED__FALSE\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"
printf 'AUTOMATIC_NEXT_JOB__NULL\n' >"$ART/AUTOMATIC_NEXT_JOB__NULL"
say "SCAN_STATIC_SIGNALS_FROZEN rows=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["rows"])' "$ART/static-score-report.json") fits=0"

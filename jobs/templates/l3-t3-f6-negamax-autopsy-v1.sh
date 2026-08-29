#!/usr/bin/env bash
# Post-terminal read-only autopsy of the R0-v2 depth-1 negamax witness.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"
: "${JASS_OBJSTORE_REMOTE:?}"
cd "$JASS_CODE_DIR"

MODEL_SHA="16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
F6_SHA="cc4837e6829d937f7330f7bc71280f3ec0bed3f431e57b2664c651e1d763db4e"
MODEL_PREFIX="r2:jass-data/runs/cpx62-1637-l3-t3-rf1-joint-ab-train-freeze-v1/20260829T082456Z-bbb2bfe4"
CURRICULUM_PREFIX="r2:jass-data/runs/cpx62-1341-jass-megacorpus-arm-d-fit-v1/20260814T191555Z-18c38a33"
MODEL_JOB="cpx62-1637-l3-t3-rf1-joint-ab-train-freeze-v1"
MODEL_ATTEMPT="20260829T082456Z-bbb2bfe4"
MODEL_CODE="bbb2bfe460ece89bef0ec30e2d52ed4b0ff847ea"
CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"
CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"
CURRICULUM_CODE="18c38a33ae78c9c2e8e2df62fca266da28dacead"
SOURCE_R0_CODE="f559baede4047f47abe13724b16d1ad669c5f36f"
SOURCE_R0_JOB="cpx62-1648-l3-t3-f6-runtime-r0-v2"
SOURCE_R0_ATTEMPT="20260829T132226Z-f559baed"

W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; }
MON=""
monitor(){
  (t0=$(date +%s); while true; do
    {
      printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
      printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
      printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
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
[ "$JASS_JOB_ID" = "cpx62-1650-l3-t3-f6-negamax-autopsy-v1" ] || die "job nomenclature drift"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
git merge-base --is-ancestor "$SOURCE_R0_CODE" HEAD || die "R0-v2 implementation is not an ancestor"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "dirty/non-detached job worktree"
[ "$(nproc)" -eq 16 ] || die "16-CPU CPX contract mismatch"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "diagnostic GO missing"
unset JASS_T3_F6_MODEL
monitor

stage fetch-authenticate-frozen-evaluators
python3 jobs/tools/fetch_result_files.py --prefix "$MODEL_PREFIX" \
  --file artefacts/t3-a-f6-only.json=t3-a-f6-only.json --out-dir "$IN" \
  --report "$ART/verified-t3-a.json" >"$W/fetch-model.log" 2>&1 || die "T3-A fetch failed"
python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_PREFIX" \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz --out-dir "$IN" \
  --report "$ART/verified-curriculum.json" >"$W/fetch-curriculum.log" 2>&1 || die "CURRICULUM fetch failed"
gunzip -t "$IN/curriculum.pjtw.gz"
gunzip -c "$IN/curriculum.pjtw.gz" >"$IN/curriculum.pjtw"
python3 - "$IN" "$ART" "$MODEL_JOB" "$MODEL_ATTEMPT" "$MODEL_CODE" \
  "$CURRICULUM_JOB" "$CURRICULUM_ATTEMPT" "$CURRICULUM_CODE" "$MODEL_SHA" "$CURRICULUM_SHA" <<'PY_AUTH'
import hashlib,json,sys
from pathlib import Path
root,art=map(Path,sys.argv[1:3]); mj,ma,mc,cj,ca,cc,msha,csha=sys.argv[3:]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name,want in [('verified-t3-a.json',(mj,ma,mc)),('verified-curriculum.json',(cj,ca,cc))]:
    row=json.loads((art/name).read_text())
    got=(row.get('job_id'),row.get('attempt_id'),row.get('code_sha'))
    if got!=want or row.get('result_state')!='completed' or row.get('exit_code')!=0:
        raise SystemExit(f'{name}: source drift {got}')
if sha(root/'t3-a-f6-only.json')!=msha: raise SystemExit('T3-A raw SHA drift')
if sha(root/'curriculum.pjtw')!=csha: raise SystemExit('CURRICULUM raw SHA drift')
PY_AUTH

stage build-production-diagnostic
EGDIR=""
for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB=128
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen-current.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON \
  -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass jass_tests t3_f6_invariance_probe \
  t3_f6_relative_probe t3_f6_negamax_autopsy >"$W/build.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB ctest --test-dir "$W/build" \
  --output-on-failure >"$W/ctest.log" 2>&1

stage reproduce-and-localise-negamax-witness
"$W/build/t3_f6_negamax_autopsy" "$IN/curriculum.pjtw" \
  "$IN/t3-a-f6-only.json" "$EXPECTED_CODE_SHA" "$ART/negamax-autopsy.json" \
  >"$W/autopsy.log" 2>&1

stage validate-read-only-autopsy
python3 - "$ART/negamax-autopsy.json" "$EXPECTED_CODE_SHA" "$MODEL_SHA" "$CURRICULUM_SHA" "$F6_SHA" <<'PY_VALIDATE'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]); code,model,curr,f6=sys.argv[2:]
r=json.loads(p.read_text())
def need(ok,msg):
    if not ok: raise SystemExit(msg)
need(r['schema']=='jass.t3_f6_negamax_autopsy.v1','schema drift')
need(r['code_sha']==code,'code SHA drift')
need(r['t3_sha256']==model and r['t0_sha256']==curr and r['f6_order_sha256']==f6,'artifact SHA drift')
need(r['root_fen']=='W:W31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50:B1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20'
     and r['root_stm']=='white','R0-v2 root drift')
need(r['t3']['actual_depth1_score']==-51,'R0-v2 score not reproduced')
need(r['strength_games']==0 and not r['force_authorized'] and not r['v3_executed'],'read-only guard drift')
need(r['pov_contract']['formula_mismatch_count']==0,'T3 native formula mismatch')
need(all(row['native_formula_exact'] for row in r['children']),'child formula mismatch')
need(r['capture_audit']['all_replies_scanned'],'capture audit incomplete')
allowed={'NEGAMAX_TEST_WAS_OVERSIMPLIFIED','T3_RUNTIME_POV_INTEGRATION_DEFECT',
         'QUIESCENCE_OR_DEPTH_SEMANTICS_EXPLAINS_MISMATCH',
         'ROOT_OR_SEARCH_SEMANTICS_EXPLAINS_MISMATCH','NEGAMAX_MISMATCH_UNRESOLVED'}
need(r['final_classification'] in allowed,'classification drift')
need(len(r['synthetic_cases'])==3,'synthetic case count drift')
(p.parent/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
PY_VALIDATE

VERDICT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["final_classification"])' "$ART/negamax-autopsy.json")
cp "$IN/t3-a-f6-only.json" "$ART/t3-a-f6-only.json"
cp "$IN/curriculum.pjtw" "$ART/curriculum.pjtw"
: >"$ART/VERDICT__$VERDICT"
: >"$ART/STRENGTH_GAMES__0"
: >"$ART/FORCE_AUTHORIZED__FALSE"
: >"$ART/V3_EXECUTED__FALSE"
say "$VERDICT strength_games=0 force_authorized=false v3_executed=false"

#!/usr/bin/env bash
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"; : "${JASS_STAGE_SPEC:?}"
: "${JASS_JOB_ID:?}"; : "${SCAN_ORACLE_VARIANTS_RECOVERY_GO:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART/variants"; RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }; die(){ say "ABORT: $*"; exit 1; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true; (cd "$W" && find . -maxdepth 2 -name '*.log' -type f -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true; rm -rf "$W/src" "$W/build" 2>/dev/null || true; exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "TECHNICAL_ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM; trap 'exit 130' INT
PY="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}/bin/python"; [ -x "$PY" ] || die "numeric venv missing"
SPEC_CODE=$("$PY" - "$JASS_STAGE_SPEC" <<'PY'
import json,sys; print(json.load(open(sys.argv[1]))['code_sha'])
PY
)
[ "$(git rev-parse HEAD)" = "$SPEC_CODE" ] || die "stage spec / HEAD mismatch"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX62 contract drift"
[ "$SCAN_ORACLE_VARIANTS_RECOVERY_GO" = 1 ] || die "recovery GO missing"
unset JASS_D3_RUNTIME_ADAPTER JASS_D3_RUNTIME_BASE_MODEL JASS_DSSD_MOVE_ORDER_POLICY JASS_TB_MOVE_ORDER_POLICY JASS_T3_F6_MODEL JASS_SEARCH_PARAMS || true

SRC_JOB="cpx62-1865-l3-scan-oracle-gate0-search-variants-v1"; SRC_ATTEMPT="20260907T202147Z-e80beb59"; SRC_CODE="e80beb59de45b7c449e50bc4c2fd89249c9c8135"; SRC_ROOT="r2:jass-data/runs/$SRC_JOB/$SRC_ATTEMPT"
G0_JOB="cpx62-1864-l3-scan-oracle-gate0-d3-retrospective-v1"; G0_ATTEMPT="20260907T195559Z-8782aed3"; G0_ROOT="r2:jass-data/runs/$G0_JOB/$G0_ATTEMPT"
SEL_ROOT="r2:jass-data/runs/home-1651-l3-scan-ceiling-selection-v1/20260829T133348Z-28e12fba"
SCAN_ROOT="r2:jass-data/runs/home-1657-l3-scan-ceiling-scan-base-v1/20260829T144418Z-46623b26"
D1_ROOT="r2:jass-data/runs/cpx62-1849-l3-decision-math-d1-wdl-listwise-fit-stage-env-recovery-requeue-v1/20260906T222203Z-08fd187a"
MODEL_SHA="e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0"
say "Gate0 1865 recovery start reuse=J1,J2 rerun=J3,J4,J5,J6 scan_searches=0 games=0"

python3 jobs/tools/fetch_result_files.py --prefix "$SRC_ROOT" --expected-state failed \
  --file artefacts/attempt-diagnostic.json=attempt-diagnostic-1865.json \
  --file artefacts/variants/J1_SCAN_VERIFY.tsv=J1.tsv --file artefacts/variants/J1_SCAN_VERIFY-report.json=J1-report.json --file artefacts/variants/J1_SCAN_VERIFY-readout.json=J1-readout.json \
  --file artefacts/variants/J2_SCAN_THREAT_REENTRY.tsv=J2.tsv --file artefacts/variants/J2_SCAN_THREAT_REENTRY-report.json=J2-report.json --file artefacts/variants/J2_SCAN_THREAT_REENTRY-readout.json=J2-readout.json \
  --out-dir "$IN" --report "$ART/verified-1865.json" >"$W/fetch-1865.log" 2>&1
"$PY" - "$ART/verified-1865.json" "$IN/attempt-diagnostic-1865.json" "$IN/J1-report.json" "$IN/J2-report.json" "$IN/J1-readout.json" "$IN/J2-readout.json" <<'PY'
import json,sys
v,d,r1,r2,o1,o2=[json.load(open(p)) for p in sys.argv[1:]]
if (v.get('job_id'),v.get('attempt_id'),v.get('code_sha'),v.get('result_state')) != ('cpx62-1865-l3-scan-oracle-gate0-search-variants-v1','20260907T202147Z-e80beb59','e80beb59de45b7c449e50bc4c2fd89249c9c8135','failed'): raise SystemExit('1865 provenance drift')
if d.get('exit_code') != 1 or d.get('failure_class') != 'STAGE_EXIT_CODE': raise SystemExit('1865 failure-shape drift')
for r,o in ((r1,o1),(r2,o2)):
 if r.get('processed_rows')!=512 or r.get('scan_searches')!=0 or r.get('strength_games')!=0: raise SystemExit('reused report guard drift')
 if o.get('parents')!=512 or o.get('scan_reference_nodes')!=200000: raise SystemExit('reused readout drift')
PY

python3 jobs/tools/fetch_result_files.py --prefix "$G0_ROOT" --expected-state completed --file artefacts/gate0-parent-ids.txt=ids.txt --file artefacts/gate0-control.tsv=control.tsv --out-dir "$IN" --report "$ART/verified-1864.json" >"$W/fetch-1864.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$SEL_ROOT" --expected-state completed --file artefacts/parents.jnnw.gz=parents.jnnw.gz --file artefacts/siblings.tsv=siblings.tsv --out-dir "$IN" --report "$ART/verified-selection.json" >"$W/fetch-selection.log" 2>&1
scan_fetch=(); for i in $(seq -w 0 15); do scan_fetch+=(--file "artefacts/scores/scan-base-shard-${i}-scores.tsv.gz=scan-${i}.tsv.gz"); done
python3 jobs/tools/fetch_result_files.py --prefix "$SCAN_ROOT" --expected-state completed "${scan_fetch[@]}" --out-dir "$IN" --report "$ART/verified-scan.json" >"$W/fetch-scan.log" 2>&1
python3 jobs/tools/fetch_result_files.py --prefix "$D1_ROOT" --expected-state completed --file artefacts/WDL_CONTROL.pjtw.gz=WDL_CONTROL.pjtw.gz --out-dir "$IN" --report "$ART/verified-d1.json" >"$W/fetch-d1.log" 2>&1
gunzip -c "$IN/parents.jnnw.gz" >"$W/parents.jnnw"; gunzip -c "$IN/WDL_CONTROL.pjtw.gz" >"$W/WDL_CONTROL.pjtw"
[ "$(sha256sum "$W/WDL_CONTROL.pjtw" | awk '{print $1}')" = "$MODEL_SHA" ] || die "WDL_CONTROL drift"
cp "$IN/J1.tsv" "$ART/variants/J1_SCAN_VERIFY.tsv"; cp "$IN/J1-report.json" "$ART/variants/J1_SCAN_VERIFY-report.json"; cp "$IN/J1-readout.json" "$ART/variants/J1_SCAN_VERIFY-readout.json"
cp "$IN/J2.tsv" "$ART/variants/J2_SCAN_THREAT_REENTRY.tsv"; cp "$IN/J2-report.json" "$ART/variants/J2_SCAN_THREAT_REENTRY-report.json"; cp "$IN/J2-readout.json" "$ART/variants/J2_SCAN_THREAT_REENTRY-readout.json"

mkdir -p "$W/src"; git archive HEAD | tar -x -C "$W/src"
"$PY" "$W/src/jobs/tools/scan_oracle_gate0_render.py" --cmake "$W/src/CMakeLists.txt"
"$PY" - "$W/src/jobs/tools/scan_oracle_gate0_search_variants.cpp" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); t=p.read_text()
needle='        assert_activation(arm, c);\n'
if t.count(needle)!=1: raise SystemExit('activation-sentinel patch anchor drift')
p.write_text(t.replace(needle,'        // Recovery: no observed activation is a screen result, not a stage failure.\n'))
PY
cmake -S "$W/src" -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass_scan_oracle_gate0_search_variants >"$W/build.log" 2>&1
scan_read=(); for i in $(seq -w 0 15); do scan_read+=(--scan-score "$IN/scan-${i}.tsv.gz"); done
for arm in J3_SCAN_SINGLE_REPLY J4_SCAN_LMR J5_SCAN_ORDERING J6_NO_NULL_MOVE; do
  say "score=$arm"
  timeout 1200s "$W/build/jass_scan_oracle_gate0_search_variants" "$W/parents.jnnw" "$IN/ids.txt" "$ART/variants/$arm.tsv" "$ART/variants/$arm-report.json" "$W/WDL_CONTROL.pjtw" "$arm" 20000 >"$W/$arm.log" 2>&1
  "$PY" jobs/tools/scan_oracle_gate0_readout.py --groups "$IN/siblings.tsv" --ids "$IN/ids.txt" "${scan_read[@]}" --control "$IN/control.tsv" --candidate "$ART/variants/$arm.tsv" --candidate-name "$arm" --out "$ART/variants/$arm-readout.json" >"$W/$arm-readout.log" 2>&1
done

"$PY" - "$ART" "$IN/control.tsv" "$SPEC_CODE" <<'PY'
import csv,json,sys
from pathlib import Path
art=Path(sys.argv[1]); control_path=Path(sys.argv[2]); code=sys.argv[3]
arms=['J1_SCAN_VERIFY','J2_SCAN_THREAT_REENTRY','J3_SCAN_SINGLE_REPLY','J4_SCAN_LMR','J5_SCAN_ORDERING','J6_NO_NULL_MOVE']
control={int(r['parent_id']):(r['from'],r['to'],r['captured_hex'],r['promotes']) for r in csv.DictReader(control_path.open(),delimiter='\t')}
rows={}; survivors=[]; total_nodes=0
for arm in arms:
 r=json.load(open(art/'variants'/f'{arm}-readout.json')); rep=json.load(open(art/'variants'/f'{arm}-report.json'))
 if r.get('parents')!=512 or rep.get('processed_rows')!=512: raise SystemExit(f'{arm} cardinality drift')
 if rep.get('scan_searches')!=0 or rep.get('strength_games')!=0: raise SystemExit(f'{arm} side-effect drift')
 if arm=='J1_SCAN_VERIFY': activated=rep.get('scan_verify_probes',0)>0
 elif arm=='J2_SCAN_THREAT_REENTRY': activated=rep.get('scan_threat_reentries',0)>0
 elif arm=='J3_SCAN_SINGLE_REPLY': activated=rep.get('single_reply_extensions',0)>0
 elif arm=='J4_SCAN_LMR': activated=rep.get('reductions',0)>0 and rep.get('reduced_plies',0)>0
 elif arm=='J5_SCAN_ORDERING': activated=rep.get('ordering_good_updates',0)>0 and rep.get('ordering_bad_updates',0)>0
 else:
  cand={int(x['parent_id']):(x['from'],x['to'],x['captured_hex'],x['promotes']) for x in csv.DictReader(open(art/'variants'/f'{arm}.tsv'),delimiter='\t')}
  activated=any(cand[k]!=control[k] for k in control)
 gate=r['gate']['verdict']; survivor=(gate=='GATE0_SUPPORTED' and activated)
 if survivor: survivors.append(arm)
 rows[arm]={'gate':r['gate'],'paired':r['paired'],'control':r['control'],'candidate':r['candidate'],'runtime_report':rep,'observed_activation':activated,'survivor':survivor}
 total_nodes += int(rep['nodes']) if arm not in ('J1_SCAN_VERIFY','J2_SCAN_THREAT_REENTRY') else 0
out={'schema':'jass.scan_oracle_gate0_search_variants_recovery_terminal.v1','verdict':'GATE0_VARIANT_SURVIVORS_FOUND' if survivors else 'GATE0_NO_VARIANT_SURVIVORS','code_sha':code,'source_job':'cpx62-1865-l3-scan-oracle-gate0-search-variants-v1','reused_arms':['J1_SCAN_VERIFY','J2_SCAN_THREAT_REENTRY'],'rerun_arms':['J3_SCAN_SINGLE_REPLY','J4_SCAN_LMR','J5_SCAN_ORDERING','J6_NO_NULL_MOVE'],'survivors':survivors,'variants':rows,'fresh_confirmation_required_before_strength':True,'strength_authorized':False,'guards':{'new_scan_searches':0,'new_strength_games':0,'new_fits':0,'new_selfplay_games':0,'promotions':0,'bakes':0},'new_candidate_nodes':total_nodes}
(art/'scientific-summary.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
print(json.dumps({'verdict':out['verdict'],'survivors':survivors,'new_candidate_nodes':total_nodes},sort_keys=True))
PY
VERDICT=$("$PY" -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/scientific-summary.json")
printf '%s\n' "$VERDICT" >"$ART/VERDICT__${VERDICT}"; printf '0\n' >"$ART/SCAN_SEARCHES__0"; printf '0\n' >"$ART/STRENGTH_GAMES__0"; printf 'false\n' >"$ART/STRENGTH_AUTHORIZED__FALSE"
say "Gate0 1865 recovery complete verdict=$VERDICT"

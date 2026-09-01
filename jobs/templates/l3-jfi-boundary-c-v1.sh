#!/usr/bin/env bash
# JFI Boundary C: authenticate frozen candidate/control, one common engine, and
# bounded candidate-vs-itself rates on an already-consumed opening root.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${JFI_D_ROOT:?}"; : "${EXPECTED_JFI_D_JOB:?}"; : "${EXPECTED_JFI_D_ATTEMPT:?}"; : "${EXPECTED_JFI_D_CODE_SHA:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"; GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$IN" "$ART" "$GEOM"; RES="$W/RESULTS.txt"; : >"$RES"
say(){ echo "$*"|tee -a "$RES"; }; die(){ say "ABORT: $*"; exit 1; }
CURRICULUM_ROOT="r2:jass-data/runs/cpx62-1341-jass-megacorpus-arm-d-fit-v1/20260814T191555Z-18c38a33"
CONSUMED_ROOT="r2:jass-data/runs/cpx62-1154-l3-big-opening-pool-v1/20260802T120251Z-9b57e0aa"
CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"; PY="$VENV/bin/python"; CACHE_MB=128
Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e; cp "$RES" "$ART/RESULTS.txt" 2>/dev/null||true; rm -rf "$W/build" "$IN" "$GEOM" "$W"/*.pjtw 2>/dev/null||true; exit "$rc"; }
trap finalize EXIT; trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND"|tee -a "$RES"; exit "$rc"' ERR
[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-[0-9]+-l3-jfi-boundary-c-v1$ ]] || die "nomenclature mismatch"
[ "${BOUNDARY_C_APPROVED:-0}" = 1 ] && [ "${NO_FRESH_OPENINGS:-0}" = 1 ] || die "Boundary-C authorization missing"
[ "${NO_STRENGTH_GAMES:-0}" = 1 ] && [ "${NO_SCAN_READS:-0}" = 1 ] && [ "${NO_PROMOTION:-0}" = 1 ] || die "zero-decision guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] && [ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "source drift"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX62 contract mismatch"
[ -f "$VENV/.jass-runtime-ready-v1" ] && [ "$(tr ',' '\n' <<<"$Q00"|wc -l)" -eq 63 ] || die "runtime/Q00 drift"
CPU_MODEL=$(lscpu|awk -F: '/^Model name:/{sub(/^[[:space:]]+/,"",$2);print $2}'); ISA_FLAGS=$(lscpu|awk -F: '/^Flags:/{sub(/^[[:space:]]+/,"",$2);print $2}')
[[ " $ISA_FLAGS " == *" avx2 "* ]] && [[ " $ISA_FLAGS " == *" bmi2 "* ]] || die "ISA drift"; export CPU_MODEL ISA_FLAGS

timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$JFI_D_ROOT" \
 --file artefacts/JFI_D_CANDIDATE_MANIFEST.json=d-manifest.json \
 --file artefacts/JASS_NATIVE_ACTIVE_V1.pjtw.gz=candidate.pjtw.gz \
 --file artefacts/VERDICT__JFI_D_JASS_NATIVE_ACTIVE_V1_FROZEN=READY \
 --out-dir "$IN" --report "$ART/verified-jfi-d.json" >"$W/fetch-d.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRICULUM_ROOT" \
 --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
 --out-dir "$IN" --report "$ART/verified-curriculum.json" >"$W/fetch-curriculum.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CONSUMED_ROOT" \
 --file artefacts/big3000-openings.fen=consumed.fen \
 --out-dir "$IN" --report "$ART/verified-consumed-root.json" >"$W/fetch-consumed.log" 2>&1
gunzip -c "$IN/candidate.pjtw.gz" >"$W/candidate.pjtw"; gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
"$PY" - "$IN/d-manifest.json" "$ART/verified-jfi-d.json" "$W/candidate.pjtw" "$W/curriculum.pjtw" \
 "$EXPECTED_JFI_D_JOB" "$EXPECTED_JFI_D_ATTEMPT" "$EXPECTED_JFI_D_CODE_SHA" "$CURRICULUM_SHA" <<'PY'
import hashlib,json,sys
d=json.load(open(sys.argv[1])); v=json.load(open(sys.argv[2])); sha=lambda p:hashlib.sha256(open(p,'rb').read()).hexdigest()
if (v.get('job_id'),v.get('attempt_id'),v.get('code_sha'),v.get('result_state'))!=(sys.argv[5],sys.argv[6],sys.argv[7],'completed'):
 raise SystemExit('JFI-D identity drift')
if d.get('candidate_name')!='JASS_NATIVE_ACTIVE_V1' or d.get('verdict')!='JFI_D_JASS_NATIVE_ACTIVE_V1_FROZEN':
 raise SystemExit('JFI-D verdict drift')
if d.get('model',{}).get('sha256')!=sha(sys.argv[3]) or sha(sys.argv[4])!=sys.argv[8]: raise SystemExit('model SHA drift')
PY
EGDIR=""; for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }; done
[ -n "$EGDIR" ] || die "EGDB unavailable"; export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1; cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
 -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass jass_tests >"$W/build.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB ctest --test-dir "$W/build" --output-on-failure >"$W/ctest.log" 2>&1
J="$W/build/jass"; for model in candidate curriculum; do printf 'hello\nquit\n'|timeout 60 "$J" --pattern "$W/$model.pjtw" >"$W/load-$model.log" 2>&1; grep -q '^ready' "$W/load-$model.log"||die "$model load failed"; done
head -n 8 "$IN/consumed.fen" >"$W/sizer.fen"; [ "$(grep -c . "$W/sizer.fen")" -eq 8 ] || die "consumed sizer count drift"
run_sizer(){ local view="$1"; local budget=(); [ "$view" = native ] && budget=(--movetime 0.1) || budget=(--depth 9)
 /usr/bin/time -f '%e' -o "$W/$view.seconds" timeout 1800s "$PY" jobs/tools/run_jass_gate_bounded.py \
  --jass "$J" --pattern-a "$W/candidate.pjtw" --pattern-b "$W/candidate.pjtw" --search-params-a "$Q00" --search-params-b "$Q00" \
  --openings-file "$W/sizer.fen" "${budget[@]}" --pairs 1 --max-plies 160 --nshards 8 --max-parallel 8 \
  --timeout 1500 --game-timeout 180 --work-dir "$W/sizer-$view" --out "$ART/$view-sizer.json" >"$W/$view.log" 2>&1; }
run_sizer native; run_sizer q00
EXE_SHA=$(sha256sum "$J"|awk '{print $1}'); CANDIDATE_SHA=$(sha256sum "$W/candidate.pjtw"|awk '{print $1}')
"$PY" - "$ART/JFI_BOUNDARY_C_INPUT.json" "$EXPECTED_CODE_SHA" "$ART" "$W" "$EXE_SHA" "$CANDIDATE_SHA" "$CURRICULUM_SHA" <<'PY'
import json,os,platform,sys
out,code,art,w,exe,candidate,curriculum=sys.argv[1:]; stat=os.statvfs(w)
def sizer(view):
 d=json.load(open(f'{art}/{view}-sizer.json'))
 if d.get('games')!=16 or d.get('pattern_a_sha256')!=candidate or d.get('pattern_b_sha256')!=candidate: raise SystemExit(f'{view} sizer drift')
 return {'games':16,'seconds':float(open(f'{w}/{view}.seconds').read()),'candidate_vs_itself':True,'consumed_openings':8}
payload={'schema':'jass.jfi.boundary_c_input.v1','code_sha':code,
 'machine':{'host':platform.node(),'nproc':os.cpu_count(),'cpu_model':os.environ['CPU_MODEL'],'isa_flags':os.environ['ISA_FLAGS'],'avx2':True,'bmi2':True},
 'disk':{'scratch_path':w,'scratch_free_bytes':stat.f_bavail*stat.f_frsize},
 'candidate':{'name':'JASS_NATIVE_ACTIVE_V1','sha256':candidate},'curriculum':{'sha256':curriculum},
 'executable':{'sha256':exe,'same_binary_both_arms':True},
 'consumed_root_sizers':{'native_0p1s':sizer('native'),'q00_depth9':sizer('q00')},
 'force_runtime':{'shards':12,'parallelism':12,'per_game_timeout_seconds':180,'per_view_timeout_seconds':21600},
 'markers':{'FRESH_OPENINGS':0,'STRENGTH_GAMES':0,'SCIENTIFIC_DECISION':False,'SCAN_READS':0,'PROMOTION_AUTHORIZED':False}}
open(out,'w').write(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY
"$PY" jobs/tools/jfi_boundary_c.py --input "$ART/JFI_BOUNDARY_C_INPUT.json" --out "$ART/JFI_BOUNDARY_C_FACTS.json"|tee -a "$RES"
printf '0\n' >"$ART/FRESH_OPENINGS__0"; printf '0\n' >"$ART/STRENGTH_GAMES__0"; printf '0\n' >"$ART/SCAN_READS__0"
printf 'FALSE\n' >"$ART/PROMOTION_AUTHORIZED__FALSE"; printf 'GO JFI FORCE\n' >"$ART/NEXT_BOUNDARY__GO_JFI_FORCE"
say "JFI_BOUNDARY_C_READY FRESH_OPENINGS=0 STRENGTH_GAMES=0 NEXT_BOUNDARY=GO_JFI_FORCE"

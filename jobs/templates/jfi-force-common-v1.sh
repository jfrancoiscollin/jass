#!/usr/bin/env bash
# Shared JFI-E runtime helpers. Source only after W/IN/ART/GEOM/PY are defined.

JFI_CURRICULUM_ROOT="r2:jass-data/runs/cpx62-1341-jass-megacorpus-arm-d-fit-v1/20260814T191555Z-18c38a33"
JFI_CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
JFI_Q00="rfp_max_depth=5,rfp_margin=100,nmp_min_depth=4,nmp_min_pieces=6,nmp_r_base=2,nmp_r_div=4,singular_min_depth=8,singular_margin=2,lmr_min_depth=3,lmr_first_full_moves=4,lmr_first_full_pv=4,lmr_first_full_nonpv=2,lmr_base=0,lmr_depth_div=6,lmr_idx_div=8,lmr_hist_div=0,lmr_formula=0,lmr_log_base=0,lmr_log_mul=40,lmr_bc_ld=100,lmr_bc_lidx=100,lmp_d1=4,lmp_d2=8,lmp_d3=14,lmp_max_depth=3,history_max=16384,hist_malus=0,hist_mode=1,prob_shift=5,hist_pure=1,hist_order_captures=0,aspiration_initial=50,use_pvs=1,razor_max_depth=4,razor_margin=200,probcut_min_depth=5,probcut_margin=150,probcut_reduction=4,ext_promotion=0,ext_forcing=0,forcing_ext_cap=0,ext_single_reply=0,use_improving=1,use_conthist=1,iid_min_depth=0,iid_reduction=2,no_reduce_forcing=0,qs_forcing_depth=0,qs_promo_depth=0,qs_threat_ext=0,qs_sacs=0,qs_sacs_depth0_only=1,multicut_min_depth=4,multicut_reduction=4,multicut_moves=8,multicut_cuts=2,tm_next_iter_pct=200,tm_min_depth=5,drawish_scaling=0,eg_pieces=40,eg_no_nmp=0,eg_no_lmp=0,eg_no_lmr=0"
JFI_BOOTSTRAP=200000; JFI_OPENINGS=3000; JFI_CANDIDATES=30000
JFI_NSH=12; JFI_PAR=12; JFI_GAME_TIMEOUT=180; JFI_VIEW_TIMEOUT=21600

jfi_authenticate_force_inputs(){
  timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$BOUNDARY_C_ROOT" \
    --file artefacts/JFI_BOUNDARY_C_FACTS.json=boundary-c.json \
    --file artefacts/NEXT_BOUNDARY__GO_JFI_FORCE=GO_JFI_FORCE \
    --out-dir "$IN" --report "$ART/verified-boundary-c.json" >"$W/fetch-boundary-c.log" 2>&1
  timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$JFI_D_ROOT" \
    --file artefacts/JFI_D_CANDIDATE_MANIFEST.json=d-manifest.json \
    --file artefacts/JASS_NATIVE_ACTIVE_V1.pjtw.gz=candidate.pjtw.gz \
    --out-dir "$IN" --report "$ART/verified-jfi-d.json" >"$W/fetch-jfi-d.log" 2>&1
  timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$JFI_CURRICULUM_ROOT" \
    --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
    --out-dir "$IN" --report "$ART/verified-curriculum.json" >"$W/fetch-curriculum.log" 2>&1
  gunzip -c "$IN/candidate.pjtw.gz" >"$W/candidate.pjtw"
  gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
  read -r CANDIDATE_SHA BOUNDARY_EXE_SHA < <("$PY" - "$IN" "$ART" "$W" \
    "$EXPECTED_BOUNDARY_C_JOB" "$EXPECTED_BOUNDARY_C_ATTEMPT" "$EXPECTED_BOUNDARY_C_CODE_SHA" \
    "$EXPECTED_JFI_D_JOB" "$EXPECTED_JFI_D_ATTEMPT" "$EXPECTED_JFI_D_CODE_SHA" "$JFI_CURRICULUM_SHA" <<'PY'
import hashlib,json,sys
root,art,work=sys.argv[1:4]; bj,ba,bc,dj,da,dc,curr=sys.argv[4:]
load=lambda p:json.load(open(p)); sha=lambda p:hashlib.sha256(open(p,'rb').read()).hexdigest()
bf=load(f'{root}/boundary-c.json'); bv=load(f'{art}/verified-boundary-c.json')
dv=load(f'{art}/verified-jfi-d.json'); dm=load(f'{root}/d-manifest.json')
if (bv.get('job_id'),bv.get('attempt_id'),bv.get('code_sha'),bv.get('result_state'))!=(bj,ba,bc,'completed'):
 raise SystemExit('Boundary-C identity drift')
if bf.get('verdict')!='JFI_BOUNDARY_C_READY' or bf.get('next_boundary')!='GO JFI FORCE':
 raise SystemExit('Boundary-C verdict drift')
if (dv.get('job_id'),dv.get('attempt_id'),dv.get('code_sha'),dv.get('result_state'))!=(dj,da,dc,'completed'):
 raise SystemExit('JFI-D identity drift')
candidate=sha(f'{work}/candidate.pjtw'); curriculum=sha(f'{work}/curriculum.pjtw')
if dm.get('candidate_name')!='JASS_NATIVE_ACTIVE_V1' or dm.get('model',{}).get('sha256')!=candidate:
 raise SystemExit('candidate bytes drift')
if bf.get('candidate',{}).get('sha256')!=candidate or curriculum!=curr or bf.get('curriculum',{}).get('sha256')!=curr:
 raise SystemExit('Boundary-C model link drift')
print(candidate,bf['executable']['sha256'])
PY
  )
  export CANDIDATE_SHA BOUNDARY_EXE_SHA
}

jfi_fetch_force_exclusions(){
  # shellcheck source=t3-f6-runtime-exclusions-v1.sh
  source jobs/templates/t3-f6-runtime-exclusions-v1.sh
  JFI_FORCE_EXCLUDE_SPECS="$T3_F6_FORCE_EXCLUDE_SPECS
t3-f6-1686|r2:jass-data/runs/cpx62-1686-l3-t3-f6-runtime-strength-pool1-v4/20260830T104034Z-0ead13cb|artefacts/pool1-openings.fen
sb1-1743|r2:jass-data/runs/cpx62-1743-l3-sb1-scan-basin-force-pool1-recovery-v10/20260901T173344Z-e05fb469|artefacts/sb1-force-pool1-openings.fen"
  JFI_EXCL_ARGS=(); JFI_EXCL_LABELS=()
  while IFS='|' read -r label prefix remote; do
    [ -n "${label:-}" ] || continue
    timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$prefix" \
      --file "$remote=exclude-$label.fen" --out-dir "$IN" \
      --report "$ART/verified-exclusion-$label.json" >"$W/fetch-exclusion-$label.log" 2>&1
    JFI_EXCL_ARGS+=(--exclude "$IN/exclude-$label.fen"); JFI_EXCL_LABELS+=("$label")
  done <<<"$JFI_FORCE_EXCLUDE_SPECS"
  [ "${#JFI_EXCL_LABELS[@]}" -eq 26 ] || die "JFI exclusion registry count drift"
}

jfi_build_force_engine(){
  local egdir=""
  for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
    ls "$dir"/db*.idx1 >/dev/null 2>&1 && { egdir="$dir"; break; }
  done
  [ -n "$egdir" ] || die "EGDB unavailable"
  export JASS_EGDB_PATH="$egdir" JASS_EGDB_CACHE_MB=128
  python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
  cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
  cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON \
    -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON \
    -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
  cmake --build "$W/build" -j8 --target jass jass_tests >"$W/build.log" 2>&1
  env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB ctest --test-dir "$W/build" --output-on-failure >"$W/ctest.log" 2>&1
  J="$W/build/jass"; export J
  [ "$(sha256sum "$J"|awk '{print $1}')" = "$BOUNDARY_EXE_SHA" ] || die "Boundary-C executable SHA drift"
  for model in candidate curriculum; do
    printf 'hello\nquit\n'|timeout 60 "$J" --pattern "$W/$model.pjtw" >"$W/load-$model.log" 2>&1
    grep -q '^ready' "$W/load-$model.log" || die "$model load failed"
  done
}

jfi_generate_pool(){
  local output="$1" seed="$2"; shift 2; local extra=("$@")
  for pass in a b; do
    "$J" --gen-opening-pool "$JFI_CANDIDATES" "$W/$output-candidates-$pass.fen" 8 32 20 "$seed" \
      >"$W/$output-generate-$pass.log" 2>&1
  done
  cmp -s "$W/$output-candidates-a.fen" "$W/$output-candidates-b.fen" || die "$output nondeterministic"
  "$PY" jobs/tools/select_independent_opening_pool.py --candidates "$W/$output-candidates-a.fen" \
    --expected "$JFI_OPENINGS" "${JFI_EXCL_ARGS[@]}" "${extra[@]}" --generator-seed "$seed" \
    --out "$ART/$output.fen" --manifest "$ART/$output-selector.json" >"$W/$output-select.log" 2>&1
  "$PY" jobs/tools/validate_opening_pool.py --pool "$ART/$output.fen" --expected "$JFI_OPENINGS" \
    --generator-seed "$seed" "${JFI_EXCL_ARGS[@]}" "${extra[@]}" \
    --out "$ART/$output-provenance.json" >"$W/$output-validate.log" 2>&1
  [ "$(grep -c . "$ART/$output.fen")" -eq "$JFI_OPENINGS" ] || die "$output cardinality drift"
}

jfi_run_gate(){
  local pool_file="$1" view="$2" seed="$3" output="$4"; local budget=()
  [ "$view" = native ] && budget=(--movetime 0.1) || budget=(--depth 9)
  timeout -k 120s 25200s "$PY" jobs/tools/run_jass_gate_bounded.py \
    --jass "$J" --pattern-a "$W/candidate.pjtw" --pattern-b "$W/curriculum.pjtw" \
    --search-params-a "$JFI_Q00" --search-params-b "$JFI_Q00" \
    --openings-file "$pool_file" "${budget[@]}" --pairs 1 --max-plies 160 \
    --nshards "$JFI_NSH" --max-parallel "$JFI_PAR" --timeout "$JFI_VIEW_TIMEOUT" \
    --game-timeout "$JFI_GAME_TIMEOUT" --fail-on-game-error --enforce-no-book \
    --paired-bootstrap-samples "$JFI_BOOTSTRAP" --paired-bootstrap-seed "$seed" \
    --work-dir "$W/gate-$output" --out "$ART/$output.json" >"$W/gate-$output.log" 2>&1
}

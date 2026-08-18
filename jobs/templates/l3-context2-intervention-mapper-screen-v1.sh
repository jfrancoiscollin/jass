#!/usr/bin/env bash
# Fit only the 30D conditional mapper on intervention 2M and audit its fixed
# contribution concentration. No PatternEval fit, force, frozen or promotion.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: >"$RES"; : >"$PROG"; echo start >"$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" >"$STAGE"; say "phase=$1"; cp "$STAGE" "$ART/STAGE.txt"; }

CORPUS_ROOT="r2:jass-data/runs/cpx62-1409-l3-context2-intervention-corpus-v1/20260818T184956Z-3465ec72"
ACTIVATION_ROOT="r2:jass-data/runs/cpx62-1410-l3-context2-intervention-activation-audit-v1/20260818T192156Z-3ef19179"
CURRENT_ROOT="r2:jass-data/runs/home-1397-l3-context2-fixed-contribution-audit-v1/20260817T222724Z-f60336ca"
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
SPLIT_SEED=577215; HOLDOUT_MOD=10; EXPECTED_RECORDS=2000000
TARGET_TIMEOUT=10800
MON=""
monitor(){
  ( t0=$(date +%s); while true; do
      { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s)-t0)/60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        [ -f "$ART/intervention-contribution-audit.json" ] && printf 'contribution_ready=1\n'
        [ -f "$ART/intervention-mapper-screen.json" ] && printf 'screen_ready=1\n'
      } >"$PROG.tmp"; mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 120
    done ) & MON="$!"
}
finalize(){
  rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt" 2>/dev/null || true
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -maxdepth 1 -type f -name '*.log' -print0 | tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$IN" "$W" 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^cpx62-([0-9]+)-l3-context2-intervention-mapper-screen-v1$ ]] || die "invalid job nomenclature"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] || die "explicit execution GO missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "job worktree must be detached"
[ -z "$(git status --porcelain)" ] || die "job worktree must start clean"
[ "$(hostname)" = cpx62 ] && [ "$(nproc)" -eq 16 ] || die "CPX 16-CPU contract mismatch"
[ -f "$VENV/.jass-runtime-ready-v1" ] || die "persistent numeric runtime absent; do not reinstall"
PY="$VENV/bin/python"; "$PY" -c 'import numpy,scipy; assert numpy.__version__ and scipy.__version__' || die "numeric runtime invalid"
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 10240 ] || die "less than 10 GiB free ($DFA MiB)"
say "host=$(hostname) nproc=$(nproc) mode=ctx2_intervention_mapper_screen eta_minutes=15-35"
monitor

stage repository-contract-tests
python3 -m py_compile jobs/tools/l3_conditional_targets.py jobs/tools/l3_context2_fixed_contribution_audit.py jobs/tools/l3_context2_intervention_mapper_screen.py
"$PY" -m unittest jobs.tests.test_l3_context2_recompose_targets \
  jobs.tests.test_l3_context2_fixed_contribution_audit \
  jobs.tests.test_l3_context2_intervention_mapper_screen \
  jobs.tests.test_l3_context2_intervention_mapper_template >"$W/tests.log" 2>&1

stage fetch-authenticated-inputs
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CORPUS_ROOT" \
  --file artefacts/context2-intervention-2m.jnnw.gz=intervention.jnnw.gz \
  --file artefacts/context2-intervention-2m.jsm.gz=intervention.jsm.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=corpus-summary.json \
  --out-dir "$IN" --report "$ART/verified-corpus.json" --expected-state completed >"$W/fetch-corpus.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$ACTIVATION_ROOT" \
  --file artefacts/context2-intervention-activation-audit.json=activation-audit.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=activation-summary.json \
  --out-dir "$IN" --report "$ART/verified-activation.json" --expected-state completed >"$W/fetch-activation.log" 2>&1
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$CURRENT_ROOT" \
  --file artefacts/fixed-current2m-contribution-audit.json=current-contribution.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=current-summary.json \
  --out-dir "$IN" --report "$ART/verified-current.json" --expected-state completed >"$W/fetch-current.log" 2>&1

"$PY" - "$ART" "$IN" <<'PY'
import json,sys
from pathlib import Path
art,src=map(Path,sys.argv[1:3])
expected={
 'verified-corpus.json':('cpx62-1409-l3-context2-intervention-corpus-v1','20260818T184956Z-3465ec72','3465ec720eb37c5c9368f2df048831f7381c5839'),
 'verified-activation.json':('cpx62-1410-l3-context2-intervention-activation-audit-v1','20260818T192156Z-3ef19179','3ef1917975dbcb827146033248fcb78984d9e687'),
 'verified-current.json':('home-1397-l3-context2-fixed-contribution-audit-v1','20260817T222724Z-f60336ca','f60336ca7b29e976e14c47eba92223fedd30eebf')}
for name,identity in expected.items():
 row=json.load(open(art/name)); got=(row.get('job_id'),row.get('attempt_id'),row.get('code_sha'))
 if got!=identity or row.get('result_state')!='completed' or row.get('exit_code')!=0:
  raise SystemExit(f'{name}: identity/state drift {got}')
if json.load(open(src/'corpus-summary.json')).get('verdict')!='JASS_CONTEXT2_INTERVENTION_CORPUS_READY': raise SystemExit('corpus verdict drift')
if json.load(open(src/'activation-summary.json')).get('verdict')!='JASS_CONTEXT2_INTERVENTION_ACTIVATION_SCREEN_PASSED': raise SystemExit('activation verdict drift')
if json.load(open(src/'current-summary.json')).get('verdict')!='JASS_CONTEXT2_FIXED_CONTRIBUTION_AUDITED': raise SystemExit('CURRENT verdict drift')
PY

stage reconstruct-opening-group-split
gunzip -c "$IN/intervention.jnnw.gz" >"$W/source.jnnw"
gunzip -c "$IN/intervention.jsm.gz" >"$W/source.jsm"
python3 tools/selfplay_frontier.py split --data "$W/source.jnnw" --meta "$W/source.jsm" \
  --out-data "$W/intervention.jnnw" --out-meta "$W/intervention.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" --manifest "$ART/split.json" >"$W/split.log" 2>&1
read -r RECORDS TRAIN HOLDOUT < <("$PY" - "$ART/split.json" <<'PY'
import json,sys
s=json.load(open(sys.argv[1])); print(s['records'],s['train_records'],s['holdout_records'])
PY
)
[ "$RECORDS" -eq "$EXPECTED_RECORDS" ] && [ "$TRAIN" -gt 0 ] && [ "$HOLDOUT" -gt 0 ] || die "split sizing drift"
rm -f "$W/source.jnnw" "$W/source.jsm"

stage build-production-ctx2-dumper
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j16 --target jass jass_tests >"$W/build.log" 2>&1
"$W/build/jass_tests" >"$W/cpp-tests.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || die "missing jass binary"
timeout 3600s "$J" --dump-conditional-context-v2 "$W/intervention.jnnw" "$W/intervention.ctx2.feat" >"$W/dump.log" 2>&1

stage fit-aligned-conditional-mapper-only
/usr/bin/time -f '%e' -o "$W/mapper.seconds" timeout "$TARGET_TIMEOUT" \
  "$PY" jobs/tools/l3_conditional_targets.py \
    --data "$W/intervention.jnnw" --meta "$W/intervention.jsm" --feat "$W/intervention.ctx2.feat" \
    --context-schema ctx2-phase-tactical-30 --group-by opening_id --row-weighting game_equal \
    --require-convergence --train-count "$TRAIN" --aligned-out "$W/aligned.npy" \
    --shuffled-out "$W/shuffled.npy" --report "$ART/conditional-targets.json" --alpha 0.30 \
    --shuffle-within-wdl --shuffle-phase-bins 4 --fold-count 5 --fold-seed 20260811 \
    --shuffle-seed 20260812 --ridge 1e-4 --max-iterations 100 --tolerance 1e-8 \
    --line-search-steps 20 >"$W/mapper.log" 2>&1

"$PY" - "$ART/conditional-targets.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1])); m=r['mapping']; s=r['shuffle_control']
if r.get('schema')!='jass.l3_conditional_targets.v2' or r.get('context_schema')!='ctx2-phase-tactical-30': raise SystemExit('mapper schema drift')
if (m.get('fold_group')!='opening_id' or not m.get('fold_local_rms') or not m.get('each_game_total_weight_equal') or not m.get('all_groups_fold_disjoint') or m.get('train_holdout_group_overlap')!=0): raise SystemExit('cross-fit contract failed')
fits=[row['fit'] for row in m['folds']]+[m['final_train_fit']['fit']]
if len(fits)!=6 or not all(row.get('converged') for row in fits): raise SystemExit('mapper convergence failed')
if s.get('fixed_point_count')!=0 or not s.get('all_final_target_marginals_preserved'): raise SystemExit('shuffle control drift')
PY

stage replay-fixed-contributions-and-screen
timeout 3600s "$PY" jobs/tools/l3_context2_fixed_contribution_audit.py \
  --data "$W/intervention.jnnw" --meta "$W/intervention.jsm" --feat "$W/intervention.ctx2.feat" \
  --aligned-target "$W/aligned.npy" --conditional-report "$ART/conditional-targets.json" \
  --chunk-size 20000 --report "$ART/intervention-contribution-audit.json" >"$W/contribution.log" 2>&1
timeout 600s "$PY" jobs/tools/l3_context2_intervention_mapper_screen.py \
  --intervention "$ART/intervention-contribution-audit.json" --current "$IN/current-contribution.json" \
  --activation "$IN/activation-audit.json" --out "$ART/intervention-mapper-screen.json" >"$W/screen.log" 2>&1

stage publish-mapper-screen
"$PY" - "$ART" "$EXPECTED_CODE_SHA" "$TRAIN" "$HOLDOUT" <<'PY' | tee -a "$RES"
import json,sys
from pathlib import Path
art=Path(sys.argv[1]); screen=json.load(open(art/'intervention-mapper-screen.json'))
verdict=screen['verdict']; c=screen['intervention']; r=screen['relative_to_current']
payload={'schema':'jass.l3_context2_intervention_mapper_job.v1','verdict':verdict,
 'code_sha':sys.argv[2],'records':2000000,'train_records':int(sys.argv[3]),'holdout_records':int(sys.argv[4]),
 'mapper_fits_run':6,'patterneval_fits_run':0,'screen':screen,'force_games_played':0,
 'frozen_read':False,'promotion_authorized':False,'automatic_next_job':None}
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/f'VERDICT__{verdict}').touch()
for name,value in screen['guards'].items(): (art/f'GUARD__{name}__{str(bool(value)).upper()}').touch()
(art/f'CONCENTRATION__TOP1_PPM_{int(round(c["largest_share"]*1e6))}__TOP3_PPM_{int(round(c["top3_share"]*1e6))}__EFFECTIVE_MILLI_{int(round(c["effective_component_count"]*1000))}').touch()
(art/f'RATIO_VS_CURRENT__TOP1_PPM_{int(round(r["largest_share_ratio"]*1e6))}__TOP3_PPM_{int(round(r["top3_share_ratio"]*1e6))}__EFFECTIVE_PPM_{int(round(r["effective_component_count_ratio"]*1e6))}').touch()
for name in ('PATTERNEVAL_FITS_RUN__0','FORCE_GAMES_PLAYED__0','FROZEN_READ__FALSE','PROMOTION_AUTHORIZED__FALSE','AUTOMATIC_NEXT_JOB__NULL'):
 (art/name).touch()
print(json.dumps(payload,sort_keys=True))
PY
say "$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["verdict"])' "$ART/intervention-mapper-screen.json") mapper_fits=6 patterneval_fits=0 force=0"

#!/usr/bin/env bash
# Preregistered target-only causal gate inside the immutable REPLAY25 recipe.
#
# B_NATIVE is reused byte-for-byte from cpx62-1449.  B_C30 reconstructs the
# exact same rows, metadata, 75/25 sample weights and CURRICULUM prior, then
# changes only the training target to historical CONTEXT_30 aligned alpha 0.30.
# One fit is followed by a fresh two-pool B_C30-vs-B_NATIVE force gate.
# No self-play, frozen read, automatic continuation or automatic promotion.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
cd "$JASS_CODE_DIR"

EXPECTED_BASE_BLOB="ffec746c56930c6236017fe0742017969d27aa5b"
BASE_COPY="$JASS_RESULT_DIR/l3-exploratory-replay-four-arm-doe-v1.certified.sh"
PATCHED="$JASS_RESULT_DIR/l3-replay-context30-target-gate-v1.generated.sh"
PATCHLOG="$JASS_ARTEFACT_DIR/replay-context30-target-substitutions.json"

git cat-file blob "$EXPECTED_BASE_BLOB" >"$BASE_COPY"
[ "$(git hash-object "$BASE_COPY")" = "$EXPECTED_BASE_BLOB" ] || {
  echo "certified 1449 template blob drift" >&2
  exit 1
}

python3 - "$BASE_COPY" "$PATCHED" "$PATCHLOG" <<'PY_RENDER'
import json
import sys
from pathlib import Path

src, dst, log = map(Path, sys.argv[1:4])
text = src.read_text(encoding="utf-8")
changes = []


def one(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one substitution, got {count}")
    text = text.replace(old, new)
    changes.append({"label": label, "count": count, "old": old, "new": new})


one(
    r"^cpx62-[0-9]+-l3-exploratory-replay-four-arm-doe-v1$",
    r"^cpx62-[0-9]+-l3-replay-context30-target-gate-v1$",
    "job_nomenclature",
)
one("NOPEN=1500", "NOPEN=3000", "force_openings_per_pool")
one("CANDIDATES=20000", "CANDIDATES=40000", "opening_candidates")
one("POOL_SEED_1=2026082116", "POOL_SEED_1=2026082211", "fresh_pool_seed_1")
one("POOL_SEED_2=2026082117", "POOL_SEED_2=2026082212", "fresh_pool_seed_2")
one("BOOTSTRAP=100000", "BOOTSTRAP=200000", "paired_bootstrap")
one("force_views_ready=%s/12", "force_views_ready=%s/4", "monitor_force_views")
one(
    'say "experiment=EXPLORATORY_POST_CTX4 D1=1409 D2=1448 arms=A,B,C,D target=native_WDL"',
    'say "experiment=REPLAY_CONTEXT30_TARGET_ONLY issue=552 baseline=B_NATIVE treatment=B_C30"',
    "run_description",
)
one(
    'say "primary=B_vs_A secondary=B_vs_C,C_vs_D force_openings_per_pool=$NOPEN"',
    'say "primary=B_C30_vs_B_NATIVE native=0.1s diagnostic=Q00_d9 force_openings_per_pool=$NOPEN"',
    "protocol_description",
)

last_exclusion = (
    "pool-context3-1428-force-pool2|"
    "r2:jass-data/runs/cpx62-1428-l3-context3-two-pool-force-exact-extras-v2/"
    "20260820T005123Z-17517b38|artefacts/ctx3-force-pool2-openings.fen\""
)
expanded_exclusions = last_exclusion[:-1] + (
    "\npool-replay-doe-1451-pool1|"
    "r2:jass-data/runs/cpx62-1451-l3-exploratory-replay-force-resume-v3/"
    "20260821T063856Z-b9b6d9ad|artefacts/replay-doe-pool1-openings.fen"
    "\npool-replay-doe-1451-pool2|"
    "r2:jass-data/runs/cpx62-1451-l3-exploratory-replay-force-resume-v3/"
    "20260821T063856Z-b9b6d9ad|artefacts/replay-doe-pool2-openings.fen"
    "\npool-replay-b-promotion-1454-pool1|"
    "r2:jass-data/runs/cpx62-1454-l3-replay-b-vs-curriculum-promotion-v1/"
    "20260821T155257Z-9e79c9d4|artefacts/replay-b-promotion-pool1-openings.fen"
    "\npool-replay-b-promotion-1454-pool2|"
    "r2:jass-data/runs/cpx62-1454-l3-replay-b-vs-curriculum-promotion-v1/"
    "20260821T155257Z-9e79c9d4|artefacts/replay-b-promotion-pool2-openings.fen\""
)
one(last_exclusion, expanded_exclusions, "exclude_selection_and_promotion_pools")

start = "stage fetch-and-authenticate-immutable-sources\n"
if text.count(start) != 1:
    raise SystemExit("target-only body splice anchor drift")
head, _ = text.split(start, 1)

body = r'''stage repository-target-only-contract-tests
python3 -m py_compile \
  jobs/tools/l3_replay_context30_targets.py \
  jobs/tools/l3_replay_context30_target_readout.py \
  tools/contextual_replay_mix.py \
  jobs/tools/l3_replay_doe_assemble.py \
  pattern_jass/tools/train_stream_exact.py
"$PY" -m unittest \
  jobs.tests.test_l3_replay_context30_target \
  jobs.tests.test_contextual_replay_mix \
  jobs.tests.test_exact_extras_fit_contract >"$W/tests.log" 2>&1

stage fetch-authenticate-D1-D2-curriculum-and-immutable-B
fetch "$D1_ROOT" verified-D1.json \
  --file artefacts/context2-intervention-2m.jnnw.gz=D1.jnnw.gz \
  --file artefacts/context2-intervention-2m.jsm.gz=D1.jsm.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=D1-summary.json >"$W/fetch-D1.log" 2>&1
fetch "$D2_ROOT" verified-D2.json \
  --file artefacts/context2-intervention-2m.jnnw.gz=D2.jnnw.gz \
  --file artefacts/context2-intervention-2m.jsm.gz=D2.jsm.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=D2-summary.json >"$W/fetch-D2.log" 2>&1
fetch "$CURRICULUM_ROOT" verified-curriculum.json \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=curriculum-summary.json >"$W/fetch-curriculum.log" 2>&1
fetch "$CTX4_ROOT" verified-ctx4.json \
  --file artefacts/JASS_CONTROL_SUMMARY.json=ctx4-summary.json >"$W/fetch-ctx4.log" 2>&1

SOURCE_1449_ROOT="r2:jass-data/runs/cpx62-1449-l3-exploratory-replay-four-arm-doe-v1/20260820T224246Z-7b22be6f"
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$SOURCE_1449_ROOT" \
  --file artefacts/B.pjtw.gz=B_NATIVE.pjtw.gz \
  --file artefacts/model-certificate.json=source-model-certificate.json \
  --file artefacts/BC-replay25-manifest.json=source-BC-replay25-manifest.json \
  --file artefacts/B-optimizer.json=source-B-optimizer.json \
  --file artefacts/B-convergence.json=source-B-convergence.json \
  --file artefacts/B-exact-extras.json=source-B-exact-extras.json \
  --file artefacts/B-weights.json=source-B-weights.json \
  --file artefacts/D1-split.json=source-D1-split.json \
  --file artefacts/D2-split.json=source-D2-split.json \
  --out-dir "$IN" --report "$ART/verified-B-native-source.json" \
  --expected-state failed >"$W/fetch-B-native.log" 2>&1

"$PY" - "$ART" "$IN" <<'PY_AUTH'
import json,sys
from pathlib import Path
art,src=map(Path,sys.argv[1:3])
def load(path): return json.load(open(path))
expected={
 'verified-D1.json':('cpx62-1409-l3-context2-intervention-corpus-v1','20260818T184956Z-3465ec72','3465ec720eb37c5c9368f2df048831f7381c5839','completed',0),
 'verified-D2.json':('cpx62-1448-l3-context2-intervention-corpus-fresh2m-exploratory-v2','20260820T215456Z-4652cdc4','4652cdc49ec98031247cb21fac8521ffe2522f9c','completed',0),
 'verified-curriculum.json':('cpx62-1341-jass-megacorpus-arm-d-fit-v1','20260814T191555Z-18c38a33','18c38a33ae78c9c2e8e2df62fca266da28dacead','completed',0),
 'verified-ctx4.json':('cpx62-1446-l3-context4-uncertainty-screen-v6','20260820T193737Z-f206a837','f206a8373b1324952599bf5f5d93632e52b22e61','completed',0),
 'verified-B-native-source.json':('cpx62-1449-l3-exploratory-replay-four-arm-doe-v1','20260820T224246Z-7b22be6f','7b22be6f4a8898035505d010f872066ac987888a','failed',1),
}
for name,want in expected.items():
 row=load(art/name); got=(row.get('job_id'),row.get('attempt_id'),row.get('code_sha'),row.get('result_state'),row.get('exit_code'))
 if got!=want: raise SystemExit(f'{name}: identity/state drift {got}')
d1=load(src/'D1-summary.json'); d2=load(src/'D2-summary.json')
cur=load(src/'curriculum-summary.json'); ctx4=load(src/'ctx4-summary.json')
cert=load(src/'source-model-certificate.json'); manifest=load(src/'source-BC-replay25-manifest.json')
if d1.get('verdict')!='JASS_CONTEXT2_INTERVENTION_CORPUS_READY' or d1.get('records')!=2_000_000: raise SystemExit('D1 contract drift')
if d2.get('verdict')!='JASS_EXPLORATORY_FRESH2M_D2_READY' or d2.get('records')!=2_000_000: raise SystemExit('D2 contract drift')
if cur.get('verdict')!='JASS_MEGACORPUS_ARM_D_FIT_READY': raise SystemExit('CURRICULUM contract drift')
if ctx4.get('verdict')!='JASS_CONTEXT4_UNCERTAINTY_DECISION_SCREEN_FAILED' or ctx4.get('next_stage_authorized') is not False: raise SystemExit('CTX4 closure drift')
if cert.get('verdict')!='JASS_EXPLORATORY_REPLAY_FOUR_MODELS_READY' or cert.get('target')!='native_JNNW_WDL': raise SystemExit('1449 model certificate drift')
arm=(cert.get('arms') or {}).get('B') or {}; model=(cert.get('models') or {}).get('B') or {}
if arm.get('label')!='REPLAY25' or arm.get('prior')!='CURRICULUM' or arm.get('effective_mass')!={'NEW':.75,'OLD':.25}: raise SystemExit('B recipe drift')
if model.get('prior_mean')!='CURRICULUM' or (model.get('convergence') or {}).get('success') is not True: raise SystemExit('B convergence/prior drift')
exact=model.get('exact_extras') or {}
if (exact.get('mg') or {}).get('max_abs')!=0 or (exact.get('eg') or {}).get('max_abs')!=0: raise SystemExit('B exact-extras drift')
recipe=cert.get('fit_recipe') or {}
if (recipe.get('architecture'),recipe.get('target'),recipe.get('l2'),recipe.get('gtol'),recipe.get('max_iterations'),recipe.get('lbfgs_maxcor')) != ('8cf_exact_fold_tempo_120_extras','wdl',1e-5,1e-4,2000,20): raise SystemExit('B fit recipe drift')
if manifest.get('seed')!=2026082106 or manifest.get('requested_effective_loss_mass')!={'OLD':.25,'NEW':.75}: raise SystemExit('source replay manifest drift')
if (manifest.get('targets') or {}).get('external_targets_copied') is not False: raise SystemExit('source B unexpectedly used external targets')
PY_AUTH

gunzip -t "$IN/D1.jnnw.gz"; gunzip -t "$IN/D1.jsm.gz"
gunzip -t "$IN/D2.jnnw.gz"; gunzip -t "$IN/D2.jsm.gz"
gunzip -t "$IN/curriculum.pjtw.gz"; gunzip -t "$IN/B_NATIVE.pjtw.gz"
gunzip -c "$IN/D1.jnnw.gz" >"$W/D1.raw.jnnw"
gunzip -c "$IN/D1.jsm.gz" >"$W/D1.raw.jsm"
gunzip -c "$IN/D2.jnnw.gz" >"$W/D2.raw.jnnw"
gunzip -c "$IN/D2.jsm.gz" >"$W/D2.raw.jsm"
gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"
gunzip -c "$IN/B_NATIVE.pjtw.gz" >"$W/B_NATIVE.pjtw"
[ "$(sha256sum "$W/curriculum.pjtw" | awk '{print $1}')" = "$CURRICULUM_SHA" ] || die "CURRICULUM raw hash drift"
"$PY" jobs/tools/assert_corpus_wdl.py --data "$W/D1.raw.jnnw" >"$W/D1-wdl.log" 2>&1
"$PY" jobs/tools/assert_corpus_wdl.py --data "$W/D2.raw.jnnw" >"$W/D2-wdl.log" 2>&1

stage reproduce-opening-splits-and-byte-identical-B-training-inputs
python3 tools/selfplay_frontier.py split --data "$W/D1.raw.jnnw" --meta "$W/D1.raw.jsm" \
  --out-data "$W/D1.split.jnnw" --out-meta "$W/D1.split.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" --manifest "$ART/D1-split.json" >"$W/D1-split.log" 2>&1
python3 tools/selfplay_frontier.py split --data "$W/D2.raw.jnnw" --meta "$W/D2.raw.jsm" \
  --out-data "$W/D2.split.jnnw" --out-meta "$W/D2.split.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" --manifest "$ART/D2-split.json" >"$W/D2-split.log" 2>&1
read -r D1_TRAIN D2_TRAIN < <("$PY" - "$ART/D1-split.json" "$ART/D2-split.json" <<'PY_SPLIT'
import json,sys
a,b=(json.load(open(path)) for path in sys.argv[1:3])
for row in (a,b):
 if row.get('records')!=2_000_000 or row.get('split_unit')!='opening_id' or not row.get('tail_is_holdout') or row.get('seed')!=577215 or row.get('holdout_mod')!=10: raise SystemExit('split contract drift')
print(a['train_records'],b['train_records'])
PY_SPLIT
)
[ "$D1_TRAIN" -gt 0 ] && [ "$D2_TRAIN" -gt 0 ] || die "empty split train"

"$PY" tools/contextual_replay_mix.py \
  --old-data "$W/D1.split.jnnw" --old-meta "$W/D1.split.jsm" --old-train-count "$D1_TRAIN" \
  --new-data "$W/D2.split.jnnw" --new-meta "$W/D2.split.jsm" --new-train-count "$D2_TRAIN" \
  --old-share 0.25 --new-share 0.75 --seed "$REPLAY_SEED" \
  --out-data "$DATA/BC-replay25.jnnw" --out-meta "$DATA/BC-replay25.jsm" \
  --out-weights "$DATA/BC-replay25-weights.npy" --manifest "$ART/BC-replay25-manifest.json" \
  >"$W/replay-mix.log" 2>&1

"$PY" - "$IN/source-BC-replay25-manifest.json" "$ART/BC-replay25-manifest.json" \
  "$ART/replay-reconstruction-certificate.json" <<'PY_REPLAY'
import json,sys
from pathlib import Path
source,current=(json.load(open(path)) for path in sys.argv[1:3]); out=Path(sys.argv[3])
for key in ('schema','operation','seed','selection_scope','holdout_rows_read_into_training','requested_effective_loss_mass','realised_effective_loss_mass','row_budget','selection','metadata'):
 if current.get(key)!=source.get(key): raise SystemExit(f'replay reconstruction drift: {key}')
for cohort in ('OLD','NEW'):
 for key in ('data_sha256','meta_sha256','records','train_records','holdout_records_excluded','metadata_schema'):
  if current['sources'][cohort].get(key)!=source['sources'][cohort].get(key): raise SystemExit(f'replay source drift: {cohort}/{key}')
for key in ('data_sha256','meta_sha256','weights_sha256'):
 if current['outputs'].get(key)!=source['outputs'].get(key): raise SystemExit(f'replay output hash drift: {key}')
if current['sample_weights']['sha256']!=source['sample_weights']['sha256']: raise SystemExit('replay weights hash drift')
if current['targets']['external_targets_copied'] or source['targets']['external_targets_copied']: raise SystemExit('native replay source target drift')
payload={'schema':'jass.l3_replay_context30_reconstruction.v1','verdict':'JASS_REPLAY25_B_INPUTS_BYTE_IDENTICAL_TO_1449','source_attempt':'20260820T224246Z-7b22be6f','data_sha256':current['outputs']['data_sha256'],'meta_sha256':current['outputs']['meta_sha256'],'weights_sha256':current['outputs']['weights_sha256'],'records':current['row_budget']['mixed_train_records'],'effective_mass':current['realised_effective_loss_mass'],'same_rows':True,'same_metadata':True,'same_sample_weights':True,'holdout_rows_read_into_training':0}
out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY_REPLAY
rm -f "$W/D1.raw.jnnw" "$W/D1.raw.jsm" "$W/D2.raw.jnnw" "$W/D2.raw.jsm"

stage build-common-certified-engine-and-BC-features
git diff --quiet 7b22be6f4a8898035505d010f872066ac987888a HEAD -- src pattern_jass/tools || die "engine/training semantics drift since B_NATIVE fit"
EGDIR=""
for dir in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do
  ls "$dir"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$dir"; break; }
done
[ -n "$EGDIR" ] || die "EGDB unavailable"
export JASS_EGDB_PATH="$EGDIR" JASS_EGDB_CACHE_MB="$CACHE_MB"
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf >"$W/gen8.log" 2>&1
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
[ "$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')" -eq 4251528 ] || die "8cf geometry drift"
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON \
  -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
  >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass jass_tests >"$W/build.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB \
  ctest --test-dir "$W/build" --output-on-failure >"$W/ctest.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || die "missing jass binary"
timeout 10800s "$J" --dump-eval-features "$DATA/BC-replay25.jnnw" "$DATA/BC.feat" >"$W/features-BC.log" 2>&1
WIDTH=$(python3 -c 'import struct,sys;f=open(sys.argv[1],"rb");assert f.read(4)==b"FEAT";print(struct.unpack("<II",f.read(8))[1])' "$DATA/BC.feat")
[ "$WIDTH" -eq "$EXPECTED_EXTRAS" ] || die "BC feature width=$WIDTH"

stage reconstruct-historical-context30-target-on-exact-B-rows
TARGET_BUILDER_BLOB="968b253084e272d69f61f952e47ec71471aaadf5"
TARGET_DIR="$W/historical-context30-builder"
mkdir -p "$TARGET_DIR"
git cat-file blob "$TARGET_BUILDER_BLOB" >"$TARGET_DIR/l3_conditional_targets.py"
[ "$(git hash-object "$TARGET_DIR/l3_conditional_targets.py")" = "$TARGET_BUILDER_BLOB" ] || die "historical target builder blob drift"
cp jobs/tools/l3_replay_context30_targets.py "$TARGET_DIR/l3_replay_context30_targets.py"
"$PY" -m py_compile "$TARGET_DIR/l3_conditional_targets.py" "$TARGET_DIR/l3_replay_context30_targets.py"
/usr/bin/time -f '%e' -o "$W/context30-target.seconds" timeout 14400s \
  "$PY" "$TARGET_DIR/l3_replay_context30_targets.py" \
    --data "$DATA/BC-replay25.jnnw" --meta "$DATA/BC-replay25.jsm" --feat "$DATA/BC.feat" \
    --out "$DATA/BC-context30.npy" --report "$ART/BC-context30-targets.json" \
    >"$W/context30-target.log" 2>&1
"$PY" - "$ART/BC-replay25-manifest.json" "$ART/BC-context30-targets.json" "$TARGET_BUILDER_BLOB" <<'PY_TARGET'
import json,sys
mix,target=(json.load(open(path)) for path in sys.argv[1:3]); blob=sys.argv[3]
if target.get('operation')!='historical_context30_aligned_train_only_oof' or target.get('records')!=mix['row_budget']['mixed_train_records']: raise SystemExit('context30 target sizing drift')
if target.get('context_schema')!='ctx1-legacy-120' or target.get('target',{}).get('name')!='CONTEXT_30_ALIGNED_alpha_0.30': raise SystemExit('context30 target recipe drift')
recipe=target.get('fixed_recipe') or {}
if recipe != {'fold_count':5,'fold_seed':20260811,'fold_group':'game_id','row_weighting':'uniform','ridge':1e-4,'max_iterations':50,'tolerance':1e-8,'line_search_steps':20}: raise SystemExit(f'context30 mapper recipe drift: {recipe}')
if target['source']['data_sha256']!=mix['outputs']['data_sha256'] or target['source']['meta_sha256']!=mix['outputs']['meta_sha256']: raise SystemExit('context30 source hash drift')
adapter=(target.get('mapping') or {}).get('adapter') or {}
if adapter.get('synthetic_row_used_in_oof_training') is not False or adapter.get('synthetic_row_included_in_output_targets') is not False or adapter.get('historical_train_recipe_unchanged') is not True: raise SystemExit('train-only adapter contract drift')
if target.get('safety',{}).get('holdout_leakage')!=0 or target.get('safety',{}).get('frozen_cohorts_read')!=0: raise SystemExit('context30 target safety drift')
target['historical_target_builder_blob']=blob
open(sys.argv[2],'w').write(json.dumps(target,indent=2,sort_keys=True)+'\n')
PY_TARGET

certify_exact_extras(){
  local model="$1" out="$2"
  "$PY" - "$model" "$out" <<'PY_EXACT'
import json,struct,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,'pattern_jass/tools')
from exact_extras import exact_extras_residuals
p,out=Path(sys.argv[1]),Path(sys.argv[2]); raw=p.read_bytes()
magic,version,scale,n_patterns,n_extras=struct.unpack_from('<5I',raw,0)
if magic!=0x57544A50 or (version&255)!=3 or scale<=0 or n_patterns!=4251528 or n_extras!=120 or len(raw)!=20+8*(n_patterns+n_extras): raise SystemExit('PJTW structure drift')
base=20+2*n_patterns*4
mg=np.frombuffer(raw,dtype='<i4',count=n_extras,offset=base).copy()
eg=np.frombuffer(raw,dtype='<i4',count=n_extras,offset=base+n_extras*4).copy()
result={'mg':exact_extras_residuals(mg),'eg':exact_extras_residuals(eg)}
if result['mg']['max_abs']!=0 or result['eg']['max_abs']!=0: raise SystemExit(f'exact extras residual {result}')
out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
PY_EXACT
}

read -r WMIN WMAX < <("$PY" - "$ART/BC-replay25-manifest.json" <<'PY_WEIGHT'
import json,sys
row=json.load(open(sys.argv[1]))['sample_weights']; print(row['min'],row['max'])
PY_WEIGHT
)

stage fit-only-B-C30-with-identical-replay-prior-and-budget
/usr/bin/time -f '%e' -o "$W/fit-B_C30.seconds" timeout "$FIT_TIMEOUT" \
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" PYTHONUNBUFFERED=1 \
  "$PY" pattern_jass/tools/train_stream_exact.py \
    --data "$DATA/BC-replay25.jnnw" --feat "$DATA/BC.feat" --out "$W/B_C30.pjtw" \
    --target external --target-values "$DATA/BC-context30.npy" \
    --targets-report "$ART/B_C30-target-consumption.json" \
    --loss logistic --exact-fold --tempo-stage \
    --l2 1e-5 --max-iter "$MAXIT" --chunk "$CHUNK" \
    --lbfgs-maxcor 20 --lbfgs-gtol 1e-4 --prune \
    --prior-mean "$W/curriculum.pjtw" --prior-decay 0 \
    --sample-weights "$DATA/BC-replay25-weights.npy" --weight-min "$WMIN" --weight-max "$WMAX" \
    --weights-report "$ART/B_C30-weights.json" \
    --optimizer-report "$ART/B_C30-optimizer.json" >"$W/fit-B_C30.log" 2>&1
[ -s "$W/B_C30.pjtw" ] || die "B_C30 produced no model"
"$PY" jobs/tools/verify_optimizer_convergence.py \
  --report "$ART/B_C30-optimizer.json" --label B_C30 \
  --expected-max-iterations "$MAXIT" --expected-maxcor 20 --expected-gtol 1e-4 \
  --receipt "$ART/B_C30-convergence.json"
certify_exact_extras "$W/B_C30.pjtw" "$ART/B_C30-exact-extras.json"
gzip -n -c "$W/B_C30.pjtw" >"$ART/B_C30.pjtw.gz"
cp "$IN/B_NATIVE.pjtw.gz" "$ART/B_NATIVE.pjtw.gz"

stage publish-target-only-model-certificate
"$PY" - "$W" "$IN" "$ART" "$EXPECTED_CODE_SHA" "$CURRICULUM_SHA" "$TARGET_BUILDER_BLOB" <<'PY_MODELS'
import hashlib,json,struct,sys
from pathlib import Path
w,src,art=map(Path,sys.argv[1:4]); code,parent_sha,builder=sys.argv[4:7]
def load(path): return json.load(open(path))
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1<<20),b''): h.update(block)
 return h.hexdigest()
def structure(path):
 raw=Path(path).read_bytes(); magic,version,scale,np_,ne=struct.unpack_from('<5I',raw,0)
 if magic!=0x57544A50 or (version&255)!=3 or scale<=0 or np_!=4251528 or ne!=120 or len(raw)!=20+8*(np_+ne): raise SystemExit(f'{path}: structure drift')
 return {'version':version,'scale':scale,'n_patterns':np_,'n_extras':ne,'size_bytes':len(raw)}
source=load(src/'source-model-certificate.json'); source_mix=load(src/'source-BC-replay25-manifest.json')
current_mix=load(art/'BC-replay25-manifest.json'); reconstruction=load(art/'replay-reconstruction-certificate.json')
target=load(art/'BC-context30-targets.json'); consumption=load(art/'B_C30-target-consumption.json')
source_b=(source.get('models') or {}).get('B') or {}; source_arm=(source.get('arms') or {}).get('B') or {}
b_native_sha=sha(w/'B_NATIVE.pjtw'); b_c30_sha=sha(w/'B_C30.pjtw')
if b_native_sha!=source_b.get('model_raw_sha256'): raise SystemExit('B_NATIVE model hash drift')
if b_native_sha==b_c30_sha: raise SystemExit('target-only treatment unexpectedly identical')
for key in ('data_sha256','meta_sha256','weights_sha256'):
 if current_mix['outputs'][key]!=source_mix['outputs'][key]: raise SystemExit(f'shared input drift: {key}')
if consumption.get('source',{}).get('sha256')!=target['output']['targets_sha256']: raise SystemExit('B_C30 consumed wrong target')
if target['source']['data_sha256']!=current_mix['outputs']['data_sha256'] or target['source']['meta_sha256']!=current_mix['outputs']['meta_sha256']: raise SystemExit('target/input alignment drift')
exact=load(art/'B_C30-exact-extras.json'); convergence=load(art/'B_C30-convergence.json')
if exact['mg']['max_abs']!=0 or exact['eg']['max_abs']!=0 or convergence.get('success') is not True: raise SystemExit('B_C30 technical gate drift')
if reconstruction.get('verdict')!='JASS_REPLAY25_B_INPUTS_BYTE_IDENTICAL_TO_1449': raise SystemExit('reconstruction certificate drift')
fit_recipe={'architecture':'8cf_exact_fold_tempo_120_extras','loss':'logistic','l2':1e-5,'gtol':1e-4,'max_iterations':2000,'lbfgs_maxcor':20,'chunk':20000,'dense_extras_constraint':'projected_inside_fit','prior_decay':0}
payload={'schema':'jass.l3_replay_context30_models.v1','verdict':'JASS_REPLAY_CONTEXT30_MODELS_READY','issue':552,'code_sha':code,
 'baseline':{'label':'B_REPLAY25_NATIVE','target':'native_JNNW_WDL','source_job':'cpx62-1449-l3-exploratory-replay-four-arm-doe-v1','source_attempt':'20260820T224246Z-7b22be6f','model_raw_sha256':b_native_sha,'model_gz_sha256':sha(art/'B_NATIVE.pjtw.gz'),'structure':structure(w/'B_NATIVE.pjtw'),'optimizer':load(src/'source-B-optimizer.json'),'convergence':load(src/'source-B-convergence.json'),'exact_extras':load(src/'source-B-exact-extras.json')},
 'candidate':{'label':'B_REPLAY25_CONTEXT30','target':'CONTEXT_30_ALIGNED_alpha_0.30','model_raw_sha256':b_c30_sha,'model_gz_sha256':sha(art/'B_C30.pjtw.gz'),'structure':structure(w/'B_C30.pjtw'),'optimizer':load(art/'B_C30-optimizer.json'),'convergence':convergence,'exact_extras':exact,'fit_seconds':float((w/'fit-B_C30.seconds').read_text()),'target_builder_seconds':float((w/'context30-target.seconds').read_text()),'target_sha256':target['output']['targets_sha256'],'target_builder_blob':builder},
 'shared_contract':{'single_scientific_difference':'training_target','same_data':True,'same_metadata':True,'same_sample_weights':True,'same_prior':True,'same_fit_recipe':True,'data_sha256':current_mix['outputs']['data_sha256'],'meta_sha256':current_mix['outputs']['meta_sha256'],'weights_sha256':current_mix['outputs']['weights_sha256'],'effective_mass':current_mix['realised_effective_loss_mass'],'prior':{'label':'CURRICULUM','raw_sha256':parent_sha},'fit_recipe':fit_recipe,'source_arm_recipe':source_arm,'reconstruction':reconstruction},
 'target_certificate':target,'models_distinct':True,'models_reused':1,'refits':1,'new_selfplay':0,'frozen_cohorts_read':0,'strength_games_played':0,'promotion_authorized':False,'automatic_next_job':None}
(art/'model-certificate.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
(art/'VERDICT__JASS_REPLAY_CONTEXT30_MODELS_READY').touch()
PY_MODELS

for model in B_NATIVE B_C30; do
  printf 'hello\nquit\n' | timeout 60 "$J" --pattern "$W/$model.pjtw" >"$W/load-$model.log" 2>&1
  grep -q '^ready' "$W/load-$model.log" || die "$model does not load"
done

stage fetch-all-historical-force-pools
EXCL_ARGS=(); EXCL_NAMES=()
while IFS='|' read -r label prefix remote_path; do
  [ -n "${label:-}" ] || continue
  fetch "$prefix" "verified-exclude-$label.json" \
    --file "$remote_path=$label.fen" >"$W/fetch-$label.log" 2>&1 ||
    die "historical pool fetch failed: $label"
  EXCL_ARGS+=(--exclude "$IN/$label.fen"); EXCL_NAMES+=("$label")
done <<<"$EXCLUDE_SPECS"
[ "${#EXCL_NAMES[@]}" -eq 23 ] || die "historical exclusion count drift"

generate_pool(){
  local index="$1"
  local seed="$2"
  local out="replay-context30-target-pool${index}-openings"
  local extra=("${EXCL_ARGS[@]}")
  if [ "$index" -eq 2 ]; then extra+=(--exclude "$ART/replay-context30-target-pool1-openings.fen"); fi
  for pass in a b; do
    "$J" --gen-opening-pool "$CANDIDATES" "$W/pool${index}-cand-$pass.fen" \
      8 32 20 "$seed" >"$W/pool${index}-gen-$pass.log" 2>&1
  done
  cmp -s "$W/pool${index}-cand-a.fen" "$W/pool${index}-cand-b.fen" || die "pool$index candidates nondeterministic"
  python3 jobs/tools/select_independent_opening_pool.py \
    --candidates "$W/pool${index}-cand-a.fen" --expected "$NOPEN" \
    "${extra[@]}" --generator-seed "$seed" \
    --out "$ART/$out.fen" --manifest "$ART/$out.json" >"$W/pool${index}-select.log" 2>&1
  python3 jobs/tools/validate_opening_pool.py \
    --pool "$ART/$out.fen" --expected "$NOPEN" --generator-seed "$seed" \
    "${extra[@]}" --out "$ART/$out-provenance.json" >"$W/pool${index}-validate.log" 2>&1
}

stage generate-certify-two-fresh-target-only-pools
generate_pool 1 "$POOL_SEED_1"
generate_pool 2 "$POOL_SEED_2"
COMMON=$(grep -Fx -f "$ART/replay-context30-target-pool1-openings.fen" \
  "$ART/replay-context30-target-pool2-openings.fen" | grep -c . || true)
[ "$COMMON" -eq 0 ] || die "fresh target-only pools overlap by $COMMON"
for index in 1 2; do
  file="$ART/replay-context30-target-pool${index}-openings.fen"
  [ "$(grep -c . "$file" || true)" -eq "$NOPEN" ] || die "pool$index cardinality drift"
  for label in "${EXCL_NAMES[@]}"; do
    overlap=$(grep -Fx -f "$IN/$label.fen" "$file" | grep -c . || true)
    [ "$overlap" -eq 0 ] || die "pool$index overlaps $label by $overlap"
  done
done

"$PY" - "$ART" "$NOPEN" "$POOL_SEED_1" "$POOL_SEED_2" "${EXCL_NAMES[@]}" <<'PY_POOLS'
import hashlib,json,sys
from pathlib import Path
art=Path(sys.argv[1]); n=int(sys.argv[2]); seeds=list(map(int,sys.argv[3:5])); exclusions=sys.argv[5:]
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def rows(path): return [value for raw in path.read_text().splitlines() if (value:=raw.split('#',1)[0].strip())]
pools=[]; sets=[]
for index,seed in enumerate(seeds,1):
 stem=art/f'replay-context30-target-pool{index}-openings'; fen=stem.with_suffix('.fen')
 values=rows(fen); manifest=json.load(open(stem.with_suffix('.json'))); provenance=json.load(open(art/f'{stem.name}-provenance.json')); digest=sha(fen)
 if len(values)!=n or len(set(values))!=n: raise SystemExit(f'pool{index}: cardinality drift')
 if manifest.get('sha256')!=digest or manifest.get('generator_seed')!=seed or manifest.get('overlap_records')!=0: raise SystemExit(f'pool{index}: selector drift')
 if provenance.get('generator_seed')!=seed or provenance.get('overlap_records')!=0: raise SystemExit(f'pool{index}: provenance drift')
 sets.append(set(values)); pools.append({'pool_index':index,'openings':n,'seed':seed,'sha256':digest,'fen':fen.name,'selector_manifest_sha256':sha(stem.with_suffix('.json')),'provenance_sha256':sha(art/f'{stem.name}-provenance.json')})
if sets[0]&sets[1]: raise SystemExit('fresh target-only pools overlap')
payload={'schema':'jass.l3_replay_context30_pools.v1','verdict':'JASS_REPLAY_CONTEXT30_TWO_FRESH_POOLS_READY','pools':pools,'mutually_disjoint':True,'mutual_overlap':0,'historical_exclusions':exclusions,'historical_exclusion_count':len(exclusions),'all_historical_overlaps_zero':True,'deterministic_generation_repeated':True,'promotion_authorized':False}
(art/'pool-certificate.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY_POOLS

stage publish-locked-target-only-force-protocol
cat >"$ART/force-protocol.json" <<'JSON_PROTOCOL'
{
  "schema": "jass.l3_replay_context30_force_protocol.v1",
  "issue": 552,
  "candidate": "B_REPLAY25_CONTEXT30",
  "baseline": "B_REPLAY25_NATIVE",
  "single_scientific_difference": "training_target",
  "openings_per_pool": 3000,
  "bootstrap_samples": 200000,
  "pool_seeds": {"pool1": 2026082211, "pool2": 2026082212},
  "gate_seeds": {
    "pool1": {"native": 2026082213, "q00": 2026082214},
    "pool2": {"native": 2026082215, "q00": 2026082216}
  },
  "combined_seeds": {"native": 2026082217, "q00": 2026082218},
  "paired_colours": true,
  "native_movetime_seconds": 0.1,
  "q00_depth": 9,
  "primary_view": "native_movetime_0.1",
  "diagnostic_view": "Q00_depth9",
  "q00_can_override_native": false,
  "positive_gate": {
    "both_native_pool_points_above_half": true,
    "inter_pool_compatible_95": true,
    "combined_native_ci95_lower_above_half": true,
    "combined_native_probability_above_half_min": 0.975
  },
  "automatic_promotion": false,
  "promotion_authorized": false
}
JSON_PROTOCOL

run_gate(){
  local pool="$1" view="$2" seed="$3"
  local budget=()
  [ "$view" = native ] && budget=(--movetime "$MOVETIME") || budget=(--depth "$FORCE_DEPTH")
  timeout -k 120s 25200s "$PY" jobs/tools/run_jass_gate_bounded.py \
    --jass "$J" --pattern-a "$W/B_C30.pjtw" --pattern-b "$W/B_NATIVE.pjtw" \
    --search-params-a "$Q00" --search-params-b "$Q00" \
    --openings-file "$ART/replay-context30-target-pool${pool}-openings.fen" \
    "${budget[@]}" --pairs 1 --max-plies 160 --nshards "$NSH" --max-parallel "$PAR" \
    --timeout 21600 --game-timeout 180 --paired-bootstrap-samples "$BOOTSTRAP" \
    --paired-bootstrap-seed "$seed" --work-dir "$W/gate-pool$pool-$view" \
    --out "$FORCE/pool$pool-$view.json" >"$W/force-pool$pool-$view.log" 2>&1
}

for pool in 1 2; do
  for view in native q00; do
    seed=$("$PY" - "$ART/force-protocol.json" "$pool" "$view" <<'PY_SEED'
import json,sys
row=json.load(open(sys.argv[1])); print(row['gate_seeds'][f'pool{sys.argv[2]}'][sys.argv[3]])
PY_SEED
)
    stage "target-only-force-pool$pool-$view"
    run_gate "$pool" "$view" "$seed" || die "pool$pool/$view gate failed"
    say "pool=$pool view=$view games=$((2*NOPEN)) complete"
  done
done

stage audit-and-publish-terminal-target-only-verdict
"$PY" jobs/tools/l3_replay_context30_target_readout.py \
  --protocol "$ART/force-protocol.json" --pool-certificate "$ART/pool-certificate.json" \
  --model-certificate "$ART/model-certificate.json" \
  --pool1-native "$FORCE/pool1-native.json" --pool1-q00 "$FORCE/pool1-q00.json" \
  --pool2-native "$FORCE/pool2-native.json" --pool2-q00 "$FORCE/pool2-q00.json" \
  --out "$ART/replay-context30-target-readout.json" >"$W/target-only-readout.log" 2>&1
cp "$ART/replay-context30-target-readout.json" "$ART/JASS_CONTROL_SUMMARY.json"
VERDICT=$("$PY" -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
NEXT=$("$PY" -c 'import json,sys;print(json.load(open(sys.argv[1])).get("next_stage_recommended") or "NONE")' "$ART/JASS_CONTROL_SUMMARY.json")
: >"$ART/VERDICT__$VERDICT"
: >"$ART/GAMES_TOTAL__24000"
: >"$ART/MODELS_REUSED__1"
: >"$ART/REFITS__1"
: >"$ART/NEW_SELFPLAY__0"
: >"$ART/FROZEN_COHORTS_READ__0"
: >"$ART/PROMOTION_AUTHORIZED__FALSE"
: >"$ART/AUTOMATIC_NEXT_JOB__NULL"
if [ "$NEXT" = DIRECT_B_CONTEXT30_VS_CURRICULUM_GATE ]; then
  : >"$ART/NEXT_STAGE_RECOMMENDED__DIRECT_B_CONTEXT30_VS_CURRICULUM_GATE"
else
  : >"$ART/NEXT_STAGE_RECOMMENDED__NONE"
fi
stage completed
say "$VERDICT games=24000 refits=1 selfplay=0 frozen=0 next=$NEXT promotion=false"
'''

text = head + body
changes.append({
    "label": "replace_four_arm_body_with_target_only_context30_fit_and_force_gate",
    "baseline": "immutable_1449_B_NATIVE",
    "treatment": "one_B_C30_refit",
    "single_scientific_difference": "training_target",
    "force_games": 24000,
    "refits": 1,
})

required = (
    "B_REPLAY25_CONTEXT30", "B_REPLAY25_NATIVE",
    "CONTEXT_30_ALIGNED_alpha_0.30", "NOPEN=3000",
    "BOOTSTRAP=200000", "POOL_SEED_1=2026082211",
    "POOL_SEED_2=2026082212", "historical_exclusion_count",
    "pool-replay-doe-1451-pool1", "pool-replay-doe-1451-pool2",
    "pool-replay-b-promotion-1454-pool1", "pool-replay-b-promotion-1454-pool2",
    "--target external", "--sample-weights",
    "--prior-mean \"$W/curriculum.pjtw\"", "REFITS__1",
    "NEW_SELFPLAY__0", "FROZEN_COHORTS_READ__0",
    "PROMOTION_AUTHORIZED__FALSE", "AUTOMATIC_NEXT_JOB__NULL",
)
for token in required:
    if token not in text:
        raise SystemExit(f"target-only protocol token missing: {token}")
for forbidden in (
    "stage sequential-four-arm-fits", "fit_arm A ", "fit_arm B ",
    "--gen-selfplay", "PROMOTION_AUTHORIZED__TRUE",
):
    if forbidden in text:
        raise SystemExit(f"target-only script contains forbidden path: {forbidden}")
if text.count("pool-replay-doe-1451-pool") != 2:
    raise SystemExit("1451 exclusion count drift")
if text.count("pool-replay-b-promotion-1454-pool") != 2:
    raise SystemExit("1454 exclusion count drift")

dst.write_text(text, encoding="utf-8")
log.write_text(json.dumps({
    "schema": "jass.l3_replay_context30_target_substitutions.v1",
    "issue": 552,
    "base_blob": "ffec746c56930c6236017fe0742017969d27aa5b",
    "baseline_source": "cpx62-1449/20260820T224246Z-7b22be6f/B",
    "treatment": "same_B_inputs_and_CURRICULUM_prior_with_CONTEXT30_target",
    "historical_target_builder_blob": "968b253084e272d69f61f952e47ec71471aaadf5",
    "scientific_force_protocol": {
        "openings_per_pool": 3000,
        "pools": 2,
        "views": ["native_0.1", "Q00_d9"],
        "bootstrap_samples": 200000,
        "games_total": 24000
    },
    "models_reused": 1,
    "refits": 1,
    "new_selfplay": 0,
    "frozen_read": false,
    "automatic_promotion": false,
    "changes": changes
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY_RENDER

bash -n "$PATCHED"
chmod +x "$PATCHED"
diff -u "$BASE_COPY" "$PATCHED" >"$JASS_ARTEFACT_DIR/replay-context30-target.patch" || true
exec bash "$PATCHED"

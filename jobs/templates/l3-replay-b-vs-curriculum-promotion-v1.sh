#!/usr/bin/env bash
# Preregistered force-only promotion gate for immutable REPLAY25 arm B.
#
# Renders from the certified 1449 end-to-end template so engine, Q00, pool
# selection and bounded-gate topology remain inherited. It replaces every
# data/fit stage with immutable B/CURRICULUM authentication, then runs a fresh
# two-pool succession gate. No refit, self-play, frozen read or auto-promotion.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
cd "$JASS_CODE_DIR"

EXPECTED_BASE_BLOB="ffec746c56930c6236017fe0742017969d27aa5b"
BASE_COPY="$JASS_RESULT_DIR/l3-exploratory-replay-four-arm-doe-v1.certified.sh"
PATCHED="$JASS_RESULT_DIR/l3-replay-b-vs-curriculum-promotion-v1.generated.sh"
PATCHLOG="$JASS_ARTEFACT_DIR/replay-b-promotion-substitutions.json"

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
    r"^cpx62-[0-9]+-l3-replay-b-vs-curriculum-promotion-v1$",
    "job_nomenclature",
)
one("NOPEN=1500", "NOPEN=3000", "promotion_openings_per_pool")
one("CANDIDATES=20000", "CANDIDATES=40000", "promotion_candidate_pool_size")
one("POOL_SEED_1=2026082116", "POOL_SEED_1=2026082201", "fresh_pool_seed_1")
one("POOL_SEED_2=2026082117", "POOL_SEED_2=2026082202", "fresh_pool_seed_2")
one("BOOTSTRAP=100000", "BOOTSTRAP=200000", "promotion_bootstrap_size")
one(
    'say "experiment=EXPLORATORY_POST_CTX4 D1=1409 D2=1448 arms=A,B,C,D target=native_WDL"',
    'say "experiment=REPLAY_B_PROMOTION candidate=B_REPLAY25 baseline=CURRICULUM issue=548"',
    "run_description",
)
one(
    'say "primary=B_vs_A secondary=B_vs_C,C_vs_D force_openings_per_pool=$NOPEN"',
    'say "primary=native_0.1 diagnostic=Q00_d9 force_openings_per_pool=$NOPEN promotion_auto=false"',
    "protocol_description",
)
one("force_views_ready=%s/12", "force_views_ready=%s/4", "monitor_force_view_count")

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
    "20260821T063856Z-b9b6d9ad|artefacts/replay-doe-pool2-openings.fen\""
)
one(last_exclusion, expanded_exclusions, "exclude_both_1451_force_pools")

start = "stage fetch-and-authenticate-immutable-sources\n"
if text.count(start) != 1:
    raise SystemExit("promotion body splice anchor drift")
head, _ = text.split(start, 1)

body = r'''stage promotion-readout-contract-tests
"$PY" -m unittest jobs.tests.test_l3_replay_b_promotion_readout \
  >"$W/test-promotion-readout.log" 2>&1

stage fetch-authenticate-immutable-candidate-and-champion
SOURCE_1449_ROOT="r2:jass-data/runs/cpx62-1449-l3-exploratory-replay-four-arm-doe-v1/20260820T224246Z-7b22be6f"
timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$SOURCE_1449_ROOT" \
  --file artefacts/B.pjtw.gz=B.pjtw.gz \
  --file artefacts/model-certificate.json=source-model-certificate.json \
  --out-dir "$IN" --report "$ART/verified-B-source.json" \
  --expected-state failed >"$W/fetch-B.log" 2>&1
fetch "$CURRICULUM_ROOT" verified-curriculum-promotion.json \
  --file artefacts/D-c-prior-then-current.pjtw.gz=curriculum.pjtw.gz \
  --file artefacts/JASS_CONTROL_SUMMARY.json=curriculum-summary.json \
  >"$W/fetch-curriculum-promotion.log" 2>&1

gunzip -t "$IN/B.pjtw.gz"
gunzip -t "$IN/curriculum.pjtw.gz"
gunzip -c "$IN/B.pjtw.gz" >"$W/B.pjtw"
gunzip -c "$IN/curriculum.pjtw.gz" >"$W/curriculum.pjtw"

"$PY" - "$ART" "$IN" "$W" "$CURRICULUM_SHA" <<'PY_MODELS'
import hashlib,json,sys
from pathlib import Path
art,src,work=map(Path,sys.argv[1:4]); curriculum_sha=sys.argv[4]
def load(path): return json.load(open(path))
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1<<20),b''): h.update(block)
 return h.hexdigest()
source_receipt=load(art/'verified-B-source.json')
expected=('cpx62-1449-l3-exploratory-replay-four-arm-doe-v1','20260820T224246Z-7b22be6f','7b22be6f4a8898035505d010f872066ac987888a','failed',1)
got=(source_receipt.get('job_id'),source_receipt.get('attempt_id'),source_receipt.get('code_sha'),source_receipt.get('result_state'),source_receipt.get('exit_code'))
if got!=expected: raise SystemExit(f'B source identity/state drift: {got}')
champ_receipt=load(art/'verified-curriculum-promotion.json')
champ_expected=('cpx62-1341-jass-megacorpus-arm-d-fit-v1','20260814T191555Z-18c38a33','18c38a33ae78c9c2e8e2df62fca266da28dacead','completed',0)
champ_got=(champ_receipt.get('job_id'),champ_receipt.get('attempt_id'),champ_receipt.get('code_sha'),champ_receipt.get('result_state'),champ_receipt.get('exit_code'))
if champ_got!=champ_expected: raise SystemExit(f'CURRICULUM identity/state drift: {champ_got}')
source=load(src/'source-model-certificate.json')
if source.get('verdict')!='JASS_EXPLORATORY_REPLAY_FOUR_MODELS_READY': raise SystemExit('1449 model verdict drift')
if source.get('target')!='native_JNNW_WDL': raise SystemExit('B target semantics drift')
if source.get('strength_games_played')!=0 or source.get('frozen_cohorts_read')!=0 or source.get('promotion_authorized') is not False: raise SystemExit('1449 model scope drift')
arms=source.get('arms') or {}; b_arm=arms.get('B') or {}
if b_arm.get('label')!='REPLAY25' or b_arm.get('prior')!='CURRICULUM': raise SystemExit('B arm recipe drift')
if b_arm.get('effective_mass')!={'NEW':0.75,'OLD':0.25}: raise SystemExit('B effective mass drift')
b=(source.get('models') or {}).get('B') or {}
conv=b.get('convergence') or {}; exact=b.get('exact_extras') or {}
if conv.get('success') is not True: raise SystemExit('B convergence drift')
if (exact.get('mg') or {}).get('max_abs')!=0 or (exact.get('eg') or {}).get('max_abs')!=0: raise SystemExit('B exact-extras drift')
if b.get('prior_mean')!='CURRICULUM': raise SystemExit('B prior identity drift')
b_sha=sha(work/'B.pjtw')
if b_sha!=b.get('model_raw_sha256'): raise SystemExit('B model raw hash drift')
champ_summary=load(src/'curriculum-summary.json')
if champ_summary.get('verdict')!='JASS_MEGACORPUS_ARM_D_FIT_READY': raise SystemExit('CURRICULUM certificate drift')
champ_sha=sha(work/'curriculum.pjtw')
if champ_sha!=curriculum_sha: raise SystemExit('CURRICULUM raw hash drift')
if b_sha==champ_sha: raise SystemExit('B unexpectedly byte-identical to CURRICULUM')
payload={
 'schema':'jass.l3_replay_b_promotion_models.v1',
 'verdict':'JASS_REPLAY_B_PROMOTION_MODELS_AUTHENTICATED',
 'candidate':{'label':'B_REPLAY25','source_job':expected[0],'source_attempt':expected[1],
              'model_raw_sha256':b_sha,'model_gz_sha256':b.get('model_gz_sha256'),
              'recipe':b_arm,'convergence':conv,'exact_extras':exact},
 'baseline':{'label':'CURRICULUM','source_job':champ_expected[0],
             'source_attempt':champ_expected[1],'model_raw_sha256':champ_sha},
 'distinct':True,'models_reused':True,'refits':0,'new_selfplay':0,
 'frozen_cohorts_read':0,'promotion_authorized':False,'automatic_next_job':None,
}
(art/'model-certificate.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY_MODELS

: >"$ART/MODELS_REUSED__TRUE"
: >"$ART/REFITS__0"
: >"$ART/NEW_SELFPLAY__0"

git diff --quiet 7b22be6f4a8898035505d010f872066ac987888a HEAD -- src pattern_jass/tools ||
  die "engine/training semantics drift since candidate fit"

stage build-common-certified-engine
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
for model in B curriculum; do
  printf 'hello\nquit\n' | timeout 60 "$J" --pattern "$W/$model.pjtw" \
    >"$W/load-$model.log" 2>&1
  grep -q '^ready' "$W/load-$model.log" || die "$model model does not load"
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
[ "${#EXCL_NAMES[@]}" -eq 21 ] || die "historical exclusion count drift"

generate_pool(){
  local index="$1"
  local seed="$2"
  local out="replay-b-promotion-pool${index}-openings"
  local extra=("${EXCL_ARGS[@]}")
  if [ "$index" -eq 2 ]; then
    extra+=(--exclude "$ART/replay-b-promotion-pool1-openings.fen")
  fi
  for pass in a b; do
    "$J" --gen-opening-pool "$CANDIDATES" "$W/pool${index}-cand-$pass.fen" \
      8 32 20 "$seed" >"$W/pool${index}-gen-$pass.log" 2>&1
  done
  cmp -s "$W/pool${index}-cand-a.fen" "$W/pool${index}-cand-b.fen" ||
    die "pool$index candidates nondeterministic"
  python3 jobs/tools/select_independent_opening_pool.py \
    --candidates "$W/pool${index}-cand-a.fen" --expected "$NOPEN" \
    "${extra[@]}" --generator-seed "$seed" \
    --out "$ART/$out.fen" --manifest "$ART/$out.json" \
    >"$W/pool${index}-select.log" 2>&1 || die "pool$index selection failed"
  python3 jobs/tools/validate_opening_pool.py \
    --pool "$ART/$out.fen" --expected "$NOPEN" --generator-seed "$seed" \
    "${extra[@]}" --out "$ART/$out-provenance.json" \
    >"$W/pool${index}-validate.log" 2>&1 || die "pool$index validation failed"
}

stage generate-certify-fresh-promotion-pool1
generate_pool 1 "$POOL_SEED_1"
stage generate-certify-fresh-promotion-pool2
generate_pool 2 "$POOL_SEED_2"
COMMON=$(grep -Fx -f "$ART/replay-b-promotion-pool1-openings.fen" \
  "$ART/replay-b-promotion-pool2-openings.fen" | grep -c . || true)
[ "$COMMON" -eq 0 ] || die "fresh promotion pools overlap by $COMMON"
for index in 1 2; do
  file="$ART/replay-b-promotion-pool${index}-openings.fen"
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
def rows(path): return [x for raw in path.read_text().splitlines() if (x:=raw.split('#',1)[0].strip())]
pools=[]; sets=[]
for index,seed in enumerate(seeds,1):
 stem=art/f'replay-b-promotion-pool{index}-openings'; fen=stem.with_suffix('.fen')
 values=rows(fen); manifest=json.load(open(stem.with_suffix('.json')))
 provenance=json.load(open(art/f'{stem.name}-provenance.json')); digest=sha(fen)
 if len(values)!=n or len(set(values))!=n: raise SystemExit(f'pool{index}: cardinality/uniqueness drift')
 if manifest.get('sha256')!=digest or manifest.get('generator_seed')!=seed or manifest.get('overlap_records')!=0: raise SystemExit(f'pool{index}: selector certificate drift')
 if provenance.get('generator_seed')!=seed or provenance.get('overlap_records')!=0: raise SystemExit(f'pool{index}: provenance drift')
 sets.append(set(values)); pools.append({'pool_index':index,'openings':n,'seed':seed,
  'sha256':digest,'fen':fen.name,'selector_manifest_sha256':sha(stem.with_suffix('.json')),
  'provenance_sha256':sha(art/f'{stem.name}-provenance.json')})
if sets[0]&sets[1]: raise SystemExit('fresh pools are not mutually disjoint')
payload={'schema':'jass.l3_replay_b_promotion_pools.v1',
 'verdict':'JASS_REPLAY_B_PROMOTION_TWO_FRESH_POOLS_READY','pools':pools,
 'mutually_disjoint':True,'mutual_overlap':0,'historical_exclusions':exclusions,
 'historical_exclusion_count':len(exclusions),'all_historical_overlaps_zero':True,
 'deterministic_generation_repeated':True,'promotion_authorized':False}
(art/'pool-certificate.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY_POOLS

stage publish-locked-promotion-protocol
cat >"$ART/promotion-force-protocol.json" <<'JSON_PROTOCOL'
{
  "schema": "jass.l3_replay_b_promotion_force_protocol.v1",
  "issue": 548,
  "candidate": "B_REPLAY25",
  "baseline": "CURRICULUM",
  "openings_per_pool": 3000,
  "bootstrap_samples": 200000,
  "pool_seeds": {"pool1": 2026082201, "pool2": 2026082202},
  "gate_seeds": {
    "pool1": {"native": 2026082203, "q00": 2026082204},
    "pool2": {"native": 2026082205, "q00": 2026082206}
  },
  "combined_seeds": {"native": 2026082207, "q00": 2026082208},
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
    --jass "$J" --pattern-a "$W/B.pjtw" --pattern-b "$W/curriculum.pjtw" \
    --search-params-a "$Q00" --search-params-b "$Q00" \
    --openings-file "$ART/replay-b-promotion-pool${pool}-openings.fen" \
    "${budget[@]}" --pairs 1 --max-plies 160 --nshards "$NSH" --max-parallel "$PAR" \
    --timeout 21600 --game-timeout 180 --paired-bootstrap-samples "$BOOTSTRAP" \
    --paired-bootstrap-seed "$seed" --work-dir "$W/gate-pool$pool-$view" \
    --out "$FORCE/pool$pool-$view.json" >"$W/force-pool$pool-$view.log" 2>&1
}

for pool in 1 2; do
  for view in native q00; do
    seed=$("$PY" - "$ART/promotion-force-protocol.json" "$pool" "$view" <<'PY_SEED'
import json,sys
r=json.load(open(sys.argv[1])); print(r['gate_seeds'][f'pool{sys.argv[2]}'][sys.argv[3]])
PY_SEED
)
    stage "promotion-force-pool$pool-$view"
    run_gate "$pool" "$view" "$seed" || die "pool$pool/$view gate failed"
    say "pool=$pool view=$view games=$((2*NOPEN)) complete"
  done
done

stage audit-and-publish-promotion-verdict
"$PY" jobs/tools/l3_replay_b_promotion_readout.py \
  --protocol "$ART/promotion-force-protocol.json" \
  --pool-certificate "$ART/pool-certificate.json" \
  --model-certificate "$ART/model-certificate.json" \
  --pool1-native "$FORCE/pool1-native.json" --pool1-q00 "$FORCE/pool1-q00.json" \
  --pool2-native "$FORCE/pool2-native.json" --pool2-q00 "$FORCE/pool2-q00.json" \
  --out "$ART/replay-b-promotion-readout.json" >"$W/promotion-readout.log" 2>&1
cp "$ART/replay-b-promotion-readout.json" "$ART/JASS_CONTROL_SUMMARY.json"
VERDICT=$("$PY" -c 'import json,sys;print(json.load(open(sys.argv[1]))["verdict"])' "$ART/JASS_CONTROL_SUMMARY.json")
REVIEW=$("$PY" -c 'import json,sys;print(str(json.load(open(sys.argv[1]))["promotion_review_recommended"]).lower())' "$ART/JASS_CONTROL_SUMMARY.json")
: >"$ART/VERDICT__$VERDICT"
: >"$ART/GAMES_TOTAL__24000"
: >"$ART/MODELS_REUSED__TRUE"
: >"$ART/REFITS__0"
: >"$ART/NEW_SELFPLAY__0"
: >"$ART/FROZEN_COHORTS_READ__0"
: >"$ART/PROMOTION_AUTHORIZED__FALSE"
: >"$ART/AUTOMATIC_NEXT_JOB__NULL"
if [ "$REVIEW" = true ]; then
  : >"$ART/PROMOTION_REVIEW_RECOMMENDED__TRUE"
else
  : >"$ART/PROMOTION_REVIEW_RECOMMENDED__FALSE"
fi
stage completed
say "$VERDICT games=24000 models_reused=true refits=0 frozen=0 promotion_review=$REVIEW auto_promotion=false"
'''

text = head + body
changes.append({
    "label": "replace_data_fit_and_multicontrast_body_with_promotion_gate",
    "candidate": "immutable_1449_B",
    "baseline": "immutable_1341_CURRICULUM",
    "force_games": 24000,
    "refits": 0,
})

required = (
    "NOPEN=3000", "CANDIDATES=40000", "BOOTSTRAP=200000",
    "POOL_SEED_1=2026082201", "POOL_SEED_2=2026082202",
    "JASS_REPLAY25_B_VS_CURRICULUM", "historical_exclusion_count",
    "pool-replay-doe-1451-pool1", "pool-replay-doe-1451-pool2",
    "--pattern-a \"$W/B.pjtw\" --pattern-b \"$W/curriculum.pjtw\"",
    "PROMOTION_AUTHORIZED__FALSE", "promotion_review_recommended",
)
for token in required:
    if token not in text:
        raise SystemExit(f"promotion protocol token missing: {token}")
for forbidden in ("fit_arm A ", "stage sequential-four-arm-fits", "--prior-mean", "--target wdl"):
    if forbidden in text:
        raise SystemExit(f"promotion script contains forbidden fit path: {forbidden}")
if text.count("pool-replay-doe-1451-pool") != 2:
    raise SystemExit("1451 exclusion count drift")

dst.write_text(text, encoding="utf-8")
log.write_text(json.dumps({
    "schema": "jass.l3_replay_b_promotion_substitutions.v1",
    "issue": 548,
    "base_blob": "ffec746c56930c6236017fe0742017969d27aa5b",
    "candidate_source": "cpx62-1449/20260820T224246Z-7b22be6f/B",
    "baseline_source": "cpx62-1341/20260814T191555Z-18c38a33/CURRICULUM",
    "scientific_force_protocol": {
        "openings_per_pool": 3000,
        "pools": 2,
        "views": ["native_0.1", "Q00_d9"],
        "bootstrap_samples": 200000,
        "games_total": 24000,
    },
    "models_reused": True,
    "refits": 0,
    "new_selfplay": 0,
    "frozen_read": False,
    "automatic_promotion": False,
    "changes": changes,
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY_RENDER

bash -n "$PATCHED"
chmod +x "$PATCHED"
diff -u "$BASE_COPY" "$PATCHED" >"$JASS_ARTEFACT_DIR/replay-b-promotion.patch" || true
exec bash "$PATCHED"

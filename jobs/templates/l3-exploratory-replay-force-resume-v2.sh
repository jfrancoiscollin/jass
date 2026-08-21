#!/usr/bin/env bash
# Technical force-only resume for the exploratory replay DOE.
#
# Reuses the four immutable, converged, exact-extras models and static readout
# produced by failed run 1449. It fixes only the Bash pool-name expansion defect
# and resumes at fresh-pool generation; it performs zero refits/self-play.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
cd "$JASS_CODE_DIR"

EXPECTED_BASE_BLOB="ffec746c56930c6236017fe0742017969d27aa5b"
BASE_COPY="$JASS_RESULT_DIR/l3-exploratory-replay-four-arm-doe-v1.certified.sh"
PATCHED="$JASS_RESULT_DIR/l3-exploratory-replay-force-resume-v2.generated.sh"
PATCHLOG="$JASS_ARTEFACT_DIR/force-resume-substitutions.json"

git cat-file blob "$EXPECTED_BASE_BLOB" >"$BASE_COPY"
[ "$(git hash-object "$BASE_COPY")" = "$EXPECTED_BASE_BLOB" ] || {
  echo "certified 1449 template blob drift" >&2
  exit 1
}

python3 - "$BASE_COPY" "$PATCHED" "$PATCHLOG" <<'PY'
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
    r"^cpx62-[0-9]+-l3-exploratory-replay-force-resume-v2$",
    "job_nomenclature",
)

# Proven shell defect: all RHS expansions of a `local` builtin happen before
# the new local `index` exists, so `out` became `replay-doe-pool-openings`.
one(
    '  local index="$1" seed="$2" out="replay-doe-pool${index}-openings"',
    '  local index="$1"\n  local seed="$2"\n  local out="replay-doe-pool${index}-openings"',
    "pool_output_name_expansion",
)

start = "stage fetch-and-authenticate-immutable-sources\n"
end = "stage fetch-historical-force-pools\n"
if text.count(start) != 1 or text.count(end) != 1:
    raise SystemExit("resume splice anchors drift")
left, remainder = text.split(start, 1)
_, right = remainder.split(end, 1)
resume = r'''stage fetch-authenticate-immutable-1449-models
SOURCE_1449_ROOT="r2:jass-data/runs/cpx62-1449-l3-exploratory-replay-four-arm-doe-v1/20260820T224246Z-7b22be6f"
fetch "$SOURCE_1449_ROOT" verified-1449-models.json \
  --file artefacts/A.pjtw.gz=A.pjtw.gz \
  --file artefacts/B.pjtw.gz=B.pjtw.gz \
  --file artefacts/C.pjtw.gz=C.pjtw.gz \
  --file artefacts/D.pjtw.gz=D.pjtw.gz \
  --file artefacts/model-certificate.json=model-certificate.json \
  --file artefacts/static-readout.json=static-readout.json \
  --file artefacts/assembly.json=assembly.json \
  --file artefacts/BC-replay25-manifest.json=BC-replay25-manifest.json \
  --expected-state failed >"$W/fetch-1449-models.log" 2>&1

for arm in A B C D; do
  gunzip -t "$IN/$arm.pjtw.gz"
  gunzip -c "$IN/$arm.pjtw.gz" >"$W/$arm.pjtw"
done
cp "$IN/model-certificate.json" "$ART/model-certificate.json"
cp "$IN/static-readout.json" "$ART/static-readout.json"
cp "$IN/assembly.json" "$ART/assembly.json"
cp "$IN/BC-replay25-manifest.json" "$ART/BC-replay25-manifest.json"

"$PY" - "$ART/verified-1449-models.json" "$IN" "$W" <<'PY_RESUME'
import hashlib,json,sys
from pathlib import Path
receipt_path,src,work=Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3])
receipt=json.load(open(receipt_path))
expected=('cpx62-1449-l3-exploratory-replay-four-arm-doe-v1','20260820T224246Z-7b22be6f','7b22be6f4a8898035505d010f872066ac987888a','failed',1)
got=(receipt.get('job_id'),receipt.get('attempt_id'),receipt.get('code_sha'),receipt.get('result_state'),receipt.get('exit_code'))
if got!=expected: raise SystemExit(f'1449 identity/state drift: {got}')
model=json.load(open(src/'model-certificate.json'))
static=json.load(open(src/'static-readout.json'))
assembly=json.load(open(src/'assembly.json'))
replay=json.load(open(src/'BC-replay25-manifest.json'))
if model.get('verdict')!='JASS_EXPLORATORY_REPLAY_FOUR_MODELS_READY': raise SystemExit('1449 model verdict drift')
if model.get('strength_games_played')!=0 or model.get('frozen_cohorts_read')!=0 or model.get('promotion_authorized') is not False: raise SystemExit('1449 model scope drift')
if model.get('ctx4_verdict_unchanged')!='JASS_CONTEXT4_UNCERTAINTY_DECISION_SCREEN_FAILED': raise SystemExit('CTX4 closure drift')
if set((model.get('models') or {}).keys())!=set('ABCD'): raise SystemExit('four model identities missing')
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(1<<20),b''): h.update(block)
 return h.hexdigest()
for arm,row in model['models'].items():
 conv=row.get('convergence') or {}; exact=row.get('exact_extras') or {}
 if conv.get('success') is not True: raise SystemExit(f'{arm}: convergence not green')
 if (exact.get('mg') or {}).get('max_abs')!=0 or (exact.get('eg') or {}).get('max_abs')!=0: raise SystemExit(f'{arm}: exact extras drift')
 if sha(work/f'{arm}.pjtw')!=row.get('model_raw_sha256'): raise SystemExit(f'{arm}: raw model hash drift')
if static != model.get('static_readout'): raise SystemExit('standalone/embedded static readout mismatch')
if assembly.get('holdout_rows_read_into_training')!=0 or replay.get('holdout_rows_read_into_training')!=0: raise SystemExit('holdout leakage certificate drift')
PY_RESUME

stage build-common-engine-for-reused-models
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
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j8 --target jass jass_tests >"$W/build.log" 2>&1
env -u JASS_EGDB_PATH -u JASS_EGDB_CACHE_MB ctest --test-dir "$W/build" --output-on-failure >"$W/ctest.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || die "missing jass binary"
for arm in A B C D; do
  printf 'hello\nquit\n' | timeout 60 "$J" --pattern "$W/$arm.pjtw" >"$W/load-$arm.log" 2>&1
  grep -q '^ready' "$W/load-$arm.log" || die "$arm model does not load"
done

: >"$ART/MODELS_REUSED_FROM_1449__4"
: >"$ART/REFITS__0"
: >"$ART/NEW_SELFPLAY__0"

stage fetch-historical-force-pools
'''
text = left + resume + right
changes.append({
    "label": "resume_from_certified_1449_models",
    "replaced_section": "fetch/split/assemble/features/four-fits/static/model-publish",
    "refits": 0,
})

one(
    ': >"$ART/FITS_RUN__4"',
    ': >"$ART/FITS_REUSED__4"\n: >"$ART/REFITS__0"',
    "terminal_fit_scope_markers",
)
one(
    'say "$VERDICT fits=4 force_games=36000 frozen=false promotion=false automatic_next_job=null"',
    'say "$VERDICT fits_reused=4 refits=0 force_games=36000 frozen=false promotion=false automatic_next_job=null"',
    "terminal_message",
)

required = (
    'NOPEN=1500', 'POOL_SEED_1=2026082116', 'POOL_SEED_2=2026082117',
    'BOOTSTRAP=100000', 'MOVETIME=0.1', 'FORCE_DEPTH=9',
    '"primary_contrast": "B_vs_A"', '"B_vs_C"', '"C_vs_D"',
    'historical_exclusion_count', 'PROMOTION_AUTHORIZED__FALSE',
)
for token in required:
    if token not in text:
        raise SystemExit(f"locked force protocol token missing: {token}")
if 'fit_arm A ' in text or 'stage sequential-four-arm-fits' in text:
    raise SystemExit('resume script still contains a production fit invocation')
if 'local index="$1" seed="$2" out=' in text:
    raise SystemExit('pool-name expansion defect survived')

dst.write_text(text, encoding="utf-8")
log.write_text(json.dumps({
    "schema":"jass.exploratory_replay_force_resume_substitutions.v2",
    "source_job":"cpx62-1449-l3-exploratory-replay-four-arm-doe-v1",
    "source_attempt":"20260820T224246Z-7b22be6f",
    "base_blob":"ffec746c56930c6236017fe0742017969d27aa5b",
    "technical_defect":"bash_local_rhs_expanded_before_local_index_assignment",
    "scientific_force_protocol_changed":False,
    "models_reused":4,
    "refits":0,
    "changes":changes,
},indent=2,sort_keys=True)+"\n",encoding="utf-8")
PY

bash -n "$PATCHED"
chmod +x "$PATCHED"
diff -u "$BASE_COPY" "$PATCHED" >"$JASS_ARTEFACT_DIR/force-resume.patch" || true
exec bash "$PATCHED"

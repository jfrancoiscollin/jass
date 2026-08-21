#!/usr/bin/env bash
# Technical wrapper over force-resume v2.
# Fixes only the fetch of failed-but-certified source 1449: the historical
# helper appends expected-state=completed, so v3 calls fetch_result_files.py
# directly with expected-state=failed. Scientific force protocol is unchanged.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
cd "$JASS_CODE_DIR"
BASE="jobs/templates/l3-exploratory-replay-force-resume-v2.sh"
EXPECTED_BASE_BLOB="2c681159e8eeb84882b35c93cd03b2acb47e8244"
PATCHED="$JASS_RESULT_DIR/l3-exploratory-replay-force-resume-v3.generated.sh"
PATCHLOG="$JASS_ARTEFACT_DIR/force-resume-v3-substitutions.json"
[ "$(git hash-object "$BASE")" = "$EXPECTED_BASE_BLOB" ] || {
  echo "force-resume v2 blob drift" >&2
  exit 1
}
python3 - "$BASE" "$PATCHED" "$PATCHLOG" <<'PY'
import json,sys
from pathlib import Path
src,dst,log=map(Path,sys.argv[1:4])
text=src.read_text(encoding='utf-8')
changes=[]
def one(old,new,label):
 global text
 count=text.count(old)
 if count!=1: raise SystemExit(f'{label}: expected one substitution, got {count}')
 text=text.replace(old,new)
 changes.append({'label':label,'old':old,'new':new,'count':count})
one(
 r'r"^cpx62-[0-9]+-l3-exploratory-replay-force-resume-v2$"',
 r'r"^cpx62-[0-9]+-l3-exploratory-replay-force-resume-v3$"',
 'job_nomenclature_v3',
)
one(
 'fetch "$SOURCE_1449_ROOT" verified-1449-models.json \\\n',
 'timeout 1800s python3 jobs/tools/fetch_result_files.py --prefix "$SOURCE_1449_ROOT" \\\n',
 'direct_failed_source_fetch',
)
one(
 '  --file artefacts/BC-replay25-manifest.json=BC-replay25-manifest.json \\\n  --expected-state failed >"$W/fetch-1449-models.log" 2>&1',
 '  --file artefacts/BC-replay25-manifest.json=BC-replay25-manifest.json \\\n  --out-dir "$IN" --report "$ART/verified-1449-models.json" \\\n  --expected-state failed >"$W/fetch-1449-models.log" 2>&1',
 'failed_source_fetch_output_contract',
)
if 'fetch "$SOURCE_1449_ROOT"' in text:
 raise SystemExit('completed-state helper still used for failed source')
if '--expected-state failed' not in text or '--report "$ART/verified-1449-models.json"' not in text:
 raise SystemExit('failed-source fetch contract missing')
dst.write_text(text,encoding='utf-8')
log.write_text(json.dumps({
 'schema':'jass.exploratory_replay_force_resume_v3_substitutions.v1',
 'base_blob':'2c681159e8eeb84882b35c93cd03b2acb47e8244',
 'technical_change_only':True,
 'scientific_force_protocol_changed':False,
 'models_reused':4,'refits':0,
 'changes':changes,
},indent=2,sort_keys=True)+'\n',encoding='utf-8')
PY
bash -n "$PATCHED"
chmod +x "$PATCHED"
diff -u "$BASE" "$PATCHED" >"$JASS_ARTEFACT_DIR/force-resume-v3.patch" || true
exec bash "$PATCHED"

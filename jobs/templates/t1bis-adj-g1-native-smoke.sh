#!/usr/bin/env bash
# Miniature fail-closed smoke for the native runner-v3 T1-bis path.
set -Eeuo pipefail
: "${JASS_CODE_DIR:?}"
: "${JASS_RESULT_DIR:?}"
: "${JASS_ARTEFACT_DIR:?}"
cd "$JASS_CODE_DIR"
INPUT_DIR="$JASS_RESULT_DIR/inputs"
mkdir -p "$INPUT_DIR" "$JASS_ARTEFACT_DIR"
python3 jobs/tools/fetch_t1bis_inputs.py \
  --remote "${T1BIS_INPUT_REMOTE:-r2:jass-data/inputs/t1bis-adj-g1/v1}" \
  --out "$INPUT_DIR" \
  --rclone "${RCLONE_BIN:-rclone}" \
  | tee "$JASS_ARTEFACT_DIR/input-verification.json"
[ -f "$INPUT_DIR/VERIFIED" ] || { echo "input verification marker missing" >&2; exit 40; }
python3 - "$INPUT_DIR/manifest.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1], encoding='utf-8'))
required = {
 'bootstrap-build-matched.pjtw.gz',
 'champion-gen2-mmto.pjtw.gz',
 'corpus-mix2M.jnnw.gz',
 'conversion_pool_train_v2.fen',
 'conv_self_eval_strat_v2.fen',
}
seen = {x['name'] for x in m['files']}
missing = sorted(required - seen)
if missing:
    raise SystemExit('missing required inputs: ' + ', '.join(missing))
PY
# The smoke deliberately stops before scientific generation. It validates the
# immutable input contract and the 16 GiB runner filesystem path only.
printf '%s\n' \
  'state=smoke-ready' \
  'full_relaunch_allowed=false' \
  'reason=native scientific launcher not yet merged and smoke-approved' \
  > "$JASS_ARTEFACT_DIR/SMOKE.txt"

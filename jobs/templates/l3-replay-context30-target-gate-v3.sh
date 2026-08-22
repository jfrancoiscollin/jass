#!/usr/bin/env bash
# Technical launcher v3 for the preregistered REPLAY25 context30 target gate.
#
# The scientific v1 renderer and its v2 validator remain pinned byte-for-byte.
# v3 removes the fragile nested-exec startup: it first materialises and audits
# the final scientific script, then executes that exact file in a separate shell
# while retaining outer render/execution logs. No scientific source, target,
# row, weight, prior, seed, pool, budget, bootstrap or threshold is changed.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
cd "$JASS_CODE_DIR"

EXPECTED_V2_BLOB="24dbb03bb9f1827b4777decc06c8d19f2ca013db"
V2_SOURCE="jobs/templates/l3-replay-context30-target-gate-v2.sh"
V2_COPY="$JASS_RESULT_DIR/l3-replay-context30-target-gate-v2.certified.sh"
GENERATED_FINAL="$JASS_RESULT_DIR/l3-replay-context30-target-gate-v1.generated.sh"
FINAL="$JASS_ARTEFACT_DIR/replay-context30-rendered.sh"
RENDER_LOG="$JASS_ARTEFACT_DIR/replay-context30-v3-render.log"
EXECUTION_LOG="$JASS_ARTEFACT_DIR/replay-context30-v3-execution.log"
RENDER_RECEIPT="$JASS_ARTEFACT_DIR/replay-context30-v3-render-receipt.json"
EXECUTION_RECEIPT="$JASS_ARTEFACT_DIR/replay-context30-v3-execution-receipt.json"

mkdir -p "$JASS_RESULT_DIR" "$JASS_ARTEFACT_DIR"
cp "$V2_SOURCE" "$V2_COPY"
[ "$(git hash-object "$V2_COPY")" = "$EXPECTED_V2_BLOB" ] || {
  echo "context30 v2 launcher blob drift" >&2
  exit 1
}
chmod +x "$V2_COPY"
: >"$RENDER_LOG"
: >"$EXECUTION_LOG"

set +e
JASS_REPLAY_CONTEXT30_RENDER_ONLY=1 \
  bash -x "$V2_COPY" > >(tee -a "$RENDER_LOG") 2>&1
RENDER_RC=$?
set -e

# On CPX the pinned renderer has been observed to write the complete valid final
# script and then return 1 in its outer copy layer. Recover only that exact
# generated output; the full syntax/token/fit-count audit below remains fatal.
RECOVERED_FROM_GENERATED=0
if [ ! -f "$FINAL" ] && [ -f "$GENERATED_FINAL" ]; then
  cp "$GENERATED_FINAL" "$FINAL"
  RECOVERED_FROM_GENERATED=1
fi

python3 - "$FINAL" "$RENDER_LOG" "$RENDER_RECEIPT" "$RENDER_RC" \
  "$EXPECTED_V2_BLOB" "$RECOVERED_FROM_GENERATED" <<'PY_RENDER_AUDIT'
import hashlib,json,sys
from pathlib import Path
final,log,out=map(Path,sys.argv[1:4]); rc=int(sys.argv[4]); v2=sys.argv[5]
recovered=bool(int(sys.argv[6]))
def sha(path):
 h=hashlib.sha256(); h.update(path.read_bytes()); return h.hexdigest()
text=final.read_text(encoding='utf-8') if final.is_file() else ''
required=(
 'B_REPLAY25_CONTEXT30','B_REPLAY25_NATIVE',
 'CONTEXT_30_ALIGNED_alpha_0.30','NOPEN=3000','CANDIDATES=40000',
 'BOOTSTRAP=200000','POOL_SEED_1=2026082211','POOL_SEED_2=2026082212',
 'pool-replay-doe-1451-pool1','pool-replay-doe-1451-pool2',
 'pool-replay-b-promotion-1454-pool1','pool-replay-b-promotion-1454-pool2',
 '--target external','--sample-weights','--prior-mean "$W/curriculum.pjtw"',
 '--pattern-a "$W/B_C30.pjtw" --pattern-b "$W/B_NATIVE.pjtw"',
 'GAMES_TOTAL__24000','REFITS__1','NEW_SELFPLAY__0',
 'FROZEN_COHORTS_READ__0','PROMOTION_AUTHORIZED__FALSE',
)
missing=[token for token in required if token not in text]
forbidden=(
 'stage sequential-four-arm-fits','fit_arm A ','fit_arm B ',
 '--gen-selfplay','PROMOTION_AUTHORIZED__TRUE',
)
surviving=[token for token in forbidden if token in text]
fit_count=text.count('"$PY" pattern_jass/tools/train_stream_exact.py')
syntax_ok=False
if final.is_file():
 import subprocess
 syntax_ok=subprocess.run(['bash','-n',str(final)],capture_output=True).returncode==0
renderer_state_ok=(rc==0) or (rc!=0 and recovered)
payload={
 'schema':'jass.l3_replay_context30_v3_render_receipt.v2',
 'source_v2_blob':v2,
 'render_exit_code':rc,
 'renderer_nonzero_recovered_from_generated_final':bool(rc!=0 and recovered),
 'recovered_from_generated_final':recovered,
 'final_script_present':final.is_file(),
 'final_script_sha256':sha(final) if final.is_file() else None,
 'final_script_size_bytes':final.stat().st_size if final.is_file() else None,
 'syntax_ok':syntax_ok,
 'required_tokens_missing':missing,
 'forbidden_tokens_surviving':surviving,
 'scientific_fit_command_count':fit_count,
 'scientific_protocol_changed':False,
 'technical_change_only':True,
 'log_sha256':sha(log),
}
out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
if not renderer_state_ok or not final.is_file() or not syntax_ok or missing or surviving or fit_count!=1:
 raise SystemExit('final context30 scientific script failed v3 render audit')
PY_RENDER_AUDIT

if [ "${JASS_REPLAY_CONTEXT30_V3_RENDER_ONLY:-0}" = 1 ]; then
  : >"$JASS_ARTEFACT_DIR/RENDER_ONLY__TRUE"
  : >"$JASS_ARTEFACT_DIR/SCIENTIFIC_SCRIPT_EXECUTED__FALSE"
  exit 0
fi

set +e
bash "$FINAL" > >(tee -a "$EXECUTION_LOG") 2>&1
SCIENTIFIC_RC=$?
set -e
python3 - "$EXECUTION_RECEIPT" "$EXECUTION_LOG" "$RENDER_RECEIPT" "$SCIENTIFIC_RC" <<'PY_EXECUTION'
import hashlib,json,sys
from pathlib import Path
out,log,render=map(Path,sys.argv[1:4]); rc=int(sys.argv[4])
def sha(path):
 h=hashlib.sha256(); h.update(path.read_bytes()); return h.hexdigest()
payload={
 'schema':'jass.l3_replay_context30_v3_execution_receipt.v1',
 'scientific_exit_code':rc,
 'execution_log_sha256':sha(log),
 'execution_log_size_bytes':log.stat().st_size,
 'render_receipt_sha256':sha(render),
 'scientific_protocol_changed':False,
 'technical_change_only':True,
}
out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
PY_EXECUTION
exit "$SCIENTIFIC_RC"

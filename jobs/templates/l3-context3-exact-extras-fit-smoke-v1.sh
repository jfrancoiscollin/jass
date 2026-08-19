#!/usr/bin/env bash
# Read-only/mechanistic verification of the exact-fold dense-extras fit contract.
# No self-play, production fit, strength game, frozen read, or promotion.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
mkdir -p "$W" "$IN" "$ART"
RES="$ART/RESULTS.txt"; : >"$RES"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
trap 'rc=$?; set +e; [ "$rc" -eq 0 ] || touch "$ART/TECHFAIL__RC_${rc}"; exit "$rc"' EXIT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] && [ -z "$(git status --porcelain)" ] || die "detached clean worktree required"
[ "$(hostname)" = cpx62 ] || die "cpx62 required"
[ "${NO_FROZEN_READ:-0}" = 1 ] && [ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] || die "safety guards missing"
VENV="${JASS_L3_NUMERIC_VENV:-/var/tmp/jass-l3-numeric-venv-current-v1}"
[ -f "$VENV/.jass-runtime-ready-v1" ] || die "numeric runtime unavailable"
PY="$VENV/bin/python"

ROOT1425="r2:jass-data/runs/cpx62-1425-l3-context3-exact-extras-audit-v1/20260819T204932Z-0c75fb87"
say phase=authenticate-1425
python3 jobs/tools/fetch_result_files.py --prefix "$ROOT1425" \
  --file artefacts/JASS_CONTROL_SUMMARY.json=summary1425.json \
  --file artefacts/exact-extras-weight-audit.json=weight-audit1425.json \
  --file artefacts/exact-extras-static-symmetry.json=static1425.json \
  --out-dir "$IN" --report "$ART/verified-1425.json" --expected-state completed >"$W/fetch1425.log" 2>&1
"$PY" - "$ART/verified-1425.json" "$IN/summary1425.json" "$IN/weight-audit1425.json" "$IN/static1425.json" <<'PY'
import json,sys
v,s,w,st=(json.load(open(p)) for p in sys.argv[1:5])
if (v.get('job_id'),v.get('attempt_id'),v.get('result_state'),v.get('exit_code')) != ('cpx62-1425-l3-context3-exact-extras-audit-v1','20260819T204932Z-0c75fb87','completed',0):
    raise SystemExit('1425 immutable identity drift')
if s.get('verdict') != 'JASS_CONTEXT3_EXACT_FOLD_DENSE_EXTRAS_DEFECT_CONFIRMED':
    raise SystemExit('1425 verdict drift')
for arm in ('aligned','shuffled','curriculum'):
    if w['models'][arm]['constraint_max_abs_after'] != 0:
        raise SystemExit(f'1425 projected weight constraint drift: {arm}')
    if w['models'][arm]['constraint_nonzero_before'] <= 0:
        raise SystemExit(f'1425 original violation missing: {arm}')
    if st['models'][arm]['projected']['max_abs_delta_cp'] != 0:
        raise SystemExit(f'1425 evaluator symmetry drift: {arm}')
PY

say phase=repository-contract-tests
python3 -m py_compile pattern_jass/tools/exact_extras.py pattern_jass/tools/train_stream_exact.py
"$PY" -m unittest jobs.tests.test_exact_extras_fit_contract >"$W/tests.log" 2>&1

say phase=synthetic-fit-through-corrected-trainer
"$PY" - "$W/synthetic.jnnw" "$W/synthetic.feat" <<'PY'
import struct,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,'pattern_jass/tools')
from exact_extras import exact_image_extras
jnnw,feat=map(Path,sys.argv[1:3])
def bb(squares):
    v=0
    for sq in squares: v |= 1 << sq
    return v
def rot(v):
    out=0
    for sq in range(50):
        if (v >> sq) & 1: out |= 1 << (49-sq)
    return out
pairs=[(bb([5,12]),bb([30,41])),(bb([1,8,17]),bb([32,39,46]))]  # (black men, white men)
rows=[]; feats=[]
rng=np.random.default_rng(1426)
for k,(bm,wm) in enumerate(pairs):
    x=rng.normal(size=120).astype(np.float32)
    # Keep the side-pair magnitudes non-degenerate; the trainer does not assume
    # these synthetic feature rows came from the C++ extractor.
    tx=exact_image_extras(x).astype(np.float32)
    rows.append((wm,0,bm,0,1,0,1)); feats.append(x)
    rows.append((rot(bm),0,rot(wm),0,1,0,-1)); feats.append(tx)
dt=np.dtype([('wm','<u8'),('wk','<u8'),('bm','<u8'),('bk','<u8'),('stm','u1'),('score','<i4'),('wdl','i1')])
a=np.array(rows,dtype=dt)
with jnnw.open('wb') as f:
    f.write(b'JNNW'+struct.pack('<I',len(a))); f.write(a.tobytes())
farr=np.stack(feats).astype('<f4')
with feat.open('wb') as f:
    f.write(b'FEAT'+struct.pack('<II',len(farr),farr.shape[1])); f.write(farr.tobytes())
PY

env PYTHONPATH="pattern_jass/tools" "$PY" pattern_jass/tools/train_stream_exact.py \
  --data "$W/synthetic.jnnw" --feat "$W/synthetic.feat" --out "$W/synthetic.pjtw" \
  --loss logistic --exact-fold --tempo-stage --l2 1e-4 --max-iter 4 \
  --chunk 2 --prune --optimizer-report "$ART/synthetic-optimizer.json" >"$W/synthetic-fit.log" 2>&1

say phase=certify-fit-contract
"$PY" - "$W/synthetic.pjtw" "$ART" <<'PY'
import json,struct,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,'pattern_jass/tools')
from exact_extras import exact_extras_residuals
p,art=Path(sys.argv[1]),Path(sys.argv[2])
raw=p.read_bytes(); magic,ver,scale,np_,ne=struct.unpack_from('<5I',raw,0)
if magic != 0x57544A50 or (ver & 255) != 3 or ne != 120:
    raise SystemExit(f'PJTW architecture drift {(hex(magic),ver,scale,np_,ne)}')
base=20+2*np_*4
mg=np.frombuffer(raw,dtype='<i4',count=ne,offset=base).copy()
eg=np.frombuffer(raw,dtype='<i4',count=ne,offset=base+ne*4).copy()
ma,ea=exact_extras_residuals(mg),exact_extras_residuals(eg)
if ma['max_abs'] != 0 or ea['max_abs'] != 0:
    raise SystemExit(f'corrected trainer emitted asymmetric extras mg={ma} eg={ea}')
out={'schema':'jass.l3_context3_exact_extras_fit_smoke.v1','verdict':'JASS_CONTEXT3_EXACT_EXTRAS_FIT_CONTRACT_VERIFIED','source_1425':'20260819T204932Z-0c75fb87','fit_kind':'synthetic_mechanistic_only','production_fit_performed':False,'selfplay':0,'strength_games':0,'frozen_read':False,'promotion_authorized':False,'n_ext':ne,'mg':ma,'eg':ea}
(art/'mechanistic-verification.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
(art/'JASS_CONTROL_SUMMARY.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
for marker in ('FROZEN_READ__FALSE','PATTERNEVAL_PRODUCTION_FITS__0','SELFPLAY__0','STRENGTH_GAMES__0','PROMOTION_AUTHORIZED__FALSE','VERDICT__JASS_CONTEXT3_EXACT_EXTRAS_FIT_CONTRACT_VERIFIED'):
    (art/marker).touch()
print(out['verdict'])
PY

say verdict=JASS_CONTEXT3_EXACT_EXTRAS_FIT_CONTRACT_VERIFIED

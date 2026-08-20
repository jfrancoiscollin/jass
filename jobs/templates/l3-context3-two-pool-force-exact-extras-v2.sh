#!/usr/bin/env bash
# CTX3 corrected causal force gate.
# Reuses the certified 1419 two-pool methodology byte-for-byte except for a
# fail-closed, audited substitution layer: corrected 1427 models, fresh seeds,
# explicit exclusion of both immutable 1419 force pools, and exact-extras
# provenance/constraint checks. No refit, self-play, frozen read or promotion.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
cd "$JASS_CODE_DIR"

[ "${NO_FROZEN_READ:-0}" = 1 ] || { echo "frozen-read guard missing" >&2; exit 1; }
[ "${NO_AUTOMATIC_PROMOTION:-0}" = 1 ] || { echo "promotion guard missing" >&2; exit 1; }

BASE="jobs/templates/l3-context3-two-pool-force-v1.sh"
PATCHED="$JASS_RESULT_DIR/l3-context3-two-pool-force-exact-extras-v2.generated.sh"
PATCHLOG="$JASS_ARTEFACT_DIR/force-template-substitutions.json"
EXPECTED_BASE_BLOB="0fb40d613308f4e278e99623fe8b64e90a5f37dc"
[ "$(git hash-object "$BASE")" = "$EXPECTED_BASE_BLOB" ] || {
  echo "certified 1419 force template blob drift" >&2; exit 1;
}

python3 - "$BASE" "$PATCHED" "$PATCHLOG" <<'PY'
import json,sys
from pathlib import Path
src,dst,log=map(Path,sys.argv[1:4])
text=src.read_text(encoding='utf-8')
changes=[]

def one(old,new,label):
    global text
    n=text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected one substitution, got {n}')
    text=text.replace(old,new)
    changes.append({'label':label,'count':n,'old':old,'new':new})

# Corrected immutable fit source.
one('FIT_JOB="cpx62-1418-l3-context3-paired-patterneval-fit-v1"',
    'FIT_JOB="cpx62-1427-l3-context3-paired-patterneval-exact-extras-v2"','fit_job')
one('FIT_ATTEMPT="20260819T074026Z-1e718553"',
    'FIT_ATTEMPT="20260819T224926Z-7fe6c654"','fit_attempt')
one('FIT_CODE_SHA="1e71855338b0642a28dd5d4023d9dba6bdf3dbf0"',
    'FIT_CODE_SHA="7fe6c654de9119fdc70164e6a4e4779cd7fe2e31"','fit_code_sha')

# Fresh pools and bootstrap/readout seeds; none reuse the 1419 preregistration.
for old,new,label in [
 ('POOL_SEED_1=2026081907','POOL_SEED_1=2026082001','pool_seed_1'),
 ('POOL_SEED_2=2026081908','POOL_SEED_2=2026082002','pool_seed_2'),
 ('GATE_BOOTSTRAP_SEED_1=2026081909','GATE_BOOTSTRAP_SEED_1=2026082003','gate_bootstrap_seed_1'),
 ('GATE_BOOTSTRAP_SEED_2=2026081910','GATE_BOOTSTRAP_SEED_2=2026082004','gate_bootstrap_seed_2'),
 ('COMBINED_NATIVE_SEED=2026081911','COMBINED_NATIVE_SEED=2026082005','combined_native_seed'),
 ('COMBINED_Q00_SEED=2026081912','COMBINED_Q00_SEED=2026082006','combined_q00_seed')]:
    one(old,new,label)

one('^cpx62-[0-9]+-l3-context3-two-pool-force-v1$',
    '^cpx62-[0-9]+-l3-context3-two-pool-force-exact-extras-v2$','job_nomenclature')
one("summary.get('verdict')=='JASS_CONTEXT3_PAIRED_PATTERNEVAL_MODELS_READY'",
    "summary.get('verdict')=='JASS_CONTEXT3_PAIRED_PATTERNEVAL_EXACT_EXTRAS_MODELS_READY'",'fit_verdict')

# 1427 has the same certified science but a stronger parent/recipe certificate.
one("require(parent.get('label')=='CURRICULUM' and parent.get('reused_without_refit') is True,'1418 parent drift')",
    "require(parent.get('label')=='CURRICULUM' and parent.get('prior_source_unchanged') is True and parent.get('dense_extras_projected_inside_fit') is True,'1427 parent drift')",'parent_contract')
one("'prior_decay':0,'l2':1e-5,'gtol':1e-4,'max_iterations':2000,'lbfgs_maxcor':20},'1418 fit recipe drift')",
    "'prior_decay':0,'l2':1e-5,'gtol':1e-4,'max_iterations':2000,'lbfgs_maxcor':20,\n 'dense_extras_constraint':'rot180_colour_swap_projected_design_and_projected_prior'},'1427 fit recipe drift')",'recipe_contract')

anchor="require(summary.get('alpha')==0.30,'1418 alpha drift')\n"
if text.count(anchor)!=1: raise SystemExit('alpha anchor drift')
text=text.replace(anchor,anchor+"pr=summary.get('mechanistic_prerequisite') or {}\nrequire(pr.get('job_id')=='cpx62-1426-l3-context3-exact-extras-fit-smoke-v1' and pr.get('attempt_id')=='20260819T215156Z-040da98c' and pr.get('verdict')=='JASS_CONTEXT3_EXACT_EXTRAS_FIT_CONTRACT_VERIFIED','1426 prerequisite drift')\nrequire(summary.get('scientific_protocol_reference')=='cpx62-1418-l3-context3-paired-patterneval-fit-v1/20260819T074026Z-1e718553','1418 protocol reference drift')\nrequire(summary.get('reuse_1419_force_pools_forbidden') is True,'1427 fresh-force-pool contract drift')\n")
changes.append({'label':'mechanistic_and_protocol_prerequisites','count':1})

arm_anchor=" arm=summary['arms'][label]; conv=load(src/f'{name}-convergence.json')\n"
if text.count(arm_anchor)!=1: raise SystemExit('arm anchor drift')
text=text.replace(arm_anchor,arm_anchor+" exact=arm.get('exact_extras') or {}\n require((exact.get('mg') or {}).get('max_abs')==0 and (exact.get('eg') or {}).get('max_abs')==0,f'{label}: exact dense-extras residual drift')\n")
changes.append({'label':'exact_extras_zero_guard','count':1})

# Explicitly exclude both immutable 1419 force pools in addition to all prior exclusions.
tail='pool-succession|r2:jass-data/runs/home-0995-l3-pure-turnover-succession-preflight-v2/20260727T054246Z-f20e59d0|artefacts/turnover-succession-openings.fen"'
newtail='pool-succession|r2:jass-data/runs/home-0995-l3-pure-turnover-succession-preflight-v2/20260727T054246Z-f20e59d0|artefacts/turnover-succession-openings.fen\\npool-context3-1419-force-pool1|r2:jass-data/runs/cpx62-1419-l3-context3-two-pool-force-v1/20260819T112556Z-8adc506a|artefacts/ctx3-force-pool1-openings.fen\\npool-context3-1419-force-pool2|r2:jass-data/runs/cpx62-1419-l3-context3-two-pool-force-v1/20260819T112556Z-8adc506a|artefacts/ctx3-force-pool2-openings.fen"'
one(tail,newtail,'exclude_1419_pools')
one('[ "${#EXCL_NAMES[@]}" -eq 15 ]','[ "${#EXCL_NAMES[@]}" -eq 17 ]','exclusion_count')

# Labels/messages are provenance only; make the corrected source explicit.
text=text.replace('1418 fetch failed','1427 fetch failed')
text=text.replace("f'1418 identity/state drift: {got}'","f'1427 identity/state drift: {got}'")
text=text.replace("'1418 verdict drift'","'1427 verdict drift'")
text=text.replace("'1418 contrast drift'","'1427 contrast drift'")
text=text.replace("'1418 scope drift'","'1427 scope drift'")
text=text.replace("'1418 promotion drift'","'1427 promotion drift'")
text=text.replace("'1418 corpus/cardinality drift'","'1427 corpus/cardinality drift'")
text=text.replace("'1418 alpha drift'","'1427 alpha drift'")
text=text.replace('fetch-and-authenticate-1418-models','fetch-and-authenticate-1427-corrected-models')

# Fail closed if any old force seeds remain or 1419 exclusions are missing.
for forbidden in ('POOL_SEED_1=2026081907','POOL_SEED_2=2026081908','GATE_BOOTSTRAP_SEED_1=2026081909','GATE_BOOTSTRAP_SEED_2=2026081910','COMBINED_NATIVE_SEED=2026081911','COMBINED_Q00_SEED=2026081912'):
    if forbidden in text: raise SystemExit(f'old 1419 seed survived: {forbidden}')
for required in ('pool-context3-1419-force-pool1','pool-context3-1419-force-pool2','JASS_CONTEXT3_PAIRED_PATTERNEVAL_EXACT_EXTRAS_MODELS_READY','exact dense-extras residual drift'):
    if required not in text: raise SystemExit(f'missing corrected force guard: {required}')

dst.write_text(text,encoding='utf-8')
log.write_text(json.dumps({'schema':'jass.ctx3_exact_extras_force_substitutions.v2','base_blob':'0fb40d613308f4e278e99623fe8b64e90a5f37dc','changes':changes,'fresh_pool_seeds':[2026082001,2026082002],'fresh_bootstrap_seeds':[2026082003,2026082004,2026082005,2026082006],'excluded_1419_attempt':'20260819T112556Z-8adc506a','fit_1427_attempt':'20260819T224926Z-7fe6c654'},indent=2,sort_keys=True)+'\n',encoding='utf-8')
PY

bash -n "$PATCHED"
chmod +x "$PATCHED"
diff -u "$BASE" "$PATCHED" >"$JASS_ARTEFACT_DIR/force-template.patch" || true
exec bash "$PATCHED"

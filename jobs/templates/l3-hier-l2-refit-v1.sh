#!/usr/bin/env bash
# L3 — refit causal HIER seul. Deux bras EXACT identiques sauf --hier-l2 0/3e-5.
# Aucun gate, aucune promotion et aucune continuation automatique dans ce job.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"
mkdir -p "$W" "$IN" "$ART" "$GEOM"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: > "$RES"; : > "$PROG"; echo start > "$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "phase=$1"; }

TURNOVER_TRAIN_PREFIX="${TURNOVER_TRAIN_PREFIX:-r2:jass-data/runs/home-0977-l3-pure-turnover1to1-train-v1/20260726T071254Z-336bb984}"
EXPECTED_TURNOVER_TRAIN_JOB="${EXPECTED_TURNOVER_TRAIN_JOB:-home-0977-l3-pure-turnover1to1-train-v1}"
EXPECTED_PARENT_MODEL_SHA256="be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2"
EXPECTED_RECORDS=2000000; EXPECTED_HOLDOUT=199204; EXPECTED_EXTRAS=120

# Préenregistré dans L3_HIER_L2_PREREGISTRATION_20260802.md. Ces valeurs ne
# sont pas paramétrables afin qu'un wrapper ne puisse pas ajouter un facteur.
L2=3e-5; HIER_CONTROL=0; HIER_CANDIDATE=3e-5
MAXIT=1000; LBFGS_MAXCOR=20; LBFGS_GTOL=1e-4; CHUNK=20000
MAX_GRAD_INF=1e-4
FIT_TIMEOUT=10800

MON=""
monitor(){
  ( t0=$(date +%s)
    while true; do
      { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s) - t0) / 60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        for arm in control hier; do
          [ -f "$W/fit-$arm.log" ] &&
            printf '%s_fit_lines=%s\n' "$arm" "$(wc -l < "$W/fit-$arm.log")"
        done
      } > "$PROG.tmp"
      mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"
      sleep 120
    done ) &
  MON="$!"
}
restore_src(){ git checkout -- src/ pattern_jass/ 2>/dev/null || true; }
finalize(){
  rc=$?
  trap - EXIT ERR TERM INT
  set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt"
  [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W/build" "$W/venv" "$IN" 2>/dev/null || true
  rm -f "$W"/*.jnnw "$W"/*.feat 2>/dev/null || true
  exit "$rc"
}
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[[ "$JASS_JOB_ID" =~ ^home-([0-9]+)-codex-hier-l2-refit-at-([0-9a-f]{8})-v[0-9]+$ ]] ||
  die "job must use home/codex/hier-l2-refit/at-sha nomenclature"
[ "${BASH_REMATCH[1]}" -ge 1200 ] || die "home job number must be >=1200"
[[ "$EXPECTED_CODE_SHA" == "${BASH_REMATCH[2]}"* ]] || die "visible SHA mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"

stage disk-guard
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 5000 ] || die "moins de 5 Go libres (${DFA} Mo)"
NCPU=$(nproc); say "  nproc=$NCPU libre=${DFA}Mo"
monitor

stage fetch-turnover-corpus-and-parent
python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_TRAIN_PREFIX" \
  --file work/m2.fit.jnnw=corpus.jnnw \
  --file work/parent-f2m.pjtw=parent.pjtw \
  --file artefacts/m2-split.json=split.json \
  --out-dir "$IN" --report "$ART/verified-turnover-train.json" \
  --expected-state completed > "$W/fetch.log" 2>&1 || die "fetch en échec"
python3 - "$ART/verified-turnover-train.json" "$EXPECTED_TURNOVER_TRAIN_JOB" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
if r.get("job_id") != sys.argv[2] or r.get("result_state") != "completed":
    raise SystemExit("source identity/state mismatch")
PY
[ "$(sha256sum "$IN/parent.pjtw" | awk '{print $1}')" = "$EXPECTED_PARENT_MODEL_SHA256" ] ||
  die "parent model hash drift"
read -r RECORDS HOLDOUT < <(python3 - "$IN/split.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print(d["records"], d["holdout_records"])
PY
)
[ "$RECORDS" = "$EXPECTED_RECORDS" ] || die "corpus records=$RECORDS"
[ "$HOLDOUT" = "$EXPECTED_HOLDOUT" ] || die "holdout=$HOLDOUT"
say "  corpus ✓ $RECORDS positions, holdout $HOLDOUT, parent conforme"

stage build-8cf-and-features
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1 ||
  { restore_src; die "génération 8cf en échec"; }
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
[ "$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')" -eq 4251528 ] ||
  { restore_src; die "8cf mismatch"; }
grep -q "g_emasks" src/scan_eval.cpp || { restore_src; die "scan_eval incompatible"; }
grep -q "root_is_drawn" src/search.cpp || { restore_src; die "engine predates drawn-root fix"; }
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
  > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass > "$W/build.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || { restore_src; die "build sans binaire"; }
restore_src
"$J" --dump-eval-features "$IN/corpus.jnnw" "$W/corpus.feat" > "$W/features.log" 2>&1 ||
  die "dump-eval-features en échec"
K=$(python3 -c 'import struct,sys;f=open(sys.argv[1],"rb");assert f.read(4)==b"FEAT";print(struct.unpack("<II",f.read(8))[1])' "$W/corpus.feat")
[ "$K" = "$EXPECTED_EXTRAS" ] || die "extras K=$K attendu $EXPECTED_EXTRAS"

stage python-runtime-and-contract
python3 -m venv "$W/venv"
if "$W/venv/bin/python" -m pip install --disable-pip-version-check --only-binary=:all: \
     numpy==1.26.4 scipy==1.14.1 > "$W/pip.log" 2>&1; then
  PINSTACK=historical
else
  "$W/venv/bin/python" -m pip install --disable-pip-version-check --only-binary=:all: \
    numpy scipy >> "$W/pip.log" 2>&1 || die "pip en échec"
  PINSTACK=current
fi
NPV=$("$W/venv/bin/python" -c 'import numpy,scipy;print(numpy.__version__,scipy.__version__)')
printf '{"stack":"%s","numpy_scipy":"%s"}\n' "$PINSTACK" "$NPV" > "$ART/numeric-stack.json"
env PYTHONPATH="$GEOM:pattern_jass/tools" "$W/venv/bin/python" \
  pattern_jass/tools/test_exact_fold.py -v > "$W/selftest.log" 2>&1 || die "selftest exact en échec"
python3 - "$ART/fit-contract.json" "$TURNOVER_TRAIN_PREFIX" \
  "$EXPECTED_PARENT_MODEL_SHA256" <<'PY'
import json, sys
out, corpus, parent_sha = sys.argv[1:]
common = {
    "corpus": corpus, "parent_sha256": parent_sha, "continuation": "warm-start",
    "fold": "exact", "geometry": "8cf", "n_ext": 120, "target": "wdl",
    "loss": "logistic", "tempo_stage": True, "l2": 3e-5,
    "holdout_count": 199204, "max_iter": 1000, "lbfgs_maxcor": 20,
    "lbfgs_gtol": 1e-4, "gradient_inf_norm_max": 1e-4,
    "chunk": 20000, "prune": True,
}
arms = {"control": {**common, "hier_l2": 0.0},
        "hier": {**common, "hier_l2": 3e-5}}
diff = [key for key in arms["control"] if arms["control"][key] != arms["hier"][key]]
if diff != ["hier_l2"]:
    raise SystemExit(f"not a one-factor contract: {diff}")
json.dump({"schema": 1, "arms": arms, "only_difference": diff},
          open(out, "w"), indent=2, sort_keys=True)
PY
say "  contrat causal ✓ seule différence=hier_l2"

fit_arm(){
  local arm="$1" hier="$2"
  stage "fit-$arm"
  set +e
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
    timeout "$FIT_TIMEOUT" "$W/venv/bin/python" pattern_jass/tools/train_stream.py \
      --data "$IN/corpus.jnnw" --feat "$W/corpus.feat" --out "$W/$arm.pjtw" \
      --target wdl --loss logistic --exact-fold --tempo-stage \
      --warm-start "$IN/parent.pjtw" --holdout-count "$HOLDOUT" \
      --l2 "$L2" --hier-l2 "$hier" --max-iter "$MAXIT" --chunk "$CHUNK" \
      --lbfgs-maxcor "$LBFGS_MAXCOR" --lbfgs-gtol "$LBFGS_GTOL" --prune \
      --optimizer-report "$ART/$arm-optimizer.json" \
      > "$W/fit-$arm.log" 2> "$W/fit-$arm-time.log"
  rc=$?; set -e
  [ "$rc" -eq 0 ] || die "fit $arm rc=$rc"
  [ -s "$W/$arm.pjtw" ] || die "fit $arm sans modèle"
  python3 - "$ART/$arm-optimizer.json" "$MAX_GRAD_INF" <<'PY'
import json, math, sys
o = json.load(open(sys.argv[1]))
limit = float(sys.argv[2])
required = {"success", "status", "message", "iterations",
            "function_evaluations", "gradient_inf_norm", "gtol"}
missing = required - set(o)
if missing:
    raise SystemExit(f"optimizer report missing keys: {sorted(missing)}")
grad = o["gradient_inf_norm"]
if (o["success"] is not True or o["status"] != 0 or o["gtol"] != 1e-4
        or not isinstance(grad, (int, float)) or not math.isfinite(grad)
        or grad > limit):
    raise SystemExit(
        f"optimizer convergence invalid: success={o['success']} status={o['status']} "
        f"grad_inf={grad} limit={limit} gtol={o['gtol']} message={o['message']!r}"
    )
PY
  gzip -n -c "$W/$arm.pjtw" > "$ART/$arm.pjtw.gz"
  say "  $arm ✓ hier_l2=$hier"
}

fit_arm control "$HIER_CONTROL"
fit_arm hier "$HIER_CANDIDATE"

stage verify-outputs
cmp -s "$W/control.pjtw" "$W/hier.pjtw" && die "expérience vide: modèles identiques"
python3 - "$W/control.pjtw" "$W/hier.pjtw" "$ART/model-contract.json" <<'PY'
import hashlib, json, struct, sys
rows = {}
for label, path in (("control", sys.argv[1]), ("hier", sys.argv[2])):
    raw = open(path, "rb").read()
    magic, version, scale, n_pat, n_ext = struct.unpack("<5I", raw[:20])
    if n_ext != 120:
        raise SystemExit(f"{label}: n_ext={n_ext}, expected 120")
    rows[label] = {"magic": magic, "version": version, "scale": scale,
                   "n_pat": n_pat, "n_ext": n_ext,
                   "sha256": hashlib.sha256(raw).hexdigest()}
shape_keys = ("magic", "version", "scale", "n_pat", "n_ext")
if any(rows["control"][k] != rows["hier"][k] for k in shape_keys):
    raise SystemExit("model shape/header differs between arms")
json.dump({"schema": 1, "models": rows}, open(sys.argv[3], "w"),
          indent=2, sort_keys=True)
PY
python3 - "$ART" <<'PY'
import json, os, sys
art = sys.argv[1]
fits = {}
for arm in ("control", "hier"):
    o = json.load(open(os.path.join(art, f"{arm}-optimizer.json")))
    fits[arm] = {k: o[k] for k in ("success", "status", "message", "iterations",
                                            "function_evaluations", "gradient_inf_norm", "gtol")}
payload = {
    "schema": 1, "verdict": "L3_HIER_L2_REFIT_READY",
    "fit_contract": json.load(open(os.path.join(art, "fit-contract.json"))),
    "models": json.load(open(os.path.join(art, "model-contract.json")))["models"],
    "optimizer": fits, "convergence_requirement": {"gradient_inf_norm_max": 1e-4,
                                                       "all_arms_pass": True},
    "promotion_authorized": False, "automatic_next_job": None,
}
json.dump(payload, open(os.path.join(art, "JASS_CONTROL_SUMMARY.json"), "w"),
          indent=2, sort_keys=True)
PY
: > "$ART/VERDICT__L3_HIER_L2_REFIT_READY"
printf 'PROMOTION_AUTHORIZED__FALSE\n' > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf 'AUTOMATIC_NEXT_JOB__NULL\n' > "$ART/AUTOMATIC_NEXT_JOB__NULL"
say "L3_HIER_L2_REFIT_READY promotion=false automatic_next_job=null"

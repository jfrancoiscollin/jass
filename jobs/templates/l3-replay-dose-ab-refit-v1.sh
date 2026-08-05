#!/usr/bin/env bash
# L3 — DOSE DE REPLAY, re-testee dans le regime PRIOR.
#
# ⛔ POURQUOI ON LA RE-TESTE. L'axe a ete clos le 27 juillet avec un optimum
# interieur a 50 % (`home-0990`→`0993`) — mais A `L2=3e-5`, c'est-a-dire AVANT
# le prior centre sur le parent, arrive le 2 aout. Or `CLAUDE.md` porte la
# lecon gravee apres l'affaire du `l2` : « une constante close dans un regime
# ne reste close que dans ce regime ». Et il porte le mecanisme : `3e-5`
# sur-pondere le parent « que la moitie memoire du melange 1:1 REINJECTE DEJA
# COMME DONNEE ». Le replay et le prior sont donc DEUX CANAUX POUR LA MEME
# FONCTION. Quand le second est arrive, l'optimum du premier a bouge.
#
# ⛔ ET ON EST PASSE A ZERO SANS LE MESURER. `mix` refuse de melanger JSM1 et
# JSM2 ; la moitie memoire est en JSM1 historique et ne peut pas acquerir de
# contexte ; donc exiger du JSM2 pour M1/M2 a force `MEMORY_RECORDS=0`. La dose
# est passee de 50 % a 0 % pour une raison de SERIALISATION.
#
# LE MONTAGE, a budget CONSTANT — c'est la seule facon de faire varier la dose
# a un seul facteur :
#   A  TARGET records, 100 % FRAIS
#   B  TARGET records, 50 % frais + 50 % MEMOIRE
# Meme budget, meme recette, meme parent, meme pile numerique, meme pool
# d'ouvertures. Seule la COMPOSITION du budget change.
#
# Les deux bras sortent en JSM1 (--downgrade-meta jsm1 des deux cotes) pour
# qu'aucune difference de sidecar ne subsiste entre eux.
#
# Aucune promotion. La porte A vs B est un job SEPARE.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${POOL_PREFIX:?}"; : "${POOL_JOB:?}"
: "${M1_PREFIX:?}"; : "${EXPECTED_M1_JOB:?}"
: "${M2_PREFIX:?}"; : "${EXPECTED_M2_JOB:?}"
: "${PARENT_PREFIX:?}"; : "${PARENT_JOB:?}"; : "${EXPECTED_PARENT_MODEL_SHA256:?}"

cd "$JASS_CODE_DIR"
W="$JASS_RESULT_DIR/work"; IN="$JASS_RESULT_DIR/inputs"; ART="$JASS_ARTEFACT_DIR"
GEOM="$JASS_RESULT_DIR/geom8"; mkdir -p "$W" "$IN" "$ART" "$GEOM"
RES="$W/RESULTS.txt"; PROG="$W/PROGRESS.txt"; STAGE="$W/.stage"
: > "$RES"; : > "$PROG"; echo start > "$STAGE"
say(){ echo "$*" | tee -a "$RES"; }
die(){ say "ABORT: $*"; exit 1; }
stage(){ echo "$1" > "$STAGE"; say "phase=$1"; }

TARGET_RECORDS="${TARGET_RECORDS:-2000000}"
MIX_SEED="${MIX_SEED:-1732050}"
SPLIT_SEED="${SPLIT_SEED:-577215}"
HOLDOUT_MOD="${HOLDOUT_MOD:-10}"
EXPECTED_EXTRAS="${EXPECTED_EXTRAS:-120}"
FOLD_FLAG="${FOLD_FLAG:---exact-fold}"
L2="${L2:-1e-5}"; LBFGS_GTOL="${LBFGS_GTOL:-1e-4}"
MAXIT="${MAXIT:-4000}"; CHUNK="${CHUNK:-20000}"; LBFGS_MAXCOR=20
FIT_TIMEOUT="${FIT_TIMEOUT:-14400}"

MON=""
monitor(){ ( t0=$(date +%s); while true; do
    { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
      printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
      printf 'elapsed_min=%d\n' "$(( ($(date +%s) - t0) / 60 ))"
      printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
      for a in fresh replay; do [ -f "$W/fit-$a.log" ] &&
        printf '%s_fit_lines=%s\n' "$a" "$(wc -l < "$W/fit-$a.log")"; done
    } > "$PROG.tmp"; mv "$PROG.tmp" "$PROG"; cp "$PROG" "$ART/PROGRESS.txt"; sleep 120
  done ) & MON="$!"; }
restore_src(){ git checkout -- src/ pattern_jass/ 2>/dev/null || true; }
finalize(){ rc=$?; trap - EXIT ERR TERM INT; set +e
  [ -z "$MON" ] || { kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null; }
  cp "$RES" "$ART/RESULTS.txt"; [ -f "$PROG" ] && cp "$PROG" "$ART/PROGRESS.txt"
  (cd "$W" && find . -type f -name '*.log' -print0 |
    tar --null -czf "$ART/logs.tar.gz" -T -) 2>/dev/null || true
  rm -rf "$W"/build* "$W/venv" "$IN" 2>/dev/null || true
  rm -f "$W"/*.jnnw "$W"/*.jsm "$W"/*.feat 2>/dev/null || true
  exit "$rc"; }
trap finalize EXIT
trap 'rc=$?; set +e; echo "ABORT line=$LINENO rc=$rc cmd=$BASH_COMMAND" | tee -a "$RES"; exit "$rc"' ERR
trap 'exit 143' TERM
trap 'exit 130' INT

[ "$JASS_JOB_ID" = "$EXPECTED_JOB_ID" ] || die "job id mismatch"
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"

stage disk-guard
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 15000 ] || die "moins de 15 Go libres (${DFA} Mo)"
NCPU=$(nproc); say "  nproc=$NCPU libre=${DFA}Mo"
monitor

stage fetch-inputs
python3 jobs/tools/fetch_result_files.py --prefix "$POOL_PREFIX" \
  --file artefacts/vol8m.jnnw.gz=pool.jnnw.gz --file artefacts/vol8m.jsm.gz=pool.jsm.gz \
  --out-dir "$IN" --report "$ART/verified-pool.json" --expected-state completed \
  > "$W/fetch-pool.log" 2>&1 || die "fetch du pool en échec"
python3 jobs/tools/fetch_result_files.py --prefix "$M1_PREFIX" \
  --file artefacts/common-fresh-500k.jnnw.gz=mem-a.jnnw.gz \
  --file artefacts/common-fresh-500k.jsm.gz=mem-a.jsm.gz \
  --file artefacts/extra-fresh-1500k.jnnw.gz=mem-b.jnnw.gz \
  --file artefacts/extra-fresh-1500k.jsm.gz=mem-b.jsm.gz \
  --out-dir "$IN" --report "$ART/verified-m1.json" --expected-state completed \
  > "$W/fetch-m1.log" 2>&1 || die "fetch M1 en échec"
python3 jobs/tools/fetch_result_files.py --prefix "$M2_PREFIX" \
  --file artefacts/m2-fresh-2m.jnnw.gz=mem-c.jnnw.gz \
  --file artefacts/m2-fresh-2m.jsm.gz=mem-c.jsm.gz \
  --out-dir "$IN" --report "$ART/verified-m2.json" --expected-state completed \
  > "$W/fetch-m2.log" 2>&1 || die "fetch M2 en échec"
python3 jobs/tools/fetch_result_files.py --prefix "$PARENT_PREFIX" \
  --file work/parent-f2m.pjtw=parent.pjtw \
  --out-dir "$IN" --report "$ART/verified-parent.json" --expected-state completed \
  > "$W/fetch-parent.log" 2>&1 || die "fetch du parent en échec"
[ "$(sha256sum "$IN/parent.pjtw" | awk '{print $1}')" = "$EXPECTED_PARENT_MODEL_SHA256" ] ||
  die "hash du parent non conforme"
for f in pool mem-a mem-b mem-c; do
  gunzip -c "$IN/$f.jnnw.gz" > "$W/$f.jnnw"; gunzip -c "$IN/$f.jsm.gz" > "$W/$f.jsm"
done
[ "$(head -c4 "$W/pool.jsm")" = "JSM2" ] || die "pool en JSM1 : ce n'est pas le corpus attendu"
for f in mem-a mem-b mem-c; do
  [ "$(head -c4 "$W/$f.jsm")" = "JSM1" ] ||
    die "$f n'est pas en JSM1 : la moitié mémoire est censée être historique"
done
say "  entrées ✓ : pool JSM2 + 3 sources mémoire JSM1 + parent"

stage assemble-memory
python3 tools/selfplay_frontier.py merge \
  --pair "$W/mem-a.jnnw" "$W/mem-a.jsm" --pair "$W/mem-b.jnnw" "$W/mem-b.jsm" \
  --pair "$W/mem-c.jnnw" "$W/mem-c.jsm" --renamespace-nested \
  --out-data "$W/memory.jnnw" --out-meta "$W/memory.jsm" \
  --manifest "$ART/memory-merge.json" > "$W/memory-merge.log" 2>&1 || die "merge mémoire en échec"
MEMN=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["records"])' "$ART/memory-merge.json")
HALF=$((TARGET_RECORDS / 2))
[ "$MEMN" -ge "$HALF" ] ||
  die "mémoire plafonnée à $MEMN records, il en faut $HALF pour un 1:1 à $TARGET_RECORDS"
say "  mémoire ✓ : $MEMN records disponibles, $HALF requis pour le bras B"

stage build-two-corpora
# Les DEUX bras passent par mix ET par --downgrade-meta jsm1, pour qu'aucune
# difference de schema ni de chemin de code ne subsiste entre eux.
python3 tools/selfplay_frontier.py mix --source FRESH "$W/pool.jnnw" "$W/pool.jsm" 1 \
  --target-records "$TARGET_RECORDS" --seed "$MIX_SEED" --downgrade-meta jsm1 \
  --out-data "$W/a.jnnw" --out-meta "$W/a.jsm" --manifest "$ART/mix-fresh.json" \
  > "$W/mix-a.log" 2>&1 || die "mix bras A en échec"
python3 tools/selfplay_frontier.py mix \
  --source FRESH "$W/pool.jnnw" "$W/pool.jsm" 1 \
  --source MEMORY "$W/memory.jnnw" "$W/memory.jsm" 1 \
  --target-records "$TARGET_RECORDS" --seed "$MIX_SEED" --downgrade-meta jsm1 \
  --namespace-openings \
  --out-data "$W/b.jnnw" --out-meta "$W/b.jsm" --manifest "$ART/mix-replay.json" \
  > "$W/mix-b.log" 2>&1 || die "mix bras B en échec"
python3 - "$ART/mix-fresh.json" "$ART/mix-replay.json" "$TARGET_RECORDS" <<'PYMIX' | tee -a "$RES"
import json, sys
a, b, target = json.load(open(sys.argv[1])), json.load(open(sys.argv[2])), int(sys.argv[3])
for name, m in (("A frais", a), ("B replay", b)):
    if m["records"] != target:
        raise SystemExit(f"{name}: {m['records']} records != {target}")
    if not m.get("sidecar_downgraded"):
        raise SystemExit(f"{name}: sidecar non degrade, les deux bras doivent etre en JSM1")
sel = {s["label"]: s["selected_records"] for s in b["sources"]}
if len(sel) != 2:
    raise SystemExit(f"bras B: {len(sel)} sources au lieu de 2")
f, m = sel["FRESH"], sel["MEMORY"]
if abs(f - m) > 1:
    raise SystemExit(f"bras B desequilibre : {f} frais / {m} memoire, un 1:1 etait demande")
print(f"  bras A : {a['records']:,} records, 100 % frais")
print(f"  bras B : {b['records']:,} records, {f:,} frais / {m:,} memoire "
      f"({100*m/(f+m):.1f} % de replay)")
PYMIX

stage split-both
for arm in a b; do
  python3 tools/selfplay_frontier.py split --data "$W/$arm.jnnw" --meta "$W/$arm.jsm" \
    --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
    --out-data "$W/$arm-split.jnnw" --out-meta "$W/$arm-split.jsm" \
    --manifest "$ART/split-$arm.json" > "$W/split-$arm.log" 2>&1 || die "split $arm en échec"
  mv "$W/$arm-split.jnnw" "$W/$arm.jnnw"; mv "$W/$arm-split.jsm" "$W/$arm.jsm"
done
HOLD_A=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["holdout_records"])' "$ART/split-a.json")
HOLD_B=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["holdout_records"])' "$ART/split-b.json")
[ "${HOLD_A:-0}" -gt 0 ] && [ "${HOLD_B:-0}" -gt 0 ] || die "holdout vide"
say "  split ✓ : holdout A=$HOLD_A  B=$HOLD_B (1/$HOLDOUT_MOD par ouverture)"

stage build-engine
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1 ||
  { restore_src; die "génération 8cf en échec"; }
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
[ "$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')" -eq 4251528 ] ||
  { restore_src; die "8cf mismatch"; }
grep -q "g_emasks"      src/scan_eval.cpp || { restore_src; die "archi: scan_eval sans g_emasks"; }
grep -q "root_is_drawn" src/search.cpp    || { restore_src; die "engine predates the drawn-root fix"; }
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass > "$W/build.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || { restore_src; die "build sans binaire"; }
restore_src
say "  8cf ✓ TOTAL_BUCKETS=4251528, garde-fou archi ✓"

stage python-runtime
python3 -m venv "$W/venv"
if "$W/venv/bin/python" -m pip install --disable-pip-version-check --only-binary=:all: \
     numpy==1.26.4 scipy==1.14.1 > "$W/pip.log" 2>&1; then PINSTACK=historical
else "$W/venv/bin/python" -m pip install --disable-pip-version-check --only-binary=:all: \
    numpy scipy >> "$W/pip.log" 2>&1 || die "pip en échec"; PINSTACK=current; fi
NPV=$("$W/venv/bin/python" -c 'import numpy,scipy;print(numpy.__version__,scipy.__version__)')
say "  pile numérique : $PINSTACK (numpy/scipy $NPV) — PARTAGÉE par les deux bras"
printf '{"stack":"%s","numpy_scipy":"%s"}\n' "$PINSTACK" "$NPV" > "$ART/numeric-stack.json"

fit_arm(){   # $1 = nom, $2 = corpus, $3 = holdout
  local arm="$1" data="$2" hold="$3"
  stage "dump-feat-$arm"
  "$J" --dump-eval-features "$data" "$W/$arm.feat" > "$W/features-$arm.log" 2>&1 ||
    die "dump-eval-features $arm en échec"
  local K
  K=$(python3 -c 'import struct,sys;f=open(sys.argv[1],"rb");assert f.read(4)==b"FEAT";print(struct.unpack("<II",f.read(8))[1])' "$W/$arm.feat")
  [ "$K" = "$EXPECTED_EXTRAS" ] || die "extras K=$K attendu $EXPECTED_EXTRAS ($arm)"
  stage "fit-$arm"
  set +e
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" PYTHONUNBUFFERED=1 \
    timeout "$FIT_TIMEOUT" "$W/venv/bin/python" pattern_jass/tools/train_stream.py \
      --data "$data" --feat "$W/$arm.feat" --out "$W/$arm.pjtw" \
      --target wdl --loss logistic "$FOLD_FLAG" --tempo-stage \
      --prior-mean "$IN/parent.pjtw" --prior-decay 0 \
      --holdout-count "$hold" --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
      --lbfgs-maxcor "$LBFGS_MAXCOR" --lbfgs-gtol "$LBFGS_GTOL" --prune \
      --optimizer-report "$ART/$arm-optimizer.json" \
      > "$W/fit-$arm.log" 2> "$W/fit-$arm-time.log"
  local rc=$?
  set -e
  [ "$rc" -eq 0 ] || die "fit $arm rc=$rc — voir fit-$arm.log"
  [ -s "$W/$arm.pjtw" ] || die "fit $arm sans modèle"
  python3 - "$ART/$arm-optimizer.json" "$arm" <<'PYCHK' || die "fit $arm : arrêt non concluant"
import json, sys
d = json.load(open(sys.argv[1]))
if not d.get("success"):
    raise SystemExit(f"{sys.argv[2]}: success=False")
if "PGTOL" not in str(d.get("message", "")).upper():
    raise SystemExit(f"{sys.argv[2]}: arret sur '{d.get('message')}' et non sur le gradient")
PYCHK
  gzip -n -c "$W/$arm.pjtw" > "$ART/$arm.pjtw.gz"
  local ll it
  ll=$(grep -o 'HOLDOUT_LOGLOSS[= ][0-9.]*' "$W/fit-$arm.log" | tail -1)
  it=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["iterations"])' "$ART/$arm-optimizer.json")
  say "  $arm : convergé, $it itérations, ${ll:-holdout n/a}"
}

say "  recette (IDENTIQUE sur les deux bras) : $FOLD_FLAG, prior sur le parent,"
say "    decay 0, gtol $LBFGS_GTOL, l2 $L2, max_iter $MAXIT"
fit_arm fresh  "$W/a.jnnw" "$HOLD_A"
fit_arm replay "$W/b.jnnw" "$HOLD_B"

stage verify-arms-differ
cmp -s "$W/fresh.pjtw" "$W/replay.pjtw" &&
  die "les deux modèles sont IDENTIQUES — le replay n'a rien changé au fit"
say "  bras distincts ✓"

stage report
say "L3_REPLAY_DOSE_AB_REFIT_READY target=$TARGET_RECORDS promotion=false automatic_next_job=null"
: > "$ART/PROMOTION_AUTHORIZED__FALSE"
: > "$ART/AUTOMATIC_NEXT_JOB__NULL"
: > "$ART/VERDICT__L3_REPLAY_DOSE_AB_REFIT_READY"
stage complete

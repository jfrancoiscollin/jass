#!/usr/bin/env bash
# L3 — M3 étage 1 : la cellule C2 de l'usine à signal, à UN SEUL FACTEUR.
#
# Deux fits sous la recette CHAMPIONNE, sur deux corpus qui ne diffèrent QUE par
# l'octet 37 — l'étiquette WDL — des records que la tablebase sait trancher.
#
#   C0  le corpus tel qu'il sort de l'autojeu
#   C2  le MÊME corpus, `--egdb-relabel` appliqué : mêmes positions, même
#       compte, même ORDRE, même sidecar, seule l'étiquette change
#
# ⛔ POURQUOI CETTE CELLULE EST SANS CONFONDANT, ET C'EST VÉRIFIÉ, PAS SUPPOSÉ.
# Le job compare les deux fichiers octet par octet et EXIGE que toute différence
# tombe à un offset ≡ 37 (mod 38). Un seul octet qui diffère ailleurs = abandon.
# Corollaire : les positions étant identiques, le dump FEAT est fait UNE fois et
# partagé — ce qui rend l'égalité des entrées du fit structurelle, pas espérée.
#
# CE QUE ÇA TESTE : l'audit tablebase mesure 24,1-24,2 % d'étiquettes fausses
# là où la base sait, sur DEUX corpus indépendants, dont 90,2 % d'étiquettes
# décisives posées sur des positions théoriquement nulles. Corriger ce biais
# vaut-il de l'Elo ?
#
# ⚠️ 2 M ET NON 12 M, ET C'EST JUSTIFIÉ PAR UNE MESURE. `cpx62-1179` a montré
# que 6× de données valent `≤ +9,5 Elo` : tester à 12 M coûterait 12h14 par fit
# (mesuré) contre ~1h30, pour un facteur dont on connaît la borne.
#
# Aucune promotion. La porte C2 vs C0 est un job SÉPARÉ.
set -Eeuo pipefail

: "${JASS_CODE_DIR:?}"; : "${JASS_RESULT_DIR:?}"; : "${JASS_ARTEFACT_DIR:?}"
: "${JASS_JOB_ID:?}"; : "${JASS_OBJSTORE_REMOTE:?}"
: "${EXPECTED_CODE_SHA:?}"; : "${EXPECTED_JOB_ID:?}"
: "${POOL_PREFIX:?}"; : "${POOL_JOB:?}"
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
SUBSAMPLE_SEED="${SUBSAMPLE_SEED:-3141592}"
SPLIT_SEED="${SPLIT_SEED:-577215}"
HOLDOUT_MOD="${HOLDOUT_MOD:-10}"
EXPECTED_EXTRAS="${EXPECTED_EXTRAS:-120}"
# Recette CHAMPIONNE L2LOW, identique sur LES DEUX BRAS — elle s'annule donc
# dans la comparaison. Ne rien y toucher ici : ce job mesure les étiquettes.
FOLD_FLAG="${FOLD_FLAG:---exact-fold}"
L2="${L2:-1e-5}"; LBFGS_GTOL="${LBFGS_GTOL:-1e-4}"
MAXIT="${MAXIT:-4000}"; CHUNK="${CHUNK:-20000}"; LBFGS_MAXCOR=20
FIT_TIMEOUT="${FIT_TIMEOUT:-14400}"
CACHE_MB="${CACHE_MB:-4096}"

MON=""
monitor(){ ( t0=$(date +%s); while true; do
    { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
      printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
      printf 'elapsed_min=%d\n' "$(( ($(date +%s) - t0) / 60 ))"
      printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
      for a in c0 c2; do [ -f "$W/fit-$a.log" ] &&
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

stage fetch-pool-and-parent
python3 jobs/tools/fetch_result_files.py --prefix "$POOL_PREFIX" \
  --file artefacts/vol8m.jnnw.gz=pool.jnnw.gz \
  --file artefacts/vol8m.jsm.gz=pool.jsm.gz \
  --out-dir "$IN" --report "$ART/verified-pool.json" \
  --expected-state completed > "$W/fetch-pool.log" 2>&1 || die "fetch du pool en échec"
python3 - "$ART/verified-pool.json" "$POOL_JOB" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
if r.get("job_id") != sys.argv[2] or r.get("result_state") != "completed":
    raise SystemExit("identite/etat du pool non conforme")
PY
python3 jobs/tools/fetch_result_files.py --prefix "$PARENT_PREFIX" \
  --file work/parent-f2m.pjtw=parent.pjtw \
  --out-dir "$IN" --report "$ART/verified-parent.json" \
  --expected-state completed > "$W/fetch-parent.log" 2>&1 || die "fetch du parent en échec"
[ "$(sha256sum "$IN/parent.pjtw" | awk '{print $1}')" = "$EXPECTED_PARENT_MODEL_SHA256" ] ||
  die "hash du parent non conforme"
gunzip -c "$IN/pool.jnnw.gz" > "$W/pool.jnnw"
gunzip -c "$IN/pool.jsm.gz"  > "$W/pool.jsm"
[ "$(head -c4 "$W/pool.jsm")" = "JSM2" ] || die "sidecar du pool en JSM1 : contexte absent"
say "  pool ✓ (sidecar JSM2) + parent ✓ hash conforme"

stage subsample-and-split
# Sous-échantillonnage UNE SEULE FOIS, puis split par ouverture. C0 et C2
# partagent donc EXACTEMENT le même ordre et la même frontière de holdout.
python3 tools/selfplay_frontier.py mix \
  --source POOL "$W/pool.jnnw" "$W/pool.jsm" 1 \
  --target-records "$TARGET_RECORDS" --seed "$SUBSAMPLE_SEED" \
  --out-data "$W/sub.jnnw" --out-meta "$W/sub.jsm" \
  --manifest "$ART/subsample.json" > "$W/mix.log" 2>&1 || die "sous-échantillonnage en échec"
python3 tools/selfplay_frontier.py split \
  --data "$W/sub.jnnw" --meta "$W/sub.jsm" \
  --holdout-mod "$HOLDOUT_MOD" --seed "$SPLIT_SEED" \
  --out-data "$W/c0.jnnw" --out-meta "$W/c0.jsm" \
  --manifest "$ART/split.json" > "$W/split.log" 2>&1 || die "split en échec"
HOLDOUT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["holdout_records"])' "$ART/split.json")
RECORDS=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["records"])' "$ART/split.json")
[ "$RECORDS" = "$TARGET_RECORDS" ] || die "records=$RECORDS attendu $TARGET_RECORDS"
[ "${HOLDOUT:-0}" -gt 0 ] || die "holdout vide"
say "  C0 ✓ : $RECORDS records, holdout $HOLDOUT (1/$HOLDOUT_MOD par ouverture)"

stage build-engines
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1 ||
  { restore_src; die "génération 8cf en échec"; }
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
[ "$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')" -eq 4251528 ] ||
  { restore_src; die "8cf mismatch"; }
grep -q "g_emasks"      src/scan_eval.cpp || { restore_src; die "archi: scan_eval sans g_emasks"; }
grep -q "root_is_drawn" src/search.cpp    || { restore_src; die "engine predates the drawn-root fix"; }
say "  8cf ✓ TOTAL_BUCKETS=4251528, garde-fou archi ✓"
BASEFLAGS="-DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"
# DEUX binaires, volontairement. Celui des features est bâti SANS EGDB, comme
# tous les fits de la campagne, pour que le dump FEAT reste byte-comparable à
# l'existant. Celui du relabel a besoin de la base. Les mélanger ferait dépendre
# les features d'un drapeau sans rapport avec ce qu'on mesure.
cmake -S . -B "$W/build-feat" $BASEFLAGS > "$W/cmake-feat.log" 2>&1
cmake --build "$W/build-feat" -j"$NCPU" --target jass > "$W/build-feat.log" 2>&1
JF="$W/build-feat/jass"; [ -x "$JF" ] || { restore_src; die "build features sans binaire"; }
EGDIR=""
for cand in /root/egdb_extracted/app /root/egdb/app /root/egdb_extracted /root/egdb; do
  [ -d "$cand" ] && { EGDIR="$cand"; break; }
done
[ -n "$EGDIR" ] || { restore_src; die "aucune base EGDB : la cellule C2 n'a aucun sens sans elle"; }
[ -d /root/egdb_intl ] || { restore_src; die "base trouvée ($EGDIR) mais /root/egdb_intl manque"; }
cmake -S . -B "$W/build-egdb" $BASEFLAGS -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
  > "$W/cmake-egdb.log" 2>&1
cmake --build "$W/build-egdb" -j"$NCPU" --target jass > "$W/build-egdb.log" 2>&1
JE="$W/build-egdb/jass"; [ -x "$JE" ] || { restore_src; die "build EGDB sans binaire"; }
restore_src
say "  binaires ✓ : features (sans EGDB) + relabel (avec EGDB, $EGDIR)"

stage relabel-c2
"$JE" --egdb-relabel "$W/c0.jnnw" "$EGDIR" "$W/c2.jnnw" "$CACHE_MB" \
  > "$W/relabel.log" 2>&1 || die "egdb-relabel en échec"
cp "$W/relabel.log" "$ART/relabel.txt"
grep -E '^egdb-relabel' "$W/relabel.log" | sed 's/^/  /' | tee -a "$RES"
CHANGED=$(sed -n 's/.*, \([0-9]\+\) labels changed.*/\1/p' "$W/relabel.log")
[ "${CHANGED:-0}" -gt 0 ] ||
  die "0 étiquette changée : C2 serait identique à C0, la cellule n'a aucun objet"
say "  étiquettes réécrites : $CHANGED / $RECORDS ($(python3 -c "print(f'{100*$CHANGED/$RECORDS:.2f}')") %)"

stage prove-single-factor
# LE contrôle qui fonde tout ce job. Toute différence entre C0 et C2 doit tomber
# sur l'octet WDL, c'est-à-dire à un offset ≡ 37 (mod 38) après l'en-tête de 8.
python3 - "$W/c0.jnnw" "$W/c2.jnnw" "$CHANGED" "$ART/single-factor.json" <<'PY' | tee -a "$RES"
import hashlib, json, sys
import numpy as np
a = open(sys.argv[1], "rb").read(); b = open(sys.argv[2], "rb").read()
if len(a) != len(b):
    raise SystemExit(f"tailles differentes : {len(a)} vs {len(b)}")
if a[:8] != b[:8]:
    raise SystemExit("en-tetes JNNW differents")
REC, HDR, WDL = 38, 8, 37
if (len(a) - HDR) % REC:
    raise SystemExit(f"taille {len(a)} non multiple de {REC} apres l'en-tete")
# Vectorise : une boucle Python sur 76 Mo coute des dizaines de secondes pour
# rien. On reshape en (n_records, 38) et on compare colonne par colonne.
A = np.frombuffer(a, dtype=np.uint8, offset=HDR).reshape(-1, REC)
B = np.frombuffer(b, dtype=np.uint8, offset=HDR).reshape(-1, REC)
neq = A != B
diff_wdl = int(neq[:, WDL].sum())
diff_other = int(neq.sum()) - diff_wdl
if diff_other:
    raise SystemExit(f"{diff_other} octets differents HORS de l'etiquette : C2 n'est PAS C0 relabellise")
if diff_wdl != int(sys.argv[3]):
    raise SystemExit(f"{diff_wdl} etiquettes differentes mais le moteur en annonce {sys.argv[3]}")
json.dump({"schema": 1, "records_differing_only_on_wdl": diff_wdl,
           "bytes_differing_elsewhere": 0,
           "c0_sha256": hashlib.sha256(a).hexdigest(),
           "c2_sha256": hashlib.sha256(b).hexdigest()},
          open(sys.argv[4], "w"), indent=2, sort_keys=True)
print(f"  UN SEUL FACTEUR PROUVE : {diff_wdl} octets WDL differents, 0 octet ailleurs")
PY

stage python-runtime
python3 -m venv "$W/venv"
if "$W/venv/bin/python" -m pip install --disable-pip-version-check --only-binary=:all: \
     numpy==1.26.4 scipy==1.14.1 > "$W/pip.log" 2>&1; then PINSTACK=historical
else "$W/venv/bin/python" -m pip install --disable-pip-version-check --only-binary=:all: \
    numpy scipy >> "$W/pip.log" 2>&1 || die "pip en échec"; PINSTACK=current; fi
NPV=$("$W/venv/bin/python" -c 'import numpy,scipy;print(numpy.__version__,scipy.__version__)')
say "  pile numérique : $PINSTACK (numpy/scipy $NPV) — PARTAGÉE par les deux bras"
printf '{"stack":"%s","numpy_scipy":"%s"}\n' "$PINSTACK" "$NPV" > "$ART/numeric-stack.json"

stage dump-eval-features
# UN SEUL dump : les positions de C0 et C2 sont identiques, prouvé ci-dessus.
"$JF" --dump-eval-features "$W/c0.jnnw" "$W/corpus.feat" > "$W/features.log" 2>&1 ||
  die "dump-eval-features en échec"
K=$(python3 -c 'import struct,sys;f=open(sys.argv[1],"rb");assert f.read(4)==b"FEAT";print(struct.unpack("<II",f.read(8))[1])' "$W/corpus.feat")
[ "$K" = "$EXPECTED_EXTRAS" ] || die "extras K=$K attendu $EXPECTED_EXTRAS"
say "  extras ✓ K=$K, dump PARTAGÉ par les deux bras"

fit_arm(){   # $1 = nom d'arme, $2 = corpus
  local arm="$1" data="$2"
  stage "fit-$arm"
  set +e
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" PYTHONUNBUFFERED=1 \
    timeout "$FIT_TIMEOUT" "$W/venv/bin/python" pattern_jass/tools/train_stream.py \
      --data "$data" --feat "$W/corpus.feat" --out "$W/$arm.pjtw" \
      --target wdl --loss logistic "$FOLD_FLAG" --tempo-stage \
      --prior-mean "$IN/parent.pjtw" --prior-decay 0 \
      --holdout-count "$HOLDOUT" --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" \
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
fit_arm c0 "$W/c0.jnnw"
fit_arm c2 "$W/c2.jnnw"

stage verify-arms-differ
cmp -s "$W/c0.pjtw" "$W/c2.pjtw" &&
  die "les deux modèles sont IDENTIQUES — le relabel n'a rien changé au fit"
say "  bras distincts ✓ ($(stat -c%s "$W/c0.pjtw") octets chacun, contenus différents)"

stage report
say "L3_TB_RELABEL_AB_REFIT_READY changed=$CHANGED records=$RECORDS promotion=false automatic_next_job=null"
: > "$ART/PROMOTION_AUTHORIZED__FALSE"
: > "$ART/AUTOMATIC_NEXT_JOB__NULL"
: > "$ART/VERDICT__L3_TB_RELABEL_AB_REFIT_READY"
stage complete

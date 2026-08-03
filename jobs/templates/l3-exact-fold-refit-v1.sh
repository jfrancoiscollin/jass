#!/usr/bin/env bash
# L3 — refit du corpus TURNOVER sous la symétrie EXACTE du damier.
#
# `symmetry.py` le dit dans son propre docstring : la symétrie exacte du damier
# est `rot180 ∘ colour-swap` ; `cs` seule et `rot` seule sont APPROXIMATIVES (les
# pions ont une direction) mais mutualisent des données. Mesuré sur TURNOVER,
# entraîné en `--color-fold` : la contrainte approximative est satisfaite à
# 0,0000 % près, et la symétrie exacte est violée à 25,8 %. On imposait
# structurellement l'approximation et on laissait la vraie s'apprendre — mal.
#
# `--exact-fold` ne plie que sur `{id, rot180∘cs}` : 2 125 764 poids canoniques
# pour la géométrie 8cf, soit EXACTEMENT le compte de Scan.
#
# ⚠️ CE N'EST PAS UN GAIN DE CAPACITÉ, et il ne faut pas le vendre comme tel. Le
# log de `home-0977` montre que `--color-fold` atteint déjà TB = 2 125 768 : les
# deux folds mutualisent le même NOMBRE de configurations par poids. Ce qui change
# est CE QU'ILS MUTUALISENT. `cs` seule identifie des positions qui ne sont pas
# équivalentes (un pion a une direction), donc elle injecte un biais dans chaque
# bucket ; `rot180∘cs` n'identifie que des positions réellement équivalentes.
# L'effet attendu est la disparition d'un biais systématique, pas une réduction de
# variance. Le moteur n'est pas touché : la sortie reste un `.pjtw` 8cf.
#
# ⚠️ DEUX BRAS DANS LE MÊME ENVIRONNEMENT. Le bras CONTROL rejoue la recette de
# TURNOVER (`--color-fold`) sur le MÊME corpus, le MÊME parent, les MÊMES
# hyperparamètres. Comparer le bras EXACT à l'artefact TURNOVER d'origine
# mélangerait l'effet du fold avec la dérive d'environnement (BLAS, CPU, versions)
# entre HOME et cpx62. Le seul écart entre les deux bras est le drapeau de fold.
#
# Aucune promotion. Les deux modèles sont des candidats à porte, rien de plus.
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
EXPECTED_RECORDS=2000000
EXPECTED_HOLDOUT=199204
EXPECTED_EXTRAS=120

# Hyperparamètres de home-0977, à l'identique. Les changer casserait la seule
# chose que ce job mesure.
L2="${L2:-3e-5}"; LBFGS_MAXCOR=20; CHUNK=20000
# `l2` est per-bras depuis le 3 aout. Motif : sous `--prior-mean`, `l2` N'EST
# PLUS une force de retrecissement vers zero, c'est la force du rappel VERS LE
# PARENT — le meme nombre, un autre sens. Sa valeur `3e-5` a ete close en
# juillet (`l2_factor_closed_on_3e5`) sur un ridge centre sur ZERO ; cette
# fermeture ne se transporte donc pas a la recette courante.
ARM_A_L2="${ARM_A_L2:-$L2}"; ARM_B_L2="${ARM_B_L2:-$L2}"
# `gtol` est un critere d'ARRET, pas un parametre du modele — et il n'est pas
# neutre entre parametrisations. `cpx62-1155` : le bras men-only descend a
# 0,000548 en 141 iterations, le bras king-aware s'arrete a 0,000913 en 12, avec
# 20 % de parametres libres EN PLUS. Les deux rapportent `success=True` ; l'un a
# convergé, l'autre a effleuré le seuil. Un A/B dont un bras est sous-ajuste ne
# mesure pas le facteur annonce. Exposé ici, defaut inchange pour que tous les
# jobs anterieurs reproduisent a l'identique. Les DEUX bras le partagent
# toujours : un gtol par bras introduirait un second facteur.
LBFGS_GTOL="${LBFGS_GTOL:-1e-3}"
# Par bras, quand la TOLERANCE elle-meme est le facteur mesure. Defaut = la
# valeur partagee, donc rien ne change pour les jobs qui comparent autre chose.
ARM_A_GTOL="${ARM_A_GTOL:-$LBFGS_GTOL}"; ARM_B_GTOL="${ARM_B_GTOL:-$LBFGS_GTOL}"
# `max_iter` etait code en dur a 1000. cpx62-1159 a converge en 904 : a une
# tolerance plus serree on depasserait le plafond, et L-BFGS s'arreterait sur
# `max_iter` en rapportant quand meme success=True. Le readout verifie donc
# aussi le MESSAGE, pas seulement le drapeau.
MAXIT="${MAXIT:-1000}"
FIT_TIMEOUT="${FIT_TIMEOUT:-3600}"   # home-0977 : 1933 s pour le fit color

MON=""
monitor(){
  ( t0=$(date +%s)
    while true; do
      { printf 'time_fr=%s\n' "$(TZ=Europe/Paris date '+%Y-%m-%dT%H:%M:%S%z')"
        printf 'phase=%s\n' "$(cat "$STAGE" 2>/dev/null || echo unknown)"
        printf 'elapsed_min=%d\n' "$(( ($(date +%s) - t0) / 60 ))"
        printf 'disk_free_mb=%s\n' "$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')"
        for a in control exact; do
          [ -f "$W/fit-$a.log" ] &&
            printf '%s_fit_lines=%s\n' "$a" "$(wc -l < "$W/fit-$a.log")"
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
[ "$(git rev-parse HEAD)" = "$EXPECTED_CODE_SHA" ] || die "code SHA mismatch"
[ -z "$(git branch --show-current)" ] || die "worktree must be detached"
[ "${FULL_RUN_APPROVED:-0}" = 1 ] && [ "${SCIENTIFIC_GO:-0}" = 1 ] ||
  die "scientific authorization missing"
[ "${NO_AUTOMATIC_CONTINUATION:-0}" = 1 ] || die "automatic continuation guard missing"

stage disk-guard
find /root -maxdepth 1 -name 'cw-*' -type d -mmin +180 ! -path "$W" -exec rm -rf {} + 2>/dev/null || true
DFA=$(df -Pm "$JASS_RESULT_DIR" | awk 'NR==2{print $4}')
[ "${DFA:-0}" -gt 5000 ] || die "moins de 5 Go libres (${DFA} Mo)"
NCPU=$(nproc)
say "  nproc=$NCPU libre=${DFA}Mo"
monitor

stage fetch-turnover-corpus-and-parent
python3 jobs/tools/fetch_result_files.py --prefix "$TURNOVER_TRAIN_PREFIX" \
  --file work/m2.fit.jnnw=corpus.jnnw \
  --file work/parent-f2m.pjtw=parent.pjtw \
  --file artefacts/m2-split.json=split.json \
  --out-dir "$IN" --report "$ART/verified-turnover-train.json" \
  --expected-state completed > "$W/fetch.log" 2>&1 || die "fetch en échec — voir fetch.log"
python3 - "$ART/verified-turnover-train.json" "$EXPECTED_TURNOVER_TRAIN_JOB" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
if r.get("job_id") != sys.argv[2] or r.get("result_state") != "completed":
    raise SystemExit("source identity/state mismatch")
PY
[ "$(sha256sum "$IN/parent.pjtw" | awk '{print $1}')" = "$EXPECTED_PARENT_MODEL_SHA256" ] ||
  die "parent model hash drift"
HOLDOUT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["holdout_records"])' "$IN/split.json")
RECORDS=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["records"])' "$IN/split.json")
[ "$RECORDS" = "$EXPECTED_RECORDS" ] || die "corpus records=$RECORDS attendu $EXPECTED_RECORDS"
[ "$HOLDOUT" = "$EXPECTED_HOLDOUT" ] || die "holdout=$HOLDOUT attendu $EXPECTED_HOLDOUT"
say "  corpus ✓ $RECORDS positions, holdout $HOLDOUT, parent hash conforme"

stage build-8cf-geometry
python3 pattern_jass/tools/gen_patterns.py --emit --variant 8cf > "$W/gen8.log" 2>&1 ||
  { restore_src; die "génération 8cf en échec"; }
cp pattern_jass/tools/patterns.py "$GEOM/patterns.py"
[ "$(PYTHONPATH="$GEOM" python3 -c 'import patterns; print(patterns.TOTAL_BUCKETS)')" -eq 4251528 ] ||
  { restore_src; die "8cf mismatch"; }
grep -q "g_emasks"        src/scan_eval.cpp || { restore_src; die "archi: scan_eval sans g_emasks"; }
grep -q "root_is_drawn"   src/search.cpp    || { restore_src; die "engine predates the drawn-root fix"; }
say "  8cf ✓ TOTAL_BUCKETS=4251528, garde-fou archi ✓"
# Mêmes drapeaux de features que home-0977 : 110+4+6 = 120 extras. EGDB est
# volontairement absent — c'est une base de finales pour la RECHERCHE, elle
# n'entre pas dans l'extraction de features, et l'exiger lierait ce fit à un
# fichier de 700 Mo sans rapport avec ce qu'il mesure. Le compte d'extras est
# asserté plus bas : si l'hypothèse est fausse, le job s'arrête là.
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON \
  -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON \
  > "$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass > "$W/build.log" 2>&1
J="$W/build/jass"; [ -x "$J" ] || { restore_src; die "build sans binaire"; }
restore_src

stage python-runtime-and-selftests
python3 -m venv "$W/venv"
# L'épinglage historique (numpy 1.26.4 / scipy 1.14.1, celui de home-0977) n'est
# plus servi pour le Python de cpx62 : PyPI ne propose plus que numpy >= 2.3 en
# roue pour cette version, et cpx62-1115 est mort là-dessus en cinq minutes.
# On tente l'épinglage d'abord — s'il passe, on est byte-comparable à l'origine —
# puis on retombe sur les versions courantes. Les DEUX bras partagent de toute
# façon la pile numérique, donc la comparaison interne ne dépend pas de ce choix ;
# seule la comparabilité avec l'artefact TURNOVER d'origine en dépend, et c'est
# précisément pourquoi ce job a son propre bras de contrôle. Les versions
# réellement résolues sont écrites dans le rapport.
if "$W/venv/bin/python" -m pip install --disable-pip-version-check --only-binary=:all: \
     numpy==1.26.4 scipy==1.14.1 > "$W/pip.log" 2>&1; then
  PINSTACK=historical
else
  "$W/venv/bin/python" -m pip install --disable-pip-version-check --only-binary=:all: \
    numpy scipy >> "$W/pip.log" 2>&1 || die "pip en échec — voir pip.log"
  PINSTACK=current
fi
NPV=$("$W/venv/bin/python" -c 'import numpy,scipy;print(numpy.__version__,scipy.__version__)')
say "  pile numérique : $PINSTACK (numpy/scipy $NPV)"
printf '{"stack":"%s","numpy_scipy":"%s"}\n' "$PINSTACK" "$NPV" > "$ART/numeric-stack.json"
env PYTHONPATH="$GEOM:pattern_jass/tools" "$W/venv/bin/python" \
  pattern_jass/tools/test_exact_fold.py -v > "$W/selftest.log" 2>&1 ||
  die "auto-tests des folds exacts en échec — voir selftest.log"
say "  venv + auto-tests du fold ✓"

stage dump-eval-features
"$J" --dump-eval-features "$IN/corpus.jnnw" "$W/corpus.feat" > "$W/features.log" 2>&1 ||
  die "dump-eval-features en échec"
K=$(python3 -c 'import struct,sys;f=open(sys.argv[1],"rb");assert f.read(4)==b"FEAT";print(struct.unpack("<II",f.read(8))[1])' "$W/corpus.feat")
[ "$K" = "$EXPECTED_EXTRAS" ] ||
  die "extras K=$K attendu $EXPECTED_EXTRAS — géométrie différente de TURNOVER, comparaison invalide"
say "  extras ✓ K=$K (identique à TURNOVER)"

# `$3` = mode de CONTINUATION. `--warm-start` ne touche que le point de départ
# de l'optimiseur : l'objectif garde un L2 **centré sur zéro**, ce qui affirme
# qu'en l'absence de données un bucket vaut 0. C'est faux quand on continue une
# lignée — la meilleure estimation est celle du parent — et ça décide du sort de
# la majorité des buckets, qui ne sont vus que quelques fois. `--prior-mean`
# déplace le centre du ridge sur le champion ; avec `--prior-decay 0` la
# précision reste uniformément `l2`, donc SEUL le centre bouge.
fit_arm(){   # $1 = nom, $2 = fold, $3 = gtol, $4 = l2, $5... = continuation
  local arm="$1" foldflag="$2" gtol="$3" l2v="$4"; shift 4
  stage "fit-$arm"
  set +e
  env JASS_PATTERNS_DIR="$GEOM" PYTHONPATH="$GEOM:pattern_jass/tools" \
    timeout "$FIT_TIMEOUT" "$W/venv/bin/python" pattern_jass/tools/train_stream.py \
      --data "$IN/corpus.jnnw" --feat "$W/corpus.feat" --out "$W/$arm.pjtw" \
      --target wdl --loss logistic "$foldflag" --tempo-stage \
      "$@" --holdout-count "$HOLDOUT" \
      --l2 "$l2v" --max-iter "$MAXIT" --chunk "$CHUNK" \
      --lbfgs-maxcor "$LBFGS_MAXCOR" --lbfgs-gtol "$gtol" \
      --prune \
      --optimizer-report "$ART/$arm-optimizer.json" \
      > "$W/fit-$arm.log" 2> "$W/fit-$arm-time.log"
  local rc=$?
  set -e
  [ "$rc" -eq 0 ] || die "fit $arm rc=$rc — voir fit-$arm.log"
  [ -s "$W/$arm.pjtw" ] || die "fit $arm sans modèle"
  # `success` seul ne suffit pas : un arret sur `max_iter` le rapporte vrai.
  python3 - "$ART/$arm-optimizer.json" "$arm" <<'PYCHK' || die "fit $arm : arret non concluant"
import json, sys
d = json.load(open(sys.argv[1]))
msg = str(d.get("message", ""))
if not d.get("success"):
    raise SystemExit(f"{sys.argv[2]}: success=False")
if "PGTOL" not in msg.upper():
    raise SystemExit(f"{sys.argv[2]}: arret sur '{msg}' et non sur le gradient")
PYCHK
  gzip -n -c "$W/$arm.pjtw" > "$ART/$arm.pjtw.gz"
  local ll; ll=$(grep -o 'HOLDOUT_LOGLOSS[= ][0-9.]*' "$W/fit-$arm.log" | tail -1)
  local it; it=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["iterations"])' \
    "$ART/$arm-optimizer.json" 2>/dev/null || echo "?")
  say "  $arm : convergé, $it itérations, ${ll:-holdout n/a}"
}

# Le bras B est paramétrable : `--exact-fold` (rot180∘cs seul) par défaut, ou
# `--exact-lr-fold` pour y ajouter la réflexion gauche-droite, elle aussi exacte.
ARM_A_FOLD="${ARM_A_FOLD:---color-fold}"
ARM_B_FOLD="${ARM_B_FOLD:---exact-fold}"
for f in "$ARM_A_FOLD" "$ARM_B_FOLD"; do
  case "$f" in --color-fold|--exact-fold) ;; *) die "fold invalide : $f";; esac
done
# Continuations, en mots pour éviter les guillemets imbriqués dans un job.
# `warm` = recette courante (L2 centré 0) ; `prior` = ridge centré sur le parent.
cont_args(){ case "$1" in
  warm)  printf '%s\n%s\n' --warm-start "$IN/parent.pjtw" ;;
  # `--king-patterns` n'agrandit PAS l'espace : il OR les dames dans
  # l'occupation (`pb = bm|bk`), donc `n_pat` est inchangé et le warm-start
  # depuis un parent men-only reste structurellement valide. Ce qui change est
  # le SENS d'une case occupée — les poids du parent servent d'initialisation,
  # pas de vérité, ce qui est exactement ce que `--warm-start` promet.
  warmking) printf '%s\n%s\n%s\n' --warm-start "$IN/parent.pjtw" --king-patterns ;;
  prior) printf '%s\n%s\n%s\n%s\n' --prior-mean "$IN/parent.pjtw" --prior-decay 0 ;;
  priorking) printf '%s\n%s\n%s\n%s\n%s\n' --prior-mean "$IN/parent.pjtw" --prior-decay 0 --king-patterns ;;
  # `priorvisit` = le prior sequentiel-bayesien PONDERE PAR LES VISITES, celui de
  # l'ere gen1/gen2. La precision devient `l2 + decay*lam*(visites_j/N)`, donc le
  # rappel vers le parent est le PLUS FORT la ou les donnees sont les PLUS
  # abondantes — l'inverse du motif qui justifiait le prior. `--prior-decay 0`
  # (la recette championne) annule ce terme et rend le rappel uniforme.
  # ⚠️ A `decay=0`, `lam` est INERTE : `dec*lam = 0`. Ne pas balayer lam a
  # decay 0 en croyant balayer une dose.
  priorvisit) printf '%s\n%s\n%s\n%s\n%s\n%s\n' --prior-mean "$IN/parent.pjtw" \
                --prior-decay "$PRIOR_DECAY" --prior-visit-scale "$PRIOR_LAM" ;;
  *) die "continuation invalide : $1" ;; esac; }
PRIOR_DECAY="${PRIOR_DECAY:-1.0}"; PRIOR_LAM="${PRIOR_LAM:-0.25}"
ARM_A_CONT="${ARM_A_CONT:-warm}"; ARM_B_CONT="${ARM_B_CONT:-warm}"
say "  bras A : $ARM_A_FOLD / $ARM_A_CONT"
say "  bras B : $ARM_B_FOLD / $ARM_B_CONT"
mapfile -t A_ARGS < <(cont_args "$ARM_A_CONT")
mapfile -t B_ARGS < <(cont_args "$ARM_B_CONT")
say "  gtol : A=$ARM_A_GTOL  B=$ARM_B_GTOL  max_iter=$MAXIT"
say "  l2   : A=$ARM_A_L2  B=$ARM_B_L2"
case "$ARM_A_CONT$ARM_B_CONT" in *priorvisit*) say "  prior pondere : decay=$PRIOR_DECAY lam=$PRIOR_LAM";; esac
fit_arm control "$ARM_A_FOLD" "$ARM_A_GTOL" "$ARM_A_L2" "${A_ARGS[@]}"
fit_arm exact   "$ARM_B_FOLD" "$ARM_B_GTOL" "$ARM_B_L2" "${B_ARGS[@]}"

stage verify-symmetries
env PYTHONPATH="$GEOM:pattern_jass/tools" "$W/venv/bin/python" - \
  "$W/control.pjtw" "$W/exact.pjtw" "$ART/symmetry-report.json" \
  "$ARM_A_FOLD" "$ARM_B_FOLD" <<'PY' | tee -a "$RES"
import json, struct, sys
import numpy as np
import patterns as P, symmetry as S
NB, NP = P.BUCKETS_PER_PATTERN, P.NUM_PATTERNS
cs = S.colorswap_map(); rp, rotperm = S.rot_structure()
rotcs = [cs[S._reorder_all(rotperm[p])] for p in range(NP)]
def viol(pat, sig):
    ok = bad = 0.0
    for p in range(NP):
        q, s = sig(p)
        a = pat[p].astype(np.float64); b = -pat[q][s].astype(np.float64)
        ok += np.sum((0.5*(a+b))**2); bad += np.sum((0.5*(a-b))**2)
    return float(bad/(ok+bad)) if ok+bad else 0.0
out = {}
for name, path in (("control", sys.argv[1]), ("exact", sys.argv[2])):
    raw = open(path, "rb").read()
    _, _, _, n_pat, n_ext = struct.unpack("<5I", raw[:20])
    pat = np.frombuffer(raw[20:], dtype="<i4")[:n_pat].reshape(NP, NB)
    e = viol(pat, lambda p: (rp[p], rotcs[p]))
    c = viol(pat, lambda p: (p, cs))
    out[name] = {"violation_rot180_cs_EXACT": round(e, 8),
                 "violation_colourswap_approx": round(c, 8)}
    print(f"  {name:<8} rot180∘cs (EXACTE) = {100*e:7.4f} %   cs seule (approx) = {100*c:7.4f} %")
json.dump(out, open(sys.argv[3], "w"), indent=2, sort_keys=True)
# Chaque bras doit satisfaire la symétrie que SON fold impose — pas celle du
# voisin. La version précédente exigeait que `control` VIOLE `rot180∘cs`, ce qui
# n'avait de sens que tant que le bras A était forcément `--color-fold`. Depuis
# que les folds sont paramétrables, deux bras `--exact-fold` (comparés sur un
# autre facteur, le prior par exemple) faisaient échouer cette assertion APRÈS
# que les deux modèles aient été produits — bug de cpx62-1145.
folds = {"control": sys.argv[4], "exact": sys.argv[5]}
for name, fold in folds.items():
    key = ("violation_rot180_cs_EXACT" if fold == "--exact-fold"
           else "violation_colourswap_approx")
    if out[name][key] > 1e-9:
        raise SystemExit(f"le bras {name} ({fold}) ne satisfait PAS la symétrie "
                         f"qu'il impose : {key}={out[name][key]}")
# Le vrai garde-fou « l'expérience n'est pas vide » ne porte pas sur une symétrie
# mais sur les modèles eux-mêmes : deux bras identiques rendraient une porte sans
# objet, quel que soit le facteur qu'on croyait faire varier.
a = open(sys.argv[1], "rb").read(); b = open(sys.argv[2], "rb").read()
if a == b:
    raise SystemExit("les deux bras sont le MÊME modèle — l'expérience est vide")
print(f"  bras distincts ✓ ({len(a)} vs {len(b)} octets, contenus différents)")
PY

stage report
python3 - "$ART" <<'PY' | tee -a "$RES"
import glob, json, os, sys
art = sys.argv[1]
d = {}
for a in ("control", "exact"):
    o = json.load(open(os.path.join(art, f"{a}-optimizer.json")))
    d[a] = {"iterations": o["iterations"], "converged": o["success"],
            "grad_inf": o["gradient_inf_norm"]}
print(f"  control : {d['control']['iterations']} itérations, convergé={d['control']['converged']}")
print(f"  exact   : {d['exact']['iterations']} itérations, convergé={d['exact']['converged']}")
json.dump(d, open(os.path.join(art, "fit-summary.json"), "w"), indent=2, sort_keys=True)
PY
cp "$ART/symmetry-report.json" "$ART/JASS_CONTROL_SUMMARY.json"
VERDICT=L3_EXACT_FOLD_REFIT_READY
: > "$ART/VERDICT__$VERDICT"
printf 'PROMOTION_AUTHORIZED__FALSE\n' > "$ART/PROMOTION_AUTHORIZED__FALSE"
printf 'AUTOMATIC_NEXT_JOB__NULL\n'    > "$ART/AUTOMATIC_NEXT_JOB__NULL"
say "$VERDICT deux modèles produits promotion=false automatic_next_job=null"

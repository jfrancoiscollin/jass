#!/usr/bin/env bash
# id: cpx62-0483-forcing-extension-ab
# description: LE DECIDEUR MANQUANT (briefing externe #1, 2026-06-27) — l'ecart 0440 est-il de la RECHERCHE (extensions sur
# coups forcants) et NON de l'eval ? Tous les A/B search anterieurs (0436 elagage, 0451 no_reduce_forcing) ont isole
# l'ELAGAGE et la NON-REDUCTION ; AUCUN n'a teste une EXTENSION. Or a profondeur fixe d11 (la jauge 0440), une ligne
# sac->rafle->regain de 2-6 plis peut etre coupee par l'horizon : le coup de SAC (un coup QUIET qui laisse l'adversaire en
# capture forcee) consomme de la profondeur, et si le budget s'epuise au milieu de l'echange l'eval-feuille voit "materiel
# en moins" -> jass evite le bon sacrifice. Le nouveau flag `ext_forcing` (src/search.cpp + search_params.hpp) ETEND de
# +1 ply tout coup quiet qui force une capture adverse (et l'exempte de LMR/LMP pour que l'extension ne soit pas defaite
# par l'elagage) -> la ligne forcee se resout a profondeur effective complete, independamment de l'horizon nominal.
#
# TEST : on REJOUE la jauge 0440 (data/dilf_combinations.fen, depth 11, eval-pur no-DB, vs Scan) sur le CHAMPION egdbmix
# ACTUEL — AUCUN re-entrainement — sous 3 configs de recherche, pour isoler proprement l'extension :
#   A baseline   : ""                     (defauts actuels — reproduit egdbmix 0.302)
#   B no-reduce  : no_reduce_forcing=1     (le levier 0451 SEUL : non-reduction sans extension — attendu ~baseline)
#   C ext-forcing: ext_forcing=1           (le NOUVEAU levier : extension +1 + exemption — implique B)
# => C - B = effet PUR de l'extension ; C - A = traitement forcant complet. IC95 bootstrap (2000 resamples) par bras.
#
# DECISION GATE :
#   C monte HORS IC (> ~0.35, idealement bien plus) ==> l'ecart 0440 etait de la RECHERCHE -> baker l'extension, re-mesurer
#       vs Scan a temps compense ; la gate NNUE devient NON PERTINENTE. (Coherent avec 0451 : a movetime jass atteint d14-16
#       et convertit 0.519 -> l'extension importe l'effet-movetime a d11.)
#   C reste ~0.30 (~A) ==> confirme "c'est l'EVAL" PROPREMENT cette fois (sans le confond extensions) -> passer aux leviers
#       donnees du briefing (#2 ballots / #4 quiet-only / #6 maitres-distribution).
# 100% recherche, AUCUN re-entrainement, AUCUN NNUE. Job court (3 x ~610 parties d11 vs Scan).
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0483-forcing-extension-ab/artefacts"; mkdir -p "$ART"
W=/root/cw-forcingext; mkdir -p "$W"
RES="$ART/RESULTS.txt"; SUM="$ART/SUMMARY.txt"
say(){ echo "$@" | tee -a "$RES"; }
[ -f "$RES" ] || : > "$RES"; [ -f "$SUM" ] || : > "$SUM"
DILF=data/dilf_combinations.fen
SCAN_BIN=/root/jass-scan/scan_linux
EGDBMIX=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
D=11

[ -x "$SCAN_BIN" ] || { say "ABORT: Scan absent ($SCAN_BIN) — la jauge 0440 a besoin de Scan"; exit 4; }

# ---- build (memes flags que 0481 : egdb ON pour matcher le champion ; path unset au jeu => eval-pur no-DB) ----
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
# sanity : le flag ext_forcing est-il bien parse ? (sinon le test ne teste rien)
"$J" --search-params "ext_forcing=1" --version >/dev/null 2>&1 || true   # ne casse pas si --version ignore le flag
git cat-file -e "origin/main:$EGDBMIX" 2>/dev/null && git show "origin/main:$EGDBMIX" | gunzip > "$W/egdbmix.pjtw" || { say "ABORT: egdbmix absent"; exit 4; }

conv_ci(){ python3 - "$1" "$DILF" <<'PY'
import json,glob,sys,os
gdir,fens=sys.argv[1],sys.argv[2]; stm={}
for ln in open(fens):
    b=ln.split('#',1)[0].strip()
    if b: stm[b]=b.split(':',1)[0]
aw=[]
for f in sorted(glob.glob(os.path.join(gdir,"game-*.json"))):
    try: g=json.load(open(f))
    except: continue
    op=g.get("opening","").strip(); s=stm.get(op)
    if s is None: continue
    jiw=g.get("jass_is_white"); out=g.get("outcome")
    if not ((jiw and s=="W") or ((not jiw) and s=="B")): continue
    aw.append(0.5 if out=="D" else (1.0 if ((out=="W" and s=="W") or (out=="L" and s=="B")) else 0.0))
n=len(aw)
if not n: print("NA NA NA 0"); sys.exit(0)
m=sum(aw)/n; seed=12345; boots=[]
for _ in range(2000):
    acc=0
    for _ in range(n):
        seed=(1103515245*seed+12345)&0x7fffffff; acc+=aw[seed%n]
    boots.append(acc/n)
boots.sort(); print(f"{m:.3f} {boots[50]:.3f} {boots[1949]:.3f} {n}")
PY
}

# ---- les 3 bras (reprise-safe : un bras dont le dump existe deja est saute) ----
ARMS=("A_baseline:" "B_noreduce:no_reduce_forcing=1" "C_extforcing:ext_forcing=1")
say "=== 0440 forcing-extension A/B (champion egdbmix, depth $D, eval-pur no-DB, vs Scan) ==="
for entry in "${ARMS[@]}"; do
  name="${entry%%:*}"; spec="${entry#*:}"
  DGD="$ART/conv-$name"
  if ls "$DGD"/game-*.json >/dev/null 2>&1; then
    say "  (reprise) bras $name deja joue -> juge seulement"
  else
    mkdir -p "$DGD"
    SP=(); [ -n "$spec" ] && SP=(--jass-search-params "$spec")
    ( unset JASS_EGDB_PATH; python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" \
        --jass-pattern "$W/egdbmix.pjtw" --scan-bb-size 0 --depth "$D" --pairs 1 \
        --openings-file "$DILF" --dump-games-dir "$DGD" "${SP[@]}" >"$W/cv-$name.log" 2>&1 ) \
      || say "  (bras $name : calibrate a signale une erreur, on juge ce qui est dumpe)"
  fi
  read M LO HI N < <(conv_ci "$DGD")
  line="$name  spec=[${spec:-<defauts>}]  0440=$M  IC95=[$LO,$HI]  (n=$N)"
  say "$line"; echo "$line" >> "$SUM"
done

say ""
say "================= LECTURE ================="
say "  baseline egdbmix attendu ~0.30. B (no_reduce SEUL) attendu ~baseline (reproduit 0451)."
say "  C (ext_forcing) HORS IC au-dessus (>~0.35) => l'ecart 0440 etait de la RECHERCHE (extension) => baker + re-juger"
say "       vs Scan a temps compense ; gate NNUE non pertinente."
say "  C ~ A => c'est l'EVAL, prouve proprement sans le confond extensions => leviers donnees (#2/#4/#6 du briefing)."
say "  Effet PUR extension = C - B ; traitement forcant complet = C - A."
cat "$SUM" | sed 's/^/  /' | tee -a "$RES"
say "==========================================="

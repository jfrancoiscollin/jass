#!/usr/bin/env bash
# id: ccx33-0592-search-ablation-fixdepth
# description: ABLATION SEARCH A PROFONDEUR FIXE (JFC "va y") — 0571 : jass a -338 Elo vs Scan a d9 (qualite PAR NOEUD),
# on ne survit qu'a la vitesse (net -150/-190 movetime). A4/0590 : eval statique ~parite => le deficit fixed-depth est
# SEARCH-side. Ce job LOCALISE lequel : quiescence (feuilles tactiques bruitees), reductions (prof. effective < nominale),
# ou ordering. Toutes cellules vs Scan, memes ouvertures dilf, gen1 (champion), moteur COIN par defaut ; les variantes
# overrident --jass-search-params PAR-DESSUS le coin (parse merge sur defauts). Lecture : une variante qui REMONTE le rate
# d9 au-dessus de base_d9(0.125) => CE composant avait du headroom => levier search a prioriser. Si AUCUNE ne bouge =>
# deficit = qualite eval-en-arbre / ordering de base => investigation structurelle. La courbe d7/d9/d11 reconfirme la
# sensibilite a la profondeur (gap retrecit => levier EBF/profondeur valide). AUCUN NNUE, recherche mesuree pas modifiee-bake.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0592-search-ablation-fixdepth/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/ccx33-0592-search-ablation-fixdepth/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-searchabl; rm -rf "$W"; mkdir -p "$W"
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
DILF=data/dilf_combinations.fen
PAIRS=2; NOPEN=60   # => 60*2*2 = 240 games/cellule

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

# ---- Scan pret ----
SCAN_BIN=/root/jass-scan/scan_linux
if [ ! -x "$SCAN_BIN" ]; then
  SRC=/root/jass-scan-src; [ -d "$SRC" ] || git clone --depth=1 https://github.com/rhalbersma/scan.git "$SRC" >"$W/sc.log" 2>&1
  mkdir -p /root/jass-scan; cp "$SRC/scan_linux" "$SCAN_BIN" 2>/dev/null && chmod +x "$SCAN_BIN"
  cp -r "$SRC/data" /root/jass-scan/data 2>/dev/null||true; cp "$SRC/scan.ini" /root/jass-scan/scan.ini 2>/dev/null||true
fi
[ -x "$SCAN_BIN" ] || { say "ABORT Scan absent"; exit 3; }

say "=== ablation search fixed-depth vs Scan — HEAD $(git log --oneline -1|cat) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
head -n "$NOPEN" "$DILF" > "$W/open.fen"
say "  eval=gen1 ; openings=$(wc -l <"$W/open.fen") ; ~$((NOPEN*PAIRS*2)) games/cellule ; coin=$(git show origin/main:src/search_params.hpp|grep -cE 'probcut_min_depth = 5|qs_threat_ext = true|lmr_first_full_nonpv = 2')/3"

# cellules : tag|depth|search-params(vide=coin defaut)
CELLS=(
  "base_d7|7|"
  "base_d9|9|"
  "base_d11|11|"
  "qsstrong_d9|9|qs_forcing_depth=6,qs_promo_depth=6"
  "softlmr_d9|9|lmr_first_full_nonpv=4,lmr_min_depth=6"
  "histlmr_d9|9|lmr_hist_div=6000"
  "noreduce_d9|9|lmr_min_depth=99,lmp_max_depth=0,razor_max_depth=0,probcut_min_depth=0"
  "allon_d9|9|qs_forcing_depth=6,qs_promo_depth=6,lmr_hist_div=6000,lmr_first_full_nonpv=4"
)
run_cell(){ local tag="$1" depth="$2" spec="$3"
  local extra=""; [ -n "$spec" ] && extra="--jass-search-params $spec"
  python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/gen1.pjtw" \
    --scan-bb-size 0 --depth "$depth" $extra --pairs "$PAIRS" --openings-file "$W/open.fen" \
    >"$W/cell_$tag.log" 2>&1
}
say ""; say "=== lancement des ${#CELLS[@]} cellules en parallele (1 coeur/cellule) ==="
PIDS=()
for e in "${CELLS[@]}"; do IFS='|' read -r tag depth spec <<<"$e"
  run_cell "$tag" "$depth" "$spec" & PIDS+=($!); say "  cellule $tag lancee (d$depth ${spec:-coin}) pid $!"
done
wait

say ""; say "=== RESULTATS (rate + Elo + IC95 ~, gen1 vs Scan) ==="
say "  cellule           depth  rate     Elo    IC95(rate)   spec"
for e in "${CELLS[@]}"; do IFS='|' read -r tag depth spec <<<"$e"
  L="$W/cell_$tag.log"
  rate=$(grep -iE 'Jass score rate' "$L" | grep -oE '[0-9]*\.[0-9]+' | head -1)
  elo=$(grep -iE 'ELO estimate' "$L" | grep -oE '[-+]?[0-9]+' | head -1)
  n=$((NOPEN*PAIRS*2))
  ic=$(python3 -c "r=float('${rate:-0}') if '${rate}' else 0; import math; print(f'{1.96*math.sqrt(max(r*(1-r),1e-9)/$n):.3f}')" 2>/dev/null||echo "?")
  printf '  %-16s  d%-3s  %-7s  %-5s  +-%-8s  %s\n' "$tag" "$depth" "${rate:-NA}" "${elo:-NA}" "${ic:-?}" "${spec:-coin}" | tee -a "$RES"
done

say ""
say "  LECTURE (comparer chaque *_d9 a base_d9) :"
say "  - une variante d9 dont le rate depasse base_d9 hors-IC => CE composant (qs/reductions/ordering) avait du"
say "    HEADROOM vs Scan a prof. fixe => c'est LE levier search a attaquer (DOE cible dessus)."
say "  - qsstrong>base => quiescence faible (feuilles tactiques) ; softlmr/noreduce>base => on reduit/prune TROP"
say "    (prof. effective < nominale) ; histlmr>base => ordering-aware reduction paie ; allon = plafond combine."
say "  - si AUCUNE ne bouge => le -338 n'est PAS dans ces boutons => qualite eval-en-arbre / ordering de base =>"
say "    prochaine etape = decomposition ordering (first-move-cutoff rate vs Scan) ou eval sur feuilles tactiques."
say "  - courbe base d7/d9/d11 : gap retrecit avec la profondeur => levier EBF/profondeur valide quoi qu'il arrive."
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0592 ablation search fixed-depth vs Scan : localise le deficit par-noeud (qs/reductions/ordering)" \
  && say "  RESULTS committe ✓" || say "  ⚠ commit echoue"
say "=== fin ablation search fixed-depth ==="

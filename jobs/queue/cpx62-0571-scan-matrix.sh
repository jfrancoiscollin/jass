#!/usr/bin/env bash
# id: cpx62-0571-scan-matrix
# description: MATRICE vs SCAN (JFC) — ou se situe gen1 (moteur COIN) face a Scan selon la config ? 8 cellules //  :
#   PROFONDEUR FIXE d7/d9/d11/d13  = QUALITE d'eval pure (a profondeur egale, notre eval vaut-elle celle de Scan ?)
#   MOVETIME BRUT   mt0.1/0.3/1.0  = FORCE REELLE (inclut notre lenteur d'eval : moins de plies/s => on perd du terrain)
#   NPS-COMPENSE    jass_mt0.6/scan_mt0.3 = isole eval de la VITESSE (on donne 2x le temps a jass pour egaliser la prof.)
# Lecture cle : competitif a prof. fixe mais perdant au movetime => on est VITESSE-limite (optimiser l'eval) ; perdant
# meme a prof. fixe => QUALITE d'eval (capacite). Dump des parties (--dump-games-dir) pour autopsie (job suivant : ou on
# perd/progresse par phase). eval=gen1 (champion ; regen NEUTRE). VERDICT + dumps tar committes job-side. AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/cpx62-0571-scan-matrix/artefacts"; mkdir -p "$ART"
ARTREL="jobs/results/cpx62-0571-scan-matrix/artefacts"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-scanmatrix; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
GEN1_GZ=jobs/results/cpx62-0545-selfplay-gen1-combo/artefacts/champion-gen1-combo.pjtw.gz
DILF=data/dilf_combinations.fen; NOPEN=60; PAIRS=1

commit_to_main(){ local ab="$1" rel="$2" msg="$3"
  for a in 1 2 3 4 5; do git fetch origin main --quiet 2>/dev/null||true
    local idx="/root/.ti.$$.$RANDOM"; rm -f "$idx"; GIT_INDEX_FILE="$idx" git read-tree origin/main 2>/dev/null||return 1
    local b; b=$(git hash-object -w "$ab")||return 1
    GIT_INDEX_FILE="$idx" git update-index --add --cacheinfo 100644 "$b" "$rel"
    local t; t=$(GIT_INDEX_FILE="$idx" git write-tree); local c; c=$(printf '%s\n' "$msg"|git commit-tree "$t" -p origin/main)
    git push origin "$c:main" 2>/dev/null && { rm -f "$idx"; return 0; }; sleep $((a*4)); done; return 1; }

say "=== MATRICE vs SCAN — gen1 (moteur COIN) — HEAD $(git log --oneline -1|cat) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON \
      -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
if [ ! -x "$SCAN_BIN" ]; then
  SRC=/root/jass-scan-src; [ -d "$SRC" ] || git clone --depth=1 https://github.com/rhalbersma/scan.git "$SRC" >"$W/sc.log" 2>&1
  mkdir -p /root/jass-scan; cp "$SRC/scan_linux" "$SCAN_BIN"; chmod +x "$SCAN_BIN"
  cp -r "$SRC/data" /root/jass-scan/data 2>/dev/null||true; cp "$SRC/scan.ini" /root/jass-scan/scan.ini 2>/dev/null||true
fi
[ -x "$SCAN_BIN" ] || { say "ABORT Scan absent"; exit 5; }
git show "origin/main:$GEN1_GZ" | gunzip > "$W/gen1.pjtw" || { say "ABORT gen1"; exit 4; }
grep -vE '^\s*(#|$)' "$DILF" | head -"$NOPEN" > "$W/open.fen"
say "  eval=gen1 ; openings=$(wc -l <"$W/open.fen") (dilf subset) ; pairs=$PAIRS => ~$(( $(wc -l <"$W/open.fen") * PAIRS * 2 )) games/cellule"

# cellules : tag|calibrate-args
CELLS=(
  "d7|--depth 7"
  "d9|--depth 9"
  "d11|--depth 11"
  "d13|--depth 13"
  "mt0.1|--movetime 0.1"
  "mt0.3|--movetime 0.3"
  "mt1.0|--movetime 1.0"
  "nps_j0.6_s0.3|--jass-movetime 0.6 --scan-movetime 0.3"
)
run_cell(){ local tag="$1" args="$2"
  python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/gen1.pjtw" \
    --scan-bb-size 0 $args --pairs "$PAIRS" --openings-file "$W/open.fen" \
    --dump-games-dir "$ART/games_$tag" >"$W/cell_$tag.log" 2>&1
}
say ""; say "=== lancement des 8 cellules en parallele ==="
declare -a PIDS=()
for e in "${CELLS[@]}"; do tag="${e%%|*}"; args="${e#*|}"; run_cell "$tag" "$args" & PIDS+=($!); say "  cellule $tag lancee (pid $!)"; done
wait

say ""; say "=== RESULTATS (score-rate + Elo estime, gen1 vs Scan) ==="
say "  cellule            rate    elo     type"
for e in "${CELLS[@]}"; do tag="${e%%|*}"
  rate=$(grep -iE 'Jass score rate' "$W/cell_$tag.log" | grep -oE '[0-9]*\.[0-9]+' | head -1)
  elo=$(grep -iE 'ELO estimate' "$W/cell_$tag.log" | grep -oE '[-+][0-9]+' | head -1)
  case "$tag" in d*) typ="prof.fixe=QUALITE-eval";; mt*) typ="movetime=FORCE-reelle";; nps*) typ="NPS-comp=eval-isolee";; esac
  printf "  %-16s  %-6s  %-6s  %s\n" "$tag" "${rate:-NA}" "${elo:-NA}" "$typ" | tee -a "$RES"
done
say ""
say "  Lecture : rate(prof.fixe) >> rate(movetime) => VITESSE-limite (eval trop lente, optimiser) ;"
say "            rate(prof.fixe) deja bas          => QUALITE d'eval (capacite, cf DOE 0569 / eval-oracle)."
say "            NPS-comp ~ prof.fixe              => confirme que le handicap movetime est bien la vitesse."

# tar des dumps pour l'autopsie (job suivant) — evite de committer des milliers de JSON en vrac
( cd "$ART" && tar czf games_dumps.tgz games_* 2>/dev/null && rm -rf games_* ) || say "  (tar dumps echoue)"
commit_to_main "$RES" "$ARTREL/RESULTS.txt" "0571 matrice vs Scan : RESULTS job-side (prof.fixe/movetime/NPS)" \
  && say "  RESULTS committe job-side ✓" || say "  ⚠ commit RESULTS echoue"
[ -f "$ART/games_dumps.tgz" ] && { commit_to_main "$ART/games_dumps.tgz" "$ARTREL/games_dumps.tgz" "0571 matrice vs Scan : dumps parties (tar) pour autopsie" \
  && say "  dumps tar committes job-side ($(du -h "$ART/games_dumps.tgz"|cut -f1))" || say "  (commit dumps echoue)"; }
say "=== fin matrice vs Scan ==="

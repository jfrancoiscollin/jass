#!/usr/bin/env bash
# id: ccx33-0484-tools-verify
# description: VERIFICATION reelle (pas gen-data) des outils du briefing avant relance du self-play (directive JFC :
# "code test implemente verifie ensuite on lancera proprement"). Lance les 3 suites unit + execute les 3 outils sur de
# VRAIES donnees (expert_games.db box-local) en petit, et controle que les JNNW produits sont valides. Donne AUSSI le
# vrai resultat du #5 : la calibration (Texel K + ECE par phase) de l'eval egdbmix vs resultats reels. Court (~15 min).
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0484-tools-verify/artefacts"; mkdir -p "$ART"
W=/root/cw-toolsverify; rm -rf "$W"; mkdir -p "$W"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
DB=/root/jass/data/expert_games.db
EGDBMIX=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz

# JNNW validator : prints "OK <count>" or "BAD ..."
jnnw_ok(){ python3 - "$1" <<'PY'
import struct,sys,os
p=sys.argv[1]
try:
    b=open(p,'rb').read()
    assert b[:4]==b'JNNW', "magic"
    n=struct.unpack('<I',b[4:8])[0]
    assert len(b)==8+n*38, f"size {len(b)} != 8+{n}*38"
    print(f"OK {n}")
except Exception as e: print(f"BAD {e}")
PY
}

# ---- 1. unit tests (logique pure) ----
say "=== 1. suites unit (logique) ==="
for t in test_master_games_to_jnnw test_build_ballots test_eval_calibration; do
  if python3 tools/$t.py >"$W/$t.log" 2>&1; then say "  PASS $t"; else say "  FAIL $t"; tail -5 "$W/$t.log"|sed 's/^/    /'|tee -a "$RES"; fi
done

# ---- build jass (pour l'oracle de replay + rescore) ----
say "=== build jass ==="
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"

# ---- 2. donnees reelles (si expert_games.db survit) ----
if [ ! -s "$DB" ]; then
  say "=== 2. donnees reelles : expert_games.db ABSENT/vide ($DB) — box-local de 0438 non survivante."
  say "    Les outils sont valides en logique (suites unit). Pour la verif donnees reelles : relancer ccx33-0438 (fetch) d'abord."
else
  NG=$(python3 -c "import sqlite3;print(sqlite3.connect('file:$DB?mode=ro',uri=True).execute('select count(*) from expert_games').fetchone()[0])" 2>/dev/null || echo 0)
  say "=== 2. donnees reelles : expert_games.db = ${NG} parties ==="

  say "  -- #2 build_ballots (ply 6-12, miroir, cap 600) --"
  python3 tools/build_ballots.py --db "$DB" --jass "$J" --out "$W/ballots.jnnw" \
      --ply-lo 6 --ply-hi 12 --cap 600 --max-games 4000 >"$W/ballots.log" 2>&1 \
      && { say "    $(tail -1 "$W/ballots.log")"; say "    JNNW: $(jnnw_ok "$W/ballots.jnnw")"; } \
      || { say "    FAIL build_ballots"; tail -5 "$W/ballots.log"|sed 's/^/      /'|tee -a "$RES"; }

  say "  -- #6 master_games_to_jnnw (quiet, label resultat, naturel) --"
  python3 tools/master_games_to_jnnw.py --db "$DB" --jass "$J" --out "$W/masters.jnnw" \
      --include-draws --max-games 4000 >"$W/masters.log" 2>&1 \
      && { say "    $(tail -1 "$W/masters.log")"; say "    JNNW: $(jnnw_ok "$W/masters.jnnw")"; } \
      || { say "    FAIL master_games_to_jnnw"; tail -5 "$W/masters.log"|sed 's/^/      /'|tee -a "$RES"; }

  say "  -- #5 eval_calibration : K de Texel + ECE par phase (eval egdbmix vs resultats reels) --"
  if [ -s "$W/masters.jnnw" ] && git cat-file -e "origin/main:$EGDBMIX" 2>/dev/null; then
    git show "origin/main:$EGDBMIX" | gunzip > "$W/egdbmix.pjtw"
    python3 tools/eval_calibration.py --jnnw "$W/masters.jnnw" --jass "$J" --pjtw "$W/egdbmix.pjtw" \
        >"$W/calib.log" 2>&1 && sed 's/^/    /' "$W/calib.log" | tee -a "$RES" \
        || { say "    FAIL eval_calibration"; tail -6 "$W/calib.log"|sed 's/^/      /'|tee -a "$RES"; }
  else
    say "    (skip calibration : masters.jnnw vide ou egdbmix absent)"
  fi
fi

say ""
say "=== LECTURE ==="
say "  PASS partout + JNNW valides => les 3 outils (#2/#5/#6) sont prets pour la recette self-play propre."
say "  #5 : ECE plat sur les phases => calibration uniforme (K non-levier confirme) ; ECE midgame >> => vrai signal."

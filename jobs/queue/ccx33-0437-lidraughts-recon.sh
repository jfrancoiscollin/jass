#!/usr/bin/env bash
# id: ccx33-0437-lidraughts-recon
# description: RECON corpus externes (lidraughts) — avant tout gros fetch. Teste ce qui est accessible depuis la box
# (egress ouvert) : API jeux, endpoint PUZZLES (= la source ideale pour une suite de test tactique position->coup),
# eventuel DUMP en bloc (database.lidraughts.org, bien + rapide que le crawl API). Puis valide le pipeline
# fetch_lidraughts_games -> pdn_to_jnnw sur un PETIT echantillon (timeout 12min). Rapporte tout. Aucun gros telechargement.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0437-lidraughts-recon/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-lidr; rm -rf "$W"; mkdir -p "$W"

# ---------- 1) probes d'acces ----------
say "=== PROBES acces lidraughts (depuis la box) ==="
probe(){ local url="$1" lbl="$2"; local code; code=$(curl -s -o "$W/probe.out" -w "%{http_code}" --max-time 20 "$url" 2>/dev/null || echo "000"); local sz; sz=$(wc -c <"$W/probe.out" 2>/dev/null||echo 0); say "  [$code] ${lbl} (${sz}o) : ${url}"; [ "$code" = 200 ] && head -c 160 "$W/probe.out" | tr '\n' ' ' | sed 's/^/      /' | tee -a "$RES"; echo | tee -a "$RES" >/dev/null; }
probe "https://lidraughts.org/api/user/lidraughts"            "API user (base joignable ?)"
probe "https://lidraughts.org/api/puzzle/daily"               "PUZZLE du jour (suite tactique ?)"
probe "https://lidraughts.org/api/puzzle/dashboard/30"        "PUZZLE dashboard"
probe "https://database.lidraughts.org"                       "DUMP en bloc (index)"
probe "https://database.lidraughts.org/lidraughts_db_puzzle.csv.zst" "DUMP puzzles (zst)"
probe "https://database.lidraughts.org/standard/list.txt"     "DUMP parties (liste)"

# ---------- 2) build jass (pour pdn_to_jnnw) ----------
say ""; say "=== build jass (pour la conversion) ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1 || { say "ABORT cmake"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
JASS="$W/build/jass"
python3 -c "import requests" 2>/dev/null || pip3 install --quiet requests 2>/dev/null || say "  (pip requests: a verifier)"

# ---------- 3) valider le pipeline fetch->jnnw sur petit echantillon (timeout 12min) ----------
say ""; say "=== ECHANTILLON fetch_lidraughts_games -> pdn_to_jnnw (timeout 12min, petits caps) ==="
DB="$W/sample.db"; SCHEMA="/root/jass/data/expert_games.schema.sql"
[ -f "$SCHEMA" ] && python3 -c "import sqlite3;c=sqlite3.connect('$DB');c.executescript(open('$SCHEMA').read());c.close()" 2>>"$W/fetch.log" || say "  (schema absent ? $SCHEMA)"
timeout 720 python3 tools/fetch_lidraughts_games.py --db "$DB" --schema "$SCHEMA" \
    --min-rating 1600 --max-rating 2300 --max-games-per-user 30 --rate-sleep 0.4 >"$W/fetch.log" 2>&1
NG=$(python3 -c "import sqlite3;print(sqlite3.connect('$DB').execute('select count(*) from expert_games').fetchone()[0])" 2>/dev/null || echo "?")
say "  parties fetchees (echantillon) : ${NG}"
tail -4 "$W/fetch.log" | sed 's/^/    fetch: /' | tee -a "$RES"
if [ "$NG" != "?" ] && [ "${NG:-0}" -gt 0 ] 2>/dev/null; then
  python3 tools/pdn_to_jnnw.py --db "$DB" --out "$W/sample.jnnw" --jass "$JASS" --min-rating 1600 --max-games 2000 >"$W/conv.log" 2>&1 || say "  (conversion: voir conv.log)"
  NP=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/sample.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo "?")
  say "  positions JNNW converties : ${NP}"
  cp "$W/sample.jnnw" "$ART/sample-lidraughts.jnnw" 2>/dev/null || true
fi
say ""
say "================= LECTURE ================="
say "  Puzzles 200 => suite de test tactique directe (position->coup) = etape 1 ideale."
say "  Dump en bloc 200 => fetch RAPIDE (vs crawl API lent) pour le gros corpus d'entrainement."
say "  Echantillon JNNW>0 => pipeline fetch->jnnw OK => on peut monter le gros corpus + le test combinaisons."
say "==========================================="

#!/usr/bin/env bash
# id: ccx33-0438-lidraughts-fetch
# description: GROS FETCH corpus lidraughts (parties amateur 1600-2300, RICHES en combinaisons + decisives) -> JNNW,
# pour MIXER au self-play (pousser le point fixe lineaire SANS distillation-Scan ni NNUE). Reutilise la DB persistante
# de 0014 si elle survit (jusqu'a 100k parties deja la), sinon remplit (timeout ~4.5h, on garde ce qu'on a). Convertit
# tout en JNNW, committe en shards gz (<=95Mo). DB gardee box-local (pour miner les combinaisons ensuite).
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0438-lidraughts-fetch/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-lidr-fetch; rm -rf "$W"; mkdir -p "$W"
DB="/root/jass/data/expert_games.db"; SCHEMA="/root/jass/data/expert_games.schema.sql"
mkdir -p /root/jass/data

# ---------- build jass (pour pdn_to_jnnw) ----------
say "=== build jass ==="
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1 || { say "ABORT cmake"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
JASS="$W/build/jass"
python3 -c "import requests" 2>/dev/null || pip3 install --quiet requests 2>/dev/null || true
[ -f "$SCHEMA" ] && python3 -c "import sqlite3;c=sqlite3.connect('$DB');c.executescript(open('$SCHEMA').read());c.close()" 2>/dev/null || true

cnt(){ python3 -c "import sqlite3;print(sqlite3.connect('$DB').execute('select count(*) from expert_games').fetchone()[0])" 2>/dev/null || echo 0; }
N0=$(cnt); say "# DB existante : ${N0} parties (survie de 0014 ?)"

# ---------- fetch (timeout ~4.5h, accumule dans la DB persistante) ----------
say "=== fetch lidraughts (1600-2300, 4.5h max, on garde ce qu'on a) ==="
timeout 16200 python3 tools/fetch_lidraughts_games.py --db "$DB" --schema "$SCHEMA" \
    --min-rating 1600 --max-rating 2300 --max-games-per-user 400 --rate-sleep 0.35 >"$W/fetch.log" 2>&1 || true
N1=$(cnt); say "# DB apres fetch : ${N1} parties (+$((N1-N0)) nouvelles)"
tail -5 "$W/fetch.log" | sed 's/^/    fetch: /' | tee -a "$RES"

# ---------- conversion DB -> JNNW (tout) ----------
say "=== conversion -> JNNW (toutes les parties, rating>=1600) ==="
python3 tools/pdn_to_jnnw.py --db "$DB" --out "$W/lidr.jnnw" --jass "$JASS" --min-rating 1600 --max-games 0 >"$W/conv.log" 2>&1 || { say "  (conversion: voir conv.log)"; tail -8 "$W/conv.log"|sed 's/^/    /'|tee -a "$RES"; }
NP=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/lidr.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
say "# corpus lidraughts : ${NP} positions"

# ---------- committe en shards gz <=95Mo ----------
if [ "${NP:-0}" -gt 0 ]; then
  python3 - "$W/lidr.jnnw" "$ART" <<'PY'
import struct,sys,math
src,art=sys.argv[1],sys.argv[2]; REC=38
b=open(src,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=memoryview(b)[8:8+n*REC]
PER=8_000_000  # ~8M pos/shard (~74Mo gz, sous le cap 95Mo)
import gzip
ns=math.ceil(n/PER)
for i in range(ns):
    a=i*PER; z=min(a+PER,n); m=z-a
    out=bytearray(b'JNNW'+struct.pack('<I',m))+bytes(body[a*REC:z*REC])
    with gzip.open(f"{art}/lidraughts-{i:02d}.jnnw.gz","wb",compresslevel=6) as f: f.write(out)
    print(f"  shard {i}: {m} pos")
print(f"{ns} shards committes")
PY
  ls -la "$ART"/lidraughts-*.jnnw.gz 2>/dev/null | awk '{printf "  %.0fMo %s\n",$5/1e6,$NF}' | tee -a "$RES"
fi
say ""
say "# SUITE : (1) mixer ce corpus au self-play -> fit train_stream -> juger vs Scan + vs champion 3e-5 ;"
say "#         (2) miner les combinaisons depuis la DB (box-local) -> suite de test tactique vs Scan."

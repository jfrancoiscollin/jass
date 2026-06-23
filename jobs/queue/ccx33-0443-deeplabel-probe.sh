#!/usr/bin/env bash
# id: ccx33-0443-deeplabel-probe
# description: OPTION B (valide JFC) — SONDE de faisabilite de la distillation value-target INDEPENDANTE : label dense =
# valeur d'une recherche profonde jass (d18-20) + ancre EGDB, sur des positions de parties FORTES (>2200), PAS Scan.
# Mesure : (1) combien de parties/positions >2200 on a (strict = 2 joueurs >2200, et loose = au moins un) ; (2) le COUT
# de labellisation (pos/s) a d18 et d20 -> projection pour 1M/5M/20M ; (3) une VALIDATION bout-en-bout (label un petit lot
# a d18 +egdb -> fit --target value -> juge vs base 3e-5) pour prouver que le champion sort sain. Aucun gros run ici :
# c'est la sonde qui dimensionne le gros job. AUCUN Scan, AUCUN NNUE. Champion de recherche = champion 3e-5 (notre meilleur
# statique ; la profondeur d18-20 l'amplifie => les labels peuvent depasser l'eval statique de Scan).
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0443-deeplabel-probe/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-deeplabel; rm -rf "$W"; mkdir -p "$W"
DB="/root/jass/data/expert_games.db"
CHAMP_GZ=jobs/results/ccx33-0426-l2sweep/artefacts/w32-chal-l2-3e5-47410792.pjtw.gz
GEOM32=/root/jass-geom32-deeplabel
PROBE18=8000; PROBE20=4000; VALIDATE=80000   # tailles sonde / validation
EGDIR=/root/egdb_extracted

[ -f "$DB" ] || { say "ABORT: DB absente $DB (lancer apres 0438 sur ccx33)"; exit 4; }

# ---------- build jass (egdb si dispo) ----------
say "=== build jass (egdb) ==="
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
cmake -S . -B "$W/build" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
    -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$W/cmake.log" 2>&1 || { say "ABORT cmake"; tail -8 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -12 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$CHAMP_GZ" 2>/dev/null | gunzip > "$W/champ.pjtw" || { say "ABORT: champion absent"; exit 4; }
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"
EGARG=""; [ -d "$EGDIR" ] && EGARG="--egdb $EGDIR" && say "  egdb present : $EGDIR (ancre finale)" || say "  (egdb absent — labels = recherche seule, sans ancre exacte)"

# ---------- 1) recensement du corpus fort ----------
say ""; say "=== 1) corpus parties fortes (DB=$DB) ==="
python3 - "$DB" <<'PY' | tee -a "$RES"
import sqlite3,sys
c=sqlite3.connect(sys.argv[1])
tot=c.execute("select count(*) from expert_games").fetchone()[0]
def cnt(expr):
    try: return c.execute(f"select count(*) from expert_games where {expr}").fetchone()[0]
    except Exception as e: return f"err:{e}"
print(f"  total parties        : {tot}")
for th in (2000,2100,2200,2300):
    print(f"  >= {th} (2 joueurs)  : {cnt(f'min(white_rating,black_rating)>={th}')}   | >= {th} (au moins 1) : {cnt(f'max(white_rating,black_rating)>={th}')}")
PY

# ---------- 2) extraction positions (>2200 strict ; fallback loose si maigre) ----------
say ""; say "=== 2) extraction positions >2200 ==="
python3 tools/pdn_to_jnnw.py --db "$DB" --out "$W/strong.jnnw" --jass "$J" --min-rating 2200 --rating-mode min --max-games 0 >"$W/extract.log" 2>&1 || say "  (extract: voir extract.log)"
NS=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/strong.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
say "  positions strict(2 joueurs>2200) : ${NS}"
MODE="strict>2200"
if [ "${NS:-0}" -lt 100000 ]; then
  say "  (strict maigre -> extraction loose : au moins un joueur >2200)"
  python3 tools/pdn_to_jnnw.py --db "$DB" --out "$W/strong.jnnw" --jass "$J" --min-rating 2200 --rating-mode max --max-games 0 >"$W/extract2.log" 2>&1 || say "  (extract loose: voir extract2.log)"
  NS=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/strong.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
  MODE="loose(>=1 joueur>2200)"
  say "  positions loose : ${NS}"
fi
[ "${NS:-0}" -ge 1000 ] || { say "ABORT: corpus fort trop maigre (${NS}) — fetcher des parties >2200 d'abord"; exit 5; }

# ---------- helpers : shard deep-relabel sur tous les coeurs ----------
take(){ python3 - "$1" "$2" "$3" <<'PY'   # in out N -> premieres N (melangees) en JNNW
import struct,sys,random; REC=38
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; N=min(int(sys.argv[3]),n)
idx=list(range(n)); random.seed(7); random.shuffle(idx); idx=idx[:N]
body=memoryview(b)[8:8+n*REC]; out=bytearray()
for i in idx: out+=body[i*REC:(i+1)*REC]
open(sys.argv[2],'wb').write(b'JNNW'+struct.pack('<I',N)+bytes(out)); print(N)
PY
}
relabel_sharded(){ local in="$1" out="$2" depth="$3"
  python3 - "$in" "$W/sh" "$NCPU" <<'PY'
import struct,sys; REC=38
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=memoryview(b)[8:8+n*REC]
pre=sys.argv[2]; k=int(sys.argv[3]); per=(n+k-1)//k
for s in range(k):
    a=s*per; z=min(a+per,n); m=max(0,z-a)
    open(f"{pre}.{s}",'wb').write(b'JNNW'+struct.pack('<I',m)+bytes(body[a*REC:z*REC]))
print(n)
PY
  for s in $(seq 0 $((NCPU-1))); do "$J" --deep-relabel "$W/sh.$s" "$W/sho.$s" "$depth" --nnue "$W/champ.pjtw" $EGARG >/dev/null 2>&1 & done; wait
  python3 - "$out" "$W/sho" "$NCPU" <<'PY'
import struct,sys; REC=38; out=sys.argv[1]; pre=sys.argv[2]; k=int(sys.argv[3]); body=b""; tot=0
for s in range(k):
    try: b=open(f"{pre}.{s}",'rb').read()
    except FileNotFoundError: continue
    if b[:4]!=b'JNNW': continue
    m=struct.unpack('<I',b[4:8])[0]; tot+=m; body+=b[8:8+m*REC]
open(out,'wb').write(b'JNNW'+struct.pack('<I',tot)+body); print(tot)
PY
  rm -f "$W"/sh.* "$W"/sho.* ; }

# ---------- 3) cout de labellisation a d18 et d20 ----------
say ""; say "=== 3) cout labellisation (sharde sur ${NCPU} coeurs) ==="
probe_rate(){ local depth="$1" nn="$2"; take "$W/strong.jnnw" "$W/probe.jnnw" "$nn" >/dev/null
  local t0=$(date +%s); relabel_sharded "$W/probe.jnnw" "$W/probed.jnnw" "$depth" >/dev/null; local t1=$(date +%s)
  local dt=$((t1-t0)); [ "$dt" -lt 1 ] && dt=1; local rate=$(( nn / dt ))
  say "  d${depth} : ${nn} pos en ${dt}s = ${rate} pos/s (agrege ${NCPU} coeurs)"
  python3 -c "r=$rate; r=max(r,1); print('    projection d%d : 1M=%.1fh  5M=%.1fh  20M=%.1fh'%($depth,1e6/r/3600,5e6/r/3600,20e6/r/3600))" | tee -a "$RES"
}
probe_rate 18 "$PROBE18" || say "  (probe d18 erreur)"
probe_rate 20 "$PROBE20" || say "  (probe d20 erreur)"

# ---------- 4) validation bout-en-bout : label un lot d18 -> fit value -> juge vs base ----------
say ""; say "=== 4) validation : label ${VALIDATE}@d18 -> fit --target value -> juge vs base 3e-5 ==="
take "$W/strong.jnnw" "$W/val.jnnw" "$VALIDATE" >/dev/null
NV=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/val.jnnw','rb').read(8)[4:8])[0])")
relabel_sharded "$W/val.jnnw" "$W/val_lbl.jnnw" 18 >/dev/null 2>&1 || say "  (label validation: erreur)"
"$J" --dump-eval-features "$W/val_lbl.jnnw" "$W/val.feat" >"$W/feat.log" 2>&1 || { say "ABORT dump feat"; exit 8; }
env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$W/val_lbl.jnnw" --feat "$W/val.feat" \
    --color-fold --tempo-stage --loss logistic --target value --value-scale 200 --max-iter 25 --chunk 1000000 --out "$W/champ_val.pjtw" >"$W/fit.log" 2>&1 || { say "TRAIN FAIL"; tail -8 "$W/fit.log"|sed 's/^/  /'; exit 9; }
grep -iE "target=VALUE|train_loss|wrote" "$W/fit.log" | sed 's/^/  /' | tee -a "$RES"
gzip -c "$W/champ_val.pjtw" > "$ART/champion-valuetarget-d18-${NV}.pjtw.gz"
# juge vs base 3e-5 (sharde)
for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py --jass-a "$J" --pattern-a "$W/champ_val.pjtw" \
    --jass-b "$J" --pattern-b "$W/champ.pjtw" --depth 9 --pairs 28 --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet >"$W/j.$s" 2>&1 & done; wait
VB=$(python3 - "$W"/j.* <<'PY'
import sys; a=d=b=0
for f in sys.argv[1:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x); d+=int(y); b+=int(z)
  except: pass
g=a+d+b; print(f"{(a+0.5*d)/g:.4f}" if g else "NA")
PY
)
say "  champion value-target (${NV}@d18) vs BASE 3e-5 : ${VB}"

say ""
say "================= LECTURE ================="
say "  corpus=${MODE} (${NS} pos). Rates d18/d20 ci-dessus => on dimensionne le GROS job (label N pos -> fit -> juge vs Scan)."
say "  validation vs_base > 0.50 sur seulement ${NV} positions => le signal value-target porte deja => GO gros run."
say "  vs_base ~ 0.50 ou < => verifier value-scale / depth / ancre egdb avant de scaler."
say "==========================================="

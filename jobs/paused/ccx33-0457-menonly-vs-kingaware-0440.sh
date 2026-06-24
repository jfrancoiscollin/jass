#!/usr/bin/env bash
# id: ccx33-0457-menonly-vs-kingaware-0440
# description: TEST DECISIF FIT-vs-FEATURE (faille methodo 2). Le verrou men-only > king-aware (0401/0408/0409) a ete juge
# sur la FORCE GLOBALE, pas sur la conversion COMBINATOIRE — or men-only lit une case de roi comme VIDE, suspect si une
# combinaison s'articule sur un roi. On re-juge men-only vs king-aware SPECIFIQUEMENT sur le set 0440 (conversion des 305
# combinaisons dilf vs Scan, depth-fixe). Meme corpus (pool self-play + 4M egdb) pour les 2 fits ; 2 builds (men-only par
# defaut, king-aware -DJASS_KING_PATTERNS) car le champion king-aware exige son build. VERDICT : king-aware convertit MIEUX
# sur 0440 => c'est la FEATURE (geometrie a rouvrir, l'iteration n'y touchera jamais) ; egal/pire => c'est le FIT (le pari
# iteration tient). On verifie aussi l'agregat (men doit gagner, sanity 0409). AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0457-menonly-vs-kingaware-0440/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-mk0440; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
DILF=data/dilf_combinations.fen
GEOM32=/root/jass-geom32-mk
POOL_TRIM=18000000; NEGDB=4000000; L2=3e-5; MAXIT=25; CHUNK=1000000; D=11; JUDGE_PAIRS=28
CMK_BASE="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"

[ -x "$SCAN_BIN" ] || { say "ABORT: Scan introuvable"; exit 4; }
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT: egdb introuvable"; exit 4; }
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1

say "=== build jass MEN-ONLY (defaut) ==="
cmake -S . -B "$W/bm" $CMK_BASE >"$W/cmM.log" 2>&1 && cmake --build "$W/bm" -j"$NCPU" --target jass >"$W/bM.log" 2>&1 || { say "BUILD men FAIL"; tail -8 "$W/bM.log"|sed 's/^/  /'; exit 6; }
JM="$W/bm/jass"
say "=== build jass KING-AWARE (-DJASS_KING_PATTERNS=ON) ==="
cmake -S . -B "$W/bk" $CMK_BASE -DJASS_KING_PATTERNS=ON >"$W/cmK.log" 2>&1 && cmake --build "$W/bk" -j"$NCPU" --target jass >"$W/bK.log" 2>&1 || { say "BUILD king FAIL"; tail -8 "$W/bK.log"|sed 's/^/  /'; exit 6; }
JK="$W/bk/jass"
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"

say "=== corpus commun : pool self-play + 4M egdb-finale ==="
tools/corpus_manifest.sh assemble "$W/pool.jnnw" 2>"$W/assemble.log" || { say "ABORT assemble"; exit 8; }
python3 - "$W/pool.jnnw" "$POOL_TRIM" <<'PY'
import struct,sys,os,shutil; REC=38
acc=sys.argv[1]; Wn=int(sys.argv[2])
with open(acc,'rb') as f:
    n=struct.unpack('<I',f.read(8)[4:8])[0]
    if n<=Wn: print(n); sys.exit(0)
    f.seek(8+(n-Wn)*REC); tmp=acc+'.t'
    with open(tmp,'wb') as o: o.write(b'JNNW'+struct.pack('<I',Wn)); shutil.copyfileobj(f,o,1<<24)
os.replace(tmp,acc); print(Wn)
PY
"$JM" --gen-egdb-wld "$NEGDB" "$W/egdb.jnnw" "$EGDIR" 7 2048 5005 >"$W/ge.log" 2>&1 || { say "ABORT gen egdb"; exit 7; }
python3 - "$W/egdb.jnnw" "$W/pool.jnnw" <<'PY'
import struct,sys; REC=38
b=open(sys.argv[1],'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:8+n*REC]; acc=sys.argv[2]
old=struct.unpack('<I',open(acc,'rb').read(8)[4:8])[0]; o=open(acc,'r+b'); o.seek(0,2); o.write(body); o.seek(4); o.write(struct.pack('<I',old+n)); o.close(); print(old+n)
PY
NMIX=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/pool.jnnw','rb').read(8)[4:8])[0])"); say "  corpus : ${NMIX}"
"$JM" --dump-eval-features "$W/pool.jnnw" "$W/feat" >"$W/feat.log" 2>&1 || { say "ABORT dump feat"; exit 8; }

say "=== fit men-only + king-aware (meme corpus) ==="
env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$W/pool.jnnw" --feat "$W/feat" \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" --out "$W/champ_men.pjtw" >"$W/fM.log" 2>&1 || { say "TRAIN men FAIL"; tail -8 "$W/fM.log"|sed 's/^/  /'; exit 9; }
env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$W/pool.jnnw" --feat "$W/feat" --king-patterns \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" --out "$W/champ_king.pjtw" >"$W/fK.log" 2>&1 || { say "TRAIN king FAIL"; tail -8 "$W/fK.log"|sed 's/^/  /'; exit 9; }
gzip -c "$W/champ_men.pjtw" > "$ART/champion-men.pjtw.gz"; gzip -c "$W/champ_king.pjtw" > "$ART/champion-king.pjtw.gz"
unset JASS_EGDB_PATH

conv(){ python3 - "$1" "$DILF" <<'PY'
import json,glob,sys,os
gdir,fens=sys.argv[1],sys.argv[2]; stm={}
for ln in open(fens):
    b=ln.split('#',1)[0].strip()
    if b: stm[b]=b.split(':',1)[0]
jw=jn=0
for f in sorted(glob.glob(os.path.join(gdir,"game-*.json"))):
    try: g=json.load(open(f))
    except: continue
    op=g.get("opening","").strip(); s=stm.get(op)
    if s is None: continue
    jiw=g.get("jass_is_white"); out=g.get("outcome")
    if not ((jiw and s=="W") or ((not jiw) and s=="B")): continue
    jw+=0.5 if out=="D" else (1.0 if ((out=="W" and s=="W") or (out=="L" and s=="B")) else 0.0); jn+=1
print(f"{jw/jn:.3f} ({jw:.0f}/{jn})" if jn else "NA")
PY
}
say ""; say "=== (1) CONVERSION combinaisons dilf vs Scan (d${D}) — LE test : men-only vs king-aware ==="
python3 tools/calibrate_vs_scan.py --jass "$JM" --scan "$SCAN_BIN" --jass-pattern "$W/champ_men.pjtw"  --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$DILF" --dump-games-dir "$ART/conv-men"  >"$W/cM.log" 2>&1 || say "  (conv men echoue)"
python3 tools/calibrate_vs_scan.py --jass "$JK" --scan "$SCAN_BIN" --jass-pattern "$W/champ_king.pjtw" --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$DILF" --dump-games-dir "$ART/conv-king" >"$W/cK.log" 2>&1 || say "  (conv king echoue)"
CM=$(conv "$ART/conv-men"); CK=$(conv "$ART/conv-king")
say "  conversion 0440 : MEN-ONLY=${CM}   KING-AWARE=${CK}   (cible 0440 = 0.246 ; Scan ~0.95)"

say ""; say "=== (2) sanity agregat (men doit gagner, rappel 0409=0.306) : men vs king self-play d9 ==="
for s in $(seq 0 $((NCPU-1))); do python3 tools/jass_vs_jass_arch.py --jass-a "$JM" --pattern-a "$W/champ_men.pjtw" \
    --jass-b "$JK" --pattern-b "$W/champ_king.pjtw" --depth 9 --pairs "$JUDGE_PAIRS" --max-plies 160 --shard "$s" --nshards "$NCPU" --quiet >"$W/sp.$s" 2>&1 & done; wait
SP=$(python3 - "$W"/sp.* <<'PY'
import sys; a=d=b=0
for f in sys.argv[1:]:
  try:
    for l in open(f):
      if l.startswith("RESULT"): _,x,y,z=l.split(); a+=int(x); d+=int(y); b+=int(z)
  except: pass
g=a+d+b; print(f"{(a+0.5*d)/g:.4f} (men={a} D={d} king={b})" if g else "NA")
PY
)
say "  men vs king (agregat self-play) : ${SP}   (>0.5 = men gagne en agregat, coherent 0409)"
say ""; say "================= VERDICT ================="
say "  KING-AWARE convertit MIEUX sur 0440 (CK > CM) => le trou est une FEATURE (men-only lit le roi comme vide) =>"
say "       la geometrie figee est sur la MAUVAISE metrique => rouvrir king-aware/geometrie. L'iteration n'y touchera JAMAIS."
say "  KING-AWARE = ou pire sur 0440 (CK <= CM) => c'est le FIT (pas la feature) => le pari donnees/mu + flux tactique tient."
say "  (agregat men>king attendu : ne contredit PAS un eventuel king>men SUR 0440 — c'est tout le point de la faille 2.)"
say "=========================================="

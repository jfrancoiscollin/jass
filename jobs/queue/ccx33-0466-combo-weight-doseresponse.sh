#!/usr/bin/env bash
# id: ccx33-0466-combo-weight-doseresponse
# description: DOSE-REPONSE du levier tactique externe (leve le caveat dilution de 0464). 0464 a injecte 155k vraies
# combinaisons (label = resultat reel) a ~5.4% du corpus (x8) => 0440 PLAT (0.304 vs egdbmix 0.302). Question : plat parce
# que DILUE, ou parce que la classe LINEAIRE ne peut PAS representer le signal ? On REUTILISE les combos deja committees
# (jobs/results/ccx33-0464-.../artefacts/combos.jnnw, 155k uniques x8) — AUCUN re-mining — et on les met a POIDS LOURD
# (~35% du corpus) : pool reduit 5M + egdb 4M + combos repliquees ~5M. Un seul fit, un seul juge combo-LOURD vs Scan sur le
# DILF complet (305) a d11 (1 juge => pas de troncature wall-time comme 0464). Comparaison aux points etablis : 0464 ~5.4%
# =0.304, egdbmix=0.302. Si LOURD >> 0.30 => c'etait la dilution, on scale le poids tactique. Si LOURD ~ 0.30 => dose-reponse
# PLATE (5%->35% sans bouger) => plafond FEATURE lineaire sur l'axe combinaisons (=> rouvre proprement C3/C4). AUCUN NNUE.
set -uo pipefail
cd /root/jass
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
ART="/root/jass/jobs/results/ccx33-0466-combo-weight-doseresponse/artefacts"; mkdir -p "$ART"
RES="$ART/RESULTS.txt"; : > "$RES"; say(){ echo "$@" | tee -a "$RES"; }
W=/root/cw-combowt; rm -rf "$W"; mkdir -p "$W"
SCAN_BIN=/root/jass-scan/scan_linux
PILOT_GZ=jobs/results/ccx33-0454-egdb-mix/artefacts/champion-egdbmix.pjtw.gz
COMBOS_GZ=jobs/results/ccx33-0464-master-combo-mining/artefacts/combos.jnnw   # deja committe (1.24M records = 155k x8)
DILF=data/dilf_combinations.fen
GEOM32=/root/jass-geom32-combowt
POOL_TRIM=5000000; NEGDB=4000000; COMBO_REPLICATE=4   # combos ~5M => ~35% de (5+4+5)=14M
L2=3e-5; MAXIT=25; CHUNK=1000000; D=11
CMK="-DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON"

HAVE_SCAN=0; [ -x "$SCAN_BIN" ] && HAVE_SCAN=1 || say "  (Scan absent — gate 0440 a faire ailleurs)"
EGDIR=""; for d in /root/egdb_db /root/egdb_extracted/app /root/egdb_extracted; do ls "$d"/db*.idx1 >/dev/null 2>&1 && { EGDIR="$d"; break; }; done
[ -n "$EGDIR" ] || { say "ABORT: egdb introuvable"; exit 4; }
say "  egdb : $EGDIR"
[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$W/clone.log" 2>&1
say "=== build jass JASS_EGDB=ON ==="
cmake -S . -B "$W/build" $CMK >"$W/cmake.log" 2>&1 && grep -q "EXTERNAL EGDB ENABLED" "$W/cmake.log" || { say "ABORT egdb build"; tail -6 "$W/cmake.log"|sed 's/^/  /'; exit 6; }
cmake --build "$W/build" -j"$NCPU" --target jass >"$W/build.log" 2>&1 || { say "BUILD FAIL"; tail -10 "$W/build.log"|sed 's/^/  /'; exit 6; }
J="$W/build/jass"
git show "origin/main:$PILOT_GZ" 2>/dev/null | gunzip > "$W/pilot.pjtw" || { say "ABORT: pilot absent"; exit 4; }
git show "origin/main:$COMBOS_GZ" > "$W/combos_base.jnnw" 2>/dev/null || { say "ABORT: combos.jnnw (0464) absent"; exit 4; }
NCB=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/combos_base.jnnw','rb').read(8)[4:8])[0])" 2>/dev/null || echo 0)
[ "${NCB:-0}" -ge 100000 ] || { say "ABORT: combos.jnnw trop maigre (${NCB})"; exit 4; }
say "  combos reutilisees (0464) : ${NCB} records"
rm -rf "$GEOM32"; mkdir -p "$GEOM32"; cp pattern_jass/tools/patterns.py "$GEOM32/patterns.py"

app(){ python3 - "$1" "$2" <<'PY'
import struct,sys,os; REC=38
b=open(sys.argv[1],'rb').read(); n=(len(b)-8)//REC; body=b[8:8+n*REC]; acc=sys.argv[2]
if os.path.exists(acc) and os.path.getsize(acc)>=8:
    old=struct.unpack('<I',open(acc,'rb').read(8)[4:8])[0]; o=open(acc,'r+b'); o.seek(0,2); o.write(body); o.seek(4); o.write(struct.pack('<I',old+n)); o.close(); print(old+n)
else: open(acc,'wb').write(b'JNNW'+struct.pack('<I',n)+body); print(n)
PY
}
trim(){ python3 - "$1" "$2" <<'PY'
import struct,sys,os,shutil; REC=38
acc=sys.argv[1]; Wn=int(sys.argv[2])
with open(acc,'rb') as f:
    n=struct.unpack('<I',f.read(8)[4:8])[0]
    if n<=Wn: print(n); sys.exit(0)
    f.seek(8+(n-Wn)*REC); tmp=acc+'.t'
    with open(tmp,'wb') as o: o.write(b'JNNW'+struct.pack('<I',Wn)); shutil.copyfileobj(f,o,1<<24)
os.replace(tmp,acc); print(Wn)
PY
}

say "=== assemble pool (reduit ${POOL_TRIM}) + egdb ${NEGDB} + combos x${COMBO_REPLICATE} (poids LOURD) ==="
tools/corpus_manifest.sh assemble "$W/pool.jnnw" 2>"$W/assemble.log" || { say "ABORT assemble"; exit 8; }
NPOOL=$(trim "$W/pool.jnnw" "$POOL_TRIM"); say "  pool : ${NPOOL}"
"$J" --gen-egdb-wld "$NEGDB" "$W/egdb.jnnw" "$EGDIR" 7 2048 8009 >"$W/ge.log" 2>&1 || { say "ABORT gen egdb"; exit 7; }
# combos lourdes = combos_base replique COMBO_REPLICATE fois
python3 - "$W/combos_base.jnnw" "$W/combos_heavy.jnnw" "$COMBO_REPLICATE" <<'PY'
import struct,sys; REC=38
src,dst,k=sys.argv[1],sys.argv[2],int(sys.argv[3])
b=open(src,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:8+n*REC]
open(dst,'wb').write(b'JNNW'+struct.pack('<I',n*k)+body*k); print(n*k)
PY
cp "$W/pool.jnnw" "$W/corpus.jnnw"; app "$W/egdb.jnnw" "$W/corpus.jnnw" >/dev/null; app "$W/combos_heavy.jnnw" "$W/corpus.jnnw" >/dev/null
NMIX=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/corpus.jnnw','rb').read(8)[4:8])[0])")
NCH=$(python3 -c "import struct;print(struct.unpack('<I',open('$W/combos_heavy.jnnw','rb').read(8)[4:8])[0])")
say "  corpus final : ${NMIX}  (combos lourdes ${NCH} = $((100*NCH/NMIX))% du corpus)"

say "=== fit champion combo-LOURD ==="
"$J" --dump-eval-features "$W/corpus.jnnw" "$W/feat" >"$W/feat.log" 2>&1 || { say "ABORT dump feat"; exit 8; }
env JASS_PATTERNS_DIR="$GEOM32" python3 pattern_jass/tools/train_stream.py --data "$W/corpus.jnnw" --feat "$W/feat" \
    --color-fold --tempo-stage --loss logistic --l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK" --out "$W/champ_heavy.pjtw" >"$W/fit.log" 2>&1 || { say "TRAIN FAIL"; tail -8 "$W/fit.log"|sed 's/^/  /'; exit 9; }
grep -iE "train_loss|wrote" "$W/fit.log" | sed 's/^/  /' | tee -a "$RES"
gzip -c "$W/champ_heavy.pjtw" > "$ART/champion-combo-heavy.pjtw.gz"; rm -f "$W/feat"
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
say ""; say "=== GATE 0440 : combo-LOURD vs Scan (DILF complet, d${D}, 1 seul juge => pas de troncature) ==="
if [ "$HAVE_SCAN" = 1 ]; then
  python3 tools/calibrate_vs_scan.py --jass "$J" --scan "$SCAN_BIN" --jass-pattern "$W/champ_heavy.pjtw" --scan-bb-size 0 --depth "$D" --pairs 1 --openings-file "$DILF" --dump-games-dir "$ART/conv-heavy" >"$W/ch.log" 2>&1 || say "  (conv heavy echoue)"
  say "  conversion 0440 : combo-LOURD(~35%) $(conv "$ART/conv-heavy")   [points etablis : egdbmix=0.302 ; 0464 ~5.4%=0.304 ; 0462 auto=0.285 ; Scan=0.95]"
else say "  GATE 0440 : Scan absent => champion committe ; conversion 0440 a faire avec Scan."; fi
say ""; say "================= LECTURE ================="
say "  combo-LOURD >> 0.30  => le plat de 0464 etait de la DILUTION => le levier tactique externe VIT, on scale le poids."
say "  combo-LOURD ~ 0.30   => DOSE-REPONSE PLATE (5%->35% sans bouger) => la classe lineaire ne represente pas le signal"
say "       combinatoire a geometrie verrouillee => PLAFOND FEATURE => rouvre proprement le debat du gate NNUE (C3/C4)."
say "=========================================="

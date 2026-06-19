#!/usr/bin/env bash
# id: cpx62-0363-wdl-bootstrap-scan-style
# description: RÉPLIQUE FIDÈLE de la recette Scan (self-play + WDL + logistique, ITÉRÉ, DEPUIS ZÉRO). Prior : 0224/0227
# (boucle WDL full-fold depuis l'eval embarquée) montait à +175 vs hc MAIS plafonnait ~0 vs Scan. Ce qui DIFFÈRE ici,
# nos fixes : (1) vrai départ MATÉRIEL-SEUL (Scan « 1 dame ≈ 3 pions », seed pjtw construit à la main, eval faible →
# parties DÉCISIVES, pas drawish) — c'est le manque de 0356/0357 qui partaient du sommet drawish ; (2) finales
# adjugées EXACT par egdb (terminate-at-TB) → signal WDL non dégénéré ; (3) GROS volume (pas de relabel = cheap) ;
# (4) jugé vs Scan d9 (depth-égale) + trajectoire DIRECT (gen_k vs gen0, même binaire = sensible) au lieu d'Elo_hc.
# Question : NOTRE gradient WDL décolle-t-il (monte vers Scan) là où 0356/0357 ont échoué ? Plat/plafonne ~0 vs Scan →
# le bootstrap WDL linéaire est volume/représentation-limité chez nous → dépasser Scan = NNUE. Monte → on scale.
# expected_duration: ~3-4 h
set -uo pipefail
cd /root/jass
export PREFLIGHT_CAP_MIN="${PREFLIGHT_CAP_MIN:-260}"
source jobs/lib/preflight.sh
ART="/root/jass/jobs/results/cpx62-0363-wdl-bootstrap-scan-style/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
SCAN_BIN=/root/jass-scan/scan_linux
NGEN=8; NPER=300000; PLAY_DEPTH=4; EVAL_DEPTH=4; SCALE=1000

preflight_build 1; preflight_train 2400000 $((NGEN+1)); preflight_note "boucle WDL ${NGEN} gens (self-play gros volume, sans relabel) + DIRECT/vsScan" 120; preflight_check

[ -d /root/egdb_intl ] || git clone --depth 1 https://github.com/eygilbert/egdb_intl /root/egdb_intl >"$ART/clone.log" 2>&1
[ -x "$SCAN_BIN" ] || { rm -rf /root/jass-scan; git clone --depth 1 https://github.com/rhalbersma/scan /root/jass-scan >"$ART/scan-clone.log" 2>&1; chmod +x "$SCAN_BIN" 2>/dev/null || true; }
[ -x "$SCAN_BIN" ] || { echo "ABORT: Scan indispo"; exit 5; }

echo "=== build (32-pat, EGDB ON pour adjudication finale + jugement) ==="
B=build-prod; rm -rf "$B"
cmake -S . -B "$B" -DCMAKE_BUILD_TYPE=Release -DJASS_EGDB=ON -DJASS_EGDB_SRC_DIR=/root/egdb_intl \
      -DJASS_ENDGAME_FEATURES=ON -DJASS_KING_MOBILITY=ON -DJASS_SCAN_PARITY=ON -DJASS_TEMPO_STAGE=ON >"$ART/cmake.log" 2>&1
grep -q "EXTERNAL EGDB ENABLED" "$ART/cmake.log" || { echo "ABORT: egdb off"; exit 6; }
cmake --build "$B" -j"$(mem_safe_jobs)" --target jass >"$ART/build.log" 2>&1 || { echo "BUILD FAIL"; tail -8 "$ART/build.log"; exit 6; }
JASS="$PWD/$B/jass"
# egdb DATA (adjudication exacte des finales <=7p en self-play) : best-effort.
[ -d /root/egdb_extracted ] && export JASS_EGDB_PATH=/root/egdb_extracted && echo "  egdb data: ON ($JASS_EGDB_PATH)" || echo "  egdb data: absente → finales jouées (signal WDL un peu + drawish)"

echo "=== seed MATÉRIEL-SEUL (Scan-like : pions ±1, dames ±3, patterns=0) ==="
# n_ext = largeur exacte des extras du binaire : on la lit dans un dump FEAT (sur un mini self-play embarqué).
"$JASS" --gen-data-wdl 256 "$ART/mini.jnnw" 2 2 60 1 >"$ART/mini.log" 2>&1
"$JASS" --dump-eval-features "$ART/mini.jnnw" "$ART/seed.feat" >/dev/null 2>&1
[ -s "$ART/seed.feat" ] || { echo "ABORT: dump FEAT (n_ext) raté"; tail -5 "$ART/mini.log"; exit 7; }
python3 - "$ART/seed.feat" "$ART/gen0.pjtw" "$SCALE" <<'PY'
import sys, struct, numpy as np
sys.path.insert(0,'pattern_jass/tools')
import patterns as P, train
from pathlib import Path
feat,out,scale=sys.argv[1],sys.argv[2],int(sys.argv[3])
raw=open(feat,'rb').read(); assert raw[:4]==b'FEAT', "FEAT manquant"
cnt,k=struct.unpack_from('<II',raw,4)
NB=P.NUM_PATTERNS*P.BUCKETS_PER_PATTERN
pat=np.zeros(NB,dtype=np.int32); ext=np.zeros(k,dtype=np.int32)
MAN=scale*1; KING=scale*3
ext[100]=MAN; ext[101]=-MAN          # men count (black +, white -)
ext[0:50]=KING; ext[50:100]=-KING    # king PST : toute dame vaut KING (≈3 pions)
train.write_weights_v3(Path(out),pat,pat.copy(),ext,ext.copy(),scale,king=False)
print('seed matériel-seul écrit : n_ext=%d NB=%d MAN=%d KING=%d'%(k,NB,MAN,KING))
PY
[ -f "$ART/gen0.pjtw" ] || { echo "ABORT: seed non construit"; exit 7; }

# self-play WDL piloté par <pilot.pjtw> → APPEND au buffer cumulatif <CUM>
CUM="$ART/cumulative.jnnw"
gen_append(){ local pilot="$1" nn="$2" tag="$3"; local per=$(( (nn + NCPU - 1) / NCPU ))
  for s in $(seq 1 "$NCPU"); do
    "$JASS" --gen-data-wdl "$per" "$ART/$tag.$s.jnnw" "$EVAL_DEPTH" "$PLAY_DEPTH" 200 "$((RANDOM*RANDOM+s))" --nnue "$pilot" >"$ART/$tag.$s.log" 2>&1 &
  done; wait
  python3 - "$ART/$tag" "$CUM" <<'PY'
import struct,glob,sys,re,os
tag,cum=sys.argv[1],sys.argv[2]; REC=38
shards=sorted(glob.glob(tag+".*.jnnw"),key=lambda p:int(re.search(r"\.(\d+)\.jnnw$",p).group(1)))
body=b""; add=0
for s in shards:
    b=open(s,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; add+=n; body+=b[8:8+n*REC]
if os.path.exists(cum):
    raw=open(cum,'rb').read(); old=struct.unpack('<I',raw[4:8])[0]
    o=open(cum,'r+b'); o.seek(0,2); o.write(body); o.seek(4); o.write(struct.pack('<I',old+add)); o.close(); print('cumulative',old+add)
else:
    open(cum,'wb').write(b'JNNW'+struct.pack('<I',add)+body); print('cumulative',add)
PY
  rm -f "$ART/$tag".*.jnnw
}
fit_wdl(){ # <cum.jnnw> <out-prefix> — recette Scan : logistique sur WDL, full-fold (32-pat OK ~1M)
  "$JASS" --dump-eval-features "$1" "$2.feat" >/dev/null 2>&1
  python3 pattern_jass/tools/train.py --data "$1" --scan-eval --eval-features-file "$2.feat" \
    --loss logistic --l2 1e-4 --max-iter 250 --scale "$SCALE" --prune --lowmem --full-fold \
    --out "$2.pjtw" >"$2-train.log" 2>&1
  [ -f "$2.pjtw" ] || { echo "TRAIN FAIL $2"; tail -8 "$2-train.log"; exit 9; }
}
rate(){ grep -E 'score rate' "$1" | grep -oE '0?\.[0-9]+|[01]\.[0-9]+' | head -1; }
direct(){ "$JASS" --benchmark-nnue-vs-nnue "$1.pjtw" "$ART/gen1.pjtw" 9 6 1 0 >"$1-direct.log" 2>&1 || true
  grep -E 'score rate' "$1-direct.log" | grep -oE '[0-9.]+' | head -1; }
vs_scan(){ python3 tools/calibrate_vs_scan.py --jass "$JASS" --scan "$SCAN_BIN" --jass-pattern "$1.pjtw" \
    --scan-bb-size 0 --jass-depth 9 --scan-depth 9 --pairs 6 --max-plies 160 >"$1-vs.log" 2>&1 || true; rate "$1-vs.log"; }

declare -A DIR VS
echo "=== gen1 : seed matériel rejoue (décisif) → fit logistique WDL = 1re vraie eval ==="
gen_append "$ART/gen0.pjtw" "$NPER" "sp1"
fit_wdl "$CUM" "$ART/gen1"
DIR[1]="0.500"; VS[1]=$(vs_scan "$ART/gen1")
echo "  gen1 vsScan=${VS[1]}"

PREV="$ART/gen1"
for g in $(seq 2 "$NGEN"); do
  echo "=== gen$g : +${NPER} self-play(gen$((g-1))) → cumulé → logistique WDL ==="
  gen_append "$PREV.pjtw" "$NPER" "sp$g"
  fit_wdl "$CUM" "$ART/gen$g"
  DIR[$g]=$(direct "$ART/gen$g"); VS[$g]=$(vs_scan "$ART/gen$g")
  echo "  gen$g : DIRECT(vs gen1)=${DIR[$g]}  vsScan=${VS[$g]}"
  PREV="$ART/gen$g"
done

echo; echo "=========================================================="
echo "   cpx62-0363 — BOOTSTRAP WDL façon Scan (matériel→self-play→logistique, itéré)"
echo "   gen :  DIRECT(vs gen1)   vsScan-d9"
for g in $(seq 1 "$NGEN"); do echo "    $g :   ${DIR[$g]:-NA}            ${VS[$g]:-NA}"; done
echo "----------------------------------------------------------"
echo "   vsScan MONTE à travers les gens (vers Scan) → notre gradient WDL décolle (départ décisif = le fix) → SCALER le volume."
echo "   vsScan plafonne ~0.0-0.1 (comme 0227) → bootstrap WDL linéaire volume/représentation-limité → dépasser Scan = NNUE."
echo "=========================================================="

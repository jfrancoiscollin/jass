#!/usr/bin/env bash
# id: ccx33-0245-federated-test
# description: FEDERATED-AVERAGING viability (option 3 « 2 box pour le même train »). Simule
# 2 box : on coupe un corpus en 2 moitiés, on entraîne A et B SÉPARÉMENT (--lowmem, ce que
# feraient 2 box en parallèle), on MOYENNE les poids (tools/avg_pjtw.py, naïf + visit-weighted)
# et on compare en Elo vs hc au fit JOINT (toute la data). Mesure la dégradation due aux buckets
# rares vus par une seule moitié. Si fed ≈ joint → on peut paralléliser le train sur 2 box.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0245-federated-test/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
REF=/root/jass/jobs/results/0141-pattern-reeval/artefacts/master-clean-scan-d10.jnnw

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release -DJASS_KING_PATTERNS=ON >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass
python3 -c "import numpy,scipy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy scipy

# --- corpus king-aware ~3M (seed self-play), split 50/50 ---
echo "=== gen corpus ~3M (king-aware self-play depth4) ==="
PER=$(( (3000000 + NCPU - 1) / NCPU ))
for s in $(seq 1 "$NCPU"); do $JASS --gen-data-wdl "$PER" "$ART/sp-$s.jnnw" 6 4 200 $((RANDOM)) >"$ART/sp-$s.log" 2>&1 & done; wait
python3 - "$ART" <<'PY'
import struct,glob,sys,re
art=sys.argv[1]; REC=38
def hdr(n): return b'JNNW'+struct.pack('<I',n)
allb=b""; tot=0
for f in sorted(glob.glob(art+"/sp-*.jnnw"),key=lambda p:int(re.search(r"-(\d+)\.jnnw$",p).group(1))):
    b=open(f,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; tot+=n; allb+=b[8:8+n*REC]
# full + two halves
half=tot//2
open(art+"/full.jnnw",'wb').write(hdr(tot)+allb)
open(art+"/A.jnnw",'wb').write(hdr(half)+allb[:half*REC])
open(art+"/B.jnnw",'wb').write(hdr(tot-half)+allb[half*REC:])
print(f"corpus {tot}  half {half}")
PY
for tag in full A B; do $JASS --dump-eval-features "$ART/$tag.jnnw" "$ART/feat-$tag" >/dev/null 2>&1; done

fit(){ python3 pattern_jass/tools/train.py --data "$ART/$1.jnnw" --scan-eval --eval-features-file "$ART/feat-$1" \
        --loss logistic --l2 3e-4 --max-iter 200 --scale 1000 --prune --full-fold --king-patterns --lowmem \
        --out "$ART/$1.pjtw" >"$ART/train-$1.log" 2>&1; }
elo(){ local lg="$ART/elo-$1.log"; $JASS --benchmark-scan-eval "$ART/$1.pjtw" hc 9 60 "$NCPU" 0 >"$lg" 2>&1
  local W=$(grep -oE 'SCAN_EVAL=[0-9]+' "$lg"|tail -1|cut -d= -f2); local L=$(grep -oE 'NNUE=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  local D=$(grep -oE 'Draws=[0-9]+' "$lg"|tail -1|cut -d= -f2)
  python3 tools/sprt_elo.py --wdl "${W:-0}" "${D:-0}" "${L:-0}" 2>/dev/null|grep -oE 'elo=[-+0-9.]+'|head -1|cut -d= -f2; }

echo "=== fit JOINT (full), A, B ==="
fit full; fit A; fit B
echo "=== merge A+B (naive) ==="
python3 tools/avg_pjtw.py --out "$ART/fed.pjtw" "$ART/A.pjtw" "$ART/B.pjtw" 2>&1 | tee "$ART/avg.log" | tail -3

E_JOINT=$(elo full); E_FED=$(elo fed); E_A=$(elo A)
echo; echo "=========================================================="
echo "   ccx33-0245 — FEDERATED-AVERAGING (Elo vs hc, 60 paires)"
echo "   JOINT (full data)      : $E_JOINT"
echo "   FEDERATED (avg A,B)    : $E_FED"
echo "   single half (A only)   : $E_A"
echo "   → fed ≈ joint : averaging viable → 2 box en parallèle sur le train (×2 vitesse)."
echo "   → fed << joint : la dégradation buckets-rares tue l'idée (rester single-box lowmem)."
echo "=========================================================="

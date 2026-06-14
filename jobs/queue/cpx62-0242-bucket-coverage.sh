#!/usr/bin/env bash
# id: cpx62-0242-bucket-coverage
# description: FAMINE DE DONNÉES — chiffre dur. Sur un corpus self-play réel, mesure
# (tools/bucket_coverage.py, Chao1 + courbe d'accumulation) : ensemble OCCURRENT foldé,
# % couvert au scale actuel, et positions nécessaires pour 95 % / dense (≥8 visites).
# DEUX modes : men-only ET king-aware (men|kings) — pour dimensionner la famine du loop
# 0241 (king-aware) vs l'ancien men-only. Pas de Scan, cheap.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0242-bucket-coverage/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
python3 -c "import numpy" 2>/dev/null || pip3 install --break-system-packages --no-cache-dir --quiet numpy

# --- corpus self-play réel : 0227 cumulé (2.6M) s'il est local, sinon en générer ~2M ---
C0227=/root/jass/jobs/results/ccx33-0227-fullfold-loop/artefacts.src/cumulative.jnnw
CORPUS=""
if [ -f "$C0227" ]; then
  CORPUS="$C0227"; echo "corpus: 0227 cumulé local ($(python3 -c "import struct;print(struct.unpack('<I',open('$C0227','rb').read(8)[4:8])[0])") positions)"
else
  echo "0227 cumulé absent → build + génère ~2M self-play depth4"
  rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
  cmake --build build-prod -j"$NCPU" --target jass >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
  JASS=/root/jass/build-prod/jass
  PER=$(( (2000000 + NCPU - 1) / NCPU ))
  for s in $(seq 1 "$NCPU"); do $JASS --gen-data-wdl "$PER" "$ART/sp-$s.jnnw" 6 4 200 $((RANDOM)) >"$ART/sp-$s.log" 2>&1 & done; wait
  python3 - "$ART/sp" "$ART/corpus.jnnw" <<'PY'
import struct,glob,sys,re
outp,dst=sys.argv[1],sys.argv[2]; REC=38; o=open(dst,'wb'); o.write(b'JNNW'); o.write(struct.pack('<I',0)); tot=0
for f in sorted(glob.glob(outp+"-*.jnnw"),key=lambda p:int(re.search(r"-(\d+)\.jnnw$",p).group(1))):
    b=open(f,'rb').read()
    if b[:4]!=b'JNNW': continue
    n=(len(b)-8)//REC; tot+=n; o.write(b[8:8+n*REC])
o.seek(4); o.write(struct.pack('<I',tot)); o.close(); print("corpus",tot)
PY
  CORPUS="$ART/corpus.jnnw"
fi

echo; echo "############## MEN-ONLY (l'ancienne géométrie) ##############"
python3 tools/bucket_coverage.py "$CORPUS" 2>&1 | tee "$ART/cov-menonly.log"
echo; echo "############## KING-AWARE (men|kings — le loop 0241) ##############"
python3 tools/bucket_coverage.py "$CORPUS" --king 2>&1 | tee "$ART/cov-king.log"

echo; echo "=========================================================="
echo "   cpx62-0242 — FAMINE : ensemble occurrent + positions pour 95% / dense(≥8)"
for m in menonly king; do
  echo "  -- $m --"
  grep -E "MODE:|Chao1 occurring|observe 95%|N>=8|N>=1 " "$ART/cov-$m.log" 2>/dev/null | sed 's/^/    /'
done
echo "  → compare le N positions cible au scale du loop (0241 ≈ 5M cumulé) = combien il manque."
echo "=========================================================="

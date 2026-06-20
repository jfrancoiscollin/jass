#!/usr/bin/env bash
# id: ccx33-0375-salvage-d12
# description: RECOVERY (l'orchestration 0368-0372 a cascadé : les .pjtw font 136Mo = full-fold réexpandu à 17M poids
# → commit >95Mo refusé). Ici ccx33 récupère la GEN DATA d12 de 0374 (artefacts.src LOCAL, 22Mo = sous le cap) +
# la dernière éval d12 GZIPPÉE (136Mo → ~qq Mo, ~99% de zéros) et les committe dans git pour que cpx62-0376 poole.
# ABORT clair si artefacts.src recyclé → signal qu'il faut régénérer (les boucles sont prouvées).
# expected_duration: ~3 min
set -uo pipefail
cd /root/jass
SRC=/root/jass/jobs/results/ccx33-0374-virtuous-loop-deep12/artefacts.src
ART=/root/jass/jobs/results/ccx33-0375-salvage-d12/artefacts; mkdir -p "$ART"
[ -d "$SRC" ] || { echo "ABORT-SALVAGE: artefacts.src de 0374 recyclé → RÉGÉNÉRER la boucle d12"; exit 4; }
[ -f "$SRC/cumulative.jnnw" ] || { echo "ABORT-SALVAGE: cumulative.jnnw d12 absent"; ls "$SRC" 2>/dev/null | head; exit 4; }

N=$(python3 -c "import struct;print(struct.unpack('<I',open('$SRC/cumulative.jnnw','rb').read(8)[4:8])[0])")
SZ=$(stat -c%s "$SRC/cumulative.jnnw")
echo "  d12 data : ${N} positions, $((SZ/1000000)) Mo"
[ "$SZ" -lt 94000000 ] || { echo "ABORT: data d12 >94Mo, à gziper aussi (imprévu)"; exit 5; }
cp "$SRC/cumulative.jnnw" "$ART/d12-data.jnnw"

GEN=$(ls "$SRC"/gen*.pjtw 2>/dev/null | sort -V | tail -1)
[ -n "$GEN" ] || { echo "ABORT: pas d'éval d12"; exit 4; }
gzip -c "$GEN" > "$ART/d12-eval.pjtw.gz"
GZ=$(stat -c%s "$ART/d12-eval.pjtw.gz")
echo "  d12 éval ($(basename "$GEN")) : 136Mo -> $((GZ/1000000)).$(( (GZ/100000)%10 )) Mo gzippé"
[ "$GZ" -lt 94000000 ] || { echo "ABORT: éval gzippée encore >94Mo (?!)"; exit 5; }
echo "=== SALVAGE d12 OK (data + éval gzip committées) → prêt pour cpx62-0376 ==="
ls -la "$ART"
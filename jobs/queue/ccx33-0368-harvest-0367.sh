#!/usr/bin/env bash
# id: ccx33-0368-harvest-0367
# description: ÉTAGE 1 de l'orchestration distribuée — committe dans git la GEN DATA + les évals de 0367 (boucle d12,
# ccx33) pour que cpx62 puisse les pooler (les 2 boxes ne partagent QUE git). Copie cumulative.jnnw (tronqué au cap
# artefact) + tous les gen*.pjtw de 0367 dans artefacts/ (committé ≤95Mo). DÉPLOYER après la fin de 0367. La data WDL
# est arch-indépendante → actif durable réutilisable. NB : dépend de la persistance d'artefacts.src de 0367 (lancer vite).
# expected_duration: ~3 min
set -uo pipefail
cd /root/jass
SRC=/root/jass/jobs/results/ccx33-0367-virtuous-loop-deep12/artefacts.src
ART=/root/jass/jobs/results/ccx33-0368-harvest-0367/artefacts; mkdir -p "$ART"
[ -d "$SRC" ] || { echo "ABORT: artefacts.src de 0367 introuvable (container recyclé ? relancer 0367)"; exit 4; }
[ -f "$SRC/cumulative.jnnw" ] || { echo "ABORT: cumulative.jnnw de 0367 absent"; ls "$SRC" | head; exit 4; }

echo "=== évals de 0367 (gen*.pjtw) ==="
n=0; for p in "$SRC"/gen*.pjtw; do [ -f "$p" ] || continue; cp "$p" "$ART/0367-$(basename "$p")"; n=$((n+1)); done
echo "  $n évals copiées"; ls -la "$ART"/0367-gen*.pjtw 2>/dev/null | tail -3
[ "$n" -ge 1 ] || { echo "ABORT: aucune éval gen*.pjtw dans 0367"; exit 5; }

echo "=== gen data (cumulative.jnnw, tronqué ≤ ~1.5M records pour rester sous le cap 95Mo) ==="
python3 - "$SRC/cumulative.jnnw" "$ART/0367-cumulative.jnnw" 1500000 <<'PY'
import struct,sys
src,out,cap=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38
b=open(src,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; body=b[8:]
k=min(n,cap)
open(out,'wb').write(b'JNNW'+struct.pack('<I',k)+body[:k*REC])
print(f"  0367 cumulative : {n} records -> harvest {k} ({k*REC/1e6:.1f} Mo)")
PY
echo; echo "=== HARVEST 0367 OK -> committé dans git, prêt pour le merge cpx62-0369 ==="
ls -la "$ART" | tail -6
#!/usr/bin/env bash
# id: ccx33-0212-genpar-seed
# description: 2-BOX HARNESS, moitié CCX33. Génère SA part (1M positions, 8 shards) d'un
# corpus seed gen0 commun (réseau EMBARQUÉ, depth4) et laisse les shards dans
# artefacts.src → le runner les COMMITE (≤95MB chacun) sur main. Le job réducteur
# cpx62-0213 attend ces shards, les fusionne avec sa propre part et entraîne (--prune).
# Démontre qu'on cumule la puissance des deux box pour UN même jeu de données.
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/ccx33-0212-genpar-seed/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc); export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"

rm -rf build-prod; cmake -S . -B build-prod -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-prod -j"$NCPU" --target jass jass_tests >"$ART/build.log" 2>&1 || { echo BUILD FAIL; tail -20 "$ART/build.log"; exit 5; }
JASS=/root/jass/build-prod/jass

# CCX33's share: 1M positions over 8 shards (~125k each → ~4.75MB, well under the 95MB
# artefact cap so the runner commits each). Embedded net (no --nnue) = identical
# generator on both boxes → a coherent seed corpus. depth4 play, eval_depth 6.
SHARE=1000000; PER=$(( (SHARE + NCPU - 1) / NCPU ))
echo "CCX33 generating $((PER*NCPU)) positions over $NCPU shards (embedded net, depth4)"
for s in $(seq 1 "$NCPU"); do
  $JASS --gen-data-wdl "$PER" "$ART/sh-$s.jnnw" 6 4 200 $((s*100003 + 17)) >"$ART/sh-$s.log" 2>&1 &
done
wait
echo "CCX33 shards done:"; for f in "$ART"/sh-*.jnnw; do
  python3 -c "import struct;print('  $(basename $f)',struct.unpack('<I',open('$f','rb').read(8)[4:8])[0])"
done
echo "=== ccx33-0212 : $NCPU shards prêts (le runner les commite) → cpx62-0213 prendra le relais ==="

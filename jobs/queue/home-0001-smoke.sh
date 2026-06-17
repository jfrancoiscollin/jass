#!/usr/bin/env bash
# id: home-0001-smoke
# description: Validation end-to-end du runner WSL2 "home-" : reporte host/CPU/RAM, build jass
# (Release), lance le moteur sur une position, et vérifie le pré-flight. Auto-contenu (aucune
# dépendance egdb/MTC/Scan ni donnée d'une autre box). Scopé home- → seules les box home- le prennent.
# expected_duration: ~5 min
set -uo pipefail
cd /root/jass
source jobs/lib/preflight.sh 2>/dev/null && { preflight_build 1; preflight_check; } || echo "(preflight indispo, on continue)"
ART="/root/jass/jobs/results/home-0001-smoke/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc)

echo "=== host ==="
echo "hostname : $(hostname)"
echo "nproc    : $NCPU"
echo "cpu      : $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ //')"
echo "mem      : $(grep MemTotal /proc/meminfo | awk '{printf "%.1f GiB\n", $2/1024/1024}')"
echo "kernel   : $(uname -r)   (WSL si 'microsoft' présent)"
echo "wsl?     : $(uname -r | grep -qi microsoft && echo OUI || echo non)"

echo "=== build jass (Release) ==="
cmake -S . -B build-home -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-home -j"$NCPU" --target jass >"$ART/build.log" 2>&1 && echo "BUILD OK" || { echo "BUILD FAIL"; tail -20 "$ART/build.log"; exit 5; }

echo "=== eval sanity (position de départ) ==="
echo "position fen W:W31-50:B1-15" | ./build-home/jass 2>&1 | head -3

echo
echo "=========================================================="
echo "  home-0001 — runner WSL2 opérationnel sur $(hostname) ($NCPU vCPU)"
echo "  Prêt à recevoir des jobs home-* (builds / self-play gen / trains autonomes)."
echo "=========================================================="

#!/usr/bin/env bash
# id: home-0002-smoke
# description: Re-essai du smoke runner "home-" après échec OOM de home-0001 (build -j16 sur 15 Go).
# Build conscient de la RAM (-j plafonné à ~RAM/2 via mem_safe_jobs). Reporte host/CPU/RAM + eval.
# expected_duration: ~8 min
set -uo pipefail
cd /root/jass
source jobs/lib/preflight.sh 2>/dev/null || true
ART="/root/jass/jobs/results/home-0002-smoke/artefacts.src"; mkdir -p "$ART"
NCPU=$(nproc)
JOBS="$(mem_safe_jobs 2>/dev/null || echo 4)"

echo "=== host ==="
echo "hostname : $(hostname)"
echo "nproc    : $NCPU   (build -j$JOBS, plafonné par la RAM)"
echo "cpu      : $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ //')"
echo "mem      : $(grep MemTotal /proc/meminfo | awk '{printf "%.1f GiB\n", $2/1024/1024}')"
echo "wsl?     : $(uname -r | grep -qi microsoft && echo OUI || echo non)"

echo "=== build jass (Release, -j$JOBS) ==="
export TMPDIR=/root/jass/.compile-tmp; mkdir -p "$TMPDIR"
cmake -S . -B build-home -DCMAKE_BUILD_TYPE=Release >"$ART/cmake.log" 2>&1
cmake --build build-home -j"$JOBS" --target jass >"$ART/build.log" 2>&1 && echo "BUILD OK" || { echo "BUILD FAIL"; tail -25 "$ART/build.log"; exit 5; }

echo "=== eval sanity ==="
echo "position fen W:W31-50:B1-15" | ./build-home/jass 2>&1 | head -3

echo
echo "=========================================================="
echo "  home-0002 — runner WSL2 OK sur $(hostname) ($NCPU threads, build -j$JOBS)"
echo "  Prêt pour des jobs home-* (self-play gen / trains autonomes)."
echo "=========================================================="

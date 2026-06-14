#!/usr/bin/env bash
# id: cpx62-0246-netprobe
# description: SONDE RÉSEAU inter-box (verif lien direct pour un param-server distribué).
# Reporte ses propres IP (publique + privées) et tente d'ATTEINDRE l'autre box (par hostname
# Hetzner + par l'IP publique que l'autre sonde a committée). Ping + handshake TCP. Cheap (~30s).
set -uo pipefail
cd /root/jass
ART="/root/jass/jobs/results/cpx62-0246-netprobe/artefacts.src"; mkdir -p "$ART"
SELF=$(hostname); OTHER=ubuntu-16gb-hel1-2
echo "=== SELF = $SELF ==="
echo "-- interfaces --"; ip -br addr 2>/dev/null || ip addr 2>/dev/null | grep -E "inet " || true
PUB=$(curl -s --max-time 6 https://ifconfig.me 2>/dev/null || curl -s --max-time 6 https://api.ipify.org 2>/dev/null || echo '?')
echo "public IP : $PUB"
echo "private-range IPs : $(ip -4 -o addr 2>/dev/null | grep -oE '10\.[0-9.]+|172\.(1[6-9]|2[0-9]|3[01])\.[0-9.]+|192\.168\.[0-9.]+' | tr '\n' ' ' || echo none)"
# publish own pub IP for the other probe to read
echo "$PUB" > "$ART/pub_ip.txt"

echo "=== reach OTHER = $OTHER ? ==="
echo "-- DNS (Hetzner internal?) --"; getent hosts "$OTHER" 2>/dev/null || echo "  no resolution for $OTHER"
echo "-- ping hostname --"; ping -c1 -W2 "$OTHER" 2>&1 | grep -E "bytes from|packet loss" | head -2 || echo "  ping failed"
# read the other probe's committed public IP, if it already ran
git fetch origin main --quiet 2>/dev/null || true
OIP=$(git show "origin/main:jobs/results/ccx33-0246-netprobe/artefacts/pub_ip.txt" 2>/dev/null | tr -d '[:space:]')
if [ -n "$OIP" ] && [ "$OIP" != "?" ]; then
  echo "-- other public IP (from its probe) = $OIP --"
  ping -c1 -W2 "$OIP" 2>&1 | grep -E "bytes from|packet loss" | head -2 || echo "  ping IP failed"
  for port in 22 443 9999; do
    timeout 4 bash -c "echo > /dev/tcp/$OIP/$port" 2>/dev/null && echo "  TCP $OIP:$port OPEN" || echo "  TCP $OIP:$port closed/filtered"
  done
else
  echo "  (l'autre sonde n'a pas encore committé son IP — relancer cette sonde après l'autre)"
fi
echo; echo "=== VERDICT : lien direct utilisable si ping IP OK + un TCP ouvert ==="

#!/usr/bin/env bash
# id: 0001-smoke
# description: validates that the GitOps runner is alive end-to-end:
#              build is fine, jass binary works, host facts get reported.
# expected_duration: 10s
set -euo pipefail
cd /root/jass

echo "=== host facts ==="
echo "host:    $(hostname)"
echo "kernel:  $(uname -r)"
echo "uptime:  $(uptime -p)"
echo "nproc:   $(nproc)"
echo "memtotal:$(free -h | awk '/^Mem:/ {print $2}')"
echo "disk:    $(df -h / | awk 'NR==2{print $4 " free of " $2}')"
echo "cpu:     $(lscpu | awk -F': +' '/Model name/{print $2; exit}')"
echo "mhz:     $(lscpu | awk -F': +' '/CPU MHz|MHz/{print $2; exit}')"

echo
echo "=== jass smoke ==="
echo "position fen W:W31-50:B1-15" | ./build/jass | head -3

echo
echo "=== runner self-check ==="
ls -la infra/
systemctl is-active jass-runner.timer

#!/usr/bin/env bash
# id: 0003-diag-after-0002
# description: diagnose why 0002-rate-test-depth20 was reaped as failed
#              (exit_code=-1). Kill any orphan jass workers, dump shard
#              logs, OOM signals, memory pressure, and the full raw log.
# expected_duration: ~10s
set -uo pipefail
cd /root/jass

OUT="/root/jass/jobs/results/0003-diag-after-0002/artefacts.src"
mkdir -p "$OUT"

echo "=== killing orphan jass workers (if any) ==="
pgrep -a jass || echo "(none found by pgrep)"
ps -ef | awk '$8 ~ /jass$/ || $0 ~ /gen-data-wdl/' | grep -v awk || true
pkill -TERM -x jass 2>/dev/null && echo "sent SIGTERM to jass" || echo "(nothing to kill)"
sleep 2
pkill -KILL -x jass 2>/dev/null && echo "sent SIGKILL to jass" || true

echo
echo "=== host snapshot ==="
uptime
free -h
df -h / | tail -1
nproc
echo "load: $(cut -d' ' -f1-3 /proc/loadavg)"

echo
echo "=== kernel OOM / killed signals (last 200 dmesg lines) ==="
dmesg -T 2>/dev/null | tail -200 | grep -iE 'oom|killed|jass|out of memory' \
    | tee "$OUT/dmesg-oom.log" \
    || echo "(no oom traces)"

echo
echo "=== runner journal around 0002 (05:25 → 05:40) ==="
journalctl -u jass-runner.service --since "2026-05-12 05:25:00" --until "2026-05-12 05:40:00" --no-pager \
    | tee "$OUT/journal-0002.log" \
    | tail -50

echo
echo "=== 0002 artefacts on disk ==="
ls -la /root/jass/jobs/results/0002-rate-test-depth20/ 2>/dev/null
echo
ls -la /root/jass/jobs/results/0002-rate-test-depth20/artefacts.src/ 2>/dev/null

echo
echo "=== per-shard logs ==="
for f in /root/jass/jobs/results/0002-rate-test-depth20/artefacts.src/shard-*.log; do
    [ -f "$f" ] || continue
    echo "--- $f (size=$(stat -c%s "$f") bytes) ---"
    cat "$f"
    echo
done

echo "=== per-shard .bin sizes ==="
for f in /root/jass/jobs/results/0002-rate-test-depth20/artefacts.src/shard-*.bin; do
    [ -f "$f" ] || continue
    sz=$(stat -c%s "$f")
    # JNNW header is 8 bytes, each record is 38 bytes
    if [ "$sz" -ge 8 ]; then
        records=$(( (sz - 8) / 38 ))
        echo "$f: $sz bytes ≈ $records records"
    else
        echo "$f: $sz bytes (too small for header)"
    fi
done

echo
echo "=== full raw log of 0002 ==="
RAW=/root/jass/jobs/results/0002-rate-test-depth20/output.log.raw
if [ -f "$RAW" ]; then
    echo "size: $(stat -c%s "$RAW") bytes"
    cat "$RAW"
else
    echo "(no raw log)"
fi

echo
echo "=== current running processes (full tree) ==="
ps -ef --forest | head -80

echo
echo "=== diag done ==="

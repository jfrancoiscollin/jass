#!/usr/bin/env bash
# id: 0006-diag-runner-state
# description: 0005 was reaped as failed rc=-1 in exactly 5 min,
#              same symptom as 0002 — so either the runner.py fix
#              didn't deploy, OR there's a deeper bug. This job
#              snapshots the runner state to find out.
# expected_duration: ~5s
set -uo pipefail
cd /root/jass

OUT="/root/jass/jobs/results/0006-diag-runner-state/artefacts.src"
mkdir -p "$OUT"

echo "=== current commit on /root/jass ==="
git log -1 --oneline
git rev-parse HEAD

echo
echo "=== infra/runner.py: setsid usage on disk ==="
grep -n -E 'setsid|Popen|start_new_session' /root/jass/infra/runner.py | tee "$OUT/runner-popen-lines.txt"

echo
echo "=== full start_job() body on disk ==="
sed -n '/^def start_job/,/^def main/p' /root/jass/infra/runner.py | tee "$OUT/runner-start_job.txt"

echo
echo "=== jobs/state/in-flight.json (if any) ==="
if [ -f /root/jass/jobs/state/in-flight.json ]; then
    cat /root/jass/jobs/state/in-flight.json
else
    echo "(no in-flight)"
fi

echo
echo "=== current jass+bash processes ==="
ps -ef --forest | grep -E 'jass|runner.py|0005|0006' | grep -v 'grep' || true

echo
echo "=== full process tree under PID 1 (depth 2) ==="
ps -ef | awk '$3 == 1 {print}' | head -30

echo
echo "=== systemd cgroup contents for jass-runner ==="
systemd-cgls --no-pager /system.slice/jass-runner.service 2>/dev/null || true
ls -la /sys/fs/cgroup/system.slice/jass-runner.service/cgroup.procs 2>/dev/null && \
    echo "--- pids in cgroup ---" && \
    cat /sys/fs/cgroup/system.slice/jass-runner.service/cgroup.procs 2>/dev/null \
    || echo "(no cgroup)"

echo
echo "=== last 60 journal lines for jass-runner.service ==="
journalctl -u jass-runner.service -n 60 --no-pager | tee "$OUT/journal-recent.txt"

echo
echo "=== 0005 raw output.log.raw ==="
RAW=/root/jass/jobs/results/0005-rate-test-depth20-v2/output.log.raw
if [ -f "$RAW" ]; then
    echo "size: $(stat -c%s "$RAW") bytes"
    echo "mtime: $(stat -c%y "$RAW")"
    cat "$RAW" | tee "$OUT/0005-output-log-raw.txt"
else
    echo "(no raw log)"
fi

echo
echo "=== done ==="

#!/usr/bin/env bash
# id: 0008-stop-runner-on-this-host
# description: gracefully takes the executing host out of the GitOps
#              rotation so a second machine (CCX63) can join without
#              the two runners racing for the same queued job. The
#              timer disable is delayed so this very job has time to
#              finalize normally (no orphan in-flight, no stuck
#              status=running).
# expected_duration: ~10s
set -uo pipefail
cd /root/jass

OUT="/root/jass/jobs/results/0008-stop-runner-on-this-host/artefacts.src"
mkdir -p "$OUT"

echo "=== host facts (which box is taking itself out) ==="
hostname
ip -4 -o addr show scope global | awk '{print $2, $4}'
echo

echo "=== current jass-runner.timer state ==="
systemctl status jass-runner.timer --no-pager 2>&1 | head -15 | tee "$OUT/timer-before.txt"
systemctl list-timers jass-runner.timer --no-pager | tee -a "$OUT/timer-before.txt"

echo
echo "=== scheduling delayed disable (T+8min, gives 1-2 ticks to reap me) ==="
# Detached background task: waits for this very job to be reaped, then
# disables the timer so no further ticks fire on this host. KillMode=process
# in jass-runner.service + new-session means the detached child survives
# the wrapper's exit and isn't tied to the runner.service unit.
nohup setsid bash -c '
    sleep 480
    /bin/systemctl disable --now jass-runner.timer >> /var/log/jass-runner-disable.log 2>&1
    /usr/bin/logger -t jass-runner "jass-runner.timer disabled by 0008-stop-runner-on-this-host"
    /bin/date -u >> /var/log/jass-runner-disable.log
    /bin/echo "disabled" >> /var/log/jass-runner-disable.log
' </dev/null >/dev/null 2>&1 &
disown
echo "scheduled. detached pid: $!"

echo
echo "=== why this is safe ==="
echo "* the next runner tick (~5 min) will reap this job normally"
echo "  (status -> completed, in-flight.json cleared)"
echo "* ~3 min after that, the detached task runs systemctl disable --now"
echo "* from that point on, no more ticks fire on this host"
echo "* this host stays SSH-reachable for ad-hoc manual use during the"
echo "  24h overlap; it just won't auto-pick anything from jobs/queue/"
echo "* tomorrow the user can simply delete the box in Hetzner Console"

echo
echo "=== to re-enable later (if needed) ==="
echo "  systemctl enable --now jass-runner.timer"

echo
echo "=== done ==="

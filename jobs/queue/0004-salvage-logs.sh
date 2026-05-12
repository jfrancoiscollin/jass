#!/usr/bin/env bash
# id: 0004-salvage-logs
# description: salvage server-side logs from 0002 and 0003 that the
#              runner produced but couldn't commit, because the repo
#              root .gitignore (`*.log`) was swallowing them. Copies
#              them as .txt into this job's artefacts/ so they finally
#              reach `main`. Also re-emits the diagnostic summary that
#              0003 produced but never got out of the server.
# expected_duration: ~5s
set -uo pipefail
cd /root/jass

OUT="/root/jass/jobs/results/0004-salvage-logs/artefacts.src"
mkdir -p "$OUT"

# Helper: cat $1 → $2, with a header noting source path + size.
salvage() {
    local src="$1" dst="$2"
    if [ ! -f "$src" ]; then
        printf '(missing: %s)\n' "$src" > "$dst"
        return
    fi
    {
        printf '### source: %s\n' "$src"
        printf '### size:   %s bytes\n' "$(stat -c%s "$src")"
        printf '### mtime:  %s\n'       "$(stat -c%y "$src")"
        printf '### -------- BEGIN CONTENT --------\n'
        cat "$src"
        printf '\n### --------- END CONTENT ---------\n'
    } > "$dst"
}

echo "=== 0002 server-side artefacts ==="
ls -la /root/jass/jobs/results/0002-rate-test-depth20/ 2>/dev/null || true
ls -la /root/jass/jobs/results/0002-rate-test-depth20/artefacts.src/ 2>/dev/null || true

echo
echo "=== 0003 server-side artefacts ==="
ls -la /root/jass/jobs/results/0003-diag-after-0002/ 2>/dev/null || true
ls -la /root/jass/jobs/results/0003-diag-after-0002/artefacts.src/ 2>/dev/null || true

echo
echo "=== salvaging 0002 logs ==="
salvage /root/jass/jobs/results/0002-rate-test-depth20/output.log.raw \
        "$OUT/0002-output-log-raw.txt"
for s in 1 2 3 4; do
    salvage /root/jass/jobs/results/0002-rate-test-depth20/artefacts.src/shard-$s.log \
            "$OUT/0002-shard-$s.txt"
done

echo "=== salvaging 0003 logs ==="
salvage /root/jass/jobs/results/0003-diag-after-0002/output.log.raw \
        "$OUT/0003-output-log-raw.txt"
salvage /root/jass/jobs/results/0003-diag-after-0002/artefacts.src/dmesg-oom.log \
        "$OUT/0003-dmesg-oom.txt"
salvage /root/jass/jobs/results/0003-diag-after-0002/artefacts.src/journal-0002.log \
        "$OUT/0003-journal-0002.txt"

echo
echo "=== fresh diag re-run (in case 0003 logs were partial) ==="
{
    echo "=== uptime / mem ==="
    uptime
    free -h
    df -h /

    echo
    echo "=== current jass processes ==="
    pgrep -a jass || echo "(no jass running)"
    ps -ef | awk '/jass/ && !/awk/ && !/0004/' || true

    echo
    echo "=== last 200 dmesg lines, OOM-filtered ==="
    dmesg -T 2>/dev/null | tail -400 | grep -iE 'oom|killed|jass|out of memory|signal' || echo "(no oom traces)"

    echo
    echo "=== runner journal 05:25 → 05:45 ==="
    journalctl -u jass-runner.service --since "2026-05-12 05:25:00" --until "2026-05-12 05:45:00" --no-pager || true
} > "$OUT/0004-fresh-diag.txt" 2>&1

echo "=== bytes salvaged ==="
ls -la "$OUT"

echo "=== done ==="

#!/usr/bin/env bash
# id: 0031-merge-cycle9-10M
# description: Combine host-a/b/c/d.bin (2.5M each) into cycle9-10M.bin
#              (10M total). Mechanical concat of JNNW records under a
#              single header. Same shape as 0021 (multi-host pilot)
#              and 0026 (single-host pilot), just over 4 inputs.
#
#              IMPORTANT: this job has to run on a host that has ALL
#              FOUR shard files on its disk. Easiest pattern:
#                * After 0030a-d finalise, scp host-b.bin, host-c.bin,
#                  host-d.bin to host A.
#                * On host A, widen JASS_HOST_FILTER so it can pick
#                  this 0031 job (e.g. unset the filter, or set it to
#                  a prefix that matches both "0030a-" and "0031-").
#                * Queue this script.
# expected_duration: ~1-2 minutes (pure file I/O on ~1.4 GB total).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0031-merge-cycle9-10M"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

HOST_A_BIN="/root/jass/jobs/results/0030a-cycle9-10M-host-a/artefacts.src/host-a.bin"
HOST_B_BIN="/root/jass/jobs/results/0030b-cycle9-10M-host-b/artefacts.src/host-b.bin"
HOST_C_BIN="/root/jass/jobs/results/0030c-cycle9-10M-host-c/artefacts.src/host-c.bin"
HOST_D_BIN="/root/jass/jobs/results/0030d-cycle9-10M-host-d/artefacts.src/host-d.bin"

for f in "$HOST_A_BIN" "$HOST_B_BIN" "$HOST_C_BIN" "$HOST_D_BIN"; do
    if [ ! -f "$f" ]; then
        echo "ABORT: $f not found on this host. scp it from the host"
        echo "  that generated it, then re-queue (delete jobs/results/0031-…/)."
        exit 3
    fi
done

echo "=== inputs ==="
ls -lh "$HOST_A_BIN" "$HOST_B_BIN" "$HOST_C_BIN" "$HOST_D_BIN"

echo
echo "=== merging ==="
python3 - <<PY
import struct
from pathlib import Path

MAGIC = b"JNNW"
HEADER_SZ = 8
RECORD_SZ = 38

inputs = [Path("$HOST_A_BIN"),
          Path("$HOST_B_BIN"),
          Path("$HOST_C_BIN"),
          Path("$HOST_D_BIN")]
out_path = Path("$ART/cycle9-10M.bin")

total = 0
with out_path.open("wb") as out:
    out.write(MAGIC)
    out.write(struct.pack("<I", 0))   # placeholder for count
    for src in inputs:
        raw = src.read_bytes()
        if raw[:4] != MAGIC:
            raise SystemExit(f"{src}: bad magic")
        cnt = struct.unpack_from("<I", raw, 4)[0]
        expected = HEADER_SZ + cnt * RECORD_SZ
        if len(raw) != expected:
            raise SystemExit(
                f"{src}: size {len(raw)} != expected {expected} "
                f"({cnt} records × {RECORD_SZ} B + {HEADER_SZ} B header)")
        out.write(raw[HEADER_SZ:])
        total += cnt
        print(f"  {src.name}: {cnt} records appended (running total {total})")
    out.seek(4)
    out.write(struct.pack("<I", total))
print(f"  merged total: {total} records → {out_path} "
      f"({out_path.stat().st_size} bytes)")
PY

echo
echo "=========================================================="
echo "       0031 MERGE-CYCLE9-10M SUMMARY"
echo "=========================================================="
echo "  inputs:    host-a/b/c/d.bin (4 × 2.5M = 10M expected)"
echo "  output:    $ART/cycle9-10M.bin"
echo "  size:      $(ls -lh "$ART/cycle9-10M.bin" | awk '{print $5}')"
echo "=========================================================="
echo
echo "Next: queue 0032-train-cycle9-10M to train a NNUE on the 10M,"
echo "then 0033-bench-cycle9-vs-v5 for the final ELO verdict."

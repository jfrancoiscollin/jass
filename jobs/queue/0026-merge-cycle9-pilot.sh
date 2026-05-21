#!/usr/bin/env bash
# id: 0026-merge-cycle9-pilot
# description: Combine 0025a's and 0025b's halves of the Cycle-9 pilot
#              into a single 1M JNNW dataset, ready for training as 0027.
#              Same merge logic as 0021 (multi-host pilot), just on the
#              larger 500K+500K halves.
#
#              Reads:
#                /root/jass/jobs/results/0025a-cycle9-pilot-host-a/
#                  artefacts.src/host-a.bin        (500K records)
#                /root/jass/jobs/results/0025b-cycle9-pilot-host-b/
#                  artefacts.src/host-b.bin        (500K records)
#              Writes:
#                $ART/cycle9-pilot-1M.bin          (1M records)
#
#              IMPORTANT: this job has to run on a host that has BOTH
#              shard files on its disk. Easiest way:
#                * After both 0025a and 0025b finalize, `scp` host-b.bin
#                  from host B to host A under the expected path.
#                * Set host A's JASS_HOST_FILTER to allow "0026-" prefix
#                  (e.g. extend it from "0025a-" to also pick "0026-").
#                * Queue this job.
# expected_duration: ~30 seconds (pure file I/O).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0026-merge-cycle9-pilot"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

HOST_A_BIN="/root/jass/jobs/results/0025a-cycle9-pilot-host-a/artefacts.src/host-a.bin"
HOST_B_BIN="/root/jass/jobs/results/0025b-cycle9-pilot-host-b/artefacts.src/host-b.bin"

for f in "$HOST_A_BIN" "$HOST_B_BIN"; do
    if [ ! -f "$f" ]; then
        echo "ABORT: $f not found on this host."
        echo "  If $f belongs to the OTHER host, scp it over manually before"
        echo "  re-queueing this job (delete jobs/results/0026-… and push)."
        exit 3
    fi
done

echo "=== inputs ==="
ls -lh "$HOST_A_BIN" "$HOST_B_BIN"

echo
echo "=== merging ==="
python3 - <<PY
import struct
from pathlib import Path

MAGIC = b"JNNW"
HEADER_SZ = 8
RECORD_SZ = 38

inputs = [Path("$HOST_A_BIN"), Path("$HOST_B_BIN")]
out_path = Path("$ART/cycle9-pilot-1M.bin")

total = 0
with out_path.open("wb") as out:
    out.write(MAGIC)
    out.write(struct.pack("<I", 0))
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
        print(f"  {src.name}: {cnt} records appended")
    out.seek(4)
    out.write(struct.pack("<I", total))
print(f"  merged total: {total} records → {out_path} "
      f"({out_path.stat().st_size} bytes)")
PY

echo
echo "=========================================================="
echo "       0026 MERGE CYCLE-9 PILOT SUMMARY"
echo "=========================================================="
echo "  inputs:    host-a.bin + host-b.bin (Cycle 9 v5-labelled)"
echo "  output:    $ART/cycle9-pilot-1M.bin"
echo "  size:      $(ls -lh "$ART/cycle9-pilot-1M.bin" | awk '{print $5}')"
echo "=========================================================="
echo
echo "Next: queue 0027-train-cycle9-pilot to train a NNUE on the 1M,"
echo "then 0028-bench-cycle9-vs-v5 for the pilot verdict."

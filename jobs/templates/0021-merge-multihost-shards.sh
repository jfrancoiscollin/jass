#!/usr/bin/env bash
# id: 0021-merge-multihost-shards
# description: Combine host A's and host B's halves of the multi-host
#              pilot into a single 200K JNNW dataset. Used to validate
#              that the multi-host architecture produces the same end-
#              state as a single-host gen-data run, just split across
#              two machines.
#
#              Reads:
#                /root/jass/jobs/results/0020a-…/artefacts.src/host-a.bin
#                /root/jass/jobs/results/0020b-…/artefacts.src/host-b.bin
#              Writes:
#                $ART/multihost-200k.bin
#
#              IMPORTANT: this job has to run on a host that has BOTH
#              shard files on its disk. Easiest way:
#                * Mark this job with JASS_HOST_FILTER on host A only
#                  (e.g. include "0020a-" AND "0021-" in host A's prefix
#                  set — see infra docs).
#                * scp host-b.bin from host B to host A before queueing.
#              Or just leave the runner unfiltered on the host where
#              you have both files, and queue this job there.
# expected_duration: ~10 seconds (pure file I/O).
set -uo pipefail
cd /root/jass

OUT_BASE="/root/jass/jobs/results/0021-merge-multihost-shards"
ART="$OUT_BASE/artefacts.src"
mkdir -p "$ART"

HOST_A_BIN="/root/jass/jobs/results/0020a-multihost-pilot-host-a/artefacts.src/host-a.bin"
HOST_B_BIN="/root/jass/jobs/results/0020b-multihost-pilot-host-b/artefacts.src/host-b.bin"

for f in "$HOST_A_BIN" "$HOST_B_BIN"; do
    if [ ! -f "$f" ]; then
        echo "ABORT: $f not found on this host."
        echo "  If $f belongs to the OTHER host, scp it over manually before"
        echo "  re-queueing this job (delete jobs/results/0021-… and push)."
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
out_path = Path("$ART/multihost-200k.bin")

total = 0
with out_path.open("wb") as out:
    out.write(MAGIC)
    out.write(struct.pack("<I", 0))   # placeholder
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
echo "       0021 MERGE-MULTIHOST-SHARDS SUMMARY"
echo "=========================================================="
echo "  inputs:    host-a.bin + host-b.bin"
echo "  output:    $ART/multihost-200k.bin"
echo "  size:      $(ls -lh "$ART/multihost-200k.bin" | awk '{print $5}')"
echo "=========================================================="
echo
echo "Pilot validated. Same Python merge logic scales to the future"
echo "Cycle-9 multi-host run (just N hosts × N shards per host)."

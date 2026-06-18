# shellcheck shell=bash
# jobs/lib/relabel.sh — parallel Scan relabel (distillation).
# relabel_with_scan.py is single-process; parallelise by sharding the input via
# --start/--max-records across N processes (each spawns its own Scan), then merge.
#
# relabel_scan_sharded <in.jnnw> <out.jnnw> <scan_bin> <depth> [ncpu]
relabel_scan_sharded() {
  local in="${1:?in}" out="${2:?out}" scan="${3:?scan}" depth="${4:?depth}" nc="${5:-$(nproc)}"
  local d tot per s; d="$(dirname "$out")"; mkdir -p "$d"
  tot=$(python3 -c "import struct;print(struct.unpack('<I',open('$in','rb').read(8)[4:8])[0])")
  per=$(( (tot + nc - 1) / nc ))
  echo "  [relabel] $tot positions, ${nc} shards × ~${per} (Scan depth ${depth})"
  for s in $(seq 0 $((nc-1))); do
    python3 tools/relabel_with_scan.py --in "$in" --out "$d/.rl-$s.jnnw" \
      --scan "$scan" --depth "$depth" --start $((s*per)) --max-records "$per" \
      --progress-every 20000 >"$d/.rl-$s.log" 2>&1 &
  done
  wait
  python3 - "$out" "$d" "$nc" <<'PY'
import sys,struct,os
out,d,nc=sys.argv[1],sys.argv[2],int(sys.argv[3]); REC=38
o=open(out,'wb'); tot=0; o.write(b'JNNW'+struct.pack('<I',0))
for s in range(nc):
    f=os.path.join(d,f'.rl-{s}.jnnw')
    if not os.path.exists(f):
        print('  [relabel] shard',s,'manquant'); continue
    b=open(f,'rb').read(); n=struct.unpack('<I',b[4:8])[0]; o.write(b[8:8+n*REC]); tot+=n
o.seek(4); o.write(struct.pack('<I',tot)); o.close()
print(f'  [relabel] mergé {tot} positions (score=Scan) -> {out}')
PY
  for s in $(seq 0 $((nc-1))); do rm -f "$d/.rl-$s.jnnw"; done
}
